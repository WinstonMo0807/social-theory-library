from rest_framework import serializers

from .library_query import LibraryScopeError, normalize_library_scope
from .library_assistant import source_is_available
from .models import LibraryConversation, LibraryMessage, LibraryMessageSource
from .services import decrypt_private_text


class LibraryConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = LibraryConversation
        fields = (
            "id",
            "title",
            "assist_mode",
            "scope",
            "archived",
            "message_count",
            "last_message_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "message_count", "last_message_at", "created_at", "updated_at")

    def validate_scope(self, value):
        try:
            return normalize_library_scope(value).as_dict()
        except LibraryScopeError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def create(self, validated_data):
        return LibraryConversation.objects.create(
            user=self.context["request"].user,
            **validated_data,
        )


class LibraryMessageSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()
    source_count = serializers.SerializerMethodField()
    evidence_count = serializers.SerializerMethodField()
    insufficient_evidence = serializers.SerializerMethodField()

    class Meta:
        model = LibraryMessage
        fields = (
            "id",
            "role",
            "content",
            "status",
            "retrieval_used",
            "source_count",
            "evidence_count",
            "insufficient_evidence",
            "query_type",
            "created_at",
            "completed_at",
        )

    def get_content(self, obj):
        return decrypt_private_text(obj.body_ciphertext)

    def get_source_count(self, obj):
        annotated = getattr(obj, "cited_source_count", None)
        if annotated is not None:
            return annotated
        return obj.sources.filter(cited=True).count()

    def get_evidence_count(self, obj):
        annotated = getattr(obj, "evidence_source_count", None)
        if annotated is not None:
            return annotated
        return obj.sources.count()

    def get_insufficient_evidence(self, obj):
        return bool((obj.usage or {}).get("insufficient_evidence"))


class LibraryQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=4000, trim_whitespace=True)
    assist_mode = serializers.ChoiceField(
        choices=LibraryConversation.AssistMode.choices,
        required=False,
    )
    scope = serializers.JSONField(required=False)
    retrieval_profile = serializers.ChoiceField(
        choices=[("stable", "稳定"), ("experimental_v2", "实验 V2")],
        required=False,
    )
    debug = serializers.BooleanField(required=False, default=False)

    def validate_assist_mode(self, value):
        if value == LibraryConversation.AssistMode.OFF:
            raise serializers.ValidationError("Ask Library 必须检索馆藏，不能关闭检索后自由回答。")
        return value

    def validate_scope(self, value):
        try:
            return normalize_library_scope(value).as_dict()
        except LibraryScopeError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class LibraryMessageSourceSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="title_snapshot", read_only=True)
    authors = serializers.JSONField(source="authors_snapshot", read_only=True)
    available = serializers.SerializerMethodField()
    reader_url = serializers.SerializerMethodField()

    class Meta:
        model = LibraryMessageSource
        fields = (
            "id",
            "source_key",
            "ordinal",
            "title",
            "authors",
            "page_index",
            "page",
            "printed_label",
            "chapter_title",
            "document_id",
            "passage_language",
            "cited",
            "available",
            "reader_url",
        )

    def get_available(self, obj):
        return source_is_available(obj)

    def get_reader_url(self, obj):
        if not source_is_available(obj):
            return None
        if obj.reader_url_snapshot:
            return obj.reader_url_snapshot
        passage_value = obj.document_id or obj.source_chunk_id
        passage = f"&passage={passage_value}" if passage_value else ""
        return f"/reader/{obj.asset_id}?page={obj.page_index or 1}{passage}"


class LibraryMessageSourceDetailSerializer(LibraryMessageSourceSerializer):
    quote = serializers.SerializerMethodField()

    class Meta(LibraryMessageSourceSerializer.Meta):
        fields = LibraryMessageSourceSerializer.Meta.fields + ("quote",)

    def get_quote(self, obj):
        if not source_is_available(obj):
            return None
        return decrypt_private_text(obj.quote_ciphertext)
