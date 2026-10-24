"""Read retained catalog relationship rows, never reader or account relations."""
from .lifecycle_views import LIFECYCLE_MODELS


LINK_LABELS={
    "catalog.contribution":"版本与责任者",
    "catalog.worknoderelation":"作品与知识条目",
    "catalog.personnoderelation":"人物与知识条目",
    "catalog.worktopicrelation":"作品与主题",
    "catalog.workdisciplinerelation":"作品与学科",
    "catalog.worksubdisciplinerelation":"作品与子学科",
    "catalog.persontopicrelation":"人物与主题",
    "catalog.persondisciplinerelation":"人物与学科",
    "catalog.personsubdisciplinerelation":"人物与子学科",
    "catalog.knowledgenodediscipline":"知识条目与学科",
    "catalog.knowledgenodesubdiscipline":"知识条目与子学科",
    "catalog.knowledgenodetopic":"知识条目与主题",
    "catalog.topicdisciplinerelation":"主题与学科",
    "catalog.topicsubdisciplinerelation":"主题与子学科",
    "catalog.topictheoryrelation":"主题与理论",
    "catalog.timelineeventrelation":"时间线对象关联",
    "catalog.readingpathitem":"阅读路径材料",
    "catalog.evidencesnippet":"知识原文证据",
    "catalog.workknowledgerelation":"旧作品知识关联",
    "catalog.personknowledgerelation":"旧人物知识关联",
}
DISPLAY_FIELDS=("status","review_status","role","relation_type","direction","node_is_source","approved","page_number","page_start","page_end","stage_name","chapter_title")


def lifecycle_fields(model):
    kinds={config.model:key for key,config in LIFECYCLE_MODELS.items()}
    return [(field,kinds[field.related_model]) for field in model._meta.fields if field.is_relation and field.related_model in kinds]


def relation_queries(obj,actor):
    from .services.curation_projects import filter_related_objects
    groups=[]
    origins=[(obj._meta,obj.pk,"",False)]
    if obj._meta.label_lower=="catalog.scholarprofile":
        from .models import Person
        origins.append((Person._meta,obj.person_id,"人物身份的",False))
    if obj._meta.label_lower=="catalog.work":
        from .models import Edition
        origins.append((Edition._meta,Edition.all_objects.filter(work_id=obj.pk).values("pk"),"所属版本的",True))
    for meta,identifier,prefix,many in origins:
        for relation in meta.related_objects:
            label=relation.related_model._meta.label_lower
            if label not in LINK_LABELS:continue
            model=relation.related_model
            rows=model.objects.filter(**{relation.field.attname+("__in" if many else ""):identifier})
            if many and any(field.name=="work" for field in model._meta.fields):rows=rows.exclude(work_id=obj.pk)
            columns=[model._meta.pk.name,relation.field.attname]
            fields=lifecycle_fields(model)
            for field,kind in fields:
                config=LIFECYCLE_MODELS[kind]
                from django.db.models import Q
                visible=Q(**{field.name+"__in":filter_related_objects(config.model.all_objects.all(),actor).values("pk")})
                rows=rows.filter(visible|Q(**{field.name+"__isnull":True})) if field.null else rows.filter(visible)
                columns.extend([field.name+"__"+config.model._meta.pk.name,field.name+"__"+config.name_field])
                if config.status_field:columns.append(field.name+"__"+config.status_field)
            available={field.name for field in model._meta.fields}
            columns.extend(field for field in DISPLAY_FIELDS if field in available)
            selected=[field.name+("__"+LIFECYCLE_MODELS[kind].name_field.rsplit("__",1)[0] if "__" in LIFECYCLE_MODELS[kind].name_field else "") for field,kind in fields]
            rows=rows.select_related(*selected).only(*columns).order_by("pk")
            key=f"link:{meta.label_lower}:{label}:{relation.field.name}"
            groups.append((key,prefix+LINK_LABELS[label],"link",rows,False))
        # Explicit through models are handled above. Auto-created M2M rows have
        # no editable lifecycle identity, so show their original target objects.
        for field in meta.many_to_many:
            through=field.remote_field.through
            if not through._meta.auto_created:continue
            kind=next((key for key,config in LIFECYCLE_MODELS.items() if config.model==field.related_model),None)
            if not kind:continue
            ids=through.objects.filter(**{field.m2m_field_name()+"_id"+("__in" if many else ""):identifier}).values(field.m2m_reverse_field_name()+"_id")
            rows=filter_related_objects(field.related_model.all_objects.filter(pk__in=ids),actor).order_by("pk")
            from .recycle_workspace import LABELS
            groups.append((f"many:{meta.label_lower}:{field.name}",prefix+"关联"+LABELS[kind],kind,rows,False))
    return groups


def row_payload(row,source,actor):
    from .recycle_related import row_payload as object_payload
    source_ids={(source._meta.label_lower,source.pk)}
    if source._meta.label_lower=="catalog.scholarprofile":source_ids.add(("catalog.person",source.person_id))
    targets=[]
    for field,kind in lifecycle_fields(type(row)):
        if not getattr(row,field.attname):continue
        target=getattr(row,field.name)
        if (target._meta.label_lower,target.pk) in source_ids:continue
        if source._meta.label_lower=="catalog.work" and kind=="edition" and target.work_id==source.pk:continue
        payload=object_payload(kind,target,actor=actor)
        if not any(item["kind"]==kind and item["object_id"]==payload["object_id"] for item in targets):targets.append(payload)
    # Original endpoints remain valid even when all other legacy endpoints use
    # a retired schema. Do not fabricate a replacement object or identity.
    original_kind=next(key for key,config in LIFECYCLE_MODELS.items() if config.model==type(source))
    first=targets[0] if targets else object_payload(original_kind,source,actor=actor)
    output=dict(first)
    label=LINK_LABELS[row._meta.label_lower]
    description=[label]
    for field in ("status","review_status","role","relation_type","direction"):
        if getattr(row,field,None):description.append(str(getattr(row,f"get_{field}_display",lambda:getattr(row,field))()))
    if getattr(row,"node_is_source",False):description.append("知识条目为关系来源")
    if hasattr(row,"approved"):description.append("已确认" if row.approved else "待确认")
    page=getattr(row,"page_number",None) or getattr(row,"page_start",None)
    if page:description.append(f"原文第{page}页")
    if not targets:description.append("其他旧关联对象请沿原编辑入口核对")
    description.append("关联记录保持原状态，恢复不自动确认或发布")
    output.update(relation_id=str(row.pk),label=label,detail=" · ".join(description),linked_objects=[{key:item[key] for key in ("kind","object_id","name","state","destination")} for item in targets[1:]],blocking=False)
    return output
