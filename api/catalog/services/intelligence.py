"""Eight-stage curation over immutable source windows and durable artifacts."""
import json
import time
from uuid import uuid4, uuid5
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_sources import build_structure, digest, require_revision_access
from catalog.services.knowledge_core import require_editor, match_entities, page_content
from catalog.services.intelligence_provider import configuration, identity, map_analysis, PROMPT_VERSION
from catalog.services.intelligence_changes import submit_draft, uuid_value
from common.task_runtime import queue_or_wait, renew_demand_lease

STAGES = ["文献读取", "章节分析", "全书综合", "实体匹配", "学术陈述", "知识页编纂", "变更集", "管理员审核"]
STRING = {"type": "string"}
ENTITY_SCHEMA = {"type": "object", "required": ["label", "kind", "definition", "context"], "properties": {
    "label": STRING, "kind": {"type":"string", "enum": list(m.Entity.Kind.values)}, "definition": STRING, "context": STRING}}
EVIDENCE_SCHEMA = {"type": "object", "required": ["page_number", "start", "end", "exact", "stance"], "properties": {
    "page_number": {"type":"integer"}, "start": {"type":"integer"}, "end": {"type":"integer"}, "exact": STRING,
    "stance": {"type":"string", "enum":["supports","opposes","qualifies","context"]}}}
ASSERTION_SCHEMA = {"type":"object", "required":["text","predicate","expression","claimant","subject","object","evidence"], "properties": {
    **{k:STRING for k in ["text","predicate","expression","claimant","subject","object"]},
    "evidence":{"type":"array","items":EVIDENCE_SCHEMA}}}
ANALYSIS_SCHEMA = {"type":"object", "required":["summary","questions","entities","assertions"], "properties": {
    "summary": STRING, "questions":{"type":"array","items":STRING},
    "entities":{"type":"array","items":ENTITY_SCHEMA}, "assertions":{"type":"array","items":ASSERTION_SCHEMA}}}
SUMMARY_SCHEMA = {"type":"object", "required":["summary","development","limitations"],
    "properties": {"summary":STRING,"development":{"type":"array","items":STRING},"limitations":{"type":"array","items":STRING}}}


@transaction.atomic
def create_run(revision, actor, *, request_id, scope=None, profile_key=""):
    require_editor(actor)
    require_revision_access(revision, actor, editorial=True)
    scope = scope or {"mode": "whole"}
    if not isinstance(scope, dict) or scope.get("mode") not in {"whole", "pages"}:
        raise ValidationError("请明确选择整部文献或PDF页范围。")
    if scope["mode"] == "pages" and (type(scope.get("start")) is not int or type(scope.get("end")) is not int or not 1 <= scope["start"] <= scope["end"] <= revision.asset.page_count):
        raise ValidationError("分析页范围不在此版本内。")
    fingerprint = digest([str(revision.pk), scope, profile_key])
    old = m.CurationRun.objects.filter(request_id=uuid_value(request_id)).first()
    if old:
        if old.input_hash != fingerprint or old.created_by_id != actor.pk:
            raise ValidationError("请求ID已用于不同任务。")
        return old
    config = configuration(profile_key)
    run = m.CurationRun.objects.create(work=revision.asset.edition.work, edition=revision.asset.edition,
        document_revision=revision, scope=scope, created_by=actor, request_id=request_id, input_hash=fingerprint,
        profile_key=config.profile_key, model_identity=identity(config), status="waiting" if config.enabled else "waiting_configuration")
    schedule(run)
    return run


def schedule(run):
    result = queue_or_wait(owner_type="curation_run", owner_key=str(run.pk), capability="llm_large",
        idempotency_key=f"curation:{run.pk}:{run.version}", payload={"task_kind":"curation_run", "run_id":str(run.pk), "version":run.version},
        preferred_queue="intelligence", publication_blocking=False)
    run.demand = result.demand
    run.save(update_fields=["demand", "updated_at"])
    # One queue message containing references only. A worker can prepare sources
    # before the user configures a model, then leave a truthful waiting state.
    from catalog.intelligence_tasks import execute_curation
    def dispatch():
        try:
            execute_curation.apply_async(args=[str(run.pk), run.version], queue="intelligence")
        except Exception:
            m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="waiting_executor",
                error={"code":"queue_unavailable","message":"执行队列未连接，任务和范围已保存，可恢复。"})
    transaction.on_commit(dispatch)


@transaction.atomic
def control_run(run_id, actor, action):
    require_editor(actor)
    run = m.CurationRun.objects.select_for_update().get(pk=run_id)
    require_revision_access(run.document_revision, actor, editorial=True)
    if action == "cancel":
        if run.demand_id:
            from common.task_runtime import _release_executor_load
            demand = m.CapabilityDemand.objects.select_for_update().select_related("claimed_by").get(pk=run.demand_id)
            if demand.state == "claimed":
                _release_executor_load(demand)
            demand.state, demand.claimed_by, demand.lease_token, demand.lease_expires_at = "canceled", None, None, None
            demand.save()
        run.status, run.finished_at = "canceled", timezone.now()
        run.version += 1
        run.save()
    elif action == "resume":
        if run.status in {"running", "waiting", "succeeded", "empty", "partial"}:
            return run
        run.version += 1
        run.status, run.error, run.finished_at = "waiting", {}, None
        run.save()
        schedule(run)
    else:
        raise ValidationError("不支持的任务操作。")
    return run


def _guard(run, lease=None):
    current = m.CurationRun.objects.get(pk=run.pk)
    if current.version != run.version or current.status == "canceled":
        raise ValidationError("任务已取消或恢复，旧执行结果不再写回。")
    if lease:
        demand = m.CapabilityDemand.objects.get(pk=lease.demand_id)
        if demand.state != "claimed" or demand.lease_token != lease.lease_token or demand.lease_expires_at <= timezone.now():
            raise ValidationError("执行租约已失效，旧结果不再写回。")
    return current


def _save_artifact(run, stage, unit, data, output, *, config=None, result=None, lease=None, elapsed=0, cache_key=None):
    _guard(run, lease)
    model = identity(config) if config else {}
    key = cache_key or digest([PROMPT_VERSION, stage, data, model])
    with transaction.atomic():
        m.CurationRun.objects.select_for_update().get(pk=run.pk)
        _guard(run, lease)
        artifact, _ = m.CurationArtifact.objects.update_or_create(run=run, stage=stage, unit=unit, defaults={
            "cache_key":key, "schema_version":PROMPT_VERSION, "status":"succeeded" if output else "empty",
            "input_manifest": data, "output":output, "output_hash":digest(output), "model_identity":model,
            "usage": {"model_calls":result.attempts, "tokens":result.usage, "cost":None} if result else {"model_calls":0},
            "elapsed_ms":elapsed, "executor_id":lease.executor_id if lease else "", "error":{}})
        m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(stage=stage, updated_at=timezone.now())
    return artifact


def _model_artifact(run, stage, unit, data, prompt, schema, config, lease, validate=None):
    key = digest([PROMPT_VERSION, stage, data, prompt, schema, identity(config)])
    cached = m.CurationArtifact.objects.filter(cache_key=key, status__in=["succeeded","empty"]).first()
    if cached:
        if validate:
            validate(cached.output)
        if cached.run_id == run.pk and cached.unit == unit:
            return cached
        return _save_artifact(run, stage, unit, data, cached.output, config=config, lease=lease, cache_key=key)
    _guard(run, lease)
    if lease:
        renew_demand_lease(lease.demand_id, lease.lease_token, executor_id=lease.executor_id, lease_seconds=int(config.timeout)+180)
    started = time.monotonic()
    result = map_analysis(config, prompt, json.dumps(data, ensure_ascii=False), schema)
    if validate:
        validate(result.data)
    return _save_artifact(run, stage, unit, data, result.data, config=config, result=result, lease=lease,
        elapsed=round((time.monotonic()-started)*1000), cache_key=key)


def prepare(run):
    structure = build_structure(run.document_revision)
    start = run.scope.get("start", 1)
    end = run.scope.get("end", run.document_revision.asset.page_count)
    nodes = list(structure.nodes.filter(kind="paragraph", segments__page__page_number__gte=start,
        segments__page__page_number__lte=end).distinct().order_by("order").prefetch_related("segments__page"))
    manifest = [{"node_id":str(n.pk),"chapter_id":str(n.parent_id),"content_hash":n.content_hash,
        "segments":[{"page_number":s.page.page_number,"start":s.start,"end":s.end,"content_hash":s.content_hash}
                    for s in n.segments.all()]} for n in nodes]
    coverage = {**structure.coverage, "scope":run.scope, "included_nodes":manifest,
        "excluded_pages": list(range(1,start))+list(range(end+1,run.document_revision.asset.page_count+1)),
        "read_nodes":0, "total_nodes":len(nodes), "analysis_complete":False}
    m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(structure=structure, coverage=coverage)
    run.structure, run.coverage = structure, coverage
    _save_artifact(run,1,"source",{"structure_hash":structure.input_hash,"scope":run.scope},coverage)
    return nodes


def windows(nodes, config):
    # Reserve prompt/schema/output space; no partial paragraph goes unnoticed.
    budget = min(config.max_input_chars - 6500, 6000)
    if budget < 300:
        raise ValidationError("当前模型输入预算过小，请在模型管理中调整。")
    pending, size, chapter = [], 0, None
    for node in nodes:
        for segment in node.segments.select_related("page").all():
            raw = {"node_id":str(node.pk), "page_number":segment.page.page_number, "start":segment.start,"end":segment.end,
                   "text":segment.page.text[segment.start:segment.end]}
            length = len(json.dumps(raw,ensure_ascii=False))
            if length > budget:
                raise ValidationError({"oversized_paragraph":str(node.pk),"characters":length,"budget":budget,
                    "message":"段落超过窗口预算，尚未发送模型；请提高已确认的模型预算或补全小节结构。"})
            if pending and (size+length > budget or chapter != str(node.parent_id)):
                yield chapter, pending
                pending, size = [], 0
            chapter = str(node.parent_id)
            pending.append(raw)
            size += length
    if pending:
        yield chapter, pending


def validate_analysis(output, source_rows):
    for statement in output.get("assertions", []):
        for evidence in statement.get("evidence", []):
            matched = next((s for s in source_rows if s["page_number"]==evidence["page_number"]
                and s["start"] <= evidence["start"] < evidence["end"] <= s["end"]),None)
            if not matched or matched["text"][evidence["start"]-matched["start"]:evidence["end"]-matched["start"]] != evidence["exact"]:
                raise ValidationError("模型引文未通过指定窗口原文回查。")


def execute(run, config, lease):
    nodes = prepare(run)
    if not config.enabled:
        m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="waiting_configuration",stage=2)
        return
    m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="running",started_at=timezone.now(),model_identity=identity(config))
    analyses = []
    read_nodes = set()
    for index, (chapter, rows) in enumerate(windows(nodes, config)):
        artifact = _model_artifact(run,2,f"window:{index}",{"chapter_id":chapter,"ranges":rows},
            "按文献顺序分析全部输入段落。引文偏移采用各段给定的原始页面起点，Unicode code point，结束不含。列出研究问题、概念和有直接证据的陈述。", ANALYSIS_SCHEMA,config,lease,
            validate=lambda output: validate_analysis(output, rows))
        analyses.append(artifact)
        read_nodes.update(row["node_id"] for row in rows)
        m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(coverage={**run.coverage,"read_nodes":len(read_nodes)})
    synthesis = {"summary":"","development":[],"limitations":[]}
    for i, artifact in enumerate(analyses):
        data = {"previous":synthesis,"next_chapter_in_order":artifact.output,"source_artifact_id":str(artifact.pk),"position":i}
        summary = _model_artifact(run,3,f"fold:{i}",data,"按真实文献次序继续综合。保留论证发展和概念变化、相反解释及覆盖限制，不按多数意见归并。",SUMMARY_SCHEMA,config,lease)
        synthesis = summary.output
    entity_proposals, entity_items, names = [], {}, {}
    for artifact in analyses:
        for raw in artifact.output.get("entities",[]):
            key = digest(raw)
            if key in entity_items:
                continue
            item_id = str(uuid5(run.pk,"entity:"+key))
            candidates = match_entities(raw["label"],raw["kind"])
            entity_proposals.append({"id":item_id,"kind":"entity","payload":{**raw,"candidates":candidates},"dependencies":[]})
            entity_items[key] = item_id
            names.setdefault(raw["label"],[]).append(item_id)
    _save_artifact(run,4,"matches",{"entities":[p["payload"] for p in entity_proposals]}, {"proposals":entity_proposals},lease=lease)
    proposals = list(entity_proposals)
    for artifact in analyses:
        for raw in artifact.output.get("assertions",[]):
            participants, dependencies = [], []
            for role, label in [("subject",raw.get("subject")),("object",raw.get("object")),("claimant",raw.get("claimant"))]:
                candidates = names.get(label,[])
                if label and len(candidates)==1:
                    dependencies.append(candidates[0]);participants.append({"role":role,"entity_id":{"change_item":candidates[0]}})
            payload = {"text":raw["text"],"predicate":raw["predicate"],"expression":raw["expression"],"participants":participants,
                "unresolved_names":[raw.get(k) for k in ["subject","object","claimant"] if raw.get(k) and len(names.get(raw[k],[])) != 1],
                "evidence":[{"stance":e["stance"],"segments":[{k:v for k,v in e.items() if k != "stance"}]} for e in raw["evidence"]]}
            claimant = names.get(raw.get("claimant"),[])
            if len(claimant)==1: payload["attribution_id"]={"change_item":claimant[0]}
            proposals.append({"id":str(uuid5(run.pk,"assertion:"+digest(payload))),"kind":"assertion","payload":payload,"dependencies":sorted(set(dependencies))})
    _save_artifact(run,5,"assertions",{"analysis_hashes":[a.output_hash for a in analyses]}, {"proposals":proposals[len(entity_proposals):]},lease=lease)
    page = m.KnowledgePage.objects.filter(work=run.work).first()
    blocks, revision = page_content(page) if page else ([],None)
    # One evidence-backed local addition. Existing human blocks are protected.
    anchors = []
    for a in proposals:
        if a["kind"]=="assertion": anchors.append({"type":"assertion","id":{"change_item":a["id"]}})
    if anchors and synthesis["summary"]:
        block_id=str(uuid5(run.pk,"wiki-summary"))
        payload={"page_id":str(page.pk) if page else None,"work_id":str(run.work_id),"block_id":block_id,"operation":"add",
            "base_revision":str(revision.pk) if revision else None,"reason":"新增文献范围综合；现有人工区块保留。",
            "block":{"id":block_id,"type":"analysis","text":synthesis["summary"],"references":anchors[:40]}}
        proposals.append({"id":str(uuid5(run.pk,"wiki:"+digest(payload))),"kind":"wiki_patch","payload":payload,
            "dependencies":[a["id"]["change_item"] for a in anchors[:40]]})
    _save_artifact(run,6,"wiki",{"page_id":str(page.pk) if page else None,"blocks":blocks,"synthesis":synthesis},
        {"proposals":[p for p in proposals if p["kind"]=="wiki_patch"]},lease=lease)
    # Repeated mentions may yield identical proposals; their evidence identity
    # remains in the fingerprint rather than a subject/predicate unique key.
    proposals = list({p["id"]:p for p in proposals}.values())
    changeset = submit_draft(run.document_revision,proposals,run.created_by,request_id=uuid5(run.pk,"changeset"),origin="intelligence",run=run)
    _save_artifact(run,7,"changeset",{"proposal_ids":[p["id"] for p in proposals]}, {"changeset_id":str(changeset.pk)},lease=lease)
    _guard(run,lease)
    missing = [page for page in run.coverage.get("missing_text_pages",[]) if page not in run.coverage["excluded_pages"]]
    complete = bool(nodes) and not missing and len(read_nodes) == len(nodes)
    m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(stage=8,
        status="partial" if not complete else "succeeded" if proposals else "empty",finished_at=timezone.now(),
        coverage={**run.coverage,"read_nodes":len(read_nodes),"analysis_complete":complete,
                  "interpretation_status":"pending_human_review"})
