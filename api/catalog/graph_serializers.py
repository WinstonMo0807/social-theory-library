"""Public graph response contract; node identity is separate from display text."""
from rest_framework import serializers
from catalog.media_views import PublicCoverMediaSerializer

from catalog.theory_serializers import CompactTheoryWorkSerializer


class GraphNodeSerializer(serializers.Serializer):
    id = serializers.CharField()
    entity_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=("knowledge_node", "scholar", "topic", "subdiscipline"))
    node_type = serializers.CharField()
    name = serializers.CharField()
    foreign_name = serializers.CharField(allow_blank=True)
    slug = serializers.CharField()
    href = serializers.CharField()
    summary = serializers.CharField(allow_blank=True)
    image_url = serializers.CharField(allow_blank=True)
    image_media = PublicCoverMediaSerializer(allow_null=True, required=False)
    period_label = serializers.CharField(allow_blank=True)
    start_year = serializers.IntegerField(allow_null=True)
    end_year = serializers.IntegerField(allow_null=True)
    is_center = serializers.BooleanField()
    depth = serializers.IntegerField()


class GraphEvidenceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    title = serializers.CharField()
    edition_label = serializers.CharField(allow_blank=True)
    quote = serializers.CharField()
    pdf_page = serializers.IntegerField()
    printed_page_label = serializers.CharField(allow_blank=True)
    reader_href = serializers.CharField()


class GraphEdgeSerializer(serializers.Serializer):
    id = serializers.CharField()
    entity_id = serializers.UUIDField()
    model = serializers.CharField()
    source = serializers.CharField()
    target = serializers.CharField()
    relation_type = serializers.CharField()
    relation_label = serializers.CharField()
    direction = serializers.ChoiceField(choices=("directed", "bidirectional", "undirected"))
    description = serializers.CharField(allow_blank=True)
    evidence_source = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    evidence = GraphEvidenceSerializer(many=True)
    evidence_truncated = serializers.BooleanField()
    source_status = serializers.ChoiceField(choices=("available", "citation_only", "missing", "unverified"))


class GraphCountsSerializer(serializers.Serializer):
    nodes = serializers.IntegerField()
    edges = serializers.IntegerField()
    scholars = serializers.IntegerField()
    topics = serializers.IntegerField()


class GraphFiltersSerializer(serializers.Serializer):
    center_kind = serializers.CharField()
    center = serializers.CharField(allow_blank=True)
    depth = serializers.IntegerField()
    limit = serializers.IntegerField()
    edge_limit = serializers.IntegerField()
    relation_type = serializers.ListField(child=serializers.CharField())
    node_type = serializers.ListField(child=serializers.CharField())
    discipline = serializers.CharField(allow_blank=True)
    start_year = serializers.IntegerField(allow_null=True)
    end_year = serializers.IntegerField(allow_null=True)
    has_collection = serializers.BooleanField(allow_null=True)
    include_candidates = serializers.BooleanField()
    scope_note = serializers.CharField()


class GraphRelationTypeSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class GraphCandidateAccessSerializer(serializers.Serializer):
    mode = serializers.CharField()
    can_review = serializers.BooleanField()
    review_href = serializers.CharField(allow_null=True)
    detail = serializers.CharField()


class GraphWorkSerializer(CompactTheoryWorkSerializer):
    version_label = serializers.CharField(allow_blank=True)


class PublicTheoryGraphSerializer(serializers.Serializer):
    center = serializers.CharField(allow_null=True)
    center_kind = serializers.CharField()
    nodes = GraphNodeSerializer(many=True)
    edges = GraphEdgeSerializer(many=True)
    depth = serializers.IntegerField()
    limit = serializers.IntegerField()
    edge_limit = serializers.IntegerField()
    truncated = serializers.BooleanField()
    state = serializers.ChoiceField(choices=("empty", "isolated", "filtered", "ready"))
    counts = GraphCountsSerializer()
    filters = GraphFiltersSerializer()
    relation_types = GraphRelationTypeSerializer(many=True)
    candidate_access = GraphCandidateAccessSerializer()
    candidate_edges = GraphEdgeSerializer(many=True)
    candidate_count = serializers.IntegerField(allow_null=True)
    candidates_truncated = serializers.BooleanField()
    selected_node = serializers.CharField(allow_null=True)
    related_works = GraphWorkSerializer(many=True)
    related_works_count = serializers.IntegerField()
    related_works_truncated = serializers.BooleanField()
    related_works_page = serializers.IntegerField()
    related_works_page_size = serializers.IntegerField()
    related_works_total_pages = serializers.IntegerField()
