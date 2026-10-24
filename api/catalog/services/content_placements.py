"""Page-local references on the existing editorial ledger, never a second catalog.

The parent row serializes edits; EditorialRevision stores draft/public snapshots;
AuditEvent is the durable request receipt. Removing a placement never deletes its
source. Saved sources retain their exact edition/document identities.
"""
from copy import deepcopy
from collections import Counter
from hashlib import sha256
import json
from uuid import NAMESPACE_URL, uuid4, uuid5

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import (Discipline, DocumentRevision, Edition, EditorialRevision, KnowledgeNode, Page, Person,
                            ReadingPath, RecommendationIssue, ScholarProfile,
                            SiteSetting, Subdiscipline, TheoryTimelineEvent, Topic)
from catalog.services import editorial_issues as ledger
from catalog.services import shared_curation
from catalog.services.publication_eligibility import active_document_revision_q, public_editions
from catalog.services.scoped_search import public_scholar_queryset
from catalog.services.semantic_search import viewer_access_statuses
from common.capabilities import Capability, capability_snapshot, has_capability
from ingestion.models import AuditEvent

KIND = "content_placement"
PAGES = {
    "scholar": (ScholarProfile, "editorial_status", "/admin/scholars/"),
    "node": (KnowledgeNode, "status", "/admin/theories/"),
    "topic": (Topic, "editorial_status", "/admin/topics/"),
    "discipline": (Discipline, "editorial_status", "/admin/theories/disciplines?discipline="),
    "subdiscipline": (Subdiscipline, "editorial_status", "/admin/theories/subdisciplines?subdiscipline="),
    "reading_path": (ReadingPath, "status", "/admin/theories/reading-paths?path="),
    "issue": (RecommendationIssue, None, "/admin/recommendations/issues/"),
    "site": (SiteSetting, None, "/admin/about?config="),
    "timeline_event": (TheoryTimelineEvent, "review_status", "/admin/theories/timeline?event="),
}
ACTIONS = ("save", "add", "move", "update", "remove", "undo", "restore", "publish", "withdraw")


def authorize(actor, page_type, *, publishing=False):
    if page_type not in PAGES:
        raise ValidationError({"page_type": "未知页面类型。"})
    if page_type == "site":
        allowed = capability_snapshot(actor).access_level in {"admin", "superadmin"}
    else:
        capability = Capability.PUBLISH_AUTHORITY if publishing else (
            Capability.EDIT_METADATA if page_type == "issue" else Capability.EDIT_DRAFT_AUTHORITY)
        allowed = has_capability(actor, capability)
    if not allowed:
        raise PermissionDenied("当前账户不能编辑或发布此页面的内容编排。")


def parent_object(page_type, page_id, *, public=False, lock=False, actor=None):
    if page_type not in PAGES:
        raise ValidationError({"page_type": "未知页面类型。"})
    if page_type == "issue" and not public:
        from catalog.services.curation_projects import require_issue_access, lock_issue
        if lock: return lock_issue(shared_curation.identifier(page_id), actor)
        require_issue_access(shared_curation.identifier(page_id), actor)
    model, status_field, _ = PAGES[page_type]
    rows = model.objects.all()
    if page_type == "site":
        rows = rows.filter(key="site_config")
    if public:
        if page_type == "scholar":
            rows = public_scholar_queryset()
        elif page_type == "issue":
            rows = ledger.published_issues()
        elif page_type == "site":
            rows = rows.filter(public=True)
        else:
            rows = rows.filter(**{status_field: "approved" if page_type == "timeline_event" else "published"})
    if lock:
        rows = rows.select_for_update()
    return get_object_or_404(rows, pk=shared_curation.identifier(page_id))


def target_id(page_type, page_id):
    # Distinct tables may legitimately have the same UUID.
    return uuid5(NAMESPACE_URL, f"stl:content-placement:{page_type}:{page_id}")


def revisions(page_type, page_id):
    return EditorialRevision.objects.filter(target_type=KIND, target_id=target_id(page_type, page_id)).order_by("-revision")


def version(row):
    return f"{row.pk}:{row.status}" if row else "0"


def _title(parent):
    if isinstance(parent, ScholarProfile):
        return parent.person.preferred_name
    if isinstance(parent, KnowledgeNode):
        return parent.canonical_name_zh
    return getattr(parent, "title", None) or getattr(parent, "name", None) or "网站内容"


def _index(value, size):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= size:
        raise ValidationError({"position": "位置必须在所选分组范围内。"})
    return value


def _edition_details(edition, source, *, span=None):
    """Readonly labels/media from this exact activated edition, never draft media."""
    if not source.get("public_eligible"):
        return {"authors": [], "publication_year": edition.publication_year, "publisher": edition.publisher,
                "image_url": "", "document_type": edition.work.document_type, "language": edition.work.language, "tags": []}
    from catalog.services.contribution_projection import contribution_projection, edition_author_projection
    snapshot = edition.active_catalog_revision.snapshot or {}
    work, data = snapshot.get("work") or {}, snapshot.get("edition") or {}
    authors = contribution_projection(edition).for_range(
        span.page.asset_id, span.document_revision_id, span.page_number)["authors"] if span else edition_author_projection(snapshot)["authors"]
    media = work.get("cover_media") or {}
    image = f"/api/catalog/works/{edition.work_id}/cover/?edition_id={edition.pk}" if work.get("cover") or media else ""
    if image and media.get("primary_rendition_id"):
        image += f"&rendition={media['primary_rendition_id']}"
    from catalog.services.publication_eligibility import public_taxonomy_snapshot
    taxonomy = public_taxonomy_snapshot(snapshot)
    return {"authors": authors, "publication_year": data.get("publication_year"),
            "document_type": work.get("document_type", ""), "language": work.get("language", ""),
            "tags": [row.get("name", "") for row in (taxonomy.get("knowledge") or {}).get("topics", []) if row.get("name")],
            "publisher": data.get("publisher") or "", "image_url": image}


def _source(target, *, public=False):
    """Resolve current permission and labels without copying catalog text into a draft."""
    kind = target.get("type")
    if not isinstance(kind, str):
        raise ValidationError({"target": "引用类型必须是文字标识。"})
    key = shared_curation.identifier(target.get("id"))
    if kind in {"scholar", "issue"}:
        from catalog.site_layout import source_card
        rows = ScholarProfile.objects.select_related("person") if kind == "scholar" else RecommendationIssue.objects.all()
        if kind == "issue":
            # Shared page references may expose only an explicitly published article.
            rows = ledger.published_issues()
        row = get_object_or_404(rows, pk=key)
        try:
            card = source_card({"type": kind, "id": str(key)})
            source = {"type": kind, "id": str(key), "title": card["title"], "summary": card["description"],
                      "href": card["href"], "image_url": card["image_url"], "public_eligible": True}
        except Http404:
            if public or kind == "issue":
                raise
            source = {"type": kind, "id": str(key), "title": _title(row), "public_eligible": False}
        source["edit_url"] = PAGES[kind][2] + str(key)
        return {"type": kind, "id": str(key)}, source
    if kind in {"work", "edition"}:
        edition_id = target.get("edition_id") if kind == "work" else key
        rows = public_editions() if public else Edition.objects.select_related("work", "active_catalog_revision")
        edition = get_object_or_404(rows, pk=shared_curation.identifier(edition_id))
        if kind == "work" and edition.work_id != key:
            raise ValidationError("出版版本不属于所选作品。")
        eligible = public_editions().filter(pk=edition.pk).exists()
        snapshot = (edition.active_catalog_revision.snapshot or {}) if eligible else {}
        title = snapshot.get("work", {}).get("title", "") if eligible else edition.work.title
        label = snapshot.get("edition", {}).get("version_label", "") if eligible else edition.version_label
        reader = edition.active_catalog_revision.reader_asset if eligible else None
        from catalog.services.publication_eligibility import current_retrieval_source_q
        readable = bool(reader and public_editions().filter(pk=edition.pk).filter(current_retrieval_source_q(
            asset_prefix="active_catalog_revision__reader_asset", access_statuses=("public", "inherit") if public else viewer_access_statuses())).exists())
        document_id = str(edition.active_catalog_revision.document_revision_id) if readable else ""
        source = {"type": kind, "id": str(key), "work_id": str(edition.work_id),
                  "edition_id": str(edition.pk), "title": title, "edition_label": label,
                  "public_eligible": eligible,
                  "reader_url": f"/reader/{reader.pk}?revision={document_id}" if readable else "",
                  "asset_id": str(reader.pk) if readable else "", "document_revision_id": document_id, "page_count": reader.page_count if readable else None,
                  "work_url": f"/works/{edition.public_slug}" if eligible and edition.public_slug else "",
                  "edit_url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}"}
        source.update(_edition_details(edition, source))
        return {"type": kind, "id": str(key), "edition_id": str(edition.pk)}, source
    if kind == "node":
        rows = KnowledgeNode.objects.filter(status="published") if public else KnowledgeNode.objects.all()
        row = get_object_or_404(rows, pk=key)
        return {"type": kind, "id": str(key)}, {
            "type": kind, "id": str(key), "title": row.canonical_name_zh,
            "href": f"/theories/nodes/{row.slug}", "summary": row.definition or row.summary,
            "public_eligible": row.status == "published", "edit_url": f"/admin/theories/{key}"}
    if kind == "span":
        row = get_object_or_404(shared_curation.sources("span", public=public), pk=key)
        if row.is_stale:
            raise ValidationError("原文已失效，请重新选择准确的文档修订。")
        reference = {"type": kind, "id": str(key), "document_revision_id": str(row.document_revision_id)}
        if target.get("document_revision_id") and str(target["document_revision_id"]) != reference["document_revision_id"]:
            raise ValidationError("原文修订已改变，不能自动改绑来源。")
        source = shared_curation.source_payload("span", row, public=public)
        source.update(_edition_details(row.page.asset.edition, source, span=row), section=row.section)
        if source["reader_url"]:
            source["reader_url"] += f"&revision={reference['document_revision_id']}"
        source["reader_target"] = {"asset_id": source["asset_id"], "document_revision_id": source["document_revision_id"], "pdf_page": source["page_start"]}
        source.update(type=kind, title=source["work_title"], edit_url=f"/admin/library/works/{source['work_id']}?edition={source['edition_id']}")
        return reference, source
    raise ValidationError({"target": "请选择已有作品、出版版本、知识节点、学者、策划或原文。"})


def _landing(value, reference, *, public=False):
    if reference["type"] not in {"work", "edition"} or not isinstance(value, dict) or set(value) != {"asset_id", "document_revision_id", "pdf_page"}:
        raise ValidationError({"reading_target": "阅读落点须指向所选出版版本的文件、文档修订和物理页。"})
    page_number = value["pdf_page"]
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        raise ValidationError({"reading_target": "物理页从1开始。"})
    rows = DocumentRevision.objects.filter(asset_id=shared_curation.identifier(value["asset_id"]), asset__edition_id=reference["edition_id"])
    if public:
        rows = rows.filter(active_document_revision_q(revision_prefix=""), asset__kind="normalized", asset__status="ready",
                           asset__validation_status="valid", asset__access_status__in=viewer_access_statuses())
    document = get_object_or_404(rows, pk=shared_curation.identifier(value["document_revision_id"]))
    get_object_or_404(Page, asset_id=document.asset_id, index=page_number)
    return {"asset_id": str(document.asset_id), "document_revision_id": str(document.pk), "pdf_page": page_number}


def _concept_usage(value, reference, page_type):
    fields = {"term", "language", "usage_type", "interpretation", "source_person_id", "attribution_note", "review_status",
              "title", "explanatory_object", "period", "context", "internal_note", "review_note", "translations"}
    if page_type != "node" or reference["type"] != "span" or not isinstance(value, dict) or set(value) - fields:
        raise ValidationError({"concept_usage": "概念用法须保存在理论或概念页，并关联准确原文。"})
    usage_type, review = value.get("usage_type", "application"), value.get("review_status", "candidate")
    if (not isinstance(usage_type, str) or not isinstance(review, str)
            or usage_type not in {"definition", "application", "criticism", "translation", "other"}
            or review not in {"candidate", "confirmed", "conflict"}):
        raise ValidationError({"concept_usage": "概念用法类型或人工确认状态无效。"})
    term = ledger._text(value.get("term", ""), 240)
    if not term:
        raise ValidationError({"concept_usage": "请填写原文使用的术语或译名。"})
    person_id = value.get("source_person_id")
    if person_id:
        person_id = str(get_object_or_404(Person, pk=shared_curation.identifier(person_id)).pk)
    note = ledger._text(value.get("attribution_note", ""), 3000)
    if review == "confirmed" and (not person_id or not note):
        raise ValidationError({"concept_usage": "确认用法前须明确作者与归属依据，不能仅由书目作者推定。"})
    translations = value.get("translations", [])
    if not isinstance(translations, list) or len(translations) > 20:
        raise ValidationError({"concept_usage": "每段原文最多记录20个译义候选。"})
    cleaned, seen = [], set()
    for row in translations:
        if not isinstance(row, dict) or set(row) != {"id", "term", "interpretation", "confirmed"} or not isinstance(row["confirmed"], bool):
            raise ValidationError({"concept_usage": "译义候选只接受编号、术语、解释和明确确认状态。"})
        identifier = str(shared_curation.identifier(row["id"]))
        candidate = ledger._text(row["term"], 240)
        if identifier in seen or not candidate:
            raise ValidationError({"concept_usage": "每个译义候选须有不同编号和术语。"})
        seen.add(identifier)
        cleaned.append({"id": identifier, "term": candidate, "interpretation": ledger._text(row["interpretation"], 2000), "confirmed": row["confirmed"]})
    return {"term": term, "language": ledger._text(value.get("language", ""), 32),
            "usage_type": usage_type, "interpretation": ledger._text(value.get("interpretation", ""), 6000),
            "source_person_id": person_id or None, "attribution_note": note, "review_status": review,
            "internal_note": ledger._text(value.get("internal_note", ""), 500),
            "review_note": ledger._text(value.get("review_note", ""), 500), "translations": cleaned,
            **{key: ledger._text(value.get(key, ""), limit) for key, limit in
               (("title", 240), ("explanatory_object", 1200), ("period", 120), ("context", 240))}}


def _normalize(items, *, existing=None, page_type=None):
    if not isinstance(items, list) or len(items) > 100:
        raise ValidationError({"items": "每页最多编排100个引用。"})
    result, seen = [], set()
    prior = {row["id"]: row for row in existing or []}
    for item in items:
        if not isinstance(item, dict) or set(item) - {"id", "area", "group", "position", "target", "reason", "local_text", "reading_target", "concept_usage", "internal_goal", "display_fields", "reason_format"}:
            raise ValidationError("只能编辑本页引用、位置与文案，不能通过编排修改馆藏或原文。")
        key = str(shared_curation.identifier(item["id"])) if item.get("id") else str(uuid4())
        if key in seen:
            raise ValidationError({"items": "引用标识重复。"})
        seen.add(key)
        target = item.get("target")
        if not isinstance(target, dict) or set(target) - {"type", "id", "edition_id", "document_revision_id"}:
            raise ValidationError({"target": "引用只接受对象及准确版本标识。"})
        if key in prior:
            if target != prior[key]["target"]:
                raise ValidationError("现有引用不能暗中改绑来源；请移除后重新选择。")
            reference = deepcopy(target)
        else:
            reference, _ = _source(target)
        area = ledger._text(item.get("area", "main"), 80)
        if not area:
            raise ValidationError({"area": "请选择展示区域。"})
        group = ledger._text(item.get("group", ""), 240)
        result.append({"id": key, "area": area, "group": group,
                       "position": sum(row["area"] == area and row["group"] == group for row in result),
                       "target": reference, "reason": ledger._text(item.get("reason", ""), 6000),
                       "local_text": ledger._text(item.get("local_text", ""), 6000)})
        fields = item.get("display_fields", ["authors", "year", "type", "tags"])
        if not isinstance(fields, list) or len(fields) > 4 or any(not isinstance(field, str) or field not in {"authors", "year", "type", "tags"} for field in fields) or len(set(fields)) != len(fields):
            raise ValidationError({"display_fields": "展示字段限作者、年份、类型和主题标签。"})
        result[-1].update(display_fields=fields, internal_goal=ledger._text(item.get("internal_goal", ""), 1000))
        if item.get("reason_format") is not None:
            from catalog.services.editorial_blocks import normalize_text_format
            formatting = item["reason_format"]
            if not isinstance(formatting, dict) or set(formatting) - {"text_style", "text_marks"}:
                raise ValidationError({"reason_format": "本页文案只接受固定文字格式。"})
            formatted = normalize_text_format({**formatting, "text": item.get("reason", "")}, {"type": "paragraph", "text": result[-1]["reason"]})
            result[-1]["reason_format"] = {key: formatted[key] for key in ("text_style", "text_marks") if key in formatted}
        if item.get("reading_target") is not None:
            landing = item["reading_target"]
            result[-1]["reading_target"] = deepcopy(landing) if key in prior and landing == prior[key].get("reading_target") else _landing(landing, reference)
        if item.get("concept_usage") is not None:
            usage = item["concept_usage"]
            result[-1]["concept_usage"] = deepcopy(usage) if key in prior and usage == prior[key].get("concept_usage") else _concept_usage(usage, reference, page_type)
    # Existing duplicate evidence uses may be intentional. Do not introduce
    # additional copies of the same work/edition into the same group.
    edition_ids = {row["target"]["id"] for row in [*result, *(existing or [])] if row["target"]["type"] == "edition"}
    works = {str(key): str(value) for key, value in Edition.objects.filter(pk__in=edition_ids).values_list("pk", "work_id")} if edition_ids else {}
    def identities(rows):
        return Counter((row.get("area", "main"), row.get("group", ""), works.get(row["target"]["id"], row["target"]["id"]))
                       for row in rows if row["target"]["type"] in {"work", "edition"})
    prior_counts = identities(existing or [])
    if any(count > max(1, prior_counts[key]) for key, count in identities(result).items()):
        raise ValidationError({"items": "同一分组不能重复加入同一作品的多个版本，请修改已有条目或移到其他分组。"})
    return result


def _resolved_items(items, *, public=False):
    output, problems = [], []
    for item in items:
        try:
            reference, source = _source(item["target"], public=public)
            if reference != item["target"]:
                raise ValidationError("来源身份改变，请重新选取。")
            usage = item.get("concept_usage")
            if usage:
                person = Person.objects.filter(pk=usage.get("source_person_id"), authority_status="verified").first() if usage.get("source_person_id") else None
                confirmed = usage.get("review_status") == "confirmed" and person is not None
                if public and not confirmed:
                    continue
                if not confirmed:
                    problems.append({"item_id": item["id"], "code": "concept_usage_unconfirmed", "detail": "概念用法须人工确认归属，并关联已核实人物。"})
                source["usage_author"] = {"id": str(person.pk), "name": person.preferred_name} if person else None
            if item.get("reading_target"):
                landing = _landing(item["reading_target"], reference, public=public)
                source["reader_target"] = landing
                source["reader_url"] = f"/reader/{landing['asset_id']}?page={landing['pdf_page']}&revision={landing['document_revision_id']}"
                if not public:
                    try:
                        _landing(landing, reference, public=True)
                    except (Http404, ValidationError):
                        problems.append({"item_id": item["id"], "code": "reading_target_not_public", "detail": "指定阅读落点的文件或文档修订尚未公开或已失效。", "edit_url": source.get("edit_url", "")})
            if public:
                source.pop("edit_url", None)
            elif not source["public_eligible"]:
                problems.append({"item_id": item["id"], "code": "source_not_public", "detail": "该来源尚未公开或已撤回。", "edit_url": source.get("edit_url", "")})
            row = {**item, "source": source}
            if public:
                row.pop("internal_goal", None)
            if public and usage:
                # Editorial opinions and alternative translations never become public by publication.
                row["concept_usage"] = {key: value for key, value in usage.items()
                    if key in {"term", "language", "usage_type", "interpretation", "source_person_id", "attribution_note", "review_status", "title", "explanatory_object", "period", "context"}}
            output.append(row)
        except (Http404, ValidationError):
            if not public:
                output.append({**item, "source": None})
                problems.append({"item_id": item["id"], "code": "source_unavailable", "detail": "来源不存在、修订失效或定位不一致，请重新选择。"})
    return output, problems


def read(page_type, page_id, *, actor=None, public=False, revision_id=None):
    if not public:
        authorize(actor, page_type)
    parent = parent_object(page_type, page_id, public=public, actor=actor)
    rows = revisions(page_type, parent.pk)
    latest = rows.first()
    published = rows.filter(status="published").first()
    if public:
        selected = published
    elif revision_id:
        selected = get_object_or_404(rows, pk=shared_curation.identifier(revision_id))
    else:
        selected = latest
    data = deepcopy(selected.materialized_preview) if selected else {"items": []}
    items, problems = _resolved_items(data.get("items", []), public=public)
    result = {"schema_version": 1, "page_type": page_type, "page_id": str(parent.pk),
              "revision_id": str(selected.pk) if selected else None,
              "configured": bool(selected), "items": items, "groups": _groups(data.get("groups"), data.get("items", [])),
              "withdrawn": data.get("withdrawn", False)}
    if public and page_type == "node":
        result["public_detail"] = public_concept_detail(result, data.get("items", []))
    if not public:
        blockers = list(problems)
        try:
            parent_object(page_type, page_id, public=True)
        except Http404:
            blockers.append({"code": "page_not_public", "detail": "所属页面尚未公开，请先发布页面。"})
        try:
            authorize(actor, page_type, publishing=True)
            may_publish = True
        except PermissionDenied:
            may_publish = False
        result.update(title=_title(parent), public_url=public_url(page_type, parent), edit_url=PAGES[page_type][2] + str(parent.pk), expected_revision=version(latest),
                      is_current_revision=bool(selected and latest and selected.pk == latest.pk),
                      published_revision_id=str(published.pk) if published else None,
                      has_unpublished_changes=bool(latest and latest.status == "draft"),
                      source_problems=problems, publication_blockers=blockers,
                      can_publish=may_publish and not blockers and bool(selected and latest and selected.pk == latest.pk and latest.status == "draft"),
                      can_withdraw=may_publish and bool(published) and not data.get("withdrawn", False),
                      state="saved_unpublished" if latest and latest.status == "draft" else "withdrawn" if data.get("withdrawn") else "published" if published else "empty",
                      impact="本页文案和位置只影响此页面；修改题名、作者或原文须进入来源编辑。")
        excluded = {row["id"] for row in data.get("items", []) if row.get("concept_usage")
                    and row["concept_usage"].get("review_status") != "confirmed"}
        confirmed_blockers = [problem for problem in blockers if problem.get("item_id") not in excluded]
        result.update(confirmed_publication_blockers=confirmed_blockers,
            can_publish_confirmed=may_publish and not confirmed_blockers and bool(items)
                and any(row["id"] not in excluded for row in items)
                and bool(selected and latest and selected.pk == latest.pk and latest.status == "draft"))
    return result


def public_url(page_type, parent):
    paths = {"scholar": "/scholars/", "node": "/theories/nodes/", "topic": "/topics/",
             "discipline": "/theories/disciplines/", "subdiscipline": "/subdisciplines/",
             "reading_path": "/theories/reading-paths/", "issue": "/recommendations/", "timeline_event": "/theories/events/"}
    return paths[page_type] + str(parent.pk if page_type == "timeline_event" else parent.slug) if page_type in paths else "/"


def _groups(value, items):
    """Keep empty groups and their order in the same revision as the item list."""
    if value is None:
        value = []
    if not isinstance(value, list) or len(value) > 100:
        raise ValidationError({"groups": "最多保留100个分组。"})
    result, seen = [], set()
    for row in value:
        if not isinstance(row, dict) or set(row) != {"area", "name"}:
            raise ValidationError({"groups": "分组只接受展示区域和名称。"})
        area, name = ledger._text(row["area"], 80), ledger._text(row["name"], 240)
        if not area or (area, name) in seen:
            raise ValidationError({"groups": "分组区域不能为空，同一区域的名称不能重复。"})
        seen.add((area, name)); result.append({"area": area, "name": name})
    for row in items:
        key = (row.get("area", "main"), row.get("group", ""))
        if key not in seen:
            seen.add(key); result.append({"area": key[0], "name": key[1]})
    return result


def public_concept_detail(result, original_items):
    """Project confirmed uses from the existing ledger, without copying failed sources."""
    from catalog.serializers import PersonCompactSerializer
    portraits = PersonCompactSerializer()
    confirmed = [row for row in original_items if (row.get("concept_usage") or {}).get("review_status") == "confirmed"]
    profiles = {str(profile.person_id): profile for profile in public_scholar_queryset().filter(
        person_id__in=[row["concept_usage"].get("source_person_id") for row in confirmed
                       if row["concept_usage"].get("source_person_id")])}
    usages = []
    for row in result["items"]:
        usage, source = row.get("concept_usage"), row.get("source")
        if not usage or usage.get("review_status") != "confirmed" or not source or source.get("type") != "span":
            continue
        author = source.get("usage_author")
        if not author:
            continue
        profile = profiles.get(author["id"])
        person = profile.person if profile else None
        usages.append({
            "id": row["id"],
            **{key: usage.get(key, "") for key in ("term", "language", "usage_type", "interpretation",
                                                  "attribution_note", "title", "explanatory_object", "period", "context")},
            "author": {**author, "original_name": person.original_name if person else "",
                       "birth_year": person.birth_year if person else None, "death_year": person.death_year if person else None,
                       "portrait_url": portraits.get_portrait(person) if person else "",
                       "portrait_media": portraits.get_portrait_media(person) if person else None,
                       "scholar_slug": profile.slug if profile else ""},
            "source": {key: source.get(key) for key in ("id", "type", "title", "public_eligible", "work_id", "work_title", "edition_id", "edition_label",
                       "asset_id", "document_revision_id", "page_start", "page_end", "printed_label", "text", "reader_url")},
        })
        usages[-1]["source"]["reader_url"] = (
            f"/reader/{source['asset_id']}?page={source['page_start']}&revision={source['document_revision_id']}")
    return {"configured": result["configured"], "revision_id": result["revision_id"],
            "usages": usages, "unavailable_usage_count": max(0, len(confirmed) - len(usages))}


def _move(items, item_id, data):
    item = next((item for item in items if item["id"] == item_id), None)
    if item is None:
        raise ValidationError({"item_id": "本页未找到所选引用。"})
    items.remove(item)
    item["area"] = data.get("area", item["area"])
    item["group"] = data.get("group", item["group"])
    matches = [index for index, row in enumerate(items) if row["area"] == item["area"] and row["group"] == item["group"]]
    position = _index(data.get("position", len(matches)), len(matches))
    insert_at = matches[position] if position < len(matches) else matches[-1] + 1 if matches else len(items)
    items.insert(insert_at, item)


@transaction.atomic
def command(page_type, page_id, data, actor):
    from accounts.models import User
    previous_actor = actor
    actor = get_object_or_404(User.objects.select_for_update(), pk=actor.pk, is_active=True)
    if actor.token_version != previous_actor.token_version:
        raise PermissionDenied("账户会话已变化，请重新核对编辑身份。")
    if not isinstance(data, dict):
        raise ValidationError("请提交编排操作对象。")
    action = data.get("action")
    if action not in ACTIONS:
        raise ValidationError({"action": "未知编排操作。"})
    allowed = {"action", "request_id", "expected_revision"} | {
        "save": {"items", "groups"}, "add": {"item", "position"}, "move": {"item_id", "position", "area", "group"},
        "update": {"item_id", "patch"}, "remove": {"item_id"}, "undo": set(),
        "restore": {"revision_id"}, "publish": {"confirmed_only"}, "withdraw": set(),
    }[action]
    if set(data) - allowed or "confirmed_only" in data and not isinstance(data["confirmed_only"], bool):
        raise ValidationError("编排请求包含不支持的字段。")
    authorize(actor, page_type, publishing=action in {"publish", "withdraw"})
    parent = parent_object(page_type, page_id, lock=True, actor=actor)
    request_id = str(shared_curation.identifier(data.get("request_id")))
    fingerprint = sha256(json.dumps(data, cls=DjangoJSONEncoder, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = target_id(page_type, parent.pk)
    receipts = AuditEvent.objects.filter(action="content_placement.command", object_type=KIND, object_id=str(key), request_id=request_id, actor=actor)
    receipt = receipts.first()
    if receipt:
        if receipt.after.get("operation") == "cancelled":
            raise ledger.EditConflict("这次未确认的请求已停止。请读取当前编排后发起新操作。")
        if receipt.after.get("fingerprint") != fingerprint:
            raise ledger.EditConflict("此请求编号已经用于另一组修改，请使用新的请求编号。")
        return {**read(page_type, page_id, actor=actor), "replayed": True, "applied_revision_id": receipt.after["revision_id"]}
    rows = revisions(page_type, parent.pk)
    latest = rows.first()
    if data.get("expected_revision") != version(latest):
        raise ledger.EditConflict("页面已有新修改；请保留当前输入，读取最新编排后核对差异。")
    items = deepcopy(latest.materialized_preview.get("items", [])) if latest else []
    groups = deepcopy(latest.materialized_preview.get("groups")) if latest else None
    existing = deepcopy(items)
    if action == "save":
        items = data.get("items")
        groups = data.get("groups", groups)
    elif action == "add":
        item = _normalize([data.get("item")], page_type=page_type)[0]
        items.append(item)
        _move(items, item["id"], {"position": data.get("position", sum(row["area"] == item["area"] and row["group"] == item["group"] for row in items) - 1)})
    elif action in {"move", "update", "remove"}:
        item_id = str(shared_curation.identifier(data.get("item_id")))
        item = next((row for row in items if row["id"] == item_id), None)
        if item is None:
            raise ValidationError({"item_id": "本页未找到所选引用。"})
        if action == "move":
            _move(items, item_id, data)
        elif action == "remove":
            items.remove(item)
        else:
            patch = data.get("patch")
            if not isinstance(patch, dict) or set(patch) - {"reason", "local_text", "reading_target", "concept_usage", "internal_goal", "display_fields", "reason_format"}:
                raise ValidationError({"patch": "此操作只能修改本页推荐理由、文案、阅读落点与有出处的概念用法。"})
            item.update(patch)
    elif action in {"undo", "restore"}:
        if action == "undo":
            undo_number = latest.materialized_preview.get("undo_next_revision", latest.base_revision) if latest else None
            if undo_number is None:
                raise ValidationError("没有可以撤销的修改。")
            previous = rows.filter(revision=undo_number).first()
        else:
            previous = get_object_or_404(rows, pk=shared_curation.identifier(data.get("revision_id")))
        if previous is None and latest is None:
            raise ValidationError("没有可以撤销的修改。")
        items = deepcopy(previous.materialized_preview.get("items", [])) if previous else []
        groups = deepcopy(previous.materialized_preview.get("groups")) if previous else None
        existing = deepcopy(items)
    if action == "publish":
        if latest is None or latest.status != "draft":
            raise ValidationError("没有待发布的编排草稿。")
        try:
            parent_object(page_type, page_id, public=True)
        except Http404:
            raise ValidationError({"page": "所属页面尚未公开，请先发布页面。"})
        publishable = [row for row in items if not row.get("concept_usage") or row["concept_usage"].get("review_status") == "confirmed"] if data.get("confirmed_only") else items
        if data.get("confirmed_only") and not publishable:
            raise ValidationError("尚无已确认的内容可以发布。")
        _, problems = _resolved_items(publishable)
        if problems:
            raise ValidationError({"source_problems": problems})
        # Re-read through the public boundary: a source may be hidden even if
        # its bibliographic record exists (exact OCR revision, access, file).
        visible, _ = _resolved_items(publishable, public=True)
        if len(visible) != len(publishable):
            raise ValidationError("存在不可公开的准确来源，请核对原文或版本。")
        revision = latest
        ledger._publish_revision(revision, actor)
    else:
        payload = {"schema_version": 1, "page_type": page_type, "page_id": str(parent.pk),
                   "title": _title(parent), "edit_url": PAGES[page_type][2] + str(parent.pk),
                   "items": [] if action == "withdraw" else _normalize(items, existing=existing, page_type=page_type), "withdrawn": action == "withdraw"}
        payload["groups"] = [] if action == "withdraw" else _groups(groups, payload["items"])
        if action == "undo":
            payload["undo_next_revision"] = previous.base_revision if previous else None
        revision = ledger._save_revision(KIND, key, payload, actor)
        if action == "withdraw":
            ledger._publish_revision(revision, actor)
    AuditEvent.objects.create(actor=actor, action="content_placement.command", object_type=KIND, object_id=str(key),
                              request_id=request_id, before={"revision_id": str(latest.pk) if latest else None},
                              after={"fingerprint": fingerprint, "revision_id": str(revision.pk), "operation": action})
    return {**read(page_type, page_id, actor=actor), "replayed": False, "applied_revision_id": str(revision.pk)}
