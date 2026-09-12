"""Combine pending edits without creating another editorial revision system."""
from copy import deepcopy
from uuid import uuid4

from django.db import transaction

from catalog.models import CanonicalObjectRevision, EditorialRevision, KnowledgeNode, ReadingPath, ScholarProfile

MODELS = {"scholar_profile": ScholarProfile, "knowledge_node": KnowledgeNode, "reading_path": ReadingPath}


@transaction.atomic
def save_object_editorial_patch(target_type, target_id, patch, *, actor, change_note="更新编辑草稿", request_key=""):
    from catalog.services.editorial_revision import EditorialRevisionConflict, changed_editorial_patch, create_editorial_revision

    model = MODELS.get(target_type)
    if model is None:
        raise EditorialRevisionConflict("此对象不支持组合编辑草稿。")
    queryset = model.objects.select_for_update()
    if target_type == "scholar_profile":
        queryset = queryset.select_related("person")
    target = queryset.get(pk=target_id)
    canonical, _ = CanonicalObjectRevision.objects.select_for_update().get_or_create(object_type=target_type, object_id=target.pk, defaults={"current_revision": 0})
    drafts = list(EditorialRevision.objects.select_for_update().filter(target_type=target_type, target_id=target.pk, status="draft").order_by("revision"))
    if any(row.base_revision != canonical.current_revision for row in drafts):
        raise EditorialRevisionConflict("正式资料已变化，请先处理旧草稿。")
    combined = {}
    for section in [*(row.patch for row in drafts), patch]:
        for field, value in section.items():
            combined[field] = {**combined.get(field, {}), **deepcopy(value)} if target_type == "scholar_profile" and field == "person" else deepcopy(value)
    clean = changed_editorial_patch(target_type=target_type, target=target, patch=combined)
    if not clean:
        for row in drafts:
            row.status = "superseded"
            row.save(update_fields=["status", "updated_at"])
        return None
    if drafts and drafts[-1].patch == clean:
        return drafts[-1]
    revision = create_editorial_revision(target_type=target_type, target_id=target.pk, patch=clean, actor=actor,
                                         idempotency_key=request_key or f"object-edit:{uuid4()}", change_note=change_note)
    if revision.status != "draft":
        raise EditorialRevisionConflict("该请求对应的草稿已经结束，请重新核对。")
    for row in drafts:
        if row.pk != revision.pk:
            row.status = "superseded"
            row.save(update_fields=["status", "updated_at"])
    return revision
