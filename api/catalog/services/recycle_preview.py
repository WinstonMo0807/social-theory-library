"""Protected, read-only restoration previews reuse the public serializers."""
from copy import copy

from django.apps import apps
from django.shortcuts import get_object_or_404

from catalog.models import Edition, EditorialRevision, Work
from catalog.services.recycle import require_editor, restore_blocker


def recycle_entry_data(entry):
    return {"id": str(entry.pk), "kind": entry.kind, "object_id": str(entry.object_id),
            "name": entry.name, "deleted_at": entry.updated_at.isoformat(),
            "reason": str((entry.before or {}).get("delete_reason") or "")}


def recycle_preview_payload(entry, *, actor, request):
    require_editor(actor)
    model = apps.get_model(entry.model_label)
    obj = get_object_or_404(model.all_objects, pk=entry.object_id)
    blocker = restore_blocker(obj)
    result = {"entry": recycle_entry_data(entry), "can_restore": not bool(blocker), "blocked_reason": blocker,
              "preview_kind": "record", "preview": {},
              "detail": "仅管理员可见。恢复后仍需在编辑区检查和发布，不自动公开或启动任务。"}
    edition = None
    if isinstance(obj, Work):
        edition = Edition.all_objects.filter(work_id=obj.pk).order_by("-is_primary", "-created_at", "pk").first()
    elif isinstance(obj, Edition):
        edition = obj
    elif entry.model_label == "ingestion.uploaditem" and obj.edition_id:
        edition = Edition.all_objects.filter(pk=obj.edition_id).first()
    if edition is not None:
        from catalog.serializers import AdminWorkPagePreviewSerializer
        from catalog.services.publication_commands import editorial_draft_applies_to_edition
        revision = EditorialRevision.objects.filter(target_type="work", target_id=edition.work_id, status="draft").order_by("-revision").first()
        if not editorial_draft_applies_to_edition(revision, edition):
            revision = None
        work = Work.all_objects.get(pk=edition.work_id)
        value = AdminWorkPagePreviewSerializer(work, context={
            "request": request, "preview_edition": edition,
            "editorial_preview": revision.materialized_preview if revision else None,
        }).data
        # A retained legacy cover must not re-enter the ordinary Work.objects
        # endpoint, which correctly excludes recycled works. Keep its bytes
        # behind this active Entry and the existing editor capability instead.
        if not value.get("cover_media") and value.get("cover"):
            value["cover"] = f"/api/catalog/admin/recycle/{entry.pk}/image/"
        result.update(preview_kind="work", preview={"work": value})
        return result
    if entry.model_label == "catalog.recommendationissue":
        from catalog.services.editorial_issues import issue_payload
        result.update(preview_kind="issue", preview=issue_payload(obj))
        return result
    object_type = {"catalog.scholarprofile": "scholar", "catalog.topic": "topic", "catalog.discipline": "discipline",
                   "catalog.subdiscipline": "subdiscipline", "catalog.readingpath": "reading_path"}.get(entry.model_label)
    if entry.model_label == "catalog.knowledgenode":
        from catalog.services.knowledge_studio import NODE_OBJECT_TYPES
        object_type = next((key for key, value in NODE_OBJECT_TYPES.items() if value == obj.node_type), None)
    if object_type:
        from catalog.services.knowledge_studio import KnowledgeObjectEditorAdapter
        target = copy(obj)
        for field in ("editorial_status", "status"):
            if hasattr(target, field):
                setattr(target, field, "draft")
        selection = KnowledgeObjectEditorAdapter.enrich(object_type=object_type, target=target, selection={
            "object_type": object_type, "id": str(obj.pk), "label": entry.name, "status": "draft",
            "preview_url": "", "editor_url": "",
        })
        perspectives = selection["preview_perspectives"]
        draft = perspectives["draft"]
        result.update(preview_kind="knowledge", preview={
            "preview_mode": True, "protected": True, "object_type": object_type, "object_id": str(obj.pk),
            "label": entry.name, "status": "draft", "active_perspective": "draft", "source": draft["source"],
            "perspective": draft, "perspectives": perspectives, "preview_routes": {},
            "content_completeness": selection.get("content_completeness", {}),
        })
        return result
    # Internal records without a public page keep their actual metadata visible.
    # They are never replaced with a mock reader page or an invented public URL.
    result["preview"] = {"name": entry.name, "kind": entry.kind, "before": entry.before,
                         "message": "这类管理记录没有独立读者页面。恢复后可回到相应管理列表继续检查。"}
    return result
