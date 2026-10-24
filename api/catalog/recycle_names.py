"""Explicit recovery renames through the original editorial revision service."""
from hashlib import sha256
import json

from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import ValidationError

from common.capabilities import has_capability
from ingestion.models import AuditEvent, FieldLock
from .models import CanonicalObjectRevision, EditorialRevision, Edition
from .lifecycle_views import LIFECYCLE_MODELS, _name


# Only names owned by this object. A version title belongs to its Work and a
# scholar's name to Person; never silently rename those shared identities here.
TARGETS = {"work":"work", "topic":"topic", "knowledge-node":"knowledge_node",
    "reading-path":"reading_path", "discipline":"discipline", "subdiscipline":"subdiscipline",
    "timeline-event":"timeline_event"}


def rename_info(kind, obj, actor, *, restoring=False):
    result={"allowed":False,"reason":"此名称属于共享身份或专用编辑流程，请从原管理入口处理。",
        "max_length":0,"suggested_name":"","version":"","public_count":0}
    target=TARGETS.get(kind)
    if not target or obj is None:return result
    from .editorial_revision_views import EDIT_CAPABILITY, PUBLISH_CAPABILITY
    config=LIFECYCLE_MODELS[kind]
    field=obj._meta.get_field(config.name_field)
    maximum=field.max_length or 600
    name=_name(obj,config.name_field)
    suffix="（历史版本）" if restoring else "（现有内容）"
    canonical=CanonicalObjectRevision.objects.filter(object_type=target,object_id=obj.pk).values_list("current_revision",flat=True).first() or 0
    drafts=list(EditorialRevision.objects.filter(target_type=target,target_id=obj.pk,status="draft").order_by("pk").values_list("pk","updated_at")[:2])
    public_count=Edition.all_objects.filter(work_id=obj.pk,state="published").count() if kind=="work" else int(bool(config.status_field and getattr(obj,config.status_field)==config.published_value))
    title_locked=kind=="work" and FieldLock.objects.filter(edition__work_id=obj.pk,field_name="title").exists()
    reason=""
    if not has_capability(actor,EDIT_CAPABILITY[target]) or not has_capability(actor,PUBLISH_CAPABILITY[target]):
        reason="直接应用名称需要原编辑与修订确认权限，请由有权限的管理员处理。"
    elif drafts:reason="此对象还有未处理的编辑草稿，请先在原编辑入口处理；恢复不会覆盖或作废它。"
    elif title_locked:reason="作品标题有人工作业锁，请先在原编目入口核对并明确解除保护；恢复不会覆盖锁定值。"
    elif public_count and not restoring:reason="现有内容仍公开，请先沿原入口撤下并核对影响，再在此改名，避免恢复顺带改变线上内容。"
    if kind=="timeline-event" and obj.merged_into_id:reason="此事件已归并，请从原归并历史处理。"
    if kind=="topic" and (obj.curation or {}).get("topic_merge"):reason="此主题已归并，请从原归并历史处理。"
    fingerprint={"kind":kind,"id":str(obj.pk),"name":name,"updated":obj.updated_at,"canonical":canonical,"drafts":drafts,"public_count":public_count,"title_locked":title_locked,"reason":reason}
    return {"allowed":not reason,"reason":reason,"max_length":maximum,"suggested_name":name[:maximum-len(suffix)]+suffix,
        "version":sha256(json.dumps(fingerprint,sort_keys=True,default=str).encode()).hexdigest(),"public_count":public_count}


def prepare_rename(kind, source, actor, values):
    """Validate the exact selected identity and title before any restore occurs."""
    from .recycle_related import names_query
    from .recycle_workspace import RecoveryConflict
    selected=values.get("rename")
    if not selected:return None
    if kind not in TARGETS:raise ValidationError("此对象须通过原身份编辑流程改名。")
    restoring=selected["target"]=="restored"
    if restoring:
        obj=source
        if obj.pk!=selected["object_id"]:raise RecoveryConflict("改名目标与恢复对象不一致。")
    else:
        matches=names_query(kind,source,actor)
        if matches.count()!=1:raise RecoveryConflict("替换名称需恰有一个同名对象。请重新比较，或为恢复对象使用新名称。")
        obj=matches.select_for_update().filter(pk=selected["object_id"]).first()
        if not obj:raise RecoveryConflict("选中的同名对象已变化，请重新比较。")
    info=rename_info(kind,obj,actor,restoring=restoring)
    if not info["allowed"]:raise RecoveryConflict(info["reason"])
    if info["version"]!=selected["expected_version"]:raise RecoveryConflict("改名对象或待处理草稿已变化，请重新预览。")
    config=LIFECYCLE_MODELS[kind]
    field=obj._meta.get_field(config.name_field)
    name=selected["new_name"].strip()
    if not name or name.casefold()==_name(obj,config.name_field).strip().casefold():raise ValidationError("请填写能区分原对象的新名称。")
    if any(ord(char)<32 or ord(char)==127 for char in name):raise ValidationError("名称不能包含换行或控制字符。")
    try:name=field.clean(name,obj)
    except ModelValidationError as error:raise ValidationError("；".join(error.messages)) from error
    # Check all identities, including recycled/archived ones. Do not reveal a
    # hidden object's title, count or ID to explain a collision.
    if config.model.all_objects.filter(**{config.name_field+"__iexact":name}).exclude(pk=obj.pk).exists():
        raise RecoveryConflict("此新名称已被保留记录使用，请换一个可区分的名称。")
    return obj,config.name_field,name,restoring


def apply_rename(kind, prepared, actor, identifier):
    if not prepared:return
    from .services.editorial_revision import create_editorial_revision,publish_editorial_revision,EditorialRevisionError
    from .recycle_workspace import RecoveryConflict
    obj,field,name,restoring=prepared
    obj.refresh_from_db()
    # Restore may withdraw a legacy publication. Recheck the resulting state,
    # then apply only this name through the established revision/validation path.
    info=rename_info(kind,obj,actor)
    if not info["allowed"]:raise RecoveryConflict(info["reason"])
    before=getattr(obj,field)
    try:
        revision=create_editorial_revision(target_type=TARGETS[kind],target_id=obj.pk,patch={field:name},actor=actor,
            idempotency_key=f"recovery-name:{identifier}",change_note="回收恢复：为恢复对象使用新名称" if restoring else "回收恢复：保留现有内容并改名")
        publish_editorial_revision(revision.pk,actor=actor)
    except EditorialRevisionError as error:raise RecoveryConflict(str(error)) from error
    AuditEvent.objects.create(actor=actor,action="recovery.renamed",object_type=obj._meta.label_lower,object_id=str(obj.pk),request_id=str(identifier),
        before={"name":before},after={"name":name,"editorial_revision_id":str(revision.pk),"restored_target":restoring,"public_restored":False})
