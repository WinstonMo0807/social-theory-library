"""Public scholars share explicit contracts; management keeps its editable serializer."""
from rest_framework import serializers
from catalog.contribution_serializers import PublicContributionScopeSerializer
from catalog.media_views import PublicCoverMediaSerializer
from catalog.reading_path_serializers import PublicReadingPathSerializer
from catalog.shared_curation_views import CurationItemSerializer
from catalog.theory_serializers import NormalizedTimelineEventSerializer


class ScholarLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    href = serializers.CharField()


class ScholarFacetSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class ScholarPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    preferred_name = serializers.CharField()
    original_name = serializers.CharField(allow_blank=True)
    aliases = serializers.ListField(child=serializers.CharField())
    birth_year = serializers.IntegerField(allow_null=True)
    death_year = serializers.IntegerField(allow_null=True)
    biography = serializers.CharField(allow_blank=True)
    portrait = serializers.CharField(allow_blank=True)
    portrait_media = PublicCoverMediaSerializer(allow_null=True)


class PublicScholarCardSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    person_id = serializers.UUIDField()
    slug = serializers.CharField()
    href = serializers.CharField()
    person = ScholarPersonSerializer()
    short_description = serializers.CharField(allow_blank=True)
    affiliations = serializers.ListField(child=serializers.CharField())
    key_concerns = serializers.ListField(child=serializers.CharField())
    nationalities = serializers.ListField(child=serializers.CharField())
    occupations = serializers.ListField(child=serializers.CharField())
    matched_alias = serializers.CharField(allow_blank=True)
    fields = ScholarLinkSerializer(many=True)
    schools = ScholarLinkSerializer(many=True)
    work_count = serializers.IntegerField()
    authored_work_count = serializers.IntegerField()
    profile_state = serializers.ChoiceField(choices=("available", "sparse"))


class ScholarPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)


class ScholarDirectoryFiltersSerializer(serializers.Serializer):
    field = serializers.ListField(child=serializers.CharField())
    period = serializers.ListField(child=serializers.CharField())
    school = serializers.ListField(child=serializers.CharField())
    sort = serializers.ChoiceField(choices=("relevance", "name", "birth", "works"))


class ScholarDirectoryFacetsSerializer(serializers.Serializer):
    fields = ScholarFacetSerializer(many=True)
    periods = ScholarFacetSerializer(many=True)
    schools = ScholarFacetSerializer(many=True)


class ScholarRecommendationsSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField(allow_null=True)
    source = serializers.CharField(allow_blank=True)
    title = serializers.CharField()
    results = PublicScholarCardSerializer(many=True)


class ScholarCuratedTopicSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    href = serializers.CharField()
    image_url = serializers.CharField(allow_blank=True)


class PublicScholarDirectorySerializer(ScholarPageSerializer):
    results = PublicScholarCardSerializer(many=True)
    query = serializers.CharField(allow_blank=True)
    filters = ScholarDirectoryFiltersSerializer()
    facets = ScholarDirectoryFacetsSerializer()
    period_notice = serializers.CharField()
    recommendations = ScholarRecommendationsSerializer()
    curated_topics = ScholarCuratedTopicSerializer(many=True)
    related_topics = ScholarLinkSerializer(many=True)


class ScholarRevisionSerializer(serializers.Serializer):
    token = serializers.CharField()
    id = serializers.UUIDField(allow_null=True)
    number = serializers.IntegerField(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    change_note = serializers.CharField(allow_blank=True)


class ScholarContributionSerializer(serializers.Serializer):
    person_id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()
    role_label = serializers.CharField()
    scope = PublicContributionScopeSerializer()


class ScholarWorkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    catalog_revision_id = serializers.UUIDField()
    title = serializers.CharField()
    original_title = serializers.CharField(allow_blank=True)
    href = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)
    document_type = serializers.CharField()
    language = serializers.CharField(allow_blank=True)
    publication_year = serializers.IntegerField(allow_null=True)
    version_label = serializers.CharField(allow_blank=True)
    roles = serializers.ListField(child=serializers.CharField())
    role_labels = serializers.ListField(child=serializers.CharField())
    contributions = ScholarContributionSerializer(many=True)
    source_status = serializers.ChoiceField(choices=("available", "no_fulltext"))
    reader_href = serializers.CharField(allow_blank=True)
    is_essential = serializers.BooleanField()
    is_recommended = serializers.BooleanField(required=False, default=False)
    recommendation_reason = serializers.CharField(allow_blank=True, required=False, default="")


class ScholarKnowledgeSerializer(ScholarLinkSerializer):
    node_type = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    relation_label = serializers.CharField(allow_blank=True)
    relation_source = serializers.ChoiceField(choices=("person_relation", "published_work_relation"))
    source_count = serializers.IntegerField()
    scholar_count = serializers.IntegerField()


class ScholarRelationRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_scholar = serializers.UUIDField()
    target_scholar = serializers.UUIDField()
    source_name = serializers.CharField()
    target_name = serializers.CharField()
    source_slug = serializers.CharField()
    target_slug = serializers.CharField()
    relation_type = serializers.CharField()
    relation_label = serializers.CharField()
    direction = serializers.ChoiceField(choices=("directed", "bidirectional", "undirected"))
    summary = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)
    status = serializers.CharField()


class ScholarProfileSourceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField(max_length=500)
    url = serializers.CharField(max_length=2000, allow_blank=True)
    fields = serializers.ListField(child=serializers.CharField())
    note = serializers.CharField(max_length=2000, allow_blank=True)


class ScholarTopicSerializer(ScholarLinkSerializer):
    description = serializers.CharField(allow_blank=True)


def _page_type(name, item):
    return type(name, (ScholarPageSerializer,), {"__module__": __name__, "results": item(many=True)})


ScholarWorkPage = _page_type("ScholarWorkPage", ScholarWorkSerializer)
ScholarKnowledgePage = _page_type("ScholarKnowledgePage", ScholarKnowledgeSerializer)
ScholarRelationPage = _page_type("ScholarRelationPage", ScholarRelationRowSerializer)
ScholarTopicPage = _page_type("ScholarTopicPage", ScholarTopicSerializer)
ScholarPathPage = _page_type("ScholarPathPage", PublicReadingPathSerializer)
ScholarSourcePage = _page_type("ScholarSourcePage", ScholarProfileSourceSerializer)
ScholarEvidencePage = _page_type("ScholarEvidencePage", CurationItemSerializer)
ScholarTimelinePage = _page_type("ScholarTimelinePage", NormalizedTimelineEventSerializer)


class ScholarCandidateAccessSerializer(serializers.Serializer):
    allowed = serializers.BooleanField()
    requested = serializers.BooleanField()
    notice = serializers.CharField()
    review_href = serializers.CharField(allow_blank=True)


class ScholarDetailFiltersSerializer(serializers.Serializer):
    section = serializers.CharField()
    role = serializers.ListField(child=serializers.CharField())
    relation_type = serializers.ListField(child=serializers.CharField())
    relation_direction = serializers.ChoiceField(choices=("all", "incoming", "outgoing"))


class ScholarDetailFacetsSerializer(serializers.Serializer):
    roles = ScholarFacetSerializer(many=True)
    relation_types = ScholarFacetSerializer(many=True)


class ScholarProseSerializer(serializers.Serializer):
    from catalog.editorial_issue_serializers import IssueTextMarkSerializer
    text = serializers.CharField(allow_blank=True)
    text_style = serializers.ChoiceField(choices=["paragraph", "ordered", "unordered", "quote"])
    text_marks = IssueTextMarkSerializer(many=True)


class ScholarProfileProseSerializer(serializers.Serializer):
    short_description = ScholarProseSerializer(required=False)
    biography = ScholarProseSerializer(required=False)


class PublicScholarDetailSerializer(PublicScholarCardSerializer):
    profile_prose = ScholarProfileProseSerializer(required=False)
    public_revision = ScholarRevisionSerializer()
    period_notice = serializers.CharField()
    graph_href = serializers.CharField()
    research_href = serializers.CharField()
    counts = serializers.DictField(child=serializers.IntegerField())
    works = ScholarWorkPage()
    recommended_works = ScholarWorkSerializer(many=True)
    concepts = ScholarKnowledgePage()
    questions = ScholarKnowledgePage()
    timeline = ScholarTimelinePage()
    relations = ScholarRelationPage()
    topics = ScholarTopicPage()
    paths = ScholarPathPage()
    sources = ScholarSourcePage()
    evidence = ScholarEvidencePage()
    featured_quote = CurationItemSerializer(allow_null=True)
    disambiguation = PublicScholarCardSerializer(many=True)
    candidate_access = ScholarCandidateAccessSerializer()
    candidate_relations = ScholarRelationPage(allow_null=True)
    filters = ScholarDetailFiltersSerializer()
    facets = ScholarDetailFacetsSerializer()
