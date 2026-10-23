"""Protected recovery views over the existing reversible deletion ledger."""
from hashlib import sha256
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import CharField, F, OuterRef, Subquery, UUIDField, Value
from django.db.models.functions import Cast, Coalesce, Replace
from rest_framework.exceptions import APIException, NotFound, PermissionDenied

from accounts.models import User
from common.capabilities import Capability, has_capability
from common.recycle import RECYCLE_MODELS
from ingestion.models import AuditEvent
from .models import RecycleEntry
from .lifecycle_views import LIFECYCLE_MODELS, CANONICAL_OBJECT_TYPES, _name
from .services.query_lexicon.mutations import acquire_entity_lock
from .services.recycle import require_editor, restore_object, restore_archived_object

LABELS = {"upload":"上传记录","work":"作品","edition":"出版版本","person":"人物","scholar":"学者页面","topic":"主题","knowledge-node":"理论与概念","theory-school":"理论流派","discipline":"学科","subdiscipline":"子学科","reading-path":"阅读路径","timeline-event":"时间线事件","knowledge-relation":"知识关系","evidence-curation":"证据编排","scholar-relation":"学者关系","recommendation-issue":"特别策划","recommendation-item":"策划材料","about-block":"网站内容","publisher":"出版机构"}
DESTINATIONS = {"upload":"/admin/review","work":"/admin/library","edition":"/admin/library","person":"/admin/scholars/people","scholar":"/admin/scholars","topic":"/admin/topics","knowledge-node":"/admin/theories","theory-school":"/admin/theories","discipline":"/admin/theories","subdiscipline":"/admin/theories","reading-path":"/admin/reading-paths","timeline-event":"/admin/theories/timeline","knowledge-relation":"/admin/theories","evidence-curation":"/admin/theories","scholar-relation":"/admin/scholars","recommendation-issue":"/admin/recommendations","recommendation-item":"/admin/recommendations","about-block":"/admin/about","publisher":"/admin/library"}
OUTPUT_FIELDS = ("object_id", "kind", "title", "changed_at", "entry_id", "record_state", "actor_name")
FIELDS = tuple("recovery_" + field for field in OUTPUT_FIELDS)


class RecoveryConflict(APIException):
    status_code = 409
    default_detail = "对象或关联状态已变化，请重新预览恢复影响。"


def collection_queries(*, search="", kind="", state="", since=None):
    entries = RecycleEntry.objects.filter(model_label__in=RECYCLE_MODELS).order_by()
    if search:
        entries = entries.filter(name__icontains=search)
    if kind:
        entries = entries.filter(kind=kind)
    if since:
        entries = entries.filter(updated_at__gte=since)
    queries = []
    for restored, name in ((False, "deleted"), (True, "restored")):
        if state and state != name:
            continue
        selected=entries.filter(restored_at__isnull=not restored)
        if restored:
            for config in LIFECYCLE_MODELS.values():
                if config.status_field:
                    selected=selected.exclude(model_label=config.model._meta.label_lower,object_id__in=config.model.objects.filter(**{config.status_field:config.archived_value}).values("pk"))
        restore_actor=AuditEvent.objects.annotate(normalized_object=Replace(F("object_id"),Value("-"),Value(""))).filter(action="record.restore",
            object_type=OuterRef("model_label"),normalized_object=Replace(Cast(OuterRef("object_id"),output_field=CharField()),Value("-"),Value(""))).order_by("-created_at","-id").values("actor__display_name")[:1]
        actor=Subquery(restore_actor) if restored else F("deleted_by__display_name")
        queries.append(selected.annotate(recovery_object_id=F("object_id"),recovery_kind=F("kind"),recovery_title=F("name"),recovery_changed_at=F("updated_at"),recovery_entry_id=F("pk"),
            recovery_record_state=Value(name,output_field=CharField()),recovery_actor_name=Coalesce(actor,Value("未记录"))).values(*FIELDS))
    if state in ("", "archived"):
        for key, config in LIFECYCLE_MODELS.items():
            if not config.status_field or kind and key != kind:
                continue
            query = config.model.objects.filter(**{config.status_field:config.archived_value}).order_by()
            # A previously restored record is shown in the current archived group only.
            if search:
                query = query.filter(**{config.name_field + "__icontains":search})
            if since:
                query = query.filter(updated_at__gte=since)
            queries.append(query.annotate(recovery_object_id=F("pk"),recovery_kind=Value(key,output_field=CharField()),recovery_title=Cast(F(config.name_field),output_field=CharField()),
                recovery_changed_at=F("updated_at"),recovery_entry_id=Value(None,output_field=UUIDField()),recovery_record_state=Value("archived",output_field=CharField()),
                recovery_actor_name=Value("详见变更历史",output_field=CharField())).values(*FIELDS))
    return queries


def collection_query(**filters):
    queries = collection_queries(**filters)
    if not queries:
        return RecycleEntry.objects.none().values("object_id")
    return queries[0].union(*queries[1:], all=True).order_by("-recovery_changed_at", "recovery_object_id", "recovery_kind")


def row_payload(row):
    row={field:row["recovery_"+field] for field in OUTPUT_FIELDS}
    return {**row, "object_id":str(row["object_id"]), "entry_id":str(row["entry_id"]) if row["entry_id"] else None,
        "label":LABELS.get(row["kind"], "管理内容"), "destination":DESTINATIONS.get(row["kind"], "/admin")}


def directory(*, search="", kind="", state="", since=None, page=1):
    filters={"search":search,"kind":kind,"since":since}
    query=collection_query(**filters,state=state)
    counts={name:collection_query(**filters,state=name).count() for name in ("deleted","archived","restored")}
    return {"count":query.count(),"page":page,"page_size":20,"counts":counts,
        "results":[row_payload(row) for row in query[(page-1)*20:page*20]],
        "kinds":[{"id":key,"label":label} for key,label in LABELS.items()],
        "notice":"回收与归档保留原对象身份及文件。恢复后不自动发布，也不重启处理；其他变更栏显示回收恢复记录。"}


def object_and_entry(kind, identifier, *, lock=False):
    config=LIFECYCLE_MODELS.get(kind)
    if not config or config.model._meta.label_lower not in RECYCLE_MODELS:
        raise NotFound("不支持的恢复对象。")
    query=config.model.all_objects
    if lock:
        query=query.select_for_update()
    obj=query.filter(pk=identifier).first()
    entry_query=RecycleEntry.objects.filter(model_label=config.model._meta.label_lower,object_id=identifier)
    if lock:
        entry_query=entry_query.select_for_update()
    entry=entry_query.first()
    if obj is None and entry is None:
        raise NotFound("未找到此对象或回收记录。")
    return config,obj,entry


def dependency_rows(obj):
    """Only catalog objects; never traverse reader notes, lists or usage records."""
    rows, total = [], 0
    model_kinds={value.model._meta.label_lower:key for key,value in LIFECYCLE_MODELS.items()}
    for relation in obj._meta.related_objects:
        label=relation.related_model._meta.label_lower
        if label not in model_kinds or not relation.get_accessor_name():
            continue
        query=relation.related_model.all_objects.filter(**{relation.field.name:obj}).order_by("pk")
        count=query.count();total+=count
        room=min(10,50-len(rows))
        if room<=0:
            continue
        for other in query[:room]:
            key=model_kinds[label];config=LIFECYCLE_MODELS[key]
            deleted=RecycleEntry.objects.filter(model_label=label,object_id=other.pk,restored_at__isnull=True).exists()
            rows.append({"kind":key,"object_id":str(other.pk),"name":_name(other,config.name_field),"label":LABELS[key],
                "state":"deleted" if deleted else "retained","blocking":False,"destination":DESTINATIONS[key],
                "detail":"需单独恢复；不会随本对象恢复。" if deleted else "原关联保留，不改变该对象的发布状态。"})
    # Forward parents determine whether a restored row can return to its list.
    for field in obj._meta.fields:
        if not field.is_relation or not field.related_model or field.related_model._meta.label_lower not in model_kinds:
            continue
        identifier=getattr(obj,field.attname)
        if not identifier:
            continue
        deleted=RecycleEntry.objects.filter(model_label=field.related_model._meta.label_lower,object_id=identifier,restored_at__isnull=True).first()
        if deleted:
            total+=1
            key=model_kinds[field.related_model._meta.label_lower]
            blocking=(obj._meta.label_lower,field.name) in {("catalog.edition","work"),("catalog.scholarprofile","person"),("catalog.recommendationissueitem","issue")}
            rows.append({"kind":key,"object_id":str(identifier),"name":deleted.name,"label":LABELS[key],"state":"deleted",
                "blocking":blocking,"destination":DESTINATIONS[key],"detail":"必须先恢复所属对象。" if blocking else "关联对象仍在回收站，需单独处理。"})
    return rows,total


def detail(kind, identifier, actor, *, locked=None):
    config,obj,entry=locked or object_and_entry(kind,identifier)
    deleted=bool(entry and entry.restored_at is None)
    archived=bool(obj and config.status_field and getattr(obj,config.status_field)==config.archived_value)
    state="deleted" if deleted else "archived" if archived else "restored"
    deps,total=dependency_rows(obj) if obj else ([],0)
    blockers=[row["detail"] for row in deps if row["blocking"]]
    if obj is None:
        blockers.append("原数据库对象缺失，不能从回收标记重建。请核对备份与历史。")
    if kind=="theory-school":
        blockers.append("旧理论流派处于迁移兼容期，须先完成规范映射。")
    if obj and kind=="recommendation-item" and (obj.issue.active_revision_id or obj.issue.scheduled_revision_id):
        blockers.append("所属策划仍公开或有排期，请先在原策划编辑中处理引用，避免恢复后直接重现公开材料。")
    if obj and kind=="person" and obj.authority_status=="merged":
        blockers.append("已归并人物必须从原归并历史处理，不能通过回收恢复解除身份归并。")
    if obj and kind=="topic" and (obj.curation or {}).get("topic_merge"):
        blockers.append("已归并主题须从原归并记录处理。")
    required=Capability.EDIT_METADATA if deleted else Capability.PUBLISH_AUTHORITY
    can_restore=bool(obj and (deleted or archived) and not blockers and has_capability(actor,required))
    label=config.model._meta.label_lower
    history=AuditEvent.objects.filter(object_id=str(identifier),object_type__in=[label,config.model._meta.label,kind,CANONICAL_OBJECT_TYPES.get(kind,kind)]).select_related("actor").order_by("-created_at","-id")[:30]
    changes=[{"id":str(event.pk),"at":event.created_at,"action":event.action,
        "actor":event.actor.display_name if event.actor else "系统或未记录", "detail":{"record.recycle":"移入回收站，文件和原关联保留。","record.restore":"恢复到管理列表，未自动公开。","entity_archive":"已归档或撤下公开展示。","entity_restore":"恢复为草稿。","recovery.confirmed":"按预览确认恢复，保留原身份。"}.get(event.action,"原对象变更记录，详情沿原编辑历史查看。")} for event in history]
    title=_name(obj,config.name_field) if obj else entry.name
    before=entry.before if entry and isinstance(entry.before,dict) else {}
    version=sha256(json.dumps({"kind":kind,"id":identifier,"object_updated":obj.updated_at if obj else None,
        "entry_updated":entry.updated_at if entry else None,"state":state,"dependencies":deps,"total":total,"blockers":blockers},cls=DjangoJSONEncoder,sort_keys=True).encode()).hexdigest()
    cover=""
    work=obj if kind=="work" else obj.work if obj and kind=="edition" else None
    if work and work.cover:
        cover=work.cover.url
    return {"kind":kind,"object_id":str(identifier),"entry_id":str(entry.pk) if entry else None,"title":title,"label":LABELS[kind],
        "record_state":state,"version":version,"destination":DESTINATIONS[kind],"cover_url":cover,
        "created_at":obj.created_at if obj else None,"updated_at":obj.updated_at if obj else None,
        "changed_at":entry.updated_at if entry and not archived else obj.updated_at,"operator":entry.deleted_by.display_name if deleted and entry.deleted_by else "详见变更历史",
        "reason":str(before.get("_recycle_reason") or "原记录未保存操作原因"),"dependencies":deps,"dependency_count":total,
        "dependencies_limited":total>len(deps),"history":changes,"blockers":blockers,"can_restore":can_restore,
        "notice":"恢复原对象和保留的关联，保持未发布；不自动恢复其他已删除对象，不覆盖同名内容，不重启任务。"}


@transaction.atomic
def confirm_restore(request, values):
    if request.headers.get("X-Editor-Owner")!=str(request.user.pk):
        raise PermissionDenied("请重新读取当前管理账户。")
    actor=User.objects.select_for_update().filter(pk=request.user.pk,is_active=True).first()
    if not actor or actor.token_version!=request.user.token_version:
        raise PermissionDenied("账户会话已经变化。")
    require_editor(actor)
    identifier=values["request_id"]
    acquire_entity_lock("recovery_command",identifier)
    receipt=AuditEvent.objects.filter(action="recovery.confirmed",request_id=str(identifier)).first()
    fingerprint=sha256(json.dumps(values,cls=DjangoJSONEncoder,sort_keys=True).encode()).hexdigest()
    if receipt:
        if receipt.actor_id!=actor.pk or receipt.after.get("fingerprint")!=fingerprint:
            raise RecoveryConflict("该请求编号对应其他恢复操作。")
        return receipt.after["result"]
    locked=object_and_entry(values["kind"],values["object_id"],lock=True)
    preview=detail(values["kind"],values["object_id"],actor,locked=locked)
    if preview["version"]!=values["expected_version"]:
        raise RecoveryConflict()
    if not preview["can_restore"]:
        raise RecoveryConflict("；".join(preview["blockers"]) or "当前账户或对象状态不允许恢复。")
    _,obj,entry=locked
    if preview["record_state"]=="deleted":
        restore_object(entry.pk,actor=actor)
    else:
        restore_archived_object(values["kind"],obj,actor=actor)
    result={"request_id":str(identifier),"kind":values["kind"],"object_id":str(obj.pk),"restored":True,"public_restored":False,
        "destination":preview["destination"],"detail":"已恢复到原管理列表，未重新发布或启动处理。此回执记录本次操作，请刷新核对后续变更。"}
    AuditEvent.objects.create(actor=actor,action="recovery.confirmed",object_type=obj._meta.label_lower,object_id=str(obj.pk),request_id=str(identifier),after={"fingerprint":fingerprint,"result":result})
    return result
