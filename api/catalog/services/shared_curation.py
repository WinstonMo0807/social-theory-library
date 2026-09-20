"""Shared curator-owned metadata over immutable, permission-checked sources."""
from copy import deepcopy
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from catalog.models import (EvidenceCuration, EvidenceCurationReference, EvidenceSpan, Passage,
                            KnowledgeNode, ScholarProfile, ScholarRelation, Topic)
from catalog.services import editorial_issues as revisions
from catalog.services.publication_eligibility import active_document_q, active_document_revision_q
from catalog.services.scoped_search import public_scholar_queryset
from catalog.services.semantic_search import viewer_access_statuses

TARGETS = {"topic": Topic, "scholar": ScholarProfile, "node": KnowledgeNode}
RELATION_TYPES = ("teaching", "cooperation", "influence", "criticism", "comparative_reading", "other")
DIRECTIONS = ("directed", "bidirectional", "undirected")


def identifier(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("对象标识无效。")


def target(kind, key, *, public=False, lock=False):
    if kind not in TARGETS:
        raise ValidationError("未知原文策展对象类型。")
    queryset = TARGETS[kind].objects.all()
    if public:
        queryset = public_scholar_queryset() if kind == "scholar" else queryset.filter(**{"status" if kind == "node" else "editorial_status": "published"})
    if lock:
        queryset = queryset.select_for_update()
    return get_object_or_404(queryset, pk=identifier(key))


def target_title(row):
    return row.person.preferred_name if isinstance(row, ScholarProfile) else row.canonical_name_zh if isinstance(row, KnowledgeNode) else row.name


def sources(kind, *, public=False):
    if kind not in {"span", "passage"}:
        raise ValidationError("原文来源类型无效。")
    model = EvidenceSpan if kind == "span" else Passage
    queryset = model.objects.select_related("page__asset__edition__work", "page__asset__edition__active_catalog_revision")
    if kind == "span":
        queryset = queryset.select_related("document_revision")
    if public:
        queryset = queryset.filter(page__asset__kind="normalized", page__asset__status="ready",
                                   page__asset__validation_status="valid", page__asset__access_status__in=viewer_access_statuses())
        queryset = queryset.filter(active_document_revision_q(revision_prefix="document_revision"), is_stale=False) if kind == "span" else queryset.filter(active_document_q(asset_prefix="page__asset"))
    return queryset


def source_payload(kind, row, *, public=False):
    page, asset = row.page, row.page.asset
    edition = asset.edition
    if page.index < 1 or (asset.page_count and page.index > asset.page_count):
        raise ValidationError("原文页序超出所选文件范围。")
    if kind == "span" and (row.document_revision.asset_id != asset.pk or row.page_number != page.index):
        raise ValidationError("原文版本、文件与页面定位不一致。")
    eligible = sources(kind, public=True).filter(pk=row.pk).exists()
    snapshot = (edition.active_catalog_revision.snapshot or {}) if edition.active_catalog_revision_id else {}
    title = snapshot.get("work", {}).get("title") if eligible else edition.work.title
    text = row.original_text if kind == "span" else row.text
    context = page.text or ""
    # These excerpts are read from the stored page on demand, never copied to a
    # curator revision or accepted back as editable source text.
    start, end = row.start_offset, row.end_offset
    locator = f"/reader/{asset.pk}?page={page.index}"
    return {"id": str(row.pk), "source_type": kind, "text": text,
            "context_before": context[max(0, start - 500):start], "context_after": context[end:end + 500],
            "work_id": str(edition.work_id), "work_title": title or "", "edition_id": str(edition.pk),
            "edition_label": (snapshot.get("edition", {}).get("version_label") or "已公开版本") if public else snapshot.get("edition", {}).get("version_label", edition.version_label) if eligible else edition.version_label,
            "asset_id": str(asset.pk), "page_start": page.index, "page_end": page.index,
            "printed_label": getattr(row, "printed_page_label", "") or page.printed_label,
            "document_revision_id": str(row.document_revision_id) if kind == "span" else str(edition.active_catalog_revision.document_revision_id) if edition.active_catalog_revision_id and edition.active_catalog_revision.document_revision_id else None,
            "reader_url": locator if eligible or (not public and asset.kind == "normalized" and asset.status == "ready") else "", "public_eligible": eligible}


def curation_payload(kind, key, *, public=False):
    parent = target(kind, key, public=public)
    row = EvidenceCuration.objects.select_related("active_revision").filter(object_type=kind, object_id=parent.pk).first()
    revision = row.active_revision if public and row else revisions._latest("evidence_curation", row.pk) if row else None
    data = deepcopy(revision.materialized_preview) if revision else {"items": []}
    reference_ids = [item["id"] for item in data["items"]]
    refs = {str(item.pk): item for item in EvidenceCurationReference.objects.filter(curation=row, pk__in=reference_ids)} if row else {}
    output = []
    # A bounded curation has at most 100 entries; source objects are batched.
    source_rows = {source_kind: {str(source.pk): source for source in sources(source_kind, public=public).filter(pk__in=
                    [getattr(ref, "span_id" if source_kind == "span" else "passage_id") for ref in refs.values()])}
                   for source_kind in ("span", "passage")}
    for item in data["items"]:
        ref = refs.get(item["id"])
        if ref is None:
            continue
        source_kind = "span" if ref.span_id else "passage"
        source_id = str(ref.span_id or ref.passage_id)
        source_row = source_rows[source_kind].get(source_id)
        if source_row is None:
            continue
        if public and ref.document_revision_id != source_row.page.asset.edition.active_catalog_revision.document_revision_id:
            continue
        try:
            resolved = source_payload(source_kind, source_row, public=public)
        except ValidationError:
            if public:
                continue
            raise
        output.append({**item, "source_type": source_kind, "source_id": source_id, "source": resolved})
    data.update(id=str(row.pk) if row else None, configured=bool(revision), object_type=kind, object_id=str(parent.pk), title=target_title(parent), items=output)
    if not public:
        data.update(edit_version=revisions.edit_version("evidence_curation", row.pk) if row else "0", has_unpublished_changes=bool(revision and revision.status == "draft"))
    return data


@transaction.atomic
def save_curation(kind, key, data, actor):
    parent = target(kind, key, lock=True)
    row, _ = EvidenceCuration.objects.get_or_create(object_type=kind, object_id=parent.pk)
    revisions._check_version("evidence_curation", row.pk, data.get("edit_version"))
    incoming = data.get("items", [])
    if not isinstance(incoming, list) or len(incoming) > 100:
        raise ValidationError("单页最多100则策展原文。")
    items, seen = [], set()
    for order, item in enumerate(incoming):
        if not isinstance(item, dict) or set(item) - {"id", "source_type", "source_id", "group_title", "reason", "order"}:
            raise ValidationError("仅可保存原文引用、分组、说明与顺序，不能修改原文或定位。")
        source_kind = item.get("source_type")
        source_row = get_object_or_404(sources(source_kind), pk=identifier(item.get("source_id")))
        resolved = source_payload(source_kind, source_row)
        source_key = (source_kind, str(source_row.pk))
        if source_key in seen:
            raise ValidationError("同一原文不能重复加入。")
        seen.add(source_key)
        reference_values = {"span_id" if source_kind == "span" else "passage_id": source_row.pk,
                            "document_revision_id": resolved["document_revision_id"]}
        if item.get("id"):
            ref = get_object_or_404(EvidenceCurationReference, pk=identifier(item["id"]), curation=row)
            if any(str(getattr(ref, name) or "") != str(value or "") for name, value in reference_values.items()):
                raise ValidationError("所选来源或文档修订已经改变，请重新选择准确原文。")
        else:
            ref = EvidenceCurationReference.objects.filter(curation=row, **reference_values).first()
            if ref is None:
                ref = EvidenceCurationReference.objects.create(curation=row, **reference_values)
        items.append({"id": str(ref.pk), "source_type": source_kind, "source_id": str(source_row.pk),
                      "group_title": revisions._text(item.get("group_title", ""), 240),
                      "reason": revisions._text(item.get("reason", ""), 6000), "order": order})
    revisions._save_revision("evidence_curation", row.pk, {"object_type": kind, "object_id": str(parent.pk), "title": target_title(parent), "items": items}, actor)
    return curation_payload(kind, parent.pk)


@transaction.atomic
def publish_curation(kind, key, expected, actor):
    parent = target(kind, key, lock=True)
    row = get_object_or_404(EvidenceCuration.objects.select_for_update(), object_type=kind, object_id=parent.pk)
    revisions._check_version("evidence_curation", row.pk, expected)
    revision = revisions._latest("evidence_curation", row.pk)
    if not revision or revision.status != "draft":
        raise ValidationError("没有待发布原文策展草稿。")
    for item in revision.materialized_preview["items"]:
        source_row = sources(item["source_type"], public=True).filter(pk=item["source_id"]).first()
        reference = EvidenceCurationReference.objects.get(pk=item["id"], curation=row)
        if source_row is None or not source_payload(item["source_type"], source_row)["public_eligible"] or reference.document_revision_id != source_row.page.asset.edition.active_catalog_revision.document_revision_id:
            raise ValidationError("所选原文的准确版本、文件或文档修订尚未公开，不能发布。")
    revisions._publish_revision(revision, actor)
    row.active_revision = revision
    row.save(update_fields=["active_revision", "updated_at"])
    return curation_payload(kind, key)


def relation_payload(row, *, public=False):
    revision = row.active_revision if public else revisions._latest("scholar_relation", row.pk)
    data = deepcopy(revision.materialized_preview) if revision else {}
    people = {str(person.pk): person for person in (public_scholar_queryset() if public else ScholarProfile.objects.select_related("person")).filter(pk__in=[data.get("source_scholar"), data.get("target_scholar")])}
    if public and len(people) != 2:
        return None
    data.update(id=str(row.pk), status=row.status, source_name=people.get(data.get("source_scholar")).person.preferred_name if people.get(data.get("source_scholar")) else "",
                target_name=people.get(data.get("target_scholar")).person.preferred_name if people.get(data.get("target_scholar")) else "")
    for side in ("source", "target"):
        profile = people.get(data.get(f"{side}_scholar"))
        data[f"{side}_slug"] = profile.slug if profile else ""
    if not public:
        data.update(edit_version=revisions.edit_version("scholar_relation", row.pk), has_unpublished_changes=bool(revision and revision.status == "draft"))
    return data


@transaction.atomic
def save_relation(key, data, actor):
    row = get_object_or_404(ScholarRelation.objects.select_for_update(), pk=key) if key else None
    if row:
        revisions._check_version("scholar_relation", row.pk, data.get("edit_version"))
    source = get_object_or_404(ScholarProfile, pk=identifier(data.get("source_scholar")))
    target_row = get_object_or_404(ScholarProfile, pk=identifier(data.get("target_scholar")))
    if source.pk == target_row.pk:
        raise ValidationError("关系两端须为不同学者。")
    kind, direction = data.get("relation_type"), data.get("direction", "directed")
    if kind not in RELATION_TYPES or direction not in DIRECTIONS:
        raise ValidationError("关系类型或方向无效。")
    payload = {"source_scholar": str(source.pk), "target_scholar": str(target_row.pk), "relation_type": kind, "direction": direction,
               "summary": revisions._text(data.get("summary", ""), 6000), "source": revisions._text(data.get("source", ""), 6000)}
    if row is None:
        row = ScholarRelation.objects.create(source_scholar=source, target_scholar=target_row, relation_type=kind, direction=direction)
    revisions._save_revision("scholar_relation", row.pk, payload, actor)
    return relation_payload(row)


@transaction.atomic
def publish_relation(key, expected, actor):
    row = get_object_or_404(ScholarRelation.objects.select_for_update(), pk=key)
    revisions._check_version("scholar_relation", row.pk, expected)
    revision = revisions._latest("scholar_relation", row.pk)
    if not revision or revision.status != "draft":
        raise ValidationError("没有待发布的学者关系草稿。")
    payload = revision.materialized_preview
    if not payload["summary"] or not payload["source"]:
        raise ValidationError("发布关系前须填写关系说明与来源。")
    if public_scholar_queryset().filter(pk__in=[payload["source_scholar"], payload["target_scholar"]]).count() != 2:
        raise ValidationError("关系两端的学者档案须先公开。")
    row.source_scholar_id, row.target_scholar_id = payload["source_scholar"], payload["target_scholar"]
    for key in ("relation_type", "direction", "summary", "source"):
        setattr(row, key, payload[key])
    row.status, row.active_revision = "published", revision
    row.save()
    revisions._publish_revision(revision, actor)
    return relation_payload(row)


@transaction.atomic
def archive_relation(key, expected, actor):
    from ingestion.models import AuditEvent
    row = get_object_or_404(ScholarRelation.objects.select_for_update(), pk=key)
    revisions._check_version("scholar_relation", row.pk, expected)
    if row.status == "archived":
        return relation_payload(row)
    latest = revisions._latest("scholar_relation", row.pk)
    if latest is None:
        raise ValidationError("关系尚无可保留的编辑版本。")
    # Preserve the current wording as a new editable revision. The former
    # published revision remains intact, and an explicit publish can restore it.
    revision = revisions._save_revision("scholar_relation", row.pk, deepcopy(latest.materialized_preview), actor)
    row.status = "archived"
    row.save(update_fields=["status", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="scholar_relation.archive", object_type="scholar_relation",
                              object_id=str(row.pk), after={"revision": revision.revision, "status": "archived"})
    return relation_payload(row)
