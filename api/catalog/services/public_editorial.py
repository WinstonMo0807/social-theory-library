"""Article-directory projection over the existing scheduled publication ledger."""
from copy import deepcopy
from datetime import datetime
from math import ceil
from uuid import UUID

from django.db.models import Case, CharField, F, JSONField, Q, Value, When
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import MediaRendition, ReadingPath, ScholarProfile, Topic
from catalog.services.public_scholars import _choice, _page, _paging

KINDS = {"article": "策划文章", "research": "研究论文", "exhibition": "原文展览"}
METADATA_FIELDS = {"kind", "keywords", "topic_ids", "scholar_ids", "reading_path_ids", "curator_role", "curator_affiliation", "curator_portrait_id"}


def metadata_input(value):
    from catalog.services.editorial_issues import _text, _rendition
    if not isinstance(value, dict) or set(value) - METADATA_FIELDS:
        raise ValidationError({"article_metadata": "文章资料包含不支持的字段。"})
    result = {"kind": _choice(value, "kind", KINDS, "article")}
    keywords = value.get("keywords", [])
    if not isinstance(keywords, list) or len(keywords) > 30:
        raise ValidationError({"keywords": "最多填写30个关键词。"})
    result["keywords"] = list(dict.fromkeys(text for row in keywords if (text := _text(row, 80))))
    for key, model in (("topic_ids", Topic), ("scholar_ids", ScholarProfile), ("reading_path_ids", ReadingPath)):
        ids = value.get(key, [])
        if not isinstance(ids, list) or len(ids) > 50:
            raise ValidationError({key: "最多选择50项明确关联。"})
        try:
            ids = list(dict.fromkeys(str(UUID(str(row))) for row in ids))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError({key: "对象编号无效。"})
        if model.objects.filter(pk__in=ids).count() != len(ids):
            raise ValidationError({key: "包含不存在的关联对象。"})
        result[key] = ids
    for key in ("curator_role", "curator_affiliation"):
        result[key] = _text(value.get(key, ""), 240)
    portrait = _rendition(value.get("curator_portrait_id"))
    result["curator_portrait_id"] = str(portrait.pk) if portrait else None
    return result


def public_metadata(payload, *, public=True):
    """Only the explicit public byline is exposed; never infer a user profile."""
    raw = payload.get("article_metadata") or {}
    result = {"kind": raw.get("kind", "article"), "keywords": raw.get("keywords", []),
        "curator_role": raw.get("curator_role", ""), "curator_affiliation": raw.get("curator_affiliation", ""),
        "curator_portrait_id": raw.get("curator_portrait_id")}
    for key, model, status in (("topic_ids", Topic, "editorial_status"), ("scholar_ids", ScholarProfile, "editorial_status"), ("reading_path_ids", ReadingPath, "status")):
        ids = raw.get(key, [])
        allowed = set(map(str, model.objects.filter(pk__in=ids, **{status: "published"}).values_list("pk", flat=True))) if public else set(ids)
        result[key] = [key for key in ids if key in allowed]
    portrait = result["curator_portrait_id"]
    if portrait and not MediaRendition.objects.filter(pk=portrait).exists():
        portrait = result["curator_portrait_id"] = None
    curator = {"name": payload.get("public_byline", ""), "role": result["curator_role"], "affiliation": result["curator_affiliation"],
        "portrait_url": (f"/api/catalog/editorial-media/{portrait}/" if public else f"/api/catalog/admin/media/renditions/{portrait}/file/") if portrait else ""}
    # There is no account identity behind an anonymous editorial byline.
    if not curator["name"]:
        curator.update(role="", affiliation="", portrait_url="")
        if public:
            result.update(curator_role="", curator_affiliation="", curator_portrait_id=None)
    return result, curator


def published_projection():
    from catalog.services.editorial_issues import published_issues
    return published_issues().annotate(public_snapshot=Case(
        When(scheduled_revision__status="published", scheduled_for__lte=timezone.now(), then=F("scheduled_revision__materialized_preview")),
        default=F("active_revision__materialized_preview"), output_field=JSONField(),
    )).annotate(public_title=KeyTextTransform("title", "public_snapshot"),
        public_byline=Coalesce(KeyTextTransform("public_byline", "public_snapshot"), Value(""), output_field=CharField()),
        public_kind=Coalesce(KeyTextTransform("kind", KeyTransform("article_metadata", "public_snapshot")), Value("article"), output_field=CharField()))


def directory_card(issue):
    from catalog.services.editorial_issues import public_issue_revision
    revision = public_issue_revision(issue)
    payload = deepcopy(revision.materialized_preview)
    metadata, curator = public_metadata(payload)
    rendition = payload.get("cover_rendition_id")
    text_length = sum(len(row.get("text", "")) for row in payload.get("body_blocks", []) if isinstance(row, dict))
    return {"id": str(issue.pk), "slug": payload.get("slug") or issue.slug, "title": payload.get("title", ""),
        "issue_label": payload.get("issue_label", ""), "introduction": payload.get("introduction", ""),
        "public_byline": payload.get("public_byline", ""), "curator": curator, "article_metadata": metadata,
        "cover_url": f"/api/catalog/editorial-media/{rendition}/" if rendition else payload.get("cover_url", ""),
        "published_at": revision.published_at.isoformat() if revision.published_at else None,
        "display_from": issue.effective_display_from.isoformat() if issue.effective_display_from else None,
        "reading_minutes": max(1, ceil(text_length / 400)) if text_length else None,
        "reading_time_notice": "按正文长度粗略估计，不含原文材料阅读。" if text_length else "",
        "href": f"/recommendations/{payload.get('slug') or issue.slug}"}


def public_directory(params=None):
    params = params or {}
    _paging(params)
    query = str(params.get("q", "")).strip()
    if len(query) > 300:
        raise ValidationError({"q": "关键词不能超过300字。"})
    kind = _choice(params, "kind", {"": "", **KINDS}, "")
    sort = _choice(params, "sort", ("newest", "oldest", "title"), "newest")
    curator = str(params.get("curator", "")).strip()
    if len(curator) > 240:
        raise ValidationError({"curator": "署名筛选过长。"})
    rows = published_projection()
    # Facets read only small metadata from effective public versions, never draft text.
    facets, topic_ids = {"curators": [], "years": [], "kinds": [{"id": key, "label": name} for key, name in KINDS.items()]}, set()
    names, years = set(), set()
    for metadata, name, date in rows.values_list("public_snapshot__article_metadata", "public_byline", "effective_display_from").iterator(chunk_size=100):
        topic_ids.update((metadata or {}).get("topic_ids", []))
        if name:
            names.add(name)
        if date:
            years.add(timezone.localtime(date).year)
    from catalog.services.public_topics import _base as topic_base, _formal, _link
    topics = [_link(_formal(row)) for row in topic_base(counts=False).filter(pk__in=topic_ids).order_by("public_name", "pk")]
    facets.update(curators=sorted(names), years=sorted(years, reverse=True), topics=topics)
    selected_topic = str(params.get("topic", "")).strip()
    if selected_topic:
        topic = next((row for row in topics if selected_topic in {row["id"], row["slug"]}), None)
        rows = rows.filter(public_snapshot__article_metadata__topic_ids__icontains=topic["id"]) if topic else rows.none()
    if kind:
        rows = rows.filter(public_kind=kind)
    if curator:
        rows = rows.filter(public_byline=curator)
    years_filter = {}
    for key in ("year_from", "year_to"):
        value = str(params.get(key, "")).strip()
        if value and (not value.isdecimal() or not 1 <= int(value) <= 9998):
            raise ValidationError({key: "年份须在1至9998之间。"})
        years_filter[key] = int(value) if value else None
    if years_filter["year_from"] and years_filter["year_to"] and years_filter["year_from"] > years_filter["year_to"]:
        raise ValidationError({"year_to": "结束年份不能早于开始年份。"})
    if years_filter["year_from"]:
        rows = rows.filter(effective_display_from__gte=timezone.make_aware(datetime(years_filter["year_from"], 1, 1)))
    if years_filter["year_to"]:
        rows = rows.filter(effective_display_from__lt=timezone.make_aware(datetime(years_filter["year_to"] + 1, 1, 1)))
    if query:
        rows = rows.filter(Q(public_title__icontains=query) | Q(public_byline__icontains=query) |
            Q(public_snapshot__introduction__icontains=query) | Q(public_snapshot__article_metadata__keywords__icontains=query))
    ordering = {"newest": ("-effective_display_from", "pk"), "oldest": ("effective_display_from", "pk"), "title": ("public_title", "pk")}[sort]
    result = _page(rows.order_by(*ordering), params, "/api/catalog/recommendation-issues/", transform=lambda rows: [directory_card(row) for row in rows])
    # This endpoint has scalar filters; commas in a curator name or search are literal.
    from urllib.parse import urlencode
    def link(page):
        pairs = {key: str(params.get(key, "")) for key in ("q", "topic", "kind", "curator", "year_from", "year_to", "sort") if params.get(key)}
        return "/api/catalog/recommendation-issues/?" + urlencode({**pairs, "view": "directory", "page": page, "page_size": result["page_size"]})
    result["next"] = link(result["page"] + 1) if result["next"] else None
    result["previous"] = link(result["page"] - 1) if result["previous"] else None
    result.update(query=query, filters={"topic": selected_topic, "kind": kind, "curator": curator, "sort": sort, **years_filter}, facets=facets)
    result["related"] = directory_related(result["results"])
    return result


def directory_related(cards):
    from catalog.models import EditorialRevision
    from catalog.services.editorial_issues import issue_payload, published_issues
    from catalog.services.public_scholars import _base, _cards
    scholar_ids = list(dict.fromkeys(key for row in cards for key in row["article_metadata"]["scholar_ids"]))
    path_ids = list(dict.fromkeys(key for row in cards for key in row["article_metadata"]["reading_path_ids"]))
    scholars = {row["id"]: row for row in _cards(_base().filter(pk__in=scholar_ids[:5]))}
    paths = {str(row.pk): row for row in ReadingPath.objects.filter(status="published", pk__in=path_ids[:3])}
    revisions = {}
    for revision in EditorialRevision.objects.filter(target_type="reading_path", target_id__in=paths, status="published", materialized_preview__status="published").order_by("target_id", "-revision"):
        revisions.setdefault(str(revision.target_id), revision.materialized_preview)
    material_rows, seen = [], set()
    # Show a bounded selection from the visible articles, with the original article as provenance.
    issues = {str(row.pk): row for row in published_issues().filter(pk__in=[row["id"] for row in cards[:3]])}
    for card in cards[:3]:
        issue = issues.get(card["id"])
        if issue is None:
            continue
        for item in issue_payload(issue, public=True, include_body=False).get("items", []):
            key = item.get("available_edition_id")
            if not key or key in seen:
                continue
            seen.add(key)
            material_rows.append({"id": key, "title": item["title"], "authors": item.get("authors", ""), "href": item.get("work_url", ""),
                "cover_url": item.get("cover_url", ""), "cover_display_uses": item.get('cover_display_uses', []),
                "article_href": card["href"], "source_status": item["status"]})
            if len(material_rows) == 3:
                break
        if len(material_rows) == 3:
            break
    path_rows = []
    for key in path_ids[:3]:
        if key not in paths:
            continue
        row = paths[key]
        raw = revisions.get(key, {})
        path_rows.append({"id": key, "title": raw.get("title", row.title), "href": f"/theories/reading-paths/{raw.get('slug', row.slug)}"})
    return {"scholars": [scholars[key] for key in scholar_ids[:5] if key in scholars], "materials": material_rows, "paths": path_rows,
        "notice": "选自本页文章明确编入的学者、材料与阅读路径。"}


def published_media_usage(rendition_id):
    """An old active image stops being public when a scheduled replacement takes over."""
    key = str(rendition_id)
    rows = published_projection()
    if rows.filter(Q(public_snapshot__cover_rendition_id=key) |
        (Q(public_snapshot__article_metadata__curator_portrait_id=key) & ~Q(public_byline=""))).exists():
        return True
    return any(block.get("type") == "image" and block.get("image_rendition_id") == key
        for blocks in rows.filter(public_snapshot__body_blocks__icontains=key).values_list("public_snapshot__body_blocks", flat=True)
        for block in blocks)


def article_context(issue, payload):
    """Published-only navigation and related content, without recursive body loading."""
    from uuid import uuid5, NAMESPACE_URL
    from catalog.services.editorial_issues import public_issue_revision
    revision = public_issue_revision(issue)
    payload["public_revision_id"] = str(revision.pk)
    for index, block in enumerate(payload["body_blocks"]):
        block.setdefault("id", str(uuid5(NAMESPACE_URL, f"stl-article:{revision.pk}:{index}")))
    payload["related"] = directory_related([{"id": str(issue.pk), "article_metadata": payload["article_metadata"], "href": f"/recommendations/{issue.slug}"}])
    length = sum(len(block.get("text", "")) for block in payload["body_blocks"])
    payload["reading_minutes"] = max(1, ceil(length / 400)) if length else None
    return payload
