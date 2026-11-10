"""Shared permission-checked query contract for DRF and MCP."""
from django.shortcuts import get_object_or_404
from catalog import models as m
from catalog.services.knowledge_core import require_editor, page_content
from catalog.services.knowledge_sources import require_revision_access, digest


def run_data(run, actor, *, detail=False):
    require_editor(actor)
    require_revision_access(run.document_revision, actor, editorial=True)
    data = {"id": str(run.pk), "work_id": str(run.work_id), "title": run.work.title,
        "edition_id": str(run.edition_id), "document_revision_id": str(run.document_revision_id),
        "asset_id": str(run.document_revision.asset_id), "pages": run.document_revision.asset.page_count,
        "scope": run.scope, "status": run.status, "stage": run.stage, "coverage": run.coverage,
        "profile_key": run.profile_key, "model_identity": run.model_identity, "error": run.error,
        "version": run.version, "created_at": run.created_at, "finished_at": run.finished_at}
    if detail:
        data["artifacts"] = list(run.artifacts.values("id", "stage", "unit", "status", "output", "usage", "elapsed_ms", "error", "input_manifest"))
        changeset = m.ChangeSet.objects.filter(run=run).first()
        data["changeset"] = changeset_data(changeset, actor) if changeset else None
    return data


def changeset_data(changeset, actor):
    from catalog.services.intelligence_changes import require_changeset_access
    require_changeset_access(changeset, actor)
    items = list(changeset.items.values("id", "kind", "payload", "dependencies", "decision", "decision_note", "application", "conflict", "reviewed_at"))
    for item in items:
        if item["kind"] == "alias":
            from uuid import UUID
            from catalog.services.knowledge_core import entity_data
            try:
                entity_id = UUID(str(item["payload"].get("entity_id", "")))
            except ValueError:
                entity_id = None
            entity = m.Entity.objects.filter(pk=entity_id).first() if entity_id else None
            item["identity"] = entity_data(entity) if entity else None
        if item["kind"] == "assertion":
            from catalog.services.knowledge_sources import locator
            item["evidence_context"] = [locator(anchor, actor, editorial=True) for anchor in m.EvidenceAnchor.objects.filter(
                pk__in=[v["anchor_id"] for v in item["payload"].get("evidence", []) if v.get("anchor_id")])]
        applied = item["application"]
        if applied.get("type") in {"assertion_withdrawal", "entity_profile", "alias"}:
            item["current_status"] = applied.get("status", "draft")
        elif applied.get("type") == "assertion":
            item["current_status"] = m.Assertion.objects.filter(pk=applied["id"]).values_list("status", flat=True).first()
        elif applied.get("page_id"):
            page = m.KnowledgePage.objects.get(pk=applied["page_id"])
            saved = m.EditorialRevision.objects.get(pk=applied["id"])
            published = m.EditorialRevision.objects.filter(target_type="knowledge_page",target_id=page.pk,status="published",revision__gte=saved.revision).exists()
            key = item["payload"].get("block_id")
            saved_block = next((b for b in saved.materialized_preview.get("body_blocks",[]) if b.get("id") == key),None)
            public_block = next((b for b in page.body_blocks if b.get("id") == key),None)
            same = saved_block == public_block
            if item["payload"].get("operation") == "metadata":
                same = all(saved.materialized_preview.get(k) == getattr(page, k) for k in ("title", "scope"))
            item["current_status"] = "published" if published and page.status == "published" and same else "draft"
        if item["kind"] == "wiki_patch" and item["payload"].get("page_id"):
            page = get_object_or_404(m.KnowledgePage, pk=item["payload"]["page_id"])
            blocks, revision = page_content(page)
            from catalog.services.knowledge_core import page_metadata
            current = page_metadata(page, draft=True) if item["payload"].get("operation") == "metadata" else next((b for b in blocks if b["id"] == item["payload"].get("block_id")), None)
            item["current"] = {"block": current, "hash": digest(current) if current else None,
                "revision_id": str(revision.pk) if revision else None}
    accepted = [i for i in items if i["decision"] == "accepted"]
    status = "published" if accepted and all(i.get("current_status") == "published" for i in accepted) and all(i["decision"] in {"accepted", "rejected"} for i in items) else changeset.status
    revision = changeset.document_revision
    work = revision.asset.edition.work if revision else changeset.subject_work
    return {"id": str(changeset.pk), "version": changeset.version, "status": status,
        "document_revision_id": str(revision.pk) if revision else None, "origin": changeset.origin, "items": items,
        "title": work.title if work else changeset.subject_entity.label if changeset.subject_entity_id else changeset.subject_page.title,
        "page_id": str(changeset.subject_page_id) if changeset.subject_page_id else None,
        "edition_id": str(revision.asset.edition_id) if revision else None,
        "work_id": str(work.pk) if work else None, "entity_id": str(changeset.subject_entity_id) if changeset.subject_entity_id else None,
        "asset_id": str(revision.asset_id) if revision else None, "pages": revision.asset.page_count if revision else 0,
        "review_url": f"/admin/intelligence?changeset={changeset.pk}"}


def sources(actor, *, work_id=None):
    require_editor(actor)
    rows = m.DocumentRevision.objects.filter(is_active=True).select_related("asset__edition__work").order_by("-created_at")
    if work_id:
        rows = rows.filter(asset__edition__work_id=work_id)
    return [{"revision_id": str(r.pk), "asset_id": str(r.asset_id), "edition_id": str(r.asset.edition_id),
        "work_id": str(r.asset.edition.work_id), "title": r.asset.edition.work.title,
        "pages": r.asset.page_count, "revision_number": r.revision, "text_checksum": r.text_checksum} for r in rows[:200]]
