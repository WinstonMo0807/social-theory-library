import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field

from catalog.models import Asset, Page, Topic, Work
from catalog.serializers import WorkCardSerializer
from catalog.services.publication_eligibility import public_edition_q

from .models import (
    Annotation,
    Bookmark,
    ReadingHistory,
    ReadingList,
    ReadingListItem,
    ReadingProgress,
    SavedItem,
    SavedTopic,
)
from .services import (
    current_reader_asset_for_work,
    decrypt_private_text,
    encrypt_private_text,
    ensure_saved_work_progress,
    readable_assets_for_user,
    readable_progress_for_user,
)


def _reader_asset_available(asset: Asset, user) -> bool:
    return readable_assets_for_user(user).filter(pk=asset.pk).exists()


def _reader_work_data(work, context):
    data = WorkCardSerializer(work, context=context).data
    edition = data.get("edition") or {}
    asset = edition.get("readable_asset")
    if asset and not readable_assets_for_user(getattr(context.get("request"), "user", None)).filter(
        pk=asset["id"], edition_id=edition["id"], edition__work=work,
    ).exists():
        edition["readable_asset"] = None
    return data


class OwnedSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class ReadingProgressSerializer(OwnedSerializer):
    work = serializers.SerializerMethodField()

    class Meta:
        model = ReadingProgress
        fields = (
            "id",
            "asset",
            "work",
            "current_page",
            "progress_ratio",
            "last_position",
            "updated_at",
        )
        read_only_fields = ("id", "updated_at")

    @extend_schema_field(WorkCardSerializer)
    def get_work(self, obj):
        return _reader_work_data(obj.asset.edition.work, self.context)

    def validate_asset(self, value):
        if not _reader_asset_available(value, self.context["request"].user):
            raise serializers.ValidationError("该阅读文件不可用。")
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        instance, _ = ReadingProgress.objects.update_or_create(
            user=user,
            asset=validated_data["asset"],
            defaults={
                "current_page": validated_data.get("current_page", 1),
                "progress_ratio": validated_data.get("progress_ratio", 0),
                "last_position": validated_data.get("last_position", {}),
            },
        )
        return instance


class AnnotationSerializer(OwnedSerializer):
    request_id = serializers.UUIDField(write_only=True, required=False)
    body = serializers.CharField(write_only=True, required=False, allow_blank=True)
    body_text = serializers.SerializerMethodField(read_only=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=40, allow_blank=True),
        max_length=12,
        required=False,
    )
    work = serializers.SerializerMethodField()

    class Meta:
        model = Annotation
        fields = (
            "id",
            "request_id",
            "asset",
            "work",
            "page",
            "kind",
            "selector",
            "quote",
            "body",
            "body_text",
            "tags",
            "color",
            "asset_sha256",
            "orphaned",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "asset_sha256", "orphaned", "created_at", "updated_at")

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_body_text(self, obj):
        request = self.context.get("request")
        if request and request.user == obj.user:
            return decrypt_private_text(obj.body_ciphertext)
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        data["tags"] = (
            json.loads(decrypt_private_text(instance.tags_ciphertext))
            if request and request.user == instance.user and instance.tags_ciphertext
            else []
        )
        return data

    def validate_tags(self, value):
        if any(not isinstance(tag, str) for tag in self.initial_data.get("tags", [])):
            raise serializers.ValidationError("标签必须是文字。")
        return list(dict.fromkeys(tag for tag in value if tag))

    @extend_schema_field(WorkCardSerializer)
    def get_work(self, obj):
        return _reader_work_data(obj.asset.edition.work, self.context)

    def validate(self, attrs):
        if self.instance and "request_id" in attrs:
            raise serializers.ValidationError({"request_id": "请求标识仅用于新建批注。"})
        asset = attrs.get("asset") or getattr(self.instance, "asset", None)
        page = attrs.get("page") or getattr(self.instance, "page", None)
        if asset is None or page is None or page.asset_id != asset.id:
            raise serializers.ValidationError("页码与阅读文件不匹配。")
        if self.instance and (asset.id != self.instance.asset_id or page.id != self.instance.page_id):
            raise serializers.ValidationError("已有批注的来源文件与页码不能更换，请在新位置创建批注。")
        if "selector" in attrs:
            selector = attrs["selector"]
            if not isinstance(selector, dict):
                raise serializers.ValidationError({"selector": "批注位置必须是对象。"})
            if "page_index" in selector and (
                type(selector["page_index"]) is not int or selector["page_index"] != page.index
            ):
                raise serializers.ValidationError({"selector": "批注位置与所选页码不一致。"})
        if not _reader_asset_available(asset, self.context["request"].user):
            raise serializers.ValidationError("该文献当前不可批注。")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from .privacy import lock_owner, require_retention
        from .research import ResearchConflict

        user = self.context["request"].user
        request_id = validated_data.pop("request_id", None)
        body = validated_data.pop("body", "")
        tags = validated_data.pop("tags", [])
        conflict = "此保存请求无法复用，请保留输入并重新确认保存状态。"
        lock_owner(user)
        if request_id is not None:
            previous = Annotation.objects.filter(pk=request_id, user=user).first()
            if previous is not None:
                existing = (previous.asset_id, previous.page_id, previous.kind, previous.selector,
                    previous.quote, previous.color, decrypt_private_text(previous.body_ciphertext),
                    json.loads(decrypt_private_text(previous.tags_ciphertext) or "[]"))
                incoming = (validated_data["asset"].pk, validated_data["page"].pk, validated_data["kind"],
                    validated_data.get("selector", {}), validated_data.get("quote", ""),
                    validated_data.get("color", Annotation._meta.get_field("color").get_default()), body, tags)
                if existing != incoming:
                    raise ResearchConflict(conflict)
                return previous
            if Annotation.objects.filter(pk=request_id).exists():
                raise ResearchConflict(conflict)
            validated_data["id"] = request_id
        require_retention(user, "personal_notes")
        validated_data["body_ciphertext"] = encrypt_private_text(body)
        validated_data["tags_ciphertext"] = encrypt_private_text(json.dumps(tags, ensure_ascii=False)) if tags else b""
        validated_data["asset_sha256"] = validated_data["asset"].sha256
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError:
            # Another owner can race for the same UUID despite our per-owner lock.
            if request_id is not None and Annotation.objects.filter(pk=request_id).exists():
                raise ResearchConflict(conflict) from None
            raise

    def update(self, instance, validated_data):
        if "body" in validated_data:
            instance.body_ciphertext = encrypt_private_text(validated_data.pop("body"))
        if "tags" in validated_data:
            tags = validated_data.pop("tags")
            instance.tags_ciphertext = encrypt_private_text(json.dumps(tags, ensure_ascii=False)) if tags else b""
        return super().update(instance, validated_data)


class BookmarkSerializer(OwnedSerializer):
    work = serializers.SerializerMethodField()
    page_index = serializers.IntegerField(source="page.index", read_only=True)

    class Meta:
        model = Bookmark
        fields = ("id", "asset", "work", "page", "page_index", "label", "created_at")
        read_only_fields = ("id", "created_at")

    @extend_schema_field(WorkCardSerializer)
    def get_work(self, obj):
        return _reader_work_data(obj.asset.edition.work, self.context)

    def validate(self, attrs):
        if attrs["page"].asset_id != attrs["asset"].id:
            raise serializers.ValidationError("页码与阅读文件不匹配。")
        if not _reader_asset_available(attrs["asset"], self.context["request"].user):
            raise serializers.ValidationError("该阅读文件不可用。")
        return attrs


class SavedItemProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingProgress
        fields = (
            "id",
            "asset",
            "current_page",
            "progress_ratio",
            "last_position",
            "updated_at",
        )
        read_only_fields = fields


class SavedItemListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        items = list(data.all() if hasattr(data, "all") else data)
        request = self.context.get("request")
        progress_by_work = {}
        if request and request.user.is_authenticated and items:
            work_ids = {item.work_id for item in items}
            progresses = (
                readable_progress_for_user(request.user)
                .filter(asset__edition__work_id__in=work_ids)
                .select_related("asset__edition")
                .order_by("-updated_at", "-created_at")
            )
            for progress in progresses:
                progress_by_work.setdefault(progress.asset.edition.work_id, progress)
        self.child._saved_progress_by_work = progress_by_work
        return super().to_representation(items)


class SavedItemSerializer(OwnedSerializer):
    title = serializers.SerializerMethodField()
    work_data = serializers.SerializerMethodField()
    reading_progress = serializers.SerializerMethodField()

    class Meta:
        model = SavedItem
        fields = (
            "id",
            "work",
            "work_data",
            "title",
            "reading_progress",
            "created_at",
        )
        read_only_fields = ("id", "created_at")
        list_serializer_class = SavedItemListSerializer

    def validate_work(self, value):
        if not value.editions.filter(public_edition_q(), is_primary=True).exists():
            raise serializers.ValidationError("该文献当前不可收藏。")
        self._validated_reader_asset = current_reader_asset_for_work(value, user=self.context["request"].user)
        return value

    def get_work_data(self, obj):
        cache = getattr(self, "_public_saved_works", None)
        if cache is None:
            cache = self._public_saved_works = {}
        if obj.work_id not in cache:
            cache[obj.work_id] = (
                _reader_work_data(obj.work, self.context)
                if obj.work.editions.filter(public_edition_q(), is_primary=True).exists()
                else None
            )
        return cache[obj.work_id]

    def get_title(self, obj):
        data = self.get_work_data(obj)
        return data["title"] if data else "来源暂不可用"

    def get_reading_progress(self, obj):
        if self.get_work_data(obj) is None:
            return None
        progress_by_work = getattr(self, "_saved_progress_by_work", None)
        if progress_by_work is not None:
            progress = progress_by_work.get(obj.work_id)
        else:
            request = self.context.get("request")
            progress = None
            if request and request.user.is_authenticated:
                progress = (
                    readable_progress_for_user(request.user)
                    .filter(asset__edition__work_id=obj.work_id)
                    .select_related("asset__edition")
                    .order_by("-updated_at", "-created_at")
                    .first()
                )
        if progress is None:
            return None
        return SavedItemProgressSerializer(progress, context=self.context).data

    @transaction.atomic
    def create(self, validated_data):
        from .privacy import lock_owner
        user = self.context["request"].user
        lock_owner(user)
        work = validated_data["work"]
        # Unknown responses can be retried without duplicating a collection.
        self.validate_work(work)
        saved_item, _ = SavedItem.objects.get_or_create(user=user, work=work)
        ensure_saved_work_progress(
            user=user,
            work=work,
            fallback_asset=getattr(self, "_validated_reader_asset", None),
        )
        return saved_item


class SavedTopicSerializer(OwnedSerializer):
    name = serializers.CharField(source="topic.name", read_only=True)
    slug = serializers.CharField(source="topic.slug", read_only=True)
    description = serializers.CharField(source="topic.description", read_only=True)

    class Meta:
        model = SavedTopic
        fields = ("id", "topic", "name", "slug", "description", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_topic(self, value: Topic):
        if value.editorial_status != "published":
            raise serializers.ValidationError("该主题当前不可收藏。")
        return value

    @transaction.atomic
    def create(self, validated_data):
        from .privacy import require_retention
        require_retention(self.context["request"].user, "followed_topics")
        return super().create(validated_data)


class ReadingListItemSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()

    class Meta:
        model = ReadingListItem
        fields = ("id", "work", "title", "order", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_work(self, value):
        if not value.editions.filter(public_edition_q(), is_primary=True).exists():
            raise serializers.ValidationError("该文献当前未公开，不能加入书单。")
        return value

    def get_title(self, obj):
        if not obj.work.editions.filter(public_edition_q(), is_primary=True).exists():
            return "来源暂不可用"
        return WorkCardSerializer(obj.work, context=self.context).data["title"]


class ReadingListSerializer(OwnedSerializer):
    items = ReadingListItemSerializer(many=True, read_only=True)

    class Meta:
        model = ReadingList
        fields = ("id", "title", "description", "is_default", "items", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class ReadingHistorySerializer(OwnedSerializer):
    title = serializers.CharField(source="asset.edition.work.title", read_only=True)
    work = serializers.SerializerMethodField()

    class Meta:
        model = ReadingHistory
        fields = ("id", "asset", "work", "title", "page_index", "session_seconds", "created_at")
        read_only_fields = ("id", "created_at")

    @extend_schema_field(WorkCardSerializer)
    def get_work(self, obj):
        return _reader_work_data(obj.asset.edition.work, self.context)

    def validate_asset(self, value):
        if not _reader_asset_available(value, self.context["request"].user):
            raise serializers.ValidationError("该阅读文件不可用。")
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        recent = ReadingHistory.objects.filter(
            user=user,
            asset=validated_data["asset"],
            updated_at__gte=timezone.now() - timedelta(minutes=30),
        ).order_by("-updated_at").first()
        if recent:
            recent.page_index = validated_data.get("page_index", recent.page_index)
            recent.session_seconds += validated_data.get("session_seconds", 0)
            recent.save(update_fields=["page_index", "session_seconds", "updated_at"])
            return recent
        validated_data["user"] = user
        return ReadingHistory.objects.create(**validated_data)
