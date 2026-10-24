"""Wire contracts shared with generated TypeScript; commands validate domain rules."""
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from drf_spectacular.helpers import lazy_serializer
from catalog.serializers import SiteConfigSerializer, AboutPageBlockSerializer


class IssueTextMarkSerializer(serializers.Serializer):
    start = serializers.IntegerField(min_value=0)
    end = serializers.IntegerField(min_value=1)
    kind = serializers.ChoiceField(choices=["strong", "em", "link"])
    href = serializers.CharField(max_length=1500, required=False)


class IssueBodyBlockSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    type = serializers.ChoiceField(choices=["paragraph", "heading", "quote", "link", "image", "evidence", "work", "person", "concept", "node", "timeline", "reading_path", "comparison", "analysis"])
    text = serializers.CharField(allow_blank=True)
    heading_level = serializers.ChoiceField(choices=[1, 2, 3], required=False)
    text_style = serializers.ChoiceField(choices=["paragraph", "ordered", "unordered"], required=False)
    text_marks = IssueTextMarkSerializer(many=True, required=False)
    source = serializers.CharField(required=False, allow_blank=True)
    url = serializers.CharField(required=False, allow_blank=True)
    image_rendition_id = serializers.UUIDField(required=False, allow_null=True)
    image_url = serializers.CharField(read_only=True, allow_blank=True)
    alt_text = serializers.CharField(required=False, allow_blank=True)
    target = serializers.DictField(required=False)
    dimensions = serializers.ListField(child=serializers.CharField(), required=False)
    rows = serializers.ListField(child=serializers.DictField(), required=False)
    references = serializers.ListField(child=serializers.DictField(), required=False)
    style = serializers.ChoiceField(choices=["paragraph", "heading"], required=False)
    source_status = serializers.CharField(read_only=True)
    resolved_sources = serializers.ListField(child=serializers.DictField(), read_only=True)


class IssueItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    kind = serializers.ChoiceField(choices=["catalog", "planned"])
    work_id = serializers.UUIDField(required=False, allow_null=True)
    edition_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True)
    authors = serializers.CharField(required=False, allow_blank=True)
    version_note = serializers.CharField(required=False, allow_blank=True)
    isbn = serializers.CharField(required=False, allow_blank=True)
    doi = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
    position = serializers.IntegerField(required=False)
    section_id = serializers.CharField(required=False, allow_blank=True)
    document_type = serializers.CharField(required=False)
    status = serializers.CharField(read_only=True)
    work_url = serializers.CharField(read_only=True)
    reader_url = serializers.CharField(read_only=True)
    cover_url = serializers.CharField(read_only=True)
    file_status = serializers.CharField(read_only=True)
    cataloging_session_id = serializers.UUIDField(read_only=True, allow_null=True)
    available_work_id = serializers.UUIDField(read_only=True, allow_null=True)
    available_edition_id = serializers.UUIDField(read_only=True, allow_null=True)
    workbench_url = serializers.CharField(read_only=True)
    match_candidates = serializers.ListField(child=serializers.DictField(), read_only=True)


class ArticleMetadataSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["article", "research", "exhibition"], required=False)
    keywords = serializers.ListField(child=serializers.CharField(max_length=80), max_length=30, required=False)
    topic_ids = serializers.ListField(child=serializers.UUIDField(), max_length=50, required=False)
    scholar_ids = serializers.ListField(child=serializers.UUIDField(), max_length=50, required=False)
    reading_path_ids = serializers.ListField(child=serializers.UUIDField(), max_length=50, required=False)
    curator_role = serializers.CharField(max_length=240, allow_blank=True, required=False)
    curator_affiliation = serializers.CharField(max_length=240, allow_blank=True, required=False)
    curator_portrait_id = serializers.UUIDField(allow_null=True, required=False)


class PublicEditorialCuratorSerializer(serializers.Serializer):
    name = serializers.CharField(allow_blank=True)
    role = serializers.CharField(allow_blank=True)
    affiliation = serializers.CharField(allow_blank=True)
    portrait_url = serializers.CharField(allow_blank=True)


class PublicEditorialCardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    issue_label = serializers.CharField(allow_blank=True)
    introduction = serializers.CharField(allow_blank=True)
    public_byline = serializers.CharField(allow_blank=True)
    curator = PublicEditorialCuratorSerializer()
    article_metadata = ArticleMetadataSerializer()
    cover_url = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)
    display_from = serializers.DateTimeField(allow_null=True)
    reading_minutes = serializers.IntegerField(allow_null=True)
    reading_time_notice = serializers.CharField(allow_blank=True)
    href = serializers.CharField()


class EditorialDirectoryFiltersSerializer(serializers.Serializer):
    topic = serializers.CharField(allow_blank=True)
    kind = serializers.CharField(allow_blank=True)
    curator = serializers.CharField(allow_blank=True)
    sort = serializers.ChoiceField(choices=["newest", "oldest", "title"])
    year_from = serializers.IntegerField(allow_null=True)
    year_to = serializers.IntegerField(allow_null=True)


class EditorialDirectoryKindSerializer(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()


class EditorialDirectoryTopicSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    href = serializers.CharField()


class EditorialDirectoryFacetsSerializer(serializers.Serializer):
    curators = serializers.ListField(child=serializers.CharField())
    years = serializers.ListField(child=serializers.IntegerField())
    kinds = EditorialDirectoryKindSerializer(many=True)
    topics = EditorialDirectoryTopicSerializer(many=True)


class EditorialRelatedMaterialSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    authors = serializers.CharField(allow_blank=True)
    href = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    article_href = serializers.CharField()
    source_status = serializers.CharField()


class EditorialRelatedPathSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    href = serializers.CharField()


class EditorialRelatedSerializer(serializers.Serializer):
    scholars = serializers.SerializerMethodField()
    materials = EditorialRelatedMaterialSerializer(many=True)
    paths = EditorialRelatedPathSerializer(many=True)
    notice = serializers.CharField()

    @extend_schema_field(lazy_serializer("catalog.scholar_serializers.PublicScholarCardSerializer")(many=True))
    def get_scholars(self, obj):
        return obj["scholars"]


class PublicEditorialDirectorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = PublicEditorialCardSerializer(many=True)
    query = serializers.CharField(allow_blank=True)
    filters = EditorialDirectoryFiltersSerializer()
    facets = EditorialDirectoryFacetsSerializer()
    related = EditorialRelatedSerializer()


class RecommendationIssueSerializer(serializers.Serializer):
    is_public = serializers.BooleanField(read_only=True, required=False)
    project_id = serializers.UUIDField(read_only=True, allow_null=True)
    project_title = serializers.CharField(read_only=True, allow_blank=True)
    project_archived = serializers.BooleanField(read_only=True)
    selection_workspace = serializers.DictField(required=False, help_text="仅后台：策划问题、筛选范围与准确选材；materials为只读当前解析。公开响应不含此字段。")
    id = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(required=False)
    title = serializers.CharField()
    issue_label = serializers.CharField(required=False, allow_blank=True)
    introduction = serializers.CharField(required=False, allow_blank=True)
    public_byline = serializers.CharField(required=False, allow_blank=True)
    article_metadata = ArticleMetadataSerializer(required=False)
    curator = PublicEditorialCuratorSerializer(read_only=True)
    related = EditorialRelatedSerializer(read_only=True)
    public_revision_id = serializers.UUIDField(read_only=True)
    reading_minutes = serializers.IntegerField(read_only=True, allow_null=True)
    body_blocks = IssueBodyBlockSerializer(many=True, required=False)
    cover_url = serializers.CharField(required=False, allow_blank=True)
    cover_rendition_id = serializers.UUIDField(required=False, allow_null=True)
    display_from = serializers.DateTimeField(required=False, allow_null=True)
    published_at = serializers.DateTimeField(read_only=True, allow_null=True)
    items = IssueItemSerializer(many=True, required=False)
    edit_version = serializers.CharField(required=False)
    draft_revision_id = serializers.UUIDField(read_only=True, allow_null=True)
    has_unpublished_changes = serializers.BooleanField(read_only=True)
    body_source_problems = serializers.ListField(child=serializers.DictField(), read_only=True)
    request_id = serializers.UUIDField(required=False, write_only=True)
    restore_revision_id = serializers.UUIDField(required=False, write_only=True)
    autosave = serializers.BooleanField(required=False, write_only=True)
    saved_at = serializers.DateTimeField(read_only=True, allow_null=True)
    saved_by = serializers.CharField(read_only=True, allow_blank=True)
    saved_revision = serializers.IntegerField(read_only=True)
    viewed_revision_id = serializers.UUIDField(read_only=True)
    viewed_revision = serializers.IntegerField(read_only=True)
    request_found = serializers.BooleanField(read_only=True)
    applied_revision_id = serializers.UUIDField(read_only=True)
    is_current_revision = serializers.BooleanField(read_only=True)


class RecommendationIssueCollectionSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    pages = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    current = RecommendationIssueSerializer(allow_null=True)
    results = RecommendationIssueSerializer(many=True)


class IssuePublicationCheckSerializer(serializers.Serializer):
    code = serializers.CharField()
    severity = serializers.ChoiceField(choices=["blocking", "warning", "notice"])
    title = serializers.CharField()
    detail = serializers.CharField()
    section = serializers.CharField()
    block_id = serializers.CharField(allow_blank=True)
    item_id = serializers.CharField(allow_blank=True)


class IssuePublicationReviewSerializer(serializers.Serializer):
    edit_version = serializers.CharField()
    checked_at = serializers.DateTimeField()
    draft_revision_id = serializers.UUIDField(allow_null=True)
    current_revision_id = serializers.UUIDField(allow_null=True)
    draft_at = serializers.DateTimeField(allow_null=True)
    current_at = serializers.DateTimeField(allow_null=True)
    checks = IssuePublicationCheckSerializer(many=True)
    changes = serializers.SerializerMethodField()
    blocking_count = serializers.IntegerField()
    warning_count = serializers.IntegerField()
    has_draft = serializers.BooleanField()
    can_publish = serializers.BooleanField()
    actor_label = serializers.CharField()
    public_url = serializers.CharField()
    reader_preview = RecommendationIssueSerializer()

    @extend_schema_field(lazy_serializer("catalog.publication_command_views.PublicationFieldDiffSerializer")(many=True))
    def get_changes(self, obj):
        return obj["changes"]


class AdminIssueSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    published = serializers.IntegerField()
    drafts = serializers.IntegerField()
    scheduled = serializers.IntegerField()


class AdminRecommendationIssueCollectionSerializer(RecommendationIssueCollectionSerializer):
    summary = AdminIssueSummarySerializer()
    upcoming = RecommendationIssueSerializer(many=True)


class EditorialPublishSerializer(serializers.Serializer):
    edit_version = serializers.CharField()


class PlannedItemLinkSerializer(EditorialPublishSerializer):
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    confirm_version = serializers.BooleanField()


class SiteHistorySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    state = serializers.CharField()
    saved_at = serializers.DateTimeField()
    saved_by = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)
    published_by = serializers.CharField(allow_blank=True)


class SiteContentSerializer(serializers.Serializer):
    from catalog.site_layout import HomeLayoutSerializer, HomeLayoutPreviewSerializer
    from catalog.site_commands import SiteReceiptSerializer
    config = SiteConfigSerializer()
    about_blocks = AboutPageBlockSerializer(many=True)
    home_layout = HomeLayoutSerializer(required=False)
    home_preview = HomeLayoutPreviewSerializer(read_only=True)
    site_id = serializers.UUIDField(read_only=True)
    history = SiteHistorySerializer(many=True, read_only=True)
    receipt = SiteReceiptSerializer(read_only=True)
    replayed = serializers.BooleanField(read_only=True)
    edit_version = serializers.CharField()
    has_unpublished_changes = serializers.BooleanField(read_only=True)


class SavedIssueListSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    item_count = serializers.IntegerField()
    saved = serializers.BooleanField()
    receipt = serializers.DictField(allow_null=True)
    notice = serializers.CharField()


class SaveIssueListCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    public_revision_id = serializers.UUIDField()
