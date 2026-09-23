"""Adapters for relation/timeline drafts in the existing editorial service."""
from copy import copy

from django.core.exceptions import ValidationError
from django.core.exceptions import ObjectDoesNotExist
from django.forms.models import model_to_dict

from catalog.models import KnowledgeRelation, TheoryTimelineEvent, TimelineEventRelation

TIMELINE_RELATION_FIELDS = ("relation_type", "node", "discipline", "scholar", "work", "evidence", "description", "sort_order")


def timeline_relations_snapshot(target):
    from catalog.services.editorial_revision import _json_value
    return [_json_value(model_to_dict(row, fields=TIMELINE_RELATION_FIELDS)) for row in target.normalized_relations.order_by("sort_order", "created_at", "pk")]


def validate_relation_patch(target, patch):
    from catalog.services.editorial_revision import EditorialRevisionError, _json_value
    # Withdrawing an existing record must remain possible even when legacy
    # content cannot pass today's publication requirements. No content changes.
    if isinstance(target, TheoryTimelineEvent) and patch == {"review_status": "rejected"}:
        return
    if isinstance(target, KnowledgeRelation) and patch == {"status": "archived"}:
        return
    if isinstance(target, KnowledgeRelation):
        from catalog.theory_serializers import KnowledgeRelationSerializer
        serializer = KnowledgeRelationSerializer(target, data=patch, partial=True)
        if not serializer.is_valid():
            raise EditorialRevisionError(f"关系修改无效：{serializer.errors}")
        patch.update(_json_value(serializer.validated_data))
        return

    from catalog.serializers import AdminTimelineEventRelationSerializer
    rows = patch.get("timeline_relations")
    if rows is not None:
        if not isinstance(rows, list) or any(not isinstance(row, dict) or set(row) - set(TIMELINE_RELATION_FIELDS) for row in rows):
            raise EditorialRevisionError("时间线关联格式无效。")
        serializer = AdminTimelineEventRelationSerializer(data=rows, many=True)
        if not serializer.is_valid():
            raise EditorialRevisionError(f"时间线关联无效：{serializer.errors}")
        rows = patch["timeline_relations"] = [_json_value(model_to_dict(TimelineEventRelation(**values), fields=TIMELINE_RELATION_FIELDS)) for values in serializer.validated_data]
        keys = [_relation_key(row) for row in rows]
        if len(set(keys)) != len(keys):
            raise EditorialRevisionError("同一对象的时间线关联不能重复。")
    preview = copy(target)
    for name, value in patch.items():
        if name == "timeline_relations":
            continue
        field = target._meta.get_field(name)
        try:
            setattr(preview, field.attname, field.to_python(value))
        except (ValidationError, TypeError, ValueError) as error:
            raise EditorialRevisionError(f"时间线字段 {field.verbose_name} 无效。") from error
    if not any(getattr(preview, f"{name}_id") for name in ("discipline", "theory_school", "subdiscipline", "scholar", "work")) and not (rows if rows is not None else target.normalized_relations.exists()):
        raise EditorialRevisionError("时间线事件至少需要关联一个理论、学科、学者或文献。")
    if preview.start_year is not None and preview.end_year is not None and preview.end_year < preview.start_year:
        raise EditorialRevisionError("结束年不能早于开始年。")
    if preview.review_status != "rejected":
        from catalog.services.timeline_evidence import validate_timeline_file
        try:
            validate_timeline_file(preview.evidence_asset, preview.evidence_page)
        except (ValueError, ObjectDoesNotExist) as error:
            raise EditorialRevisionError(str(error)) from error
    if "image" in patch and patch["image"] and patch["image"] != str(target.image.name or ""):
        path = str(patch["image"])
        if not path.startswith("public/knowledge/timeline/") or ".." in path.split("/") or not target.image.storage.exists(path):
            raise EditorialRevisionError("图片不存在或不属于时间线图片，请重新上传。")
    try:
        preview.full_clean()
    except ValidationError as error:
        raise EditorialRevisionError(f"时间线修改无效：{'；'.join(error.messages)}") from error


def _relation_key(row):
    return tuple(str(row.get(name) or "") for name in ("relation_type", "node", "discipline", "scholar", "work", "evidence"))


def _model_values(row):
    return {TimelineEventRelation._meta.get_field(name).attname: value for name, value in row.items()}


def apply_timeline_relations(target, rows):
    # Retain stable existing relation IDs when the same association is edited.
    existing = {_relation_key(model_to_dict(row, fields=TIMELINE_RELATION_FIELDS)): row for row in target.normalized_relations.select_for_update()}
    retained = []
    for values in rows:
        row = existing.get(_relation_key(values))
        if row is None:
            row = TimelineEventRelation.objects.create(event=target, **_model_values(values))
        else:
            for name, value in _model_values(values).items():
                setattr(row, name, value)
            row.save()
        retained.append(row.pk)
    target.normalized_relations.exclude(pk__in=retained).delete()


def serialize_timeline_draft(target, revision, context):
    from catalog.serializers import AdminTimelineEventRelationSerializer
    rows = revision.materialized_preview.get("timeline_relations", timeline_relations_snapshot(target))
    return list(AdminTimelineEventRelationSerializer(
        [TimelineEventRelation(event=target, **_model_values(row)) for row in rows],
        many=True, context=context,
    ).data)


def validated_editorial_values(target, values):
    """Translate the established serializer names; stage uploads without replacing originals."""
    values = dict(values)
    if "normalized_relations" in values:
        values["timeline_relations"] = [dict(row) for row in values.pop("normalized_relations")]
    uploaded = values.get("image")
    if uploaded is not None and hasattr(uploaded, "chunks"):
        field = target._meta.get_field("image")
        values["image"] = field.storage.save(field.generate_filename(target, uploaded.name), uploaded)
    return values
