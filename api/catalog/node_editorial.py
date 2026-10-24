"""Private node editing notes and optional formatting bound to canonical prose."""
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from catalog.editorial_issue_serializers import IssueTextMarkSerializer
from catalog.services.editorial_blocks import normalize_text_format

PROSE_FIELDS = ("summary", "definition", "theoretical_boundary")


class NodeProseText(serializers.Serializer):
    text = serializers.CharField(allow_blank=True)
    text_style = serializers.ChoiceField(choices=["paragraph", "ordered", "unordered", "quote"])
    text_marks = IssueTextMarkSerializer(many=True)


class NodeProse(serializers.Serializer):
    summary = NodeProseText(required=False)
    definition = NodeProseText(required=False)
    theoretical_boundary = NodeProseText(required=False)


class NodeEditorialDetails(serializers.Serializer):
    internal_note = serializers.CharField(allow_blank=True, max_length=500)
    prose = NodeProse()


def normalize_node_editorial(value):
    if not isinstance(value, dict) or set(value) - {"internal_note", "prose"}:
        raise ValidationError("仅可保存内部编辑说明和正文格式。")
    note, prose = value.get("internal_note", ""), value.get("prose", {})
    if not isinstance(note, str) or len(note) > 500:
        raise ValidationError("内部编辑说明最多500字。")
    if not isinstance(prose, dict) or set(prose) - set(PROSE_FIELDS):
        raise ValidationError("仅可设置简介、定义和理论边界的格式。")
    result = {}
    for field, row in prose.items():
        if not isinstance(row, dict) or set(row) - {"text", "text_style", "text_marks"}:
            raise ValidationError("正文格式必须绑定原文字，不接收HTML或其他字段。")
        text = row.get("text")
        if not isinstance(text, str) or len(text) > 30000:
            raise ValidationError("格式最多对应30000字；较长的原文仍可作为纯文本保存。")
        block = normalize_text_format(row, {"type": "paragraph", "text": text.strip()})
        result[field] = {"text": block["text"], "text_style": block.get("text_style", "paragraph"), "text_marks": block.get("text_marks", [])}
    return {"internal_note": note, "prose": result}


@extend_schema_field(NodeEditorialDetails)
class NodeEditorialField(serializers.JSONField):
    def to_internal_value(self, data):
        return normalize_node_editorial(super().to_internal_value(data))

    def to_representation(self, value):
        return normalize_node_editorial(value)


def public_node_prose(node):
    """Never return private notes or marks referring to different canonical text."""
    details = node.editorial_details if isinstance(node.editorial_details, dict) else {}
    prose = details.get("prose", {})
    result = {}
    if not isinstance(prose, dict):
        return result
    for field in PROSE_FIELDS:
        row = prose.get(field)
        if not isinstance(row, dict) or row.get("text") != getattr(node, field):
            continue
        try:
            result.update(normalize_node_editorial({"prose": {field: row}})["prose"])
        except ValidationError:
            continue
    return result
