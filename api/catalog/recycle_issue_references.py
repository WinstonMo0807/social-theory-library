"""Read-only issue references from immutable editorial snapshots."""
from django.db.models import BooleanField,CharField,F,Func,OuterRef,Q,Subquery,Value
from django.db.models.functions import Cast,Replace
from .models import EditorialRevision,Edition,EvidenceSpan


class HasIssueReference(Func):
    output_field=BooleanField()

    def __init__(self,*expressions,field="id",many=False,**extra):
        if field not in {"id","edition_id"}:raise ValueError("Unknown issue identity field")
        self.reference_field,self.many=field,many
        super().__init__(*expressions,**extra)

    def as_sql(self,compiler,connection,**extra_context):
        snapshot,params=compiler.compile(self.source_expressions[0])
        kind,kp=compiler.compile(self.source_expressions[1])
        keys,ip=compiler.compile(self.source_expressions[2])
        if connection.vendor=="postgresql":
            # Fixed paths mirror editorial_blocks.block_references, plus issue
            # material identities. Never search arbitrary strings for UUIDs.
            types=' || '.join(f'@.type == "{value}"' for value in ("evidence","work","person","concept","node","timeline","reading_path"))
            paths=[f"$.body_blocks[*] ? ({types}).target",'$.body_blocks[*] ? (@.type == "analysis").references[*]',
                '$.body_blocks[*] ? (@.type == "comparison").rows[*].cells[*].evidence[*]']
            queries=[f"SELECT ref->>'type' AS kind,ref->>'{self.reference_field}' AS key FROM jsonb_path_query({snapshot}, '{path}') ref" for path in paths]
            if self.reference_field=="id":
                queries.extend([f"SELECT 'person',ref #>> '{{}}' FROM jsonb_path_query({snapshot}, '$.body_blocks[*] ? (@.type == \"comparison\").rows[*].person_id') ref",
                    f"SELECT 'work',ref #>> '{{}}' FROM jsonb_path_query({snapshot}, '$.items[*].work_id') ref",
                    f"SELECT 'edition',ref #>> '{{}}' FROM jsonb_path_query({snapshot}, '$.items[*].edition_id') ref"])
            rows=" UNION ALL ".join(queries)
            copies=len(queries)
        else:
            # json_each expands one known shape at a time. Every scalar/array
            # is type-guarded so corrupt old snapshots cannot abort the page.
            def obj(alias):return f"CASE WHEN {alias}.type='object' THEN {alias}.value ELSE '{{}}' END"
            def arr(expression,path):return f"CASE WHEN json_type({expression}, '{path}')='array' THEN json_extract({expression}, '{path}') ELSE '[]' END"
            blocks=f"json_each({arr(snapshot,'$.body_blocks')}) b"
            target=f"json_extract({obj('b')}, '$.target')"
            target=f"CASE WHEN json_type({obj('b')}, '$.target')='object' THEN {target} ELSE '{{}}' END"
            nested=f"{blocks},json_each({arr(obj('b'),'$.rows')}) r"
            evidence=f"{nested},json_each({arr(obj('r'),'$.cells')}) c,json_each({arr(obj('c'),'$.evidence')}) e"
            block_type=f"json_extract({obj('b')}, '$.type')"
            queries=[f"SELECT json_extract({target}, '$.type') AS kind,json_extract({target}, '$.{self.reference_field}') AS key FROM {blocks} WHERE {block_type} IN ('evidence','work','person','concept','node','timeline','reading_path')",
                f"SELECT json_extract({obj('r')}, '$.type'),json_extract({obj('r')}, '$.{self.reference_field}') FROM {blocks},json_each({arr(obj('b'),'$.references')}) r WHERE {block_type}='analysis'",
                f"SELECT json_extract({obj('e')}, '$.type'),json_extract({obj('e')}, '$.{self.reference_field}') FROM {evidence} WHERE {block_type}='comparison'"]
            if self.reference_field=="id":
                queries.extend([f"SELECT 'person',json_extract({obj('r')}, '$.person_id') FROM {nested} WHERE {block_type}='comparison'",
                    f"SELECT 'work',json_extract({obj('i')}, '$.work_id') FROM json_each({arr(snapshot,'$.items')}) i",
                    f"SELECT 'edition',json_extract({obj('i')}, '$.edition_id') FROM json_each({arr(snapshot,'$.items')}) i"])
            rows=" UNION ALL ".join(queries)
            copies=len(queries)*2
        compare=f"REPLACE(issue_ref.key,'-','') IN {keys}" if self.many else f"REPLACE(issue_ref.key,'-','')=REPLACE({keys},'-','')"
        return f"EXISTS(SELECT 1 FROM ({rows}) issue_ref WHERE issue_ref.kind={kind} AND {compare})",[*params*copies,*kp,*ip]


def issue_references(obj,actor,*,include_recycled=True):
    from .services.curation_projects import visible_issues
    kinds={"catalog.work":"work","catalog.edition":"edition","catalog.knowledgenode":"node","catalog.person":"person",
        "catalog.scholarprofile":"person","catalog.theorytimelineevent":"timeline","catalog.readingpath":"reading_path"}
    kind=kinds.get(obj._meta.label_lower)
    if not kind:return None
    identifier=obj.person_id if obj._meta.label_lower=="catalog.scholarprofile" else obj.pk
    snapshot=F("materialized_preview")
    match=Q(HasIssueReference(snapshot,Value(kind),Value(str(identifier))))
    if kind in {"work","edition"}:
        editions=Edition.all_objects.filter(work_id=obj.pk) if kind=="work" else Edition.all_objects.filter(pk=obj.pk)
        def keys(rows):return Subquery(rows.order_by().annotate(compact=Replace(Cast("pk",CharField()),Value("-"),Value(""))).values("compact"))
        match|=Q(HasIssueReference(snapshot,Value("edition"),keys(editions),many=True))
        match|=Q(HasIssueReference(snapshot,Value("work"),keys(editions),field="edition_id",many=True))
        match|=Q(HasIssueReference(snapshot,Value("span"),keys(EvidenceSpan.objects.filter(page__asset__edition_id__in=editions.values("pk"))),many=True))
    pages=visible_issues(actor,include_recycled=include_recycled)
    latest=EditorialRevision.objects.filter(target_type="recommendation_issue",target_id=OuterRef("target_id")).order_by("-revision")
    rows=EditorialRevision.objects.filter(target_type="recommendation_issue",target_id__in=pages.values("pk")).annotate(
        latest_id=Subquery(latest.values("pk")[:1]),
        active_id=Subquery(pages.filter(pk=OuterRef("target_id")).values("active_revision_id")[:1]),
        scheduled_id=Subquery(pages.filter(pk=OuterRef("target_id")).values("scheduled_revision_id")[:1]))
    return rows.alias(matches=match).filter(Q(pk=F("latest_id"))|Q(pk=F("active_id"))|Q(pk=F("scheduled_id")),matches=True).defer("patch","materialized_preview").order_by("-updated_at","pk")


def issue_reference_payload(revision,actor):
    from .services.curation_projects import visible_issues
    from .recycle_related import row_payload
    from .recycle_workspace import RecoveryConflict
    parent=visible_issues(actor,include_recycled=True).filter(pk=revision.target_id).first()
    if parent is None:raise RecoveryConflict("文章所属项目或权限已变化，请重新读取关联。")
    row=row_payload("recommendation-issue",parent,actor=actor)
    states=[]
    if revision.pk==revision.latest_id:states.append("最新修订")
    if revision.pk==revision.active_id:states.append("登记公开修订")
    if revision.pk==revision.scheduled_id:states.append("登记排期修订")
    row.update(relation_id=str(revision.pk),detail=f"正文与材料第{revision.revision}版 · {'、'.join(states)}。引用保持原状，不随恢复重新发布或启动排期。")
    return row
