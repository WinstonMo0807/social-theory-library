"""Protected recovery views over the existing reversible deletion ledger."""
from hashlib import sha256
import json
from pathlib import Path

from django.core.exceptions import SuspiciousFileOperation
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import CharField, F, OuterRef, Subquery, UUIDField, Value, Q
from django.db.models.functions import Cast, Coalesce, Replace
from django.db.models.fields.json import KeyTextTransform
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from accounts.models import User
from common.capabilities import Capability, has_capability
from common.recycle import RECYCLE_MODELS
from ingestion.models import AuditEvent
from .models import Contribution, RecycleEntry
from .lifecycle_views import LIFECYCLE_MODELS, CANONICAL_OBJECT_TYPES, _name
from .services.query_lexicon.mutations import acquire_entity_lock
from .services.recycle import require_editor, restore_object, restore_archived_object

LABELS = {"upload":"上传记录","work":"作品","edition":"出版版本","person":"人物","scholar":"学者页面","topic":"主题","knowledge-node":"理论与概念","theory-school":"理论流派","discipline":"学科","subdiscipline":"子学科","reading-path":"阅读路径","timeline-event":"时间线事件","knowledge-relation":"知识关系","evidence-curation":"证据编排","scholar-relation":"学者关系","recommendation-issue":"特别策划","recommendation-item":"策划材料","about-block":"网站内容","publisher":"出版机构"}
DESTINATIONS = {"upload":"/admin/review","work":"/admin/library","edition":"/admin/library","person":"/admin/scholars/people","scholar":"/admin/scholars","topic":"/admin/topics","knowledge-node":"/admin/theories","theory-school":"/admin/theories","discipline":"/admin/theories","subdiscipline":"/admin/theories","reading-path":"/admin/reading-paths","timeline-event":"/admin/theories/timeline","knowledge-relation":"/admin/theories","evidence-curation":"/admin/theories","scholar-relation":"/admin/scholars","recommendation-issue":"/admin/recommendations","recommendation-item":"/admin/recommendations","about-block":"/admin/about","publisher":"/admin/library"}
OUTPUT_FIELDS = ("object_id", "kind", "title", "changed_at", "entry_id", "record_state", "actor_name", "actor_id", "reason")
FIELDS = tuple("recovery_" + field for field in OUTPUT_FIELDS)


class RecoveryConflict(APIException):
    status_code = 409
    default_detail = "对象或关联状态已变化，请重新预览恢复影响。"


def collection_queries(*, search="", kind="", state="", since=None, actor=None, operator="", reason=""):
    from .services.curation_projects import visible_issues, filter_related_objects
    from .models import RecommendationIssueItem
    issues = visible_issues(actor, include_recycled=True).values("pk")
    entries = RecycleEntry.objects.filter(model_label__in=RECYCLE_MODELS).filter(
        ~Q(model_label="catalog.recommendationissue") | Q(object_id__in=issues)).filter(
        ~Q(model_label="catalog.recommendationissueitem") | Q(object_id__in=RecommendationIssueItem.all_objects.filter(issue_id__in=issues).values("pk"))).order_by()
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
        restore_event=AuditEvent.objects.annotate(normalized_object=Replace(F("object_id"),Value("-"),Value(""))).filter(action="record.restore",
            object_type=OuterRef("model_label"),normalized_object=Replace(Cast(OuterRef("object_id"),output_field=CharField()),Value("-"),Value(""))).order_by("-created_at","-id")
        actor_name=Subquery(restore_event.values("actor__display_name")[:1]) if restored else F("deleted_by__display_name")
        actor_id=Subquery(restore_event.values("actor_id")[:1]) if restored else F("deleted_by_id")
        query=selected.annotate(recovery_object_id=F("object_id"),recovery_kind=F("kind"),recovery_title=F("name"),recovery_changed_at=F("updated_at"),recovery_entry_id=F("pk"),
            recovery_record_state=Value(name,output_field=CharField()),recovery_actor_name=Coalesce(actor_name,Value("未记录")),
            recovery_actor_id=Coalesce(Cast(actor_id,output_field=CharField()),Value("")),
            recovery_reason=Value("",output_field=CharField()) if restored else Coalesce(KeyTextTransform("_recycle_reason","before"),Value(""),output_field=CharField()))
        queries.append(filter_recovery_rows(query,operator,reason).values(*FIELDS))
    if state in ("", "archived"):
        for key, config in LIFECYCLE_MODELS.items():
            if not config.status_field or kind and key != kind:
                continue
            query = filter_related_objects(config.model.objects.filter(**{config.status_field:config.archived_value}),actor).order_by()
            # A previously restored record is shown in the current archived group only.
            if search:
                query = query.filter(**{config.name_field + "__icontains":search})
            if since:
                query = query.filter(updated_at__gte=since)
            archive_event=AuditEvent.objects.annotate(normalized_object=Replace(F("object_id"),Value("-"),Value(""))).filter(action="entity_archive",
                object_type__in=[config.model._meta.label,config.model._meta.label_lower,key],
                normalized_object=Replace(Cast(OuterRef("pk"),output_field=CharField()),Value("-"),Value(""))).order_by("-created_at","-id")
            query=query.annotate(recovery_object_id=F("pk"),recovery_kind=Value(key,output_field=CharField()),recovery_title=Cast(F(config.name_field),output_field=CharField()),
                recovery_changed_at=F("updated_at"),recovery_entry_id=Value(None,output_field=UUIDField()),recovery_record_state=Value("archived",output_field=CharField()),
                recovery_actor_name=Coalesce(Subquery(archive_event.values("actor__display_name")[:1]),Value("未记录")),
                recovery_actor_id=Coalesce(Cast(Subquery(archive_event.values("actor_id")[:1]),output_field=CharField()),Value("")),
                recovery_reason=Value("",output_field=CharField()))
            queries.append(filter_recovery_rows(query,operator,reason).values(*FIELDS))
    return queries


def filter_recovery_rows(query, operator, reason):
    if operator:
        query=query.filter(recovery_actor_id=operator)
    if reason:
        query=query.filter(recovery_reason__icontains=reason)
    return query


def collection_query(**filters):
    queries = collection_queries(**filters)
    if not queries:
        return RecycleEntry.objects.none().values("object_id")
    return queries[0].union(*queries[1:], all=True).order_by("-recovery_changed_at", "recovery_object_id", "recovery_kind")


def row_payload(row):
    row={field:row["recovery_"+field] for field in OUTPUT_FIELDS}
    return {**row, "object_id":str(row["object_id"]), "entry_id":str(row["entry_id"]) if row["entry_id"] else None,
        "label":LABELS.get(row["kind"], "管理内容"), "destination":DESTINATIONS.get(row["kind"], "/admin")}


def cover_url(obj, kind):
    source=obj.work if obj and kind=="edition" else obj.person if obj and kind=="scholar" else obj
    rendition=getattr(source,"cover_rendition_id",None) if kind in {"work","edition"} else getattr(source,"portrait_rendition_id",None) if kind in {"person","scholar"} else None
    if rendition: return f"/api/catalog/admin/media/renditions/{rendition}/file/"
    image=getattr(source,"cover",None) if kind in {"work","edition"} else getattr(source,"portrait",None) if kind in {"person","scholar"} else None
    return image.url if image else ""


def presentation(obj, kind):
    """Display original metadata only after the recovery object's permission check."""
    subtitle="";kind_label=LABELS[kind];description="";image=cover_url(obj,kind)
    if obj and kind in {"work","edition"}:
        work=obj.work if kind=="edition" else obj
        contributions=Contribution.objects.filter(approved=True,role__in=["author","chief_editor","editor"])
        contributions=contributions.filter(edition=obj) if kind=="edition" else contributions.filter(edition__work=work)
        names=list(dict.fromkeys(contributions.order_by("order","pk").values_list("person__preferred_name",flat=True)))
        year=obj.publication_year if kind=="edition" else work.first_publication_date.year if work.first_publication_date else None
        subtitle=" · ".join(part for part in ["、".join(names),str(year) if year else ""] if part)
        kind_label=work.get_document_type_display()
        description=work.abstract
    elif obj and kind=="recommendation-issue":
        from .services.editorial_issues import issue_draft_payload
        payload=issue_draft_payload(obj)
        rendition=payload.get("cover_rendition_id")
        image=f"/api/catalog/admin/media/renditions/{rendition}/file/" if rendition else payload.get("cover_url") or ""
        subtitle=" · ".join(str(payload.get(key) or "") for key in ("issue_label","public_byline") if payload.get(key))
        description=str(payload.get("introduction") or "")
    return {"cover_url":image,"subtitle":subtitle,"kind_label":kind_label,"description":description}


def directory(*, search="", kind="", state="", since=None, page=1, page_size=20, actor=None, operator="", reason=""):
    filters={"search":search,"kind":kind,"since":since,"actor":actor,"operator":operator,"reason":reason}
    query=collection_query(**filters,state=state)
    counts={name:collection_query(**filters,state=name).count() for name in ("deleted","archived","restored")}
    results=[row_payload(row) for row in query[(page-1)*page_size:page*page_size]]
    # Resolve images only for the current, already permission-filtered page.
    for image_kind in {row["kind"] for row in results} & {"work","edition","person","scholar","recommendation-issue"}:
        objects=LIFECYCLE_MODELS[image_kind].model.all_objects.filter(pk__in=[row["object_id"] for row in results if row["kind"]==image_kind])
        if image_kind in {"edition","scholar"}: objects=objects.select_related("work" if image_kind=="edition" else "person")
        images={str(obj.pk):presentation(obj,image_kind) for obj in objects}
        for row in results:
            if row["kind"]==image_kind: row.update(images.get(row["object_id"],{}))
    for row in results:
        row.setdefault("cover_url","");row.setdefault("subtitle","");row.setdefault("kind_label",row["label"]);row.setdefault("description","")
    options=[part.filter(recovery_actor_id__gt="").values("recovery_actor_id","recovery_actor_name") for part in collection_queries(**{**filters,"operator":""},state=state)]
    operators=list(options[0].union(*options[1:]).order_by("recovery_actor_name","recovery_actor_id")[:101]) if options else []
    return {"count":query.count(),"page":page,"page_size":page_size,"counts":counts,
        "results":results,"operators":[{"id":row["recovery_actor_id"],"label":row["recovery_actor_name"]} for row in operators[:100]],"operators_limited":len(operators)>100,
        "kinds":[{"id":key,"label":label} for key,label in LABELS.items()],
        "notice":"回收与归档保留原对象身份及文件。恢复后不自动发布，也不重启处理；其他变更栏显示回收恢复记录。"}


def object_and_entry(kind, identifier, *, lock=False, actor=None):
    config=LIFECYCLE_MODELS.get(kind)
    if not config or config.model._meta.label_lower not in RECYCLE_MODELS:
        raise NotFound("不支持的恢复对象。")
    query=config.model.all_objects
    from .services.curation_projects import protect_related_object
    candidate = query.filter(pk=identifier).first()
    if candidate: protect_related_object(candidate, actor, lock=lock)
    elif kind in {"recommendation-issue", "recommendation-item"}: raise NotFound("原文章对象不可用。")
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


def dependency_rows(obj, actor=None):
    """Bounded summary; the related endpoint pages the same visible querysets."""
    from .recycle_related import relation_queries, row_payload
    rows,total=[],0
    for _,_,kind,query,blocking in relation_queries(obj,actor):
        total+=query.count()
        room=min(10,max(0,50-len(rows)))
        rows.extend(row_payload(kind,other,blocking=blocking,actor=actor,source=obj) for other in query[:room])
    return rows,total


def source_file_check(obj, kind):
    """Explicit preflight of retained originals/current reader files, never a repair."""
    from django.utils import timezone
    from .models import Asset
    if not obj or kind not in {"work", "edition"}:
        return {"state":"not_required","checked_at":None,"total":0,"checks":[],"blockers":[]}
    query=Asset.objects.filter(edition__work_id=obj.pk) if kind=="work" else Asset.objects.filter(edition_id=obj.pk)
    query=query.filter(Q(kind=Asset.Kind.ORIGINAL)|Q(kind__in=[Asset.Kind.NORMALIZED,Asset.Kind.OCR_PDF],is_current=True)).order_by("pk")
    total=query.count()
    # ponytail: bound one synchronous preflight; unusually large histories need a queued inspector.
    if total>200:
        return {"state":"incomplete","checked_at":timezone.now(),"total":total,"checks":[],
            "blockers":["原件与当前阅读文件超过200份，本次未完成存储核对。请先由维护人员核对完整文件记录，不能把部分检查当作完成。"]}
    checks=[]
    for asset in query:
        state,size="available",None
        try:
            if not asset.file or not asset.file.storage.exists(asset.file.name):state="missing"
            else:
                # The project's canonical Asset storage is local NAS FileSystemStorage.
                if not Path(asset.file.path).is_file():state="missing"
                else:
                    size=asset.file.size
                    if size<=0 or asset.byte_size>0 and size!=asset.byte_size:state="size_changed"
        except (OSError,ValueError,NotImplementedError,SuspiciousFileOperation):state="unavailable"
        checks.append({"asset_id":str(asset.pk),"source_sha256":asset.sha256,"size":size,"state":state})
    missing=sum(row["state"]=="missing" for row in checks)
    changed=sum(row["state"]=="size_changed" for row in checks)
    unavailable=sum(row["state"]=="unavailable" for row in checks)
    blockers=([f"登记的原件或当前阅读文件有{missing}份缺失，先核对存储挂载或从备份恢复文件。"] if missing else [])
    if changed:blockers.append(f"有{changed}份文件大小与登记不符，请先在原文件管理中校验，不覆盖原件。")
    if unavailable:blockers.append(f"有{unavailable}份文件暂不可核对，请先恢复存储访问。")
    return {"state":"blocked" if blockers else "checked","checked_at":timezone.now(),"total":total,"checks":checks,"blockers":blockers}


def detail(kind, identifier, actor, *, locked=None, check_files=False):
    config,obj,entry=locked or object_and_entry(kind,identifier,actor=actor)
    deleted=bool(entry and entry.restored_at is None)
    archived=bool(obj and config.status_field and getattr(obj,config.status_field)==config.archived_value)
    state="deleted" if deleted else "archived" if archived else "restored"
    from .recycle_related import destination, name_summary, history_query, history_payload
    from .recycle_names import rename_info
    deps,total=dependency_rows(obj,actor) if obj else ([],0)
    names=name_summary(kind,obj,actor)
    rename=rename_info(kind,obj,actor,restoring=True)
    blockers=[row["detail"] for row in deps if row["blocking"]]
    if names["limited"]:blockers.append("同名对象超过500个，本次未完成身份比较，请先沿原管理入口整理同名记录。")
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
    public_children=[]
    public_editions=[]
    if obj and kind in {"work","edition"}:
        from .services.recycle import published_restore_editions
        public_editions=list(published_restore_editions(obj).order_by("pk").values("pk","updated_at"))
        if public_editions and not has_capability(actor,Capability.WITHDRAW_WORK):
            blockers.append("仍有关联版本保留旧公开状态，需要有下架权限的管理员恢复；恢复时先撤下旧版本，避免原馆藏直接重新公开。")
    if obj and kind=="person":
        from .services.recycle import published_person_profiles
        public_children=list(published_person_profiles(obj).order_by("pk").values("pk","updated_at"))
        if public_children and not has_capability(actor,Capability.PUBLISH_AUTHORITY):
            blockers.append("此人物关联旧公开学者页，请有发布管理权限的管理员恢复；恢复时需一并撤下旧公开状态，避免页面自动重新公开。")
    storage=source_file_check(obj,kind) if check_files else {"state":"pending" if kind in {"work","edition"} else "not_required","checked_at":None,"total":None,"checks":[],"blockers":[]}
    blockers.extend(storage["blockers"])
    required=Capability.EDIT_METADATA if deleted else Capability.PUBLISH_AUTHORITY
    can_restore=bool(obj and (deleted or archived) and not blockers and has_capability(actor,required))
    history=history_query(kind,identifier)
    history_count=history.count()
    changes=[history_payload(event) for event in history[:4]]
    title=_name(obj,config.name_field) if obj else entry.name
    before=entry.before if entry and isinstance(entry.before,dict) else {}
    version=sha256(json.dumps({"kind":kind,"id":identifier,"object_updated":obj.updated_at if obj else None,
        "entry_updated":entry.updated_at if entry else None,"state":state,"dependencies":deps,"total":total,"blockers":blockers,
        "files":storage["checks"],"public_children":public_children,"public_editions":public_editions,"names":names["fingerprint"],"rename":rename["version"]},cls=DjangoJSONEncoder,sort_keys=True).encode()).hexdigest()
    return {"kind":kind,"object_id":str(identifier),"entry_id":str(entry.pk) if entry else None,"title":title,"label":LABELS[kind],
        "record_state":state,"version":version,"destination":destination(kind,obj) if obj else DESTINATIONS[kind],**presentation(obj,kind),
        "created_at":obj.created_at if obj else None,"updated_at":obj.updated_at if obj else None,
        "changed_at":entry.updated_at if entry and not archived else obj.updated_at,"operator":entry.deleted_by.display_name if deleted and entry.deleted_by else "详见变更历史",
        "reason":str(before.get("_recycle_reason") or "原记录未保存操作原因"),"dependencies":deps,"dependency_count":total,
        "dependencies_limited":total>len(deps),"history":changes,"history_count":history_count,"names":{key:names[key] for key in ("count","results","limited")},"rename":rename,"blockers":blockers,"can_restore":can_restore,
        "storage":{"state":storage["state"],"checked_at":storage["checked_at"],"total":storage["total"]},
        "notice":"恢复原对象和保留的关联，保持未发布；不自动恢复其他已删除对象，不覆盖同名内容，不重启任务。"+(" 此人物的旧公开学者页将一并撤下，档案内容和历史修订保留，需另行审核发布。" if public_children else "")+(f" {len(public_editions)}个旧公开版本将通过原下架流程撤下，文件、身份与版本历史保留，需要另行审核发布。" if public_editions else "")}


def locked_recovery_actor(request):
    if request.headers.get("X-Editor-Owner")!=str(request.user.pk):
        raise PermissionDenied("请重新读取当前管理账户。")
    actor=User.objects.select_for_update().filter(pk=request.user.pk,is_active=True).first()
    if not actor or actor.token_version!=request.user.token_version:
        raise PermissionDenied("账户会话已经变化。")
    require_editor(actor)
    return actor


def command_event(actor, identifier):
    events=list(AuditEvent.objects.filter(action__in=["recovery.confirmed","recovery.cancelled"],request_id=str(identifier))[:2])
    if len(events)>1:
        raise RecoveryConflict("原请求有多条恢复回执，请保留编号并核对变更历史。")
    event=events[0] if events else None
    if event and event.actor_id!=actor.pk:
        raise RecoveryConflict("此请求编号不属于当前账户的恢复操作。")
    return event


def command_result(event, actor):
    after=event.after if isinstance(event.after,dict) else {}
    result=after.get("result")
    fields=("request_id","kind","object_id","restored","public_restored","destination","detail")
    if (not isinstance(result,dict) or any(key not in result for key in fields) or result["restored"] is not True
            or result["public_restored"] is not False or result["request_id"]!=event.request_id
            or result["kind"] not in LIFECYCLE_MODELS or not str(result["destination"]).startswith("/admin/")):
        raise RecoveryConflict("原恢复已登记，但回执不完整。请保留编号并核对原对象历史。")
    if result["kind"] in {"recommendation-issue","recommendation-item"}:
        object_and_entry(result["kind"],result["object_id"],actor=actor)
    return {key:result[key] for key in fields}


@transaction.atomic
def recovery_receipt(request, identifier, *, cancel=False):
    actor=locked_recovery_actor(request)
    acquire_entity_lock("recovery_command",identifier)
    if cancel and request.data!={"action":"cancel_pending"}:
        raise ValidationError("只接受取消尚未执行的原请求。")
    event=command_event(actor,identifier)
    if not event:
        if not cancel:
            raise NotFound("尚未查到已登记的恢复结果，请求仍可能在途。查询不会重新提交；请稍后查回或取消未执行请求。")
        event=AuditEvent.objects.create(actor=actor,action="recovery.cancelled",object_type="RecoveryCommand",object_id="",request_id=str(identifier),after={})
    applied=event.action=="recovery.confirmed"
    return {"request_id":str(identifier),"actor_id":str(actor.pk),"state":"applied" if applied else "cancelled",
        "created_at":event.created_at,"result":command_result(event,actor) if applied else None}


@transaction.atomic
def confirm_restore(request, values):
    actor=locked_recovery_actor(request)
    identifier=values["request_id"]
    acquire_entity_lock("recovery_command",identifier)
    receipt=command_event(actor,identifier)
    fingerprint=sha256(json.dumps(values,cls=DjangoJSONEncoder,sort_keys=True).encode()).hexdigest()
    if receipt:
        if receipt.action=="recovery.cancelled":
            raise RecoveryConflict("原恢复请求已取消，迟到的操作不会执行。请重新读取对象后再决定。")
        if not isinstance(receipt.after,dict) or receipt.after.get("fingerprint")!=fingerprint:
            raise RecoveryConflict("该请求编号对应其他恢复操作。")
        return command_result(receipt,actor)
    if values.get("rename"):
        if values["kind"]=="topic":
            from .topic_editor import lock_topic_hierarchy
            lock_topic_hierarchy()
        # Both identities are locked in a deterministic order before their
        # separate ledger/revision locks. No current content is overwritten.
        model=LIFECYCLE_MODELS[values["kind"]].model
        list(model.all_objects.select_for_update().filter(pk__in=[values["object_id"],values["rename"]["object_id"]]).order_by("pk"))
    locked=object_and_entry(values["kind"],values["object_id"],lock=True,actor=actor)
    preview=detail(values["kind"],values["object_id"],actor,locked=locked,check_files=True)
    if preview["version"]!=values["expected_version"]:
        raise RecoveryConflict()
    if not preview["can_restore"]:
        raise RecoveryConflict("；".join(preview["blockers"]) or "当前账户或对象状态不允许恢复。")
    if preview["names"]["count"] and values.get("keep_separate") is not True and not values.get("rename"):
        raise RecoveryConflict("存在同名对象，请先比较并明确选择保留独立对象后恢复。不会自动覆盖或合并。")
    _,obj,entry=locked
    from .recycle_names import prepare_rename,apply_rename
    prepared=prepare_rename(values["kind"],obj,actor,values)
    if preview["record_state"]=="deleted":
        restore_object(entry.pk,actor=actor)
    else:
        restore_archived_object(values["kind"],obj,actor=actor)
    apply_rename(values["kind"],prepared,actor,identifier)
    result={"request_id":str(identifier),"kind":values["kind"],"object_id":str(obj.pk),"restored":True,"public_restored":False,
        "destination":preview["destination"],"detail":"已恢复到原管理列表，未重新发布或启动处理。此回执记录本次操作，请刷新核对后续变更。"}
    if prepared:result["detail"]="已按确认方案改名，两个对象的身份、内容与关联均保留。"+result["detail"]
    AuditEvent.objects.create(actor=actor,action="recovery.confirmed",object_type=obj._meta.label_lower,object_id=str(obj.pk),request_id=str(identifier),after={"fingerprint":fingerprint,"result":result})
    return result
