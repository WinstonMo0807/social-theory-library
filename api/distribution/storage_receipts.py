"""Durable command outcomes; looking up a receipt never resubmits a task."""
import json
from hashlib import sha256

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent
from .models import BackupJob, BackupVerification
from .storage_workspace import StorageConflict, backup_payload, verification_payload

ACTION = "storage_workspace_command"
LOCK = "backup_workspace_command"


def fingerprint(values):
    return sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def locked_actor(request):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("请重新读取当前维护账户。")
    actor = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if not actor or actor.token_version != request.user.token_version or not has_capability(actor, Capability.RUN_BACKUP):
        raise PermissionDenied("账户会话或备份维护权限已变化。")
    return actor


def receipt_payload(row):
    return {"actor_id": str(row.actor_id), "request_id": str(row.pk),
        "state": row.after["state"], "created_at": row.created_at,
        "result": row.after.get("result"), "legacy": False}


def legacy_receipt(actor, identifier, values=None):
    """Recover pre-receipt records without reapplying their commands."""
    events = list(AuditEvent.objects.filter(request_id=str(identifier)).exclude(action=ACTION)[:2])
    if len(events) > 1:
        raise StorageConflict("旧请求存在多条记录，请保留编号并核对维护日志。")
    event = events[0] if events else None
    job = BackupJob.objects.filter(pk=identifier).first()
    check = BackupVerification.objects.filter(pk=identifier).first()
    if not event and not job and not check:
        return None
    if ((event and event.actor_id != actor.pk) or (job and job.requested_by_id != actor.pk)
            or (check and check.requested_by_id != actor.pk)):
        raise StorageConflict("请求编号不属于当前维护账户。")
    after = event.after if event else {}
    operation = ""
    result = {"request_id": str(identifier)}
    valid = True
    if job and event and event.action == "storage_backup_requested" and not check:
        operation = "create_backup"
        result["backup"] = backup_payload(job)
        if values:
            base = job.manifest.get('incremental_base', {}) if isinstance(job.manifest, dict) else {}
            valid = (values.get("include_originals") == job.include_originals and str(values.get("retry_from_id") or "") == str(after.get("retry_from_id") or "")
                     and str(values.get('base_backup_id') or '') == str(job.incremental_base_id or '')
                     and (values.get('expected_base_checksum') or '') == (base.get('archive_sha256','') if isinstance(base,dict) else ''))
    elif check and not job and not event:
        operation = "verify_archive"
        result["verification"] = verification_payload(check)
        if values:
            valid = str(values.get("backup_id")) == str(check.backup_id) and values.get("expected_checksum") == check.expected_checksum
    elif event and not job and not check and event.action in {"storage_schedule_saved", "storage_backup_closed", "storage_verification_closed"}:
        operation = {"storage_schedule_saved": "save_schedule", "storage_backup_closed": "close_stalled_backup",
            "storage_verification_closed": "close_stalled_verification"}[event.action]
        if operation == "save_schedule":
            result["schedule_saved"] = True
        elif operation == "close_stalled_backup":
            target = BackupJob.objects.filter(pk=event.object_id).first()
            if not target:
                raise StorageConflict("原操作已登记，但备份记录已变化，请保留请求编号核对日志。")
            result["backup"] = backup_payload(target)
        else:
            target = BackupVerification.objects.filter(pk=event.object_id).first()
            if not target:
                raise StorageConflict("原关闭操作已登记，但校验记录已变化。")
            result["verification"] = verification_payload(target)
            if values:
                valid = str(values.get("verification_id")) == str(target.pk) and str(values.get("backup_id")) == str(target.backup_id) and values.get("expected_checksum") == target.expected_checksum
        if values and operation != "close_stalled_verification":
            valid = after.get("fingerprint") == fingerprint(values)
    else:
        raise StorageConflict("请求编号已有其他记录，不能作为新的存储操作执行。")
    if values and (values["operation"] != operation or not valid):
        raise StorageConflict("原请求编号对应的操作或范围不同，请先查回原结果。")
    result["operation"] = operation
    return {"actor_id": str(actor.pk), "request_id": str(identifier), "state": "applied",
        "created_at": (event or job or check).created_at, "result": result, "legacy": True}


def find_receipt(actor, identifier):
    row = AuditEvent.objects.filter(pk=identifier).first()
    if row:
        if row.action != ACTION or row.actor_id != actor.pk:
            raise StorageConflict("请求编号不属于当前账户的存储操作。")
        return receipt_payload(row)
    return legacy_receipt(actor, identifier)


@transaction.atomic
def execute(request, values, apply):
    actor = locked_actor(request)
    identifier = values["request_id"]
    acquire_entity_lock(LOCK, identifier)
    old = AuditEvent.objects.filter(pk=identifier).first()
    if old:
        if old.action != ACTION or old.actor_id != actor.pk:
            raise StorageConflict("请求编号已用于其他操作。")
        if old.after["state"] == "cancelled":
            raise StorageConflict("原请求已取消，迟到的操作不会执行。请读取当前记录后再决定。")
        if old.after.get("fingerprint") != fingerprint(values):
            raise StorageConflict("原请求编号对应不同的操作或范围，请查回原结果。")
        return old.after["result"]
    legacy = legacy_receipt(actor, identifier, values)
    result = legacy["result"] if legacy else apply(actor, values)
    # Persist only the same redacted response already returned to this owner.
    result = json.loads(json.dumps(result, cls=DjangoJSONEncoder))
    AuditEvent.objects.create(pk=identifier, actor=actor, action=ACTION, object_type="StorageCommand", object_id="",
        request_id=str(identifier), after={"state": "applied", "fingerprint": fingerprint(values), "result": result})
    return result


@transaction.atomic
def lookup(request, identifier, *, cancel=False):
    actor = locked_actor(request)
    acquire_entity_lock(LOCK, identifier)
    if cancel and request.data != {"action": "cancel_pending"}:
        raise ValidationError("只接受取消尚未登记的请求。")
    receipt = find_receipt(actor, identifier)
    if receipt:
        return receipt
    if not cancel:
        raise NotFound("尚未查到已登记的结果；请求仍可能在途。查询不会重新提交，请稍后查回或取消未执行请求。")
    row = AuditEvent.objects.create(pk=identifier, actor=actor, action=ACTION, object_type="StorageCommand", object_id="",
        request_id=str(identifier), after={"state": "cancelled", "fingerprint": "", "result": None})
    return receipt_payload(row)
