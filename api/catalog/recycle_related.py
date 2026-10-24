"""Paged management relationships and identity comparisons; never traverse reader data."""
from hashlib import sha256
import json
from django.core.paginator import Paginator, InvalidPage
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from ingestion.models import AuditEvent
from .models import RecycleEntry
from .lifecycle_views import LIFECYCLE_MODELS, CANONICAL_OBJECT_TYPES, _name
from .services.curation_projects import filter_related_objects


def destination(kind, obj):
    from .recycle_workspace import DESTINATIONS
    if kind == "work": return f"/admin/library/works/{obj.pk}"
    if kind == "edition": return f"/admin/library/works/{obj.work_id}?edition={obj.pk}"
    if kind == "scholar": return f"/admin/scholars/{obj.pk}"
    if kind == "topic": return f"/admin/topics/{obj.pk}"
    if kind == "knowledge-node": return f"/admin/theories/{obj.pk}"
    if kind == "reading-path": return f"/admin/reading-paths?path={obj.pk}"
    if kind == "recommendation-issue": return f"/admin/recommendations/issues/{obj.pk}"
    if kind == "recommendation-item": return f"/admin/recommendations/issues/{obj.issue_id}"
    return DESTINATIONS[kind]


def row_payload(kind, obj, *, blocking=False):
    from .recycle_workspace import LABELS
    config = LIFECYCLE_MODELS[kind]
    deleted = RecycleEntry.objects.filter(model_label=obj._meta.label_lower,object_id=obj.pk,restored_at__isnull=True).exists()
    archived = config.status_field and getattr(obj,config.status_field)==config.archived_value
    state = "deleted" if deleted else "archived" if archived else "retained"
    return {"kind": kind, "object_id": str(obj.pk), "name": _name(obj,config.name_field), "label": LABELS[kind],
        "state":state,"blocking":blocking and deleted,"destination":destination(kind,obj),
        "detail":"必须先恢复所属对象。" if blocking and deleted else "需单独恢复，不随本对象恢复。" if deleted else "保留当前状态，不随本对象重新发布。"}


def relation_queries(obj, actor):
    from .recycle_workspace import LABELS
    kinds = {value.model._meta.label_lower:key for key,value in LIFECYCLE_MODELS.items()}
    groups=[]
    for relation in obj._meta.related_objects:
        kind=kinds.get(relation.related_model._meta.label_lower)
        if not kind or not relation.get_accessor_name(): continue
        rows=filter_related_objects(relation.related_model.all_objects.filter(**{relation.field.name:obj}),actor).order_by("pk").distinct()
        role="（作为来源）" if relation.field.name.startswith("source_") else "（作为目标）" if relation.field.name.startswith("target_") else ""
        groups.append((f"reverse:{kind}:{relation.field.name}", f"引用此对象的{LABELS[kind]}{role}",kind,rows,False))
    for field in obj._meta.fields:
        if not field.is_relation or not field.related_model: continue
        kind=kinds.get(field.related_model._meta.label_lower); identifier=getattr(obj,field.attname)
        if not kind or not identifier: continue
        rows=filter_related_objects(field.related_model.all_objects.filter(pk=identifier),actor)
        blocking=(obj._meta.label_lower,field.name) in {("catalog.edition","work"),("catalog.scholarprofile","person"),("catalog.recommendationissueitem","issue")}
        role="（来源）" if field.name.startswith("source_") else "（目标）" if field.name.startswith("target_") else ""
        groups.append((f"parent:{field.name}",f"所属或关联{LABELS[kind]}{role}",kind,rows,blocking))
    return sorted(groups,key=lambda row:(not row[0].startswith("parent:"),row[0]))


def names_query(kind,obj,actor):
    config=LIFECYCLE_MODELS[kind]
    if obj is None or config.name_field=="id": return config.model.objects.none()
    name=_name(obj,config.name_field).strip()
    if not name: return config.model.objects.none()
    rows=config.model.objects.filter(**{config.name_field+"__iexact":name}).exclude(pk=obj.pk)
    if config.status_field:rows=rows.exclude(**{config.status_field:config.archived_value})
    if kind=="person":rows=rows.exclude(authority_status="merged")
    return filter_related_objects(rows,actor).order_by("pk")


def name_payload(kind,obj):
    row=row_payload(kind,obj)
    if kind=="edition":
        row["detail"]=" · ".join(str(value) for value in [obj.version_label,obj.publication_year,obj.publisher,obj.isbn or obj.doi] if value) or "版本信息尚未填写"
    elif kind=="work":
        row["detail"]=obj.get_document_type_display()+" · 同名不表示同一作品"
    else:row["detail"]="独立对象，恢复不会合并、改名或覆盖它。"
    return row


def name_summary(kind,obj,actor):
    query=names_query(kind,obj,actor)
    identities=list(query.values_list("pk","updated_at")[:501])
    return {"count":query.count(), "results":[name_payload(kind,row) for row in query[:10]],
        "limited":len(identities)>500,"fingerprint":sha256(json.dumps(identities,default=str).encode()).hexdigest()}


def history_query(kind,identifier):
    config=LIFECYCLE_MODELS[kind];label=config.model._meta.label_lower
    return AuditEvent.objects.filter(object_id__in=[str(identifier),str(identifier).replace("-","")],
        object_type__in=[label,config.model._meta.label,kind,CANONICAL_OBJECT_TYPES.get(kind,kind)]).select_related("actor").order_by("-created_at","-id")


def history_payload(event):
    return {"id":str(event.pk),"at":event.created_at,"action":event.action,"actor":event.actor.display_name if event.actor else "系统或未记录",
        "detail":{"record.recycle":"移入回收站，文件和原关联保留。","record.restore":"恢复到管理列表，未自动公开。",
            "entity_archive":"已归档或撤下公开展示。","entity_restore":"恢复为草稿。","recovery.confirmed":"按预览确认恢复，保留原身份。"}.get(event.action,"原对象变更记录，详情沿原编辑历史查看。")}


def related_page(kind,identifier,actor,*,category="dependencies",relation="",page=1,as_of=None):
    from .recycle_workspace import object_and_entry
    _,obj,_=object_and_entry(kind,identifier,actor=actor)
    as_of=as_of or timezone.now()
    if as_of>timezone.now():raise ValidationError("不能读取未来记录。")
    groups=[];blocking=False;row_kind=kind;chosen=""
    if category=="dependencies":
        descriptors=relation_queries(obj,actor) if obj else []
        groups=[{"id":key,"label":label,"count":rows.count()} for key,label,_,rows,_ in descriptors]
        chosen=relation or next((row["id"] for row in groups if row["count"]),groups[0]["id"] if groups else "")
        selected=next((row for row in descriptors if row[0]==chosen),None)
        if relation and not selected:raise ValidationError("关联类型已变化，请重新读取。")
        rows=selected[3] if selected else LIFECYCLE_MODELS[kind].model.objects.none()
        if selected:row_kind,blocking=selected[2],selected[4]
    elif category=="history":rows=history_query(kind,identifier).filter(created_at__lte=as_of)
    else:rows=names_query(kind,obj,actor)
    paginator=Paginator(rows,20)
    try:current=paginator.page(page)
    except InvalidPage as error:raise ValidationError("此页已不存在，请返回第一页重新读取。") from error
    result={"category":category,"relation":chosen,"groups":groups,"count":paginator.count,"page":current.number,
        "total_pages":paginator.num_pages,"as_of":as_of,"dependencies":[],"history":[],"names":[],
        "notice":"按关联类型查看全部管理对象外键；读者私人关系不在范围，JSON内容编排引用仍需沿原编排入口核对。" if category=="dependencies" else
            "显示原对象审计摘要，不含原始操作载荷、凭据或私人正文。" if category=="history" else
            "同名可能是不同作品、版本或身份。恢复保留原ID，不自动合并、覆盖或更改公开内容。"}
    result[category]=[history_payload(row) if category=="history" else name_payload(kind,row) if category=="names" else row_payload(row_kind,row,blocking=blocking) for row in current.object_list]
    return result
