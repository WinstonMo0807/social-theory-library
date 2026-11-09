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
        "scope": run.scope, "status": run.status, "stage": run.stage, "coverage": run.coverage,
        "profile_key": run.profile_key, "model_identity": run.model_identity, "error": run.error,
        "version": run.version, "created_at": run.created_at, "finished_at": run.finished_at}
    if detail:
        data["artifacts"] = list(run.artifacts.values("id", "stage", "unit", "status", "output", "usage", "elapsed_ms", "error", "input_manifest"))
        changeset = m.ChangeSet.objects.filter(run=run).first()
        data["changeset"] = changeset_data(changeset, actor) if changeset else None
    return data


def changeset_data(changeset, actor):
    require_editor(actor)
    require_revision_access(changeset.document_revision, actor, editorial=True)
    items = list(changeset.items.values("id", "kind", "payload", "dependencies", "decision", "decision_note", "application", "conflict", "reviewed_at"))
    for item in items:
        if item["kind"] == "wiki_patch" and item["payload"].get("page_id"):
            page = get_object_or_404(m.KnowledgePage, pk=item["payload"]["page_id"])
            blocks, revision = page_content(page)
            current = next((b for b in blocks if b["id"] == item["payload"].get("block_id")), None)
            item["current"] = {"block": current, "hash": digest(current) if current else None,
                "revision_id": str(revision.pk) if revision else None}
    return {"id": str(changeset.pk), "version": changeset.version, "status": changeset.status,
        "document_revision_id": str(changeset.document_revision_id), "origin": changeset.origin, "items": items}


def sources(actor, *, work_id=None):
    require_editor(actor)
    rows = m.DocumentRevision.objects.filter(is_active=True).select_related("asset__edition__work").order_by("-created_at")
    if work_id:
        rows = rows.filter(asset__edition__work_id=work_id)
    return [{"revision_id": str(r.pk), "asset_id": str(r.asset_id), "edition_id": str(r.asset.edition_id),
        "work_id": str(r.asset.edition.work_id), "title": r.asset.edition.work.title,
        "pages": r.asset.page_count, "revision_number": r.revision, "text_checksum": r.text_checksum} for r in rows[:200]]
