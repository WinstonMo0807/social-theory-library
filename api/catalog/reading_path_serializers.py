"""Public reading-path contract and bounded editorial metadata."""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field


class PathCreditInput(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    role = serializers.CharField(max_length=100)


class PathMetadataInput(serializers.Serializer):
    estimated_weeks = serializers.IntegerField(min_value=1, max_value=520, allow_null=True, required=False)
    prerequisite = serializers.CharField(max_length=10000, allow_blank=True, required=False)
    learning_questions = serializers.ListField(child=serializers.CharField(max_length=2000), max_length=40, required=False)
    related_debate_ids = serializers.ListField(child=serializers.UUIDField(), max_length=40, required=False)
    curator_note = serializers.CharField(max_length=20000, allow_blank=True, required=False)
    credits = PathCreditInput(many=True, required=False, max_length=30)
    topics = serializers.ListField(child=serializers.UUIDField(), max_length=40, required=False)


class PathStageInput(serializers.Serializer):
    estimated_reading = serializers.CharField(max_length=120, allow_blank=True, default="")
    learning_questions = serializers.ListField(child=serializers.CharField(max_length=2000), max_length=40, default=list)
    related_debate_ids = serializers.ListField(child=serializers.UUIDField(), max_length=40, default=list)


class PathDependencyInput(serializers.Serializer):
    item_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["learning_order", "theory_related"])
    reason = serializers.CharField(max_length=1000, allow_blank=True, default="")


class PublicPathDependency(PathDependencyInput):
    title = serializers.CharField()


class PathMaterialInput(serializers.Serializer):
    learning_goal = serializers.CharField(max_length=2000, allow_blank=True, default="")
    dependencies = PathDependencyInput(many=True, max_length=64, default=list)
    material_kind = serializers.ChoiceField(choices=["work", "chapter", "paper", "node"], default="work")
    edition = serializers.UUIDField(allow_null=True, default=None)
    asset = serializers.UUIDField(allow_null=True, default=None)
    document_revision = serializers.UUIDField(allow_null=True, default=None)
    chapter_title = serializers.CharField(max_length=300, allow_blank=True, default="")
    page_start = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    page_end = serializers.IntegerField(min_value=1, allow_null=True, default=None)
    printed_page_label = serializers.CharField(max_length=80, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=["active", "withdrawn"], default="active")
    substitute_edition_ids = serializers.ListField(child=serializers.UUIDField(), max_length=12, default=list)


class PathStageItemInput(PathMaterialInput):
    id = serializers.UUIDField(required=False)
    node = serializers.UUIDField(allow_null=True, required=False)
    work = serializers.UUIDField(allow_null=True, required=False)
    recommendation_reason = serializers.CharField(allow_blank=True, required=False)
    prerequisite = serializers.CharField(allow_blank=True, required=False)
    editorial_note = serializers.CharField(allow_blank=True, required=False)
    position = serializers.IntegerField(min_value=0, required=False)
    is_required = serializers.BooleanField(required=False)


class PathStageGroupInput(PathStageInput):
    id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(allow_blank=True, required=False)
    position = serializers.IntegerField(min_value=0, required=False)
    items = PathStageItemInput(many=True, max_length=600)


@extend_schema_field(PathStageGroupInput(many=True))
class ReadingPathStageGroupsField(serializers.JSONField):
    """Describe the existing JSON command without changing its normalization."""


class ReadingPathQuery(serializers.Serializer):
    q = serializers.CharField(max_length=300, allow_blank=True, required=False)
    search = serializers.CharField(max_length=300, allow_blank=True, required=False)
    discipline = serializers.CharField(max_length=180, allow_blank=True, required=False)
    topic = serializers.CharField(max_length=180, allow_blank=True, required=False)
    node = serializers.CharField(max_length=180, allow_blank=True, required=False)
    difficulty = serializers.ChoiceField(choices=["", "beginner", "intermediate", "advanced"], required=False)
    page = serializers.IntegerField(min_value=1, required=False)
    revision = serializers.CharField(max_length=80, required=False)
    compare_to = serializers.CharField(max_length=80, required=False)


class PathRevisionOutput(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    token = serializers.CharField()
    number = serializers.IntegerField(allow_null=True)
    published_at = serializers.CharField(allow_null=True)
    change_note = serializers.CharField(allow_blank=True)
    legacy = serializers.BooleanField()


class PathLinkOutput(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField()
    href = serializers.CharField()


class PathMaterialOutput(serializers.Serializer):
    id = serializers.CharField()
    stage_id = serializers.CharField()
    kind = serializers.ChoiceField(choices=["work", "chapter", "paper", "node"])
    title = serializers.CharField()
    work_id = serializers.UUIDField(allow_null=True)
    edition_id = serializers.UUIDField(allow_null=True)
    node_id = serializers.UUIDField(allow_null=True)
    asset_id = serializers.UUIDField(allow_null=True)
    document_revision_id = serializers.UUIDField(allow_null=True)
    chapter_title = serializers.CharField(allow_blank=True)
    page_start = serializers.IntegerField(allow_null=True)
    page_end = serializers.IntegerField(allow_null=True)
    printed_page_label = serializers.CharField(allow_blank=True)
    version_label = serializers.CharField(allow_blank=True)
    authors = serializers.ListField(child=serializers.CharField())
    publication_year = serializers.IntegerField(allow_null=True)
    cover_url = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_null=True)
    reader_url = serializers.CharField(allow_null=True)
    source_status = serializers.ChoiceField(choices=["available", "no_fulltext", "unavailable", "withdrawn", "revision_changed"])
    source_notice = serializers.CharField()
    reason = serializers.CharField(allow_blank=True)
    prerequisite = serializers.CharField(allow_blank=True)
    is_required = serializers.BooleanField()
    position = serializers.IntegerField()
    reading_order = serializers.IntegerField()
    substitutes = serializers.ListField(child=serializers.DictField())
    learning_goal = serializers.CharField(allow_blank=True)
    dependencies = PublicPathDependency(many=True)


class PathStageOutput(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    position = serializers.IntegerField()
    estimated_reading = serializers.CharField(allow_blank=True)
    learning_questions = serializers.ListField(child=serializers.CharField())
    related_debates = PathLinkOutput(many=True)
    items = PathMaterialOutput(many=True)


class PublicReadingPathListSerializer(serializers.ListSerializer):
    def to_representation(self, data):
        if self.context.get("include_unpublished_items"):
            return super().to_representation(data)
        rows = list(data.all() if hasattr(data, "all") else data)
        if not rows or isinstance(rows[0], dict):
            return super().to_representation(rows)
        from catalog.services.public_reading_paths import public_reading_path_snapshots
        return public_reading_path_snapshots(rows, request=self.context.get("request"))


class PublicReadingPathSerializer(serializers.Serializer):
    class Meta:
        list_serializer_class = PublicReadingPathListSerializer

    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    introduction = serializers.CharField(allow_blank=True)
    learning_goal = serializers.CharField(allow_blank=True)
    audience = serializers.CharField(allow_blank=True)
    difficulty = serializers.CharField()
    estimated_reading = serializers.CharField(allow_blank=True)
    estimated_weeks = serializers.IntegerField(allow_null=True)
    prerequisite = serializers.CharField(allow_blank=True)
    curator_note = serializers.CharField(allow_blank=True)
    credits = PathCreditInput(many=True)
    topics = PathLinkOutput(many=True)
    learning_questions = serializers.ListField(child=serializers.CharField())
    related_debates = PathLinkOutput(many=True)
    revision = PathRevisionOutput()
    latest_revision = PathRevisionOutput()
    is_current_revision = serializers.BooleanField()
    versions = PathRevisionOutput(many=True)
    versions_truncated = serializers.BooleanField()
    stages = PathStageOutput(many=True)
    items = PathMaterialOutput(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())
    cover_url = serializers.CharField(allow_blank=True)
    cover_media = serializers.JSONField(allow_null=True)
    primary_discipline_data = serializers.JSONField(allow_null=True)
    diff = serializers.JSONField(required=False)
    preview = serializers.BooleanField(required=False)

    def to_representation(self, instance):
        if isinstance(instance, dict):
            return super().to_representation(instance)
        from catalog.services.public_reading_paths import public_reading_path_snapshot
        return super().to_representation(public_reading_path_snapshot(instance.pk, request=self.context.get("request")))
