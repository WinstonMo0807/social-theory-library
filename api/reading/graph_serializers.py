"""Only graph controls and an owner-authored title may be retained."""
from collections.abc import Mapping
import math
from uuid import UUID

from rest_framework import serializers

KINDS = ("knowledge_node", "scholar", "topic", "subdiscipline")
EDGE_MODELS = ("KnowledgeRelation", "PersonNodeRelation", "KnowledgeNodeTopic", "KnowledgeNodeSubdiscipline",
    "PersonTopicRelation", "PersonSubdisciplineRelation", "TopicSubdisciplineRelation", "ScholarRelation")


class StrictGraphInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise serializers.ValidationError("只能保存列出的图谱控件，不能附带候选、原文或其他资料。")
        return super().to_internal_value(data)


class GraphInteger(serializers.IntegerField):
    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        return super().to_internal_value(data)


class GraphFloat(serializers.FloatField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if isinstance(data, bool) or not math.isfinite(value):
            self.fail("invalid")
        return value


class GraphSelection(serializers.CharField):
    def __init__(self, *args, kinds=KINDS, **kwargs):
        self.kinds = kinds
        super().__init__(*args, max_length=100, allow_blank=True, default="", **kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not value:
            return value
        kind, _, identifier = value.partition(":")
        try:
            normalized = str(UUID(identifier))
        except (ValueError, TypeError, AttributeError):
            self.fail("invalid")
        if kind not in self.kinds:
            self.fail("invalid")
        return f"{kind}:{normalized}"


class GraphOffsetInput(StrictGraphInput):
    x = GraphFloat(min_value=-1_000_000, max_value=1_000_000)
    y = GraphFloat(min_value=-1_000_000, max_value=1_000_000)


class GraphViewStateInput(StrictGraphInput):
    center_kind = serializers.ChoiceField(choices=KINDS)
    center = serializers.UUIDField()
    depth = GraphInteger(min_value=1, max_value=3, default=1)
    limit = GraphInteger(min_value=1, max_value=120, default=60)
    edge_limit = GraphInteger(min_value=1, max_value=300, default=150)
    node_type = serializers.ListField(child=serializers.SlugField(max_length=64), max_length=30, default=list)
    relation_type = serializers.ListField(child=serializers.SlugField(max_length=64), max_length=30, default=list)
    discipline = serializers.SlugField(max_length=180, allow_blank=True, default="")
    start_year = GraphInteger(min_value=-32768, max_value=32767, allow_null=True, default=None)
    end_year = GraphInteger(min_value=-32768, max_value=32767, allow_null=True, default=None)
    has_collection = serializers.BooleanField(allow_null=True, default=None)
    selected_node = GraphSelection()
    selected_edge = GraphSelection(kinds=EDGE_MODELS)
    view_mode = serializers.ChoiceField(choices=("graph", "list", "topics", "scholars", "works"), default="graph")
    zoom = GraphFloat(min_value=.15, max_value=4, default=1)
    offset = GraphOffsetInput(default=lambda: {"x": 0, "y": 0})

    def validate(self, attrs):
        from catalog.models import KnowledgeNode
        from catalog.services.theory_graph import RELATION_TYPES
        if set(attrs["node_type"]) - set(KnowledgeNode.NodeType.values):
            raise serializers.ValidationError({"node_type": "包含不支持的知识节点类型。"})
        if set(attrs["relation_type"]) - RELATION_TYPES.keys():
            raise serializers.ValidationError({"relation_type": "包含不支持的正式关系类型。"})
        if attrs["start_year"] is not None and attrs["end_year"] is not None and attrs["start_year"] > attrs["end_year"]:
            raise serializers.ValidationError({"end_year": "结束年不能早于开始年。"})
        attrs["node_type"] = list(dict.fromkeys(attrs["node_type"]))
        attrs["relation_type"] = list(dict.fromkeys(attrs["relation_type"]))
        return attrs


class GraphViewDataInput(StrictGraphInput):
    title = serializers.CharField(max_length=160, allow_blank=False)
    view = GraphViewStateInput()


class GraphViewCreateInput(StrictGraphInput):
    request_id = serializers.UUIDField()
    data = GraphViewDataInput()


class GraphViewUpdateInput(GraphViewCreateInput):
    expected_revision = GraphInteger(min_value=1)


class GraphViewDeleteInput(StrictGraphInput):
    request_id = serializers.UUIDField()
    expected_revision = GraphInteger(min_value=1)


class GraphViewRecordOutput(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField(min_value=1)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    data = GraphViewDataInput()


class GraphViewReceiptOutput(serializers.Serializer):
    request_id = serializers.UUIDField()
    applied_revision = serializers.IntegerField(min_value=1)
    deleted = serializers.BooleanField()


class GraphViewCommandOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    record = GraphViewRecordOutput(allow_null=True)
    receipt = GraphViewReceiptOutput(allow_null=True)


class GraphViewPageOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    count = serializers.IntegerField(min_value=0)
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = GraphViewRecordOutput(many=True)
