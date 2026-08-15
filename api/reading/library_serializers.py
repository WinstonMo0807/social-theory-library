from rest_framework import serializers

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
        if not isinstance(value, dict):
            raise serializers.ValidationError("检索范围必须是对象。")
        if len(str(value)) > 4000:
            raise serializers.ValidationError("检索范围过大。")
        return value

    def create(self, validated_data):
        return LibraryConversation.objects.create(
            user=self.context["request"].user,
            **validated_data,
        )


class LibraryMessageSerializer(serializers.ModelSerializer):
    content = serializers.SerializerMethodField()
    source_count = serializers.SerializerMethodField()

    class Meta:
        model = LibraryMessage
        fields = (
            "id",
            "role",
            "content",
            "status",
            "retrieval_used",
            "source_count",
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


class LibraryQuestionSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=4000, trim_whitespace=True)
    assist_mode = serializers.ChoiceField(
        choices=LibraryConversation.AssistMode.choices,
        required=False,
    )


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
            "printed_label",
            "chapter_title",
            "cited",
            "available",
            "reader_url",
        )

    def get_available(self, obj):
        return source_is_available(obj)

    def get_reader_url(self, obj):
        if not source_is_available(obj):
            return None
        passage = f"&passage={obj.source_chunk_id}" if obj.source_chunk_id else ""
        return f"/reader/{obj.asset_id}?page={obj.page_index or 1}{passage}"


class LibraryMessageSourceDetailSerializer(LibraryMessageSourceSerializer):
    quote = serializers.SerializerMethodField()

    class Meta(LibraryMessageSourceSerializer.Meta):
        fields = LibraryMessageSourceSerializer.Meta.fields + ("quote",)

    def get_quote(self, obj):
        if not source_is_available(obj):
            return None
        return decrypt_private_text(obj.quote_ciphertext)
