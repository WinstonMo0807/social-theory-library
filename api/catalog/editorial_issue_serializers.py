"""Wire contracts shared with generated TypeScript; commands validate domain rules."""
from rest_framework import serializers
from catalog.serializers import SiteConfigSerializer, AboutPageBlockSerializer


class IssueBodyBlockSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["paragraph", "heading", "quote", "link"])
    text = serializers.CharField(allow_blank=True)
    source = serializers.CharField(required=False, allow_blank=True)
    url = serializers.CharField(required=False, allow_blank=True)


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


class RecommendationIssueSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(required=False)
    title = serializers.CharField()
    issue_label = serializers.CharField(required=False, allow_blank=True)
    introduction = serializers.CharField(required=False, allow_blank=True)
    public_byline = serializers.CharField(required=False, allow_blank=True)
    body_blocks = IssueBodyBlockSerializer(many=True, required=False)
    cover_url = serializers.CharField(required=False, allow_blank=True)
    cover_rendition_id = serializers.UUIDField(required=False, allow_null=True)
    display_from = serializers.DateTimeField(required=False, allow_null=True)
    published_at = serializers.DateTimeField(read_only=True, allow_null=True)
    items = IssueItemSerializer(many=True, required=False)
    edit_version = serializers.CharField(required=False)
    draft_revision_id = serializers.UUIDField(read_only=True, allow_null=True)
    has_unpublished_changes = serializers.BooleanField(read_only=True)


class RecommendationIssueCollectionSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    current = RecommendationIssueSerializer(allow_null=True)
    results = RecommendationIssueSerializer(many=True)


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


class SiteContentSerializer(serializers.Serializer):
    config = SiteConfigSerializer()
    about_blocks = AboutPageBlockSerializer(many=True)
    edit_version = serializers.CharField()
    has_unpublished_changes = serializers.BooleanField(read_only=True)


class SavedIssueListSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    item_count = serializers.IntegerField()
    planned_count = serializers.IntegerField()
