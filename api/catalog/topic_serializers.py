"""Topic public DTOs; canonical management continues using AdminTopicSerializer."""
from rest_framework import serializers
from catalog.media_views import PublicCoverMediaSerializer
from catalog.scholar_serializers import PublicScholarCardSerializer, ScholarPageSerializer, ScholarRevisionSerializer, ScholarWorkSerializer
from catalog.reading_path_serializers import PublicReadingPathSerializer
from catalog.shared_curation_views import CurationItemSerializer


class TopicLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    name = serializers.CharField()
    href = serializers.CharField()


class PublicTopicCardSerializer(TopicLinkSerializer):
    description = serializers.CharField(allow_blank=True)
    problem_statement = serializers.CharField(allow_blank=True)
    hero_image = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)
    tags = serializers.ListField(child=serializers.CharField())
    matched_alias = serializers.CharField(allow_blank=True)
    parent = TopicLinkSerializer(allow_null=True)
    work_count = serializers.IntegerField()
    edition_count = serializers.IntegerField()
    scholar_count = serializers.IntegerField()
    question_count = serializers.IntegerField()
    profile_state = serializers.ChoiceField(choices=("available", "sparse"))


class TopicHierarchySerializer(TopicLinkSerializer):
    parent_id = serializers.UUIDField(allow_null=True)
    child_count = serializers.IntegerField()
    descendant_count = serializers.IntegerField()
    count = serializers.IntegerField()


class TopicDirectoryFiltersSerializer(serializers.Serializer):
    parent = serializers.CharField(allow_blank=True)
    parents = serializers.ListField(child=serializers.CharField())
    discipline = serializers.CharField(allow_blank=True)
    subdiscipline = serializers.CharField(allow_blank=True)
    theory = serializers.CharField(allow_blank=True)
    sort = serializers.ChoiceField(choices=("relevance", "name", "works", "updated"))


class TopicRecommendationsSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField(allow_null=True)
    source = serializers.CharField(allow_blank=True)
    results = PublicTopicCardSerializer(many=True)


class PublicTopicDirectorySerializer(ScholarPageSerializer):
    results = PublicTopicCardSerializer(many=True)
    query = serializers.CharField(allow_blank=True)
    filters = TopicDirectoryFiltersSerializer()
    hierarchy = TopicHierarchySerializer(many=True)
    selected_parent = TopicLinkSerializer(allow_null=True)
    selected_parents = TopicLinkSerializer(many=True)
    recommendations = TopicRecommendationsSerializer()
    disambiguation = PublicTopicCardSerializer(many=True)
    overlap_notice = serializers.CharField(allow_blank=True)


class TopicKnowledgeSerializer(TopicLinkSerializer):
    node_type = serializers.ChoiceField(choices=("research_problem", "debate", "concept"))
    summary = serializers.CharField(allow_blank=True)
    relation_label = serializers.CharField(allow_blank=True)
    work_count = serializers.IntegerField()
    discussion_count = serializers.IntegerField()
    response_count = serializers.IntegerField()
    count_notice = serializers.CharField()


class TopicWorkSerializer(ScholarWorkSerializer):
    edition_id = serializers.UUIDField(allow_null=True)
    catalog_revision_id = serializers.UUIDField(allow_null=True)
    source_status = serializers.ChoiceField(choices=("available", "no_fulltext", "planned"))
    source_notice = serializers.CharField()
    selection = serializers.ChoiceField(choices=("related", "foundational", "disputed"))
    issue_id = serializers.UUIDField(allow_null=True)
    issue_item_id = serializers.UUIDField(allow_null=True)


class TopicArticleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    slug = serializers.CharField()
    title = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    href = serializers.CharField()
    cover_url = serializers.CharField(allow_blank=True)
    public_byline = serializers.CharField(allow_blank=True)
    published_at = serializers.DateTimeField(allow_null=True)


class TopicUnavailableSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=("question", "concept", "work", "scholar", "article", "path"))
    status = serializers.ChoiceField(choices=("unavailable",))
    notice = serializers.CharField()


class TopicKnowledgePageSerializer(ScholarPageSerializer):
    results = TopicKnowledgeSerializer(many=True)


class TopicWorkPageSerializer(ScholarPageSerializer):
    results = TopicWorkSerializer(many=True)


class TopicScholarPageSerializer(ScholarPageSerializer):
    results = PublicScholarCardSerializer(many=True)


class TopicArticlePageSerializer(ScholarPageSerializer):
    results = TopicArticleSerializer(many=True)


class TopicPathPageSerializer(ScholarPageSerializer):
    results = PublicReadingPathSerializer(many=True)


class TopicEvidencePageSerializer(ScholarPageSerializer):
    results = CurationItemSerializer(many=True)


class TopicIntroductionSerializer(serializers.Serializer):
    description = serializers.CharField(allow_blank=True)
    problem_statement = serializers.CharField(allow_blank=True)
    formation_context = serializers.CharField(allow_blank=True)
    core_questions = serializers.ListField(child=serializers.CharField())
    research_dimensions = serializers.ListField(child=serializers.CharField())
    methods = serializers.ListField(child=serializers.CharField())


class TopicDetailFiltersSerializer(serializers.Serializer):
    section = serializers.ChoiceField(choices=("overview", "questions", "works", "scholars", "concepts", "articles", "paths", "evidence"))
    question_type = serializers.ChoiceField(choices=("all", "research_problem", "debate"))
    availability = serializers.ChoiceField(choices=("all", "readable", "no_fulltext", "planned"))
    reading = serializers.ChoiceField(choices=("all", "foundational", "disputed"))
    sort = serializers.ChoiceField(choices=("relevance", "published", "title"))


class TopicLegacySerializer(serializers.Serializer):
    timeline = serializers.JSONField()
    research_dimensions = serializers.ListField(child=serializers.CharField())
    methods = serializers.ListField(child=serializers.CharField())
    subdisciplines = TopicLinkSerializer(many=True)
    linked_theories = TopicLinkSerializer(many=True)
    theory_nodes = TopicLinkSerializer(many=True)
    curated_works = serializers.JSONField()
    reading_paths = serializers.JSONField()
    related_scholars = serializers.JSONField()


class PublicTopicDetailSerializer(PublicTopicCardSerializer):
    public_revision = ScholarRevisionSerializer()
    breadcrumbs = TopicLinkSerializer(many=True)
    children = TopicLinkSerializer(many=True)
    introduction = TopicIntroductionSerializer()
    counts = serializers.DictField(child=serializers.IntegerField())
    questions = TopicKnowledgePageSerializer()
    works = TopicWorkPageSerializer()
    scholars = TopicScholarPageSerializer()
    concepts = TopicKnowledgePageSerializer()
    articles = TopicArticlePageSerializer()
    paths = TopicPathPageSerializer()
    evidence = TopicEvidencePageSerializer()
    featured_quote = CurationItemSerializer(allow_null=True)
    unavailable_links = TopicUnavailableSerializer(many=True)
    unavailable_notice = serializers.CharField(allow_blank=True)
    discussion_notice = serializers.CharField()
    feedback_href = serializers.CharField()
    graph_href = serializers.CharField()
    research_href = serializers.CharField()
    filters = TopicDetailFiltersSerializer()
    work_facets = serializers.DictField(child=serializers.IntegerField())
    legacy = TopicLegacySerializer()
