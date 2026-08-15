from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import Asset, Page, PublicationState, Topic, Work
from catalog.serializers import WorkCardSerializer

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
    readable_progress_for_user,
)


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

    def get_work(self, obj):
        return WorkCardSerializer(
            obj.asset.edition.work,
            context=self.context,
        ).data

    def validate_asset(self, value):
        if (
            value.edition.state != PublicationState.PUBLISHED
            or value.kind != Asset.Kind.NORMALIZED
            or value.status != Asset.Status.READY
            or not value.is_current
        ):
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
    body = serializers.CharField(write_only=True, required=False, allow_blank=True)
    body_text = serializers.SerializerMethodField(read_only=True)
    work = serializers.SerializerMethodField()

    class Meta:
        model = Annotation
        fields = (
            "id",
            "asset",
            "work",
            "page",
            "kind",
            "selector",
            "quote",
            "body",
            "body_text",
            "color",
            "asset_sha256",
            "orphaned",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "asset_sha256", "orphaned", "created_at", "updated_at")

    def get_body_text(self, obj):
        request = self.context.get("request")
        if request and request.user == obj.user:
            return decrypt_private_text(obj.body_ciphertext)
        return None

    def get_work(self, obj):
        return WorkCardSerializer(
            obj.asset.edition.work,
            context=self.context,
        ).data

    def validate(self, attrs):
        asset = attrs.get("asset") or getattr(self.instance, "asset", None)
        page = attrs.get("page") or getattr(self.instance, "page", None)
        if asset is None or page is None or page.asset_id != asset.id:
            raise serializers.ValidationError("页码与阅读文件不匹配。")
        if (
            asset.edition.state != PublicationState.PUBLISHED
            or asset.kind != Asset.Kind.NORMALIZED
            or asset.status != Asset.Status.READY
            or not asset.is_current
        ):
            raise serializers.ValidationError("该文献当前不可批注。")
        return attrs

    def create(self, validated_data):
        body = validated_data.pop("body", "")
        validated_data["body_ciphertext"] = encrypt_private_text(body)
        validated_data["asset_sha256"] = validated_data["asset"].sha256
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "body" in validated_data:
            instance.body_ciphertext = encrypt_private_text(validated_data.pop("body"))
        return super().update(instance, validated_data)


class BookmarkSerializer(OwnedSerializer):
    work = serializers.SerializerMethodField()
    page_index = serializers.IntegerField(source="page.index", read_only=True)

    class Meta:
        model = Bookmark
        fields = ("id", "asset", "work", "page", "page_index", "label", "created_at")
        read_only_fields = ("id", "created_at")

    def get_work(self, obj):
        return WorkCardSerializer(
            obj.asset.edition.work,
            context=self.context,
        ).data

    def validate(self, attrs):
        if attrs["page"].asset_id != attrs["asset"].id:
            raise serializers.ValidationError("页码与阅读文件不匹配。")
        if (
            attrs["asset"].edition.state != PublicationState.PUBLISHED
            or attrs["asset"].kind != Asset.Kind.NORMALIZED
            or attrs["asset"].status != Asset.Status.READY
            or not attrs["asset"].is_current
        ):
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
    title = serializers.CharField(source="work.title", read_only=True)
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
        if not value.editions.filter(state=PublicationState.PUBLISHED).exists():
            raise serializers.ValidationError("该文献当前不可收藏。")
        self._validated_reader_asset = current_reader_asset_for_work(value)
        if self._validated_reader_asset is None:
            raise serializers.ValidationError("该文献当前没有可用的在线阅读文件。")
        return value

    def get_work_data(self, obj):
        return WorkCardSerializer(obj.work, context=self.context).data

    def get_reading_progress(self, obj):
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
        user = self.context["request"].user
        work = validated_data["work"]
        saved_item = SavedItem.objects.create(user=user, **validated_data)
        progress = ensure_saved_work_progress(
            user=user,
            work=work,
            fallback_asset=getattr(self, "_validated_reader_asset", None),
        )
        if progress is None:
            raise serializers.ValidationError(
                {"work": "该文献当前没有可用的在线阅读文件。"}
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


class ReadingListItemSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="work.title", read_only=True)

    class Meta:
        model = ReadingListItem
        fields = ("id", "work", "title", "order", "created_at")
        read_only_fields = ("id", "created_at")


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

    def get_work(self, obj):
        return WorkCardSerializer(
            obj.asset.edition.work,
            context=self.context,
        ).data

    def validate_asset(self, value):
        if (
            value.edition.state != PublicationState.PUBLISHED
            or value.kind != Asset.Kind.NORMALIZED
            or value.status != Asset.Status.READY
            or not value.is_current
        ):
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
