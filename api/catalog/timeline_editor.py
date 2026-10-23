"""M23 editorial evidence on the original event and revision identities."""
from uuid import UUID

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from catalog.models import Asset, TheoryTimelineEvent
from catalog.services.timeline_evidence import validate_timeline_file


def validate_timeline_details(value, target=None):
    allowed = {"sources", "time_note", "conflict_note", "editor_note", "confirmed", "duplicate_reason"}
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
    rows = value.get("sources", [])
    if not isinstance(rows, list) or len(rows) > 20:
        raise ValidationError("同一事件最多记录 20 条补充出处。")
    clean["sources"], seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"id", "kind", "citation", "locator", "quote", "status", "asset_id", "page"}:
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
        clean["sources"].append(source)
    return clean


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
    rows = TheoryTimelineEvent.objects.all()
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
