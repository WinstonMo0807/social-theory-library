"""Read contracts for the existing public theory overview and local graph."""
from rest_framework import serializers

from catalog.theory_serializers import (
    CompactTheoryWorkSerializer, DisciplineCompactSerializer,
    EvidenceSnippetSerializer, KnowledgeNodeListSerializer,
    NormalizedTimelineEventSerializer, ReadingPathSerializer,
    WorkNodeRelationSerializer,
)


class TheoryOverviewDisciplineSerializer(DisciplineCompactSerializer):
    counts = serializers.DictField(child=serializers.IntegerField(min_value=0))

    class Meta(DisciplineCompactSerializer.Meta):
        fields = DisciplineCompactSerializer.Meta.fields + ("counts",)


class TheoryBrowseCountsSerializer(serializers.Serializer):
    theory_traditions = serializers.IntegerField(min_value=0)
    subdisciplines = serializers.IntegerField(min_value=0)
    debates = serializers.IntegerField(min_value=0)


class TheoryRecentSerializer(serializers.Serializer):
    nodes = KnowledgeNodeListSerializer(many=True)
    timeline_events = NormalizedTimelineEventSerializer(many=True)
    work_relations = WorkNodeRelationSerializer(many=True)


class TheorySystemOverviewSerializer(serializers.Serializer):
    disciplines = TheoryOverviewDisciplineSerializer(many=True)
    featured_nodes = KnowledgeNodeListSerializer(many=True)
    browse = TheoryBrowseCountsSerializer()
    reading_paths = ReadingPathSerializer(many=True)
    recent = TheoryRecentSerializer()


class LocalTheoryGraphNodeSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField()
    name = serializers.CharField()
    node_type = serializers.CharField(required=False)
    foreign_name = serializers.CharField(required=False, allow_blank=True)
    slug = serializers.CharField(required=False, allow_blank=True)
    summary = serializers.CharField(required=False, allow_blank=True)
    period_label = serializers.CharField(required=False, allow_blank=True)
    is_center = serializers.BooleanField(required=False)
    work = CompactTheoryWorkSerializer(required=False, allow_null=True)


class LocalTheoryGraphEdgeSerializer(serializers.Serializer):
    id = serializers.CharField()
    source = serializers.CharField()
    target = serializers.CharField()
    relation_type = serializers.CharField()
    relation_label = serializers.CharField()
    direction = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    evidence_source = serializers.CharField(required=False, allow_blank=True)
    evidence = EvidenceSnippetSerializer(many=True, required=False)


class LocalTheoryGraphSerializer(serializers.Serializer):
    center = serializers.UUIDField(allow_null=True)
    nodes = LocalTheoryGraphNodeSerializer(many=True)
    edges = LocalTheoryGraphEdgeSerializer(many=True)
    depth = serializers.IntegerField(required=False, min_value=1, max_value=2)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=30)
    truncated = serializers.BooleanField()
