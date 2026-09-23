"""Reversible deletion commands. Never remove files or cascade through citations."""
from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from common.capabilities import Capability, has_capability
from common.recycle import RECYCLE_MODELS
from catalog.models import RecycleEntry, Edition, Work, Person, ScholarProfile
from ingestion.models import AuditEvent, UploadItem, ProcessingJob


def require_editor(actor):
    if not has_capability(actor, Capability.EDIT_METADATA):
        raise PermissionDenied("当前账号没有管理删除与恢复的权限。")


@transaction.atomic
def recycle_object(obj, *, actor, kind, name):
    require_editor(actor)
    label = obj._meta.label_lower
    if label not in RECYCLE_MODELS:
        raise ValidationError("该对象不支持移入回收站。")
    obj = type(obj).all_objects.select_for_update().get(pk=obj.pk)
    entry = RecycleEntry.objects.filter(model_label=label, object_id=obj.pk).first()
    if entry and entry.restored_at is None:
        return entry
    if isinstance(obj, Person) and obj.authority_status == "merged":
        raise ValidationError("此人物已合并，请从合并历史处理，不能删除来源身份。")
    if label == "catalog.topic" and (obj.curation or {}).get("topic_merge"):
        raise ValidationError("此主题已合并，请保留来源记录供审计。")
    if isinstance(obj, Person) and obj.contributions.exists():
        raise ValidationError("此人物仍作为馆藏作者或译者使用。请先合并或替换这些关联；删除学者展示资料不需要删除人物身份。")

    before = {field: str(getattr(obj, field) or "") for field in ("status", "state", "editorial_status", "review_status", "authority_status", "workflow_state", "error_code", "error_message", "active_revision_id", "scheduled_revision_id", "visible") if hasattr(obj, field)}
    if label == "catalog.recommendationissueitem":
        from catalog.models import RecommendationIssue
        parent_issue = RecommendationIssue.all_objects.select_for_update().get(pk=obj.issue_id)
        before["parent_public_revision"] = str(parent_issue.active_revision_id or "")
        before["parent_scheduled_revision"] = str(parent_issue.scheduled_revision_id or "")
        if parent_issue.active_revision_id or parent_issue.scheduled_revision_id:
            if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
                raise PermissionDenied("删除公开或排期推荐还需要发布管理权限。")
        if parent_issue.scheduled_revision_id:
            parent_issue.scheduled_revision = None
            parent_issue.scheduled_for = None
            parent_issue.save(update_fields=["scheduled_revision", "scheduled_for", "updated_at"])
    editions = [obj] if isinstance(obj, Edition) else list(Edition.objects.filter(work=obj)) if isinstance(obj, Work) else []
    if any(edition.state == "published" for edition in editions):
        if not has_capability(actor, Capability.WITHDRAW_WORK):
            raise PermissionDenied("删除公开馆藏还需要下架权限。")
        from catalog.services.publication_commands import withdraw_revision
        for edition in editions:
            if edition.state == "published":
                withdraw_revision(edition, actor=actor, reason="管理员下架并移入回收站")

    # Existing publication commands close canonical projections and retain revisions.
    from catalog.lifecycle_views import LIFECYCLE_MODELS, EDITORIAL_LIFECYCLE_TARGETS, _draft_public_withdrawal
    config = LIFECYCLE_MODELS.get(kind)
    if config and getattr(obj, config.status_field, None) == config.published_value:
        if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
            raise PermissionDenied("删除公开知识条目还需要发布管理权限。")
        if kind in EDITORIAL_LIFECYCLE_TARGETS:
            from types import SimpleNamespace
            from catalog.services.editorial_revision import publish_editorial_revision
            revision = _draft_public_withdrawal(request=SimpleNamespace(user=actor, headers={}), kind=kind, obj=obj, config=config)
            publish_editorial_revision(revision.pk, actor=actor)
            obj.refresh_from_db()
        else:
            setattr(obj, config.status_field, config.archived_value)
            obj.save(update_fields=[config.status_field, "updated_at"])

    if isinstance(obj, UploadItem):
        # Removing an intake receipt never withdraws an existing published holding.
        obj.status, obj.workflow_state, obj.processing_token = "deleted", "archived", ""
        obj.save(update_fields=["status", "workflow_state", "processing_token", "updated_at"])
        ProcessingJob.objects.filter(upload_item=obj, status__in=["pending", "running", "paused"]).update(
            status="canceled", task_id="", finished_at=timezone.now(), updated_at=timezone.now(), error_code="record_recycled")
    # These public projections have no general publication state field. Retain
    # their revisions, but never reactivate them just by restoring the record.
    if label in {"catalog.evidencecuration", "catalog.scholarrelation", "catalog.recommendationissue", "catalog.aboutpageblock"}:
        if getattr(obj, "active_revision_id", None) or getattr(obj, "visible", False):
            if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
                raise PermissionDenied("删除公开内容还需要发布管理权限。")
        changed = []
        for field in ("active_revision", "scheduled_revision", "scheduled_for", "published_at"):
            if hasattr(obj, field):
                setattr(obj, field, None)
                changed.append(field)
        if hasattr(obj, "visible"):
            obj.visible = False
            changed.append("visible")
        if hasattr(obj, "status"):
            obj.status = "draft"
            changed.append("status")
        if changed:
            obj.save(update_fields=[*changed, "updated_at"])
    if isinstance(obj, (Work, Edition)):
        ids = [edition.pk for edition in editions]
        ProcessingJob.objects.filter(edition_id__in=ids, status__in=["pending", "running", "paused"]).update(
            status="canceled", task_id="", finished_at=timezone.now(), updated_at=timezone.now(), error_code="record_recycled")
    defaults = {"kind": kind, "name": name[:600], "before": before, "deleted_by": actor, "restored_at": None}
    entry, _ = RecycleEntry.objects.update_or_create(model_label=label, object_id=obj.pk, defaults=defaults)
    AuditEvent.objects.create(actor=actor, action="record.recycle", object_type=label, object_id=str(obj.pk), before=before,
                              after={"recycle_id": str(entry.pk), "files_preserved": True, "references_preserved": True})
    if isinstance(obj, UploadItem):
        AuditEvent.objects.create(actor=actor, action="upload_item_delete", object_type="ingestion.UploadItem", object_id=str(obj.pk), before=before,
                                  after={"recycle_id": str(entry.pk), "linked_publication_preserved": True, "files_preserved": True})
    from catalog.discovery_signals import _wake
    if getattr(settings, "DISCOVERY_ENABLED", False):
        transaction.on_commit(_wake)
    return entry


@transaction.atomic
def restore_object(entry_id, *, actor):
    require_editor(actor)
    entry = RecycleEntry.objects.select_for_update().get(pk=entry_id)
    model = apps.get_model(entry.model_label)
    obj = model.all_objects.select_for_update().get(pk=entry.object_id)
    if entry.restored_at:
        return obj
    parent = getattr(obj, "work_id", None) if isinstance(obj, Edition) else getattr(obj, "person_id", None) if isinstance(obj, ScholarProfile) else None
    if parent and RecycleEntry.objects.filter(object_id=parent, restored_at__isnull=True).exists():
        raise ValidationError("请先恢复所属作品或人物，再恢复本条记录。")
    entry.restored_at = timezone.now()
    entry.save(update_fields=["restored_at", "updated_at"])
    fields = []
    for field in ("editorial_status", "status", "state"):
        if hasattr(obj, field) and getattr(obj, field) in ("published", "archived", "withdrawn", "deleted"):
            setattr(obj, field, "draft")
            fields.append(field)
    if isinstance(obj, UploadItem):
        obj.status = "failed" if entry.before.get("status") == "failed" else "needs_review"
        obj.workflow_state = "failed" if obj.status == "failed" else "needs_review"
        fields = ["status", "workflow_state"]
    if entry.model_label == "catalog.theorytimelineevent" and obj.review_status == "rejected":
        obj.review_status = "suggested"
        fields.append("review_status")
    # Restoration does not resume tasks or activate any old public revision.
    if fields:
        obj.save(update_fields=[*fields, "updated_at"])
    AuditEvent.objects.create(actor=actor, action="record.restore", object_type=entry.model_label, object_id=str(obj.pk), after={"public_restored": False})
    return obj
