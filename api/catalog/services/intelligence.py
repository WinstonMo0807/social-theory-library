"""Eight-stage curation over immutable source windows and durable artifacts."""
import json
import time
from uuid import uuid4, uuid5
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_sources import current_structure, digest, require_revision_access
from catalog.services.knowledge_core import require_editor, match_entities, page_content
from catalog.services.intelligence_provider import configuration, identity, map_analysis, PROMPT_VERSION
from catalog.services.intelligence_changes import submit_draft, uuid_value, proposal_fingerprint
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
    "category":STRING, "direction":{"type":"string","enum":["directed","undirected"]},
    "conditions":{"type":"object","properties":{k:STRING for k in ["time","region","population","research_object","concept_usage","other"]}},
    "participants":{"type":"array","items":{"type":"object","required":["role","label"],"properties":{
        "role":{"type":"string","enum":["subject","object","claimant","quoted","criticized","context"]},"label":STRING}}},
    "evidence":{"type":"array","items":EVIDENCE_SCHEMA}}}
ANALYSIS_SCHEMA = {"type":"object", "required":["summary","questions","entities","assertions"], "properties": {
    "summary": STRING, "questions":{"type":"array","items":STRING},
    "entities":{"type":"array","items":ENTITY_SCHEMA}, "assertions":{"type":"array","items":ASSERTION_SCHEMA}}}
SUMMARY_SCHEMA = {"type":"object", "required":["summary","development","limitations"],
    "properties": {"summary":STRING,"development":{"type":"array","items":STRING},"limitations":{"type":"array","items":STRING}}}
MATCH_SCHEMA = {"type": "object", "required": ["comparisons"], "properties": {"comparisons": {"type": "array", "items": {
    "type": "object", "required": ["candidate_id", "judgment", "reason"], "properties": {
        "candidate_id": STRING, "judgment": {"type": "string", "enum": ["same_suggested", "different", "uncertain"]}, "reason": STRING}}}}}
WIKI_SCHEMA = {"type":"object", "required":["text","reason","assertion_ids"], "properties": {
    "operation":{"type":"string","enum":["add","replace","delete","none"]},"block_id":STRING,
    "text":STRING,"reason":STRING,"assertion_ids":{"type":"array","items":STRING}}}


def validate_wiki_patch(output, data):
    operation=output.get("operation","add")
    refs=output.get("assertion_ids",[])
    changed=operation in {"replace","delete"} or bool(output.get("text","").strip())
    if operation not in {"add","replace","delete","none"} or set(refs)-{a["id"] for a in data["assertions"]} or (changed and not refs):
        raise ValidationError("知识页建议缺少本批原文陈述来源，或操作类型无效。")
    if operation in {"replace","delete"}:
        blocks=[c for c in data["existing_blocks"] if c["block"]["id"]==output.get("block_id")]
        if len(blocks)!=1 or blocks[0]["block"].get("type") not in {"analysis","paragraph","heading"}:
            raise ValidationError("修改目标必须是本次实际读取的唯一文字区块。")
        if not output.get("reason","").strip() or operation=="replace" and not output.get("text","").strip():
            raise ValidationError("区块修改须说明理由并填写替换正文。")


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
    from django.db.models import Q
    # Remote completion locks demand before run; use the same order here.
    initial = m.CurationRun.objects.get(pk=run_id)
    demands = list(m.CapabilityDemand.objects.select_for_update().filter(
        Q(pk=initial.demand_id) | Q(payload__run_id=str(run_id))).order_by("pk"))
    run = m.CurationRun.objects.select_for_update().get(pk=run_id)
    require_revision_access(run.document_revision, actor, editorial=True)
    if action == "cancel":
        from common.task_runtime import _release_executor_load
        for demand in demands:
            if demand.state in {"completed","canceled"}:
                continue
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
        from common.task_runtime import _release_executor_load
        for demand in demands:
            if demand.state in {"completed","canceled"}:
                continue
            if demand.state == "claimed": _release_executor_load(demand)
            demand.state="canceled";demand.claimed_by=None;demand.lease_token=None;demand.lease_expires_at=None;demand.save()
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
    from django.conf import settings
    if settings.INTELLIGENCE_EXECUTION == "remote":
        from catalog.services.intelligence_remote import queue_stage
        queue_stage(run,stage,unit,data,prompt,schema,config,key,lease)
    if lease:
        renew_demand_lease(lease.demand_id, lease.lease_token, executor_id=lease.executor_id, lease_seconds=int(config.timeout)+180)
    started = time.monotonic()
    try:
        result = map_analysis(config, prompt, json.dumps(data, ensure_ascii=False), schema)
        if validate:
            validate(result.data)
    except Exception as exc:
        _guard(run, lease)
        m.CurationArtifact.objects.update_or_create(run=run, stage=stage, unit=unit, defaults={
            "cache_key": key, "schema_version": PROMPT_VERSION, "status": "failed", "input_manifest": data,
            "output": {}, "output_hash": "", "model_identity": identity(config),
            "usage": {"model_calls": None, "cost": None}, "elapsed_ms": round((time.monotonic()-started)*1000),
            "error": {"code": type(exc).__name__, "message": str(exc)[:1200]}})
        raise
    return _save_artifact(run, stage, unit, data, result.data, config=config, result=result, lease=lease,
        elapsed=round((time.monotonic()-started)*1000), cache_key=key)


def prepare(run):
    started = time.monotonic()
    structure = current_structure(run.document_revision, prepare=True)
    start = run.scope.get("start", 1)
    end = run.scope.get("end", run.document_revision.asset.page_count)
    nodes = list(structure.nodes.filter(kind__in=["paragraph","footnote","table","references","unresolved"], segments__page__page_number__gte=start,
        segments__page__page_number__lte=end).distinct().order_by("order").prefetch_related("segments__page"))
    manifest = [{"node_id":str(n.pk),"chapter_id":str(n.parent_id),"content_hash":n.content_hash,
        "segments":[{"page_number":s.page.page_number,"start":s.start,"end":s.end,"content_hash":s.content_hash}
                    for s in n.segments.all() if start <= s.page.page_number <= end]} for n in nodes]
    coverage = {**structure.coverage, "scope":run.scope, "included_nodes":manifest,
        "excluded_pages": list(range(1,start))+list(range(end+1,run.document_revision.asset.page_count+1)),
        "read_nodes":0, "total_nodes":len(nodes), "analysis_complete":False}
    m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(structure=structure, coverage=coverage)
    run.structure, run.coverage = structure, coverage
    _save_artifact(run,1,"source",{"structure_hash":structure.input_hash,"scope":run.scope},coverage,
        elapsed=round((time.monotonic()-started)*1000))
    return nodes


def windows(nodes, config, scope=None):
    from django.conf import settings
    # Reserve prompt/schema and output, using the strict transport's byte ceiling.
    budget = min(config.max_input_chars-6500, (int(getattr(settings,"INTELLIGENCE_CONTEXT_TOKENS",32768))-config.max_output_tokens-6500)//4)
    if budget < 300:
        raise ValidationError("当前模型输入预算过小，请在模型管理中调整。")
    pending, size, chapter = [], 0, None
    scope = scope or {}
    for node in nodes:
        parts = [s for s in node.segments.select_related("page").all() if scope.get("start",1) <= s.page.page_number <= scope.get("end",10**9)]
        for part_index,segment in enumerate(parts):
            cursor = segment.start
            while cursor < segment.end:
                raw = {"node_id":str(node.pk),"kind":node.kind,"page_number":segment.page.page_number,"start":cursor,
                    "end":segment.end,"text":segment.page.text[cursor:segment.end],"node_complete":part_index == len(parts)-1}
                if len(json.dumps(raw,ensure_ascii=False))+2 > budget:
                    # Oversized paragraphs are explicit contiguous windows, never truncation.
                    low,high = cursor+1,segment.end
                    while low < high:
                        mid = (low+high+1)//2
                        if len(json.dumps({**raw,"end":mid,"text":segment.page.text[cursor:mid]},ensure_ascii=False))+2 <= budget:
                            low = mid
                        else: high = mid-1
                    boundary = low
                    for index in range(low-1, cursor+(low-cursor)//2, -1):
                        if segment.page.text[index] in "。！？.!?\n": boundary = index+1; break
                    raw.update(end=boundary,text=segment.page.text[cursor:boundary],node_complete=False)
                length = len(json.dumps(raw,ensure_ascii=False))+2
                if length > budget:
                    raise ValidationError("单个原文字符和必要来源字段超出输入预算，未调用模型。")
                if pending and (size+length > budget or chapter != str(node.parent_id)):
                    yield chapter,pending
                    pending,size = [],0
                chapter = str(node.parent_id)
                pending.append(raw);size += length;cursor = raw["end"]
    if pending:
        yield chapter,pending


def validate_analysis(output, source_rows):
    for statement in output.get("assertions", []):
        for evidence in statement.get("evidence", []):
            matched = next((s for s in source_rows if s["page_number"]==evidence["page_number"]
                and s["start"] <= evidence["start"] < evidence["end"] <= s["end"]),None)
            if not matched or matched["text"][evidence["start"]-matched["start"]:evidence["end"]-matched["start"]] != evidence["exact"]:
                raise ValidationError("模型引文未通过指定窗口原文回查。")


def compile_wiki(run, proposals, config, lease):
    """Bounded, evidence-backed patches to work and affected identity pages.

    Entity destinations remain dependencies until an editor resolves identity.
    Existing pages provide editorial context, never new primary evidence.
    """
    assertions = [p for p in proposals if p["kind"] == "assertion"]
    proposal_map = {p["id"]:p for p in proposals}
    def source_value(value):
        if isinstance(value,dict):
            if set(value) == {"change_item"}:
                entity = proposal_map[value["change_item"]]["payload"]
                return {k:entity.get(k,"") for k in ("label","kind","definition","context")}
            return {k:source_value(v) for k,v in value.items()}
        if isinstance(value,list): return [source_value(v) for v in value]
        return value
    source_assertions = {a["id"]:{"id":proposal_fingerprint(run.document_revision_id,"assertion",a["payload"],proposal_map),
        **source_value(a["payload"])} for a in assertions}
    targets = [{"key":"work", "title":run.work.title, "work_id":str(run.work_id),
        "pages":list(m.KnowledgePage.objects.filter(work=run.work)), "assertions":assertions}]
    for entity in (p for p in proposals if p["kind"] == "entity"):
        related = [a for a in assertions if entity["id"] in a["dependencies"]]
        if related:
            ids = [c["id"] for c in entity["payload"].get("candidates",[])]
            targets.append({"key":entity["id"],"title":entity["payload"]["label"],"entity_id":{"change_item":entity["id"]},
                "pages":list(m.KnowledgePage.objects.filter(entity_id__in=ids)),"assertions":related})
    results = []
    budget = min(config.max_input_chars-6500, 6500)
    for target in targets:
        if not target["assertions"]: continue
        contexts = []
        for page in target["pages"]:
            blocks, revision = page_content(page)
            contexts += [{"page_id":str(page.pk),"entity_id":str(page.entity_id) if page.entity_id else None,
                "revision_id":str(revision.pk) if revision else None,"block":b} for b in blocks]
        batches, batch = [], []
        # Partition at whole assertions; no sampling or truncating source claims.
        for assertion in target["assertions"]:
            source = source_assertions[assertion["id"]]
            if batch and len(json.dumps([*batch,source],ensure_ascii=False)) > budget:
                batches.append(batch);batch=[]
            if len(json.dumps(source,ensure_ascii=False)) > budget:
                raise ValidationError("单条学术陈述超过编纂输入预算，请扩大明确预算或缩小上游陈述范围。")
            batch.append(source)
        if batch: batches.append(batch)
        for position, batch in enumerate(batches):
            data = {"destination":{"title":target["title"],"identity_pending":target["key"] != "work"},
                "source_revision":str(run.document_revision_id),"assertions":batch,"existing_blocks":[],"omitted_context_blocks":[]}
            for context in contexts:
                if len(json.dumps({**data,"existing_blocks":[*data["existing_blocks"],context]},ensure_ascii=False)) <= budget:
                    data["existing_blocks"].append(context)
                else:
                    data["omitted_context_blocks"].append(context["block"]["id"])
            current_ids = {source_assertions[a["id"]]["id"]:a["id"] for a in target["assertions"]}
            artifact = _model_artifact(run,6,f"page:{target['key']}:{position}",data,
                "为目标知识页提出一个局部patch。operation为add、replace、delete或none；replace/delete须给出已读block_id及具体理由。"
                "仅用本批有原文证据的陈述，说明与其他来源可能不同的用法或解释。"
                "已有区块仅供避免重复，不能作为新增事实证据；省略的区块未读取，不能声称审阅整页。人物同名候选尚未合并。"
                "人工区块默认受保护，只有新原文确实要求修订时才能提出待人工处理的修改，不直接覆盖。无实质变化时operation为none。返回实际使用的assertion_ids。",
                WIKI_SCHEMA,config,lease,validate=lambda output:validate_wiki_patch(output,data))
            output = artifact.output
            operation=output.get("operation","add")
            if operation=="none" or operation=="add" and not output["text"].strip(): continue
            refs = [current_ids[key] for key in output["assertion_ids"]]
            current = next((c for c in contexts if c["block"]["id"]==output.get("block_id")),None) if operation!="add" else None
            block_id = current["block"]["id"] if current else str(uuid5(run.pk,f"wiki:{target['key']}:{position}"))
            payload = {"operation":operation,"block_id":block_id,"reason":output["reason"],
                "block":{"id":block_id,"type":"analysis","text":output["text"],
                    "references":[{"type":"assertion","id":{"change_item":key}} for key in refs]}}
            if current:
                payload.update(page_id=current["page_id"],base_hash=digest(current["block"]),base_revision=current["revision_id"],
                    base_value=current["block"],human_protected=bool(current["block"].get("human_edited") or current["block"].get("origin") in {"human","manual","migration"}))
                if operation=="replace":
                    payload["block"]["references"]=[*current["block"].get("references",[]),*payload["block"]["references"]]
            dependencies = list(refs)
            if target["key"] == "work":
                payload["work_id"] = target["work_id"]
                if target["pages"]:
                    page=target["pages"][0];_,revision=page_content(page)
                    payload.update(page_id=str(page.pk),base_revision=str(revision.pk) if revision else None)
            else:
                payload["entity_id"] = target["entity_id"]
                dependencies.append(target["key"])
            results.append({"id":str(uuid5(run.pk,"wiki:"+digest(payload))),"kind":"wiki_patch","payload":payload,
                "dependencies":sorted(set(dependencies)),"source_artifact_id":str(artifact.pk)})
    _save_artifact(run,6,"wiki",{"source_revision":str(run.document_revision_id)}, {"proposals":results},lease=lease)
    return results


def execute(run, config, lease):
    nodes = prepare(run)
    if not config.enabled:
        m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="waiting_configuration",stage=2)
        return
    m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="running",started_at=timezone.now(),model_identity=identity(config))
    analyses = []
    read_nodes = set()
    for index, (chapter, rows) in enumerate(windows(nodes, config, run.scope)):
        chapter_node = m.DocumentNode.objects.get(pk=chapter)
        chapter_path, parent = [], chapter_node
        while parent:
            if parent.title: chapter_path.insert(0,parent.title)
            parent = parent.parent
        source_rows = [{k:v for k,v in row.items() if k not in {"node_id","node_complete"}} for row in rows]
        artifact = _model_artifact(run,2,f"window:{index}",{"revision":str(run.document_revision_id),
            "parser_version":run.structure.parser_version,"chapter_path":chapter_path,"ranges":source_rows},
            "按文献顺序分析全部输入段落。引文偏移采用各段给定的原始页面起点，Unicode code point，结束不含。列出研究问题、概念、方法及有直接证据的陈述。"
            "主张者不等于书籍作者；额外参与者在participants标明quoted/criticized等角色，并在entities逐一列出。conditions只填写原文支持的时间、地区、人群、研究对象和概念用法，未知留空。", ANALYSIS_SCHEMA,config,lease,
            validate=lambda output: validate_analysis(output, rows))
        analyses.append(artifact)
        read_nodes.update(row["node_id"] for row in rows if row["node_complete"])
        m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(coverage={**run.coverage,"read_nodes":len(read_nodes)})
    synthesis = {"summary":"","development":[],"limitations":[]}
    for i, artifact in enumerate(analyses):
        data = {"previous":synthesis,"next_chapter_in_order":artifact.output,"source_artifact_hash":artifact.output_hash,"position":i}
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
            comparisons = []
            if candidates:
                candidate_ids = {c["id"] for c in candidates}
                def validate_matches(output):
                    seen = [c["candidate_id"] for c in output["comparisons"]]
                    if set(seen) != candidate_ids or len(seen) != len(candidate_ids):
                        raise ValidationError("身份比较没有完整覆盖限定候选，或引用了候选之外的身份。")
                match = _model_artifact(run,4,"entity:"+key,{"proposed":raw,"bounded_candidates":candidates},
                    "逐一比较限定候选的身份、定义、语境和来源。名称相同或译名相似不足以判定同一。仅提出同一、不同或不确定的建议；每个候选恰好一项，管理员决定归并。",
                    MATCH_SCHEMA,config,lease,validate=validate_matches)
                comparisons = match.output["comparisons"]
            entity_proposals.append({"id":item_id,"kind":"entity","source_artifact_id":str(artifact.pk),"payload":{**raw,"candidates":candidates,
                "comparisons":comparisons,"identity_decision":"pending_human_review"},"dependencies":[]})
            entity_items[key] = item_id
            names.setdefault(raw["label"],[]).append(item_id)
    _save_artifact(run,4,"matches",{"entities":[p["payload"] for p in entity_proposals]}, {"proposals":entity_proposals},lease=lease)
    proposals = list(entity_proposals)
    for artifact in analyses:
        for raw in artifact.output.get("assertions",[]):
            participants, dependencies = [], []
            roles=list(dict.fromkeys([(role,raw.get(role)) for role in ("subject","object","claimant")]+[
                (p["role"],p["label"]) for p in raw.get("participants",[])]))
            for role, label in roles:
                candidates = names.get(label,[])
                if label and len(candidates)==1:
                    dependencies.append(candidates[0]);participants.append({"role":role,"entity_id":{"change_item":candidates[0]}})
            payload = {"text":raw["text"],"predicate":raw["predicate"],"expression":raw["expression"],"participants":participants,
                "category":raw.get("category","proposition"),"direction":raw.get("direction","directed"),"conditions":raw.get("conditions",{}),
                "unresolved_names":list(dict.fromkeys(label for _,label in roles if label and len(names.get(label,[])) != 1)),
                "unresolved_participants":[{"role":role,"label":label} for role,label in roles if label and len(names.get(label,[]))!=1],
                "evidence":[{"stance":e["stance"],"segments":[{k:v for k,v in e.items() if k != "stance"}]} for e in raw["evidence"]]}
            claimant = names.get(raw.get("claimant"),[])
            if len(claimant)==1: payload["attribution_id"]={"change_item":claimant[0]}
            proposals.append({"id":str(uuid5(run.pk,"assertion:"+digest(payload))),"kind":"assertion","payload":payload,
                "source_artifact_id":str(artifact.pk),"dependencies":sorted(set(dependencies))})
    _save_artifact(run,5,"assertions",{"analysis_hashes":[a.output_hash for a in analyses]}, {"proposals":proposals[len(entity_proposals):]},lease=lease)
    proposals += compile_wiki(run, proposals, config, lease)
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
