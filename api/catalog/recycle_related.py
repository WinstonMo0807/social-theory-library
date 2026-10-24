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


def row_payload(kind, obj, *, blocking=False, actor=None):
    from .recycle_workspace import LABELS
    if kind=="placement":return placement_payload(obj,actor)
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
    uses=placement_queries(obj,actor)
    if uses is not None:groups.append(("placements","内容编排引用（最新与公开修订）","placement",uses,False))
    return sorted(groups,key=lambda row:(not row[0].startswith("parent:"),row[0]))


def placement_queries(obj,actor):
    """Reuse original placement revisions, including exact edition and evidence links."""
    from django.db.models import F,Value,Q,CharField,Subquery
    from django.db.models.functions import Cast,Replace
    from .models import Edition,EvidenceSpan,Passage
    from .placement_uses import HasPlacementReference,allowed_pages,placement_use_revisions
    kinds={"catalog.work":"work","catalog.edition":"edition","catalog.knowledgenode":"node","catalog.scholarprofile":"scholar"}
    kind=kinds.get(obj._meta.label_lower)
    if not kind:return None
    snapshot=F("materialized_preview")
    matches=Q(HasPlacementReference(snapshot,Value(kind),Value(str(obj.pk))))
    if kind in {"work","edition"}:
        editions=Edition.all_objects.filter(work_id=obj.pk) if kind=="work" else Edition.all_objects.filter(pk=obj.pk)
        def keys(rows):
            return Subquery(rows.order_by().annotate(compact=Replace(Cast("pk",CharField()),Value("-"),Value(""))).values("compact"))
        # Keep keys in indexed SQL subqueries; never load an unbounded evidence ID list.
        matches|=Q(HasPlacementReference(snapshot,Value("edition"),keys(editions),many=True))
        matches|=Q(HasPlacementReference(snapshot,Value("work"),keys(editions),reference_field="edition_id",many=True))
        for source,model in (("span",EvidenceSpan),("passage",Passage)):
            matches|=Q(HasPlacementReference(snapshot,Value(source),keys(model.objects.filter(page__asset__edition_id__in=editions.values("pk"))),many=True))
    return placement_use_revisions(kind,obj.pk,allowed_pages(actor,include_recycled=True),matches=matches)


def placement_payload(revision,actor):
    from uuid import UUID
    from .placement_uses import allowed_pages,PAGE_LABELS
    from .services import content_placements as placements
    from .recycle_workspace import RecoveryConflict
    data=revision.materialized_preview if isinstance(revision.materialized_preview,dict) else {}
    try:identifier=UUID(str(data.get("page_id")))
    except (ValueError,TypeError,AttributeError):raise RecoveryConflict("编排引用身份不完整，请先在原编排记录核对。") from None
    page_type=data.get("page_type");pages=allowed_pages(actor,include_recycled=True).get(page_type)
    parent=pages.filter(pk=identifier).first() if pages is not None else None
    if parent is None or revision.target_id!=placements.target_id(page_type,parent.pk):
        raise RecoveryConflict("编排所属对象或访问权限已变化，请重新读取关联。")
    kinds={"node":"knowledge-node","scholar":"scholar","topic":"topic","discipline":"discipline","subdiscipline":"subdiscipline",
        "reading_path":"reading-path","issue":"recommendation-issue","timeline_event":"timeline-event"}
    kind=kinds.get(page_type)
    row=row_payload(kind,parent,actor=actor) if kind else {"kind":"site","object_id":str(parent.pk),"name":placements._title(parent),"label":PAGE_LABELS[page_type],"state":"retained","blocking":False}
    row["destination"]=f"/admin/content/{page_type}/{parent.pk}?revision={revision.pk}"
    states=[]
    if revision.pk==revision.latest_id:states.append("最新修订")
    if revision.pk==revision.published_id:states.append("已登记公开修订")
    row["detail"]=f"内容编排第{revision.revision}版 · {'、'.join(states)}。引用保留，不随恢复重新发布；页面实际可见性仍按原发布条件。"
    return row


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
        "notice":"按类型分页查看已接入的管理对象外键及内容编排引用；不含读者私人资料。编排包括最新与登记公开修订，其他历史和未接入的内容结构仍需原编辑入口核对。" if category=="dependencies" else
            "显示原对象审计摘要，不含原始操作载荷、凭据或私人正文。" if category=="history" else
            "同名可能是不同作品、版本或身份。恢复保留原ID，不自动合并、覆盖或更改公开内容。"}
    result[category]=[history_payload(row) if category=="history" else name_payload(kind,row) if category=="names" else row_payload(row_kind,row,blocking=blocking,actor=actor) for row in current.object_list]
    return result
