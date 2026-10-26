"""M23 editorial evidence on the original event and revision identities."""
from uuid import UUID

from django.db.models import BooleanField, Case, F, Func, IntegerField, OuterRef, Q, Subquery, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, NullIf
from rest_framework.exceptions import ValidationError

from catalog.models import Asset, EditorialRevision, TheoryTimelineEvent
from catalog.services.timeline_evidence import validate_timeline_file


class DraftScholarRelation(Func):
    output_field = BooleanField()

    def as_sql(self, compiler, connection, **extra_context):
        snapshot, params = compiler.compile(self.source_expressions[0])
        key, key_params = compiler.compile(self.source_expressions[1])
        if connection.vendor == "postgresql":
            rows = f"jsonb_array_elements(CASE WHEN jsonb_typeof({snapshot}->'timeline_relations') = 'array' THEN {snapshot}->'timeline_relations' ELSE '[]'::jsonb END) AS relation(value)"
            subject = "relation.value->>'scholar'"
        else:
            rows = f"json_each(CASE WHEN json_type({snapshot}, '$.timeline_relations') = 'array' THEN json_extract({snapshot}, '$.timeline_relations') ELSE '[]' END) AS relation"
            subject = "json_extract(CASE WHEN relation.type = 'object' THEN relation.value ELSE '{}' END, '$.scholar')"
        return f"EXISTS (SELECT 1 FROM {rows} WHERE {subject} = {key})", [*params, *params, *key_params]


def timeline_for_scholar(queryset, identifier):
    """Include current public membership and the latest draft's own membership."""
    try:
        key = str(UUID(str(identifier)))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"scholar": "请选择有效学者身份。"}) from None
    draft = EditorialRevision.objects.filter(target_type="timeline_event", target_id=OuterRef("pk"), status="draft").order_by("-revision")
    return queryset.alias(scholar_draft=Subquery(draft.values("materialized_preview")[:1])).alias(
        draft_member=DraftScholarRelation(F("scholar_draft"), Value(key)),
    ).filter(Q(scholar_id=key) | Q(normalized_relations__scholar_id=key) | Q(scholar_draft__scholar=key) | Q(draft_member=True)).annotate(
        scholar_sort_year=Case(When(scholar_draft__isnull=False, then=Cast(NullIf(KeyTextTransform("start_year", "scholar_draft"), Value("null")), IntegerField())), default=F("start_year"), output_field=IntegerField()),
    ).distinct()


def validate_timeline_details(value, target=None):
    allowed = {"sources", "time_note", "conflict_note", "editor_note", "confirmed", "duplicate_reason", "primary_image_rendition_id", "primary_kind"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValidationError("事件核对资料格式无效。")
    clean = {}
    for name in ("time_note", "conflict_note", "editor_note", "duplicate_reason"):
        text = value.get(name, "")
        if not isinstance(text, str) or len(text) > 2000:
            raise ValidationError("说明须为不超过 2000 字的文字。")
        clean[name] = text.strip()
    confirmed = value.get("confirmed", False)
    if not isinstance(confirmed, bool):
        raise ValidationError("请明确是否已人工核对出处。")
    clean["confirmed"] = confirmed
    primary_kind = value.get("primary_kind", "other")
    if not isinstance(primary_kind, str) or primary_kind not in {"book", "article", "archive", "other"}:
        raise ValidationError("主要出处类型无效。")
    clean["primary_kind"] = primary_kind
    rows = value.get("sources", [])
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValidationError("同一事件最多记录 20 条补充出处。")
    clean["sources"], seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"id", "kind", "citation", "locator", "quote", "status", "asset_id", "page", "image_rendition_id"}:
            raise ValidationError("补充出处字段无效。")
        try:
            identifier = str(UUID(str(row.get("id", ""))))
        except (ValueError, TypeError):
            raise ValidationError("补充出处缺少稳定编号。") from None
        if identifier in seen:
            raise ValidationError("补充出处编号不能重复。")
        seen.add(identifier)
        source = {"id": identifier}
        for name, maximum in (("citation", 1000), ("locator", 240), ("quote", 4000)):
            text = row.get(name, "")
            if not isinstance(text, str) or len(text) > maximum:
                raise ValidationError(f"出处 {name} 超过允许长度。")
            source[name] = text.strip()
        if not source["citation"]:
            raise ValidationError("每条补充出处需要填写书目或来源说明。")
        for name, choices, default in (("kind", {"book", "article", "archive", "other"}, "book"),
                                       ("status", {"adopted", "disputed", "related"}, "related")):
            choice = row.get(name, default)
            if choice not in choices:
                raise ValidationError("出处类型或核对状态无效。")
            source[name] = choice
        asset_id, page = row.get("asset_id"), row.get("page")
        source["asset_id"], source["page"] = None, None
        if asset_id:
            try:
                asset = Asset.objects.select_related("edition__work").get(pk=UUID(str(asset_id)))
                validate_timeline_file(asset, page)
            except (ValueError, TypeError, Asset.DoesNotExist) as error:
                raise ValidationError("补充出处的阅读文件或 PDF 页序已不可用，请重新选择。") from error
            source["asset_id"], source["page"] = str(asset.pk), page
        elif page is not None:
            raise ValidationError("填写 PDF 页序前须选择对应文件。")
        source["image_rendition_id"] = row.get("image_rendition_id")
        clean["sources"].append(source)
    clean["primary_image_rendition_id"] = value.get("primary_image_rendition_id")
    from catalog.services.timeline_media import validate_evidence_images
    return validate_evidence_images(clean)


def ensure_timeline_publication(target):
    details = validate_timeline_details(target.editorial_details, target)
    if not details["confirmed"]:
        raise ValidationError("请先人工核对来源，再确认发布事件。")
    if not target.source.strip() or not target.description.strip():
        raise ValidationError("发布需要事件说明和主要出处。")
    if any(row["status"] == "disputed" for row in details["sources"]) and not details["conflict_note"]:
        raise ValidationError("来源存在分歧，请记录采用判断与分歧说明。")
    if target.event_type in {"birth", "death", "appointment"} and not target.scholar_id:
        raise ValidationError("人物生平事件须明确关联对应学者。")
    if target.event_type in {"publication", "translation"} and not target.subject_edition_id:
        raise ValidationError("出版或译本出版事件须关联明确的出版版本。")


def similar_timeline_events(data):
    rows = TheoryTimelineEvent.objects.filter(merged_into__isnull=True)
    subjects = Q()
    if data.get("work"):
        subjects |= Q(work_id=data["work"]) | Q(subject_edition__work_id=data["work"])
    if data.get("scholar"):
        subjects |= Q(scholar_id=data["scholar"]) | Q(normalized_relations__scholar_id=data["scholar"])
    title = data.get("title", "").strip()
    if not subjects and not title:
        return rows.none()
    rows = rows.filter(subjects if subjects else Q(title__iexact=title))
    if data.get("event_type"):
        rows = rows.filter(event_type=data["event_type"])
    year = data.get("start_year")
    if year is not None:
        rows = rows.filter(Q(start_year__range=(year-1, year+1)) | Q(start_year__lte=year, end_year__gte=year))
    if data.get("exclude"):
        rows = rows.exclude(pk=data["exclude"])
    return rows.distinct().order_by("start_year", "title", "pk")
