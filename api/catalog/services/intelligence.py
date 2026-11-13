"""Eight-stage curation over immutable source windows and durable artifacts."""
import json
import time
from uuid import uuid4, uuid5
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_sources import current_structure, digest, require_revision_access
from catalog.services.knowledge_core import require_editor, match_entities, page_content, page_metadata
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
    "methods":{"type":"array","items":STRING}, "limitations":{"type":"array","items":STRING},
    "argument_role":STRING,
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


def validate_scope(revision, scope=None):
    scope = scope or {"mode": "whole"}
    if not isinstance(scope, dict) or scope.get("mode") not in {"whole", "pages"}:
        raise ValidationError("请明确选择整部文献或PDF页范围。")
    if scope["mode"] == "pages" and (type(scope.get("start")) is not int or type(scope.get("end")) is not int or not 1 <= scope["start"] <= scope["end"] <= revision.asset.page_count):
        raise ValidationError("分析页范围不在此版本内。")
    targets = scope.get("target_page_ids", [])
    if not isinstance(targets, list) or len(targets) > 30:
        raise ValidationError("编纂目标知识页最多30项。")
    for key in targets:
        uuid_value(key)
    if scope.get("compilation_id"):
        uuid_value(scope["compilation_id"])
    return scope


@transaction.atomic
def create_run(revision, actor, *, request_id, scope=None, profile_key="", execution_mode="provider"):
    require_editor(actor)
    require_revision_access(revision, actor, editorial=True)
    scope = validate_scope(revision, scope)
    if execution_mode not in {"provider", "agent"}:
        raise ValidationError("编纂执行方式无效。")
    fingerprint = digest([str(revision.pk), scope, profile_key])
    if execution_mode == "agent":
        fingerprint = digest([fingerprint, "interactive-agent"])
    old = m.CurationRun.objects.filter(request_id=uuid_value(request_id)).first()
    if old:
        if old.input_hash != fingerprint or old.created_by_id != actor.pk:
            raise ValidationError("请求ID已用于不同任务。")
        return old
    config = configuration(profile_key)
    run = m.CurationRun.objects.create(work=revision.asset.edition.work, edition=revision.asset.edition,
        document_revision=revision, scope=scope, created_by=actor, request_id=request_id, input_hash=fingerprint,
        profile_key=config.profile_key, execution_mode=execution_mode, model_identity=identity(config),
        status="waiting" if config.enabled or execution_mode == "agent" else "waiting_configuration")
    if execution_mode == "agent":
        from catalog.services.knowledge_compilation import run_configuration
        run.model_identity = identity(run_configuration(run))
        run.save(update_fields=["model_identity", "updated_at"])
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
    require_editor(current.created_by)
    require_revision_access(current.document_revision, current.created_by, editorial=True)
    if current.scope.get("compilation_id") and not m.KnowledgeCompilation.objects.filter(
            pk=current.scope["compilation_id"], enabled=True, latest_run=current).exists():
        raise ValidationError("持续编纂已暂停或来源已更新，旧结果不再写回。")
    if lease:
        demand = m.CapabilityDemand.objects.get(pk=lease.demand_id)
        if demand.state != "claimed" or demand.lease_token != lease.lease_token or demand.lease_expires_at <= timezone.now():
            raise ValidationError("执行租约已失效，旧结果不再写回。")
    return current


def _save_artifact(run, stage, unit, data, output, *, config=None, result=None, lease=None, elapsed=0, cache_key=None, reused_from=None):
    _guard(run, lease)
    model = identity(config) if config else {}
    key = cache_key or digest([PROMPT_VERSION, stage, data, model])
    with transaction.atomic():
        m.CurationRun.objects.select_for_update().get(pk=run.pk)
        _guard(run, lease)
        no_candidates = stage == 2 and not output.get("entities") and not output.get("assertions")
        usage = {"model_calls":result.attempts, "tokens":result.usage, "cost":None} if result else {"model_calls":0}
        if reused_from:
            usage.update(reused_from_artifact_id=str(reused_from.pk), reused_output_hash=reused_from.output_hash)
        artifact, _ = m.CurationArtifact.objects.update_or_create(run=run, stage=stage, unit=unit, defaults={
            "cache_key":key, "schema_version":PROMPT_VERSION, "status":"empty" if not output or no_candidates else "succeeded",
            "input_manifest": data, "output":output, "output_hash":digest(output), "model_identity":model,
            "usage": usage,
            "elapsed_ms":elapsed, "executor_id":lease.executor_id if lease else "", "error":{}})
        m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(stage=stage, updated_at=timezone.now())
    return artifact


def _model_artifact(run, stage, unit, data, prompt, schema, config, lease, validate=None):
    # A new revision may retain an identical window. Its exact ranges and book
    # identity must match before reusing interpretation; revalidate every quote.
    cache_data = {k:v for k,v in data.items() if k != "revision"} if stage == 2 else data
    key = digest([PROMPT_VERSION, stage, cache_data, prompt, schema, identity(config)])
    # A resume walks the earlier outputs to reconstruct the ordered fold. Read
    # each stage's completed receipts once, without reloading their source text
    # or rewriting a receipt just because another run has the same cache key.
    stages = getattr(run, "_artifact_cache", None)
    if stages is None:
        stages = run._artifact_cache = {}
    if stage not in stages:
        stages[stage] = {a.unit:a for a in run.artifacts.filter(stage=stage, status__in=["succeeded","empty"])
            .only("id", "run_id", "stage", "unit", "cache_key", "status", "output", "output_hash")}
    own = stages[stage].get(unit)
    cached = own if own and own.cache_key == key else m.CurationArtifact.objects.filter(
        cache_key=key, status__in=["succeeded","empty"]).order_by("created_at", "id").first()
    if cached:
        if validate:
            validate(cached.output)
        if cached.run_id == run.pk and cached.unit == unit:
            return cached
        saved = _save_artifact(run, stage, unit, data, cached.output, config=config, lease=lease, cache_key=key, reused_from=cached)
        stages[stage][unit] = saved
        return saved
    _guard(run, lease)
    if run.execution_mode == "agent":
        from catalog.services.knowledge_compilation import queue_agent_stage
        queue_agent_stage(run, stage, unit, data, prompt, schema, config, key, lease)
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
    saved = _save_artifact(run, stage, unit, data, result.data, config=config, result=result, lease=lease,
        elapsed=round((time.monotonic()-started)*1000), cache_key=key)
    stages[stage][unit] = saved
    return saved


def chapter_paths(structure, chapter_ids):
    """Fetch unique ancestors by depth, not once for every resumed window."""
    requested = {str(key) for key in chapter_ids}
    rows, pending = {}, requested
    while pending:
        batch = {str(row["id"]):row for row in structure.nodes.filter(pk__in=pending).values("id", "parent_id", "title")}
        if set(batch) != pending:
            raise ValidationError("章节节点不属于当前正文结构。")
        rows.update(batch)
        pending = {str(row["parent_id"]) for row in batch.values() if row["parent_id"]} - rows.keys()
    paths = {}
    for key in requested:
        path, seen, cursor = [], set(), key
        while cursor:
            if cursor in seen:
                raise ValidationError("正文层级存在循环，不能编纂。")
            seen.add(cursor)
            row = rows[cursor]
            if row["title"]:
                path.insert(0, row["title"])
            cursor = str(row["parent_id"]) if row["parent_id"] else None
        paths[key] = path
    return paths


def prepare(run):
    started = time.monotonic()
    structure = current_structure(run.document_revision, prepare=True)
    start = run.scope.get("start", 1)
    end = run.scope.get("end", run.document_revision.asset.page_count)
    nodes = list(structure.nodes.filter(kind__in=["paragraph","footnote","table","references","unresolved"], segments__page__page_number__gte=start,
        segments__page__page_number__lte=end).distinct().order_by("order").prefetch_related("segments__page"))
    source_input = {"structure_hash":structure.input_hash,"scope":run.scope}
    prepared = run.artifacts.filter(stage=1, unit="source", status="succeeded").only("input_manifest", "output_hash").first()
    if (run.structure_id == structure.pk and prepared and prepared.input_manifest == source_input
            and "total_nodes" in run.coverage):
        # Immutable structure + identical scope: retain the coverage ledger.
        # Each agent response resumes here; rewriting a long book's complete
        # node manifest per window makes database work quadratic in book size.
        coverage = {k:v for k,v in run.coverage.items() if k != "included_nodes"}
        coverage.update(source_artifact_id=str(prepared.pk), source_manifest_hash=prepared.output_hash)
        if coverage != run.coverage:
            # Compact legacy runs once; the complete ledger stays in stage 1.
            m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(coverage=coverage)
        run.structure, run.coverage = structure, coverage
        return nodes
    manifest = [{"node_id":str(n.pk),"chapter_id":str(n.parent_id),"content_hash":n.content_hash,
        "segments":[{"page_number":s.page.page_number,"start":s.start,"end":s.end,"content_hash":s.content_hash}
                    for s in n.segments.all() if start <= s.page.page_number <= end]} for n in nodes]
    coverage = {**structure.coverage, "scope":run.scope, "included_nodes":manifest,
        "excluded_pages": list(range(1,start))+list(range(end+1,run.document_revision.asset.page_count+1)),
        "read_nodes":0, "total_nodes":len(nodes), "analysis_complete":False}
    artifact = _save_artifact(run,1,"source",source_input,coverage,
        elapsed=round((time.monotonic()-started)*1000))
    # Frequent progress updates must not rewrite thousands of immutable ranges.
    progress = {k:v for k,v in coverage.items() if k != "included_nodes"}
    progress.update(source_artifact_id=str(artifact.pk), source_manifest_hash=artifact.output_hash)
    m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(structure=structure, coverage=progress)
    run.structure, run.coverage = structure, progress
    return nodes


def source_rows(rows):
    """Compact adjacent OCR lines without normalizing their raw page offsets.

    Node identities remain in the coverage ledger. The model needs one source
    range per contiguous page/type, not a repeated locator around every line.
    """
    packed = []
    for row in rows:
        item = {k:row[k] for k in ("kind", "page_number", "start", "end", "text")}
        gap = row.get("gap_before")
        if (packed and gap is not None and packed[-1]["page_number"] == item["page_number"]
                and packed[-1]["kind"] == item["kind"]
                and packed[-1]["end"] + len(gap) == item["start"]):
            packed[-1]["text"] += gap + item["text"]
            packed[-1]["end"] = item["end"]
        else:
            packed.append(item)
    return packed


def windows(nodes, config, scope=None):
    from django.conf import settings
    # Reserve prompt/schema and output, using the strict transport's byte ceiling.
    budget = min(config.max_input_chars-6500, (int(getattr(settings,"INTELLIGENCE_CONTEXT_TOKENS",32768))-config.max_output_tokens-6500)//4)
    if budget < 300:
        raise ValidationError("当前模型输入预算过小，请在模型管理中调整。")
    pending, chapter, previous = [], None, None
    scope = scope or {}
    for node in nodes:
        parts = [s for s in node.segments.all() if scope.get("start",1) <= s.page.page_number <= scope.get("end",10**9)]
        for part_index,segment in enumerate(parts):
            cursor = segment.start
            while cursor < segment.end:
                raw = {"node_id":str(node.pk),"kind":node.kind,"page_number":segment.page.page_number,"start":cursor,
                    "end":segment.end,"text":segment.page.text[cursor:segment.end],"node_complete":part_index == len(parts)-1}
                gap = segment.page.text[previous[1]:cursor] if previous and previous[0] == raw["page_number"] and previous[1] <= cursor else None
                raw["gap_before"] = gap if gap is not None and (not gap or gap.isspace()) else None
                if len(json.dumps(source_rows([raw]),ensure_ascii=False)) > budget:
                    # Oversized paragraphs are explicit contiguous windows, never truncation.
                    low,high = cursor+1,segment.end
                    while low < high:
                        mid = (low+high+1)//2
                        if len(json.dumps(source_rows([{**raw,"end":mid,"text":segment.page.text[cursor:mid]}]),ensure_ascii=False)) <= budget:
                            low = mid
                        else: high = mid-1
                    boundary = low
                    for index in range(low-1, cursor+(low-cursor)//2, -1):
                        if segment.page.text[index] in "。！？.!?\n": boundary = index+1; break
                    raw.update(end=boundary,text=segment.page.text[cursor:boundary],node_complete=False)
                length = len(json.dumps(source_rows([raw]),ensure_ascii=False))
                if length > budget:
                    raise ValidationError("单个原文字符和必要来源字段超出输入预算，未调用模型。")
                if pending and (len(json.dumps(source_rows([*pending,raw]),ensure_ascii=False)) > budget or chapter != str(node.parent_id)):
                    yield chapter,pending
                    pending = []
                chapter = str(node.parent_id)
                pending.append(raw);cursor = raw["end"]
                previous = (raw["page_number"], raw["end"])
    if pending:
        yield chapter,pending


def validate_analysis(output, source_rows):
    for statement in output.get("assertions", []):
        for evidence in statement.get("evidence", []):
            matched = next((s for s in source_rows if s["page_number"]==evidence["page_number"]
                and s["start"] <= evidence["start"] < evidence["end"] <= s["end"]),None)
            if not matched or matched["text"][evidence["start"]-matched["start"]:evidence["end"]-matched["start"]] != evidence["exact"]:
                raise ValidationError("模型引文未通过指定窗口原文回查。")


def assertion_evidence(raw, pages):
    """Join adjacent quote fragments only across literal raw whitespace.

    OCR line boundaries are not separate academic sources. Different stances,
    pages and non-whitespace gaps remain distinct, with exact offsets retained.
    """
    rows = []
    for evidence in raw:
        segment = {k:v for k,v in evidence.items() if k != "stance"}
        previous = rows[-1] if rows else None
        if previous and previous["stance"] == evidence["stance"]:
            last = previous["segments"][-1]
            if last["page_number"] == segment["page_number"] and last["end"] <= segment["start"]:
                page = pages[segment["page_number"]]
                gap = page[last["end"]:segment["start"]]
                if not gap or gap.isspace():
                    last["end"] = segment["end"]
                    last["exact"] = page[last["start"]:last["end"]]
                    continue
        rows.append({"stance":evidence["stance"], "segments":[segment]})
    return rows


def compile_wiki(run, proposals, config, lease, *, synthesis=None):
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
    occupied = {page.pk for target in targets for page in target["pages"]}
    for page in m.KnowledgePage.objects.filter(pk__in=run.scope.get("target_page_ids", [])).exclude(pk__in=occupied):
        targets.append({"key":f"page:{page.pk}", "page_id":str(page.pk), "title":page.title,
            "scope":page.scope, "pages":[page], "assertions":assertions})
    argument_context = None
    if synthesis is not None:
        argument_context = {"output":synthesis.output, "source_artifact_hash":synthesis.output_hash,
            "last_window":int(synthesis.unit.split(":")[-1]),
            "total_windows":run.coverage.get("total_windows"), "interpretation_status":"unreviewed"}
    results = []
    budget = min(config.max_input_chars-6500, 6500)
    for target in targets:
        if not target["assertions"]: continue
        if len(target["pages"]) == 1 and (target["key"] == "work" or "page_id" in target):
            target.update(page_metadata(target["pages"][0], draft=True))
        contexts = []
        for page in target["pages"]:
            blocks, revision = page_content(page)
            contexts += [{"page_id":str(page.pk),"entity_id":str(page.entity_id) if page.entity_id else None,
                "revision_id":str(revision.pk) if revision else None,"block":b} for b in blocks]
        base = {"destination":{"title":target["title"],"scope":target.get("scope", ""),
                "identity_pending":target["key"] != "work" and "page_id" not in target},
            "source_revision":str(run.document_revision_id),"assertions":[],"existing_blocks":[],"omitted_context_blocks":[]}
        if argument_context is not None:
            base["argument_context"] = argument_context
        source_budget = budget - len(json.dumps(base, ensure_ascii=False))
        if source_budget <= 0:
            raise ValidationError("全书论证语境超过编纂输入预算；请缩短综合产物或扩大明确预算，未截断原文或综合。")
        batches, batch = [], []
        # Partition at whole assertions; no sampling or truncating source claims.
        for assertion in target["assertions"]:
            source = source_assertions[assertion["id"]]
            if batch and len(json.dumps([*batch,source],ensure_ascii=False)) > source_budget:
                batches.append(batch);batch=[]
            if len(json.dumps([source],ensure_ascii=False)) > source_budget:
                raise ValidationError("单条学术陈述超过编纂输入预算，请扩大明确预算或缩小上游陈述范围。")
            batch.append(source)
        if batch: batches.append(batch)
        for position, batch in enumerate(batches):
            data = {**base, "assertions":batch, "existing_blocks":[], "omitted_context_blocks":[]}
            for context in contexts:
                if len(json.dumps({**data,"existing_blocks":[*data["existing_blocks"],context]},ensure_ascii=False)) <= budget:
                    data["existing_blocks"].append(context)
                else:
                    data["omitted_context_blocks"].append(context["block"]["id"])
            current_ids = {source_assertions[a["id"]]["id"]:a["id"] for a in target["assertions"]}
            artifact = _model_artifact(run,6,f"page:{target['key']}:{position}",data,
                "为目标知识页提出一个局部patch。operation为add、replace、delete或none；replace/delete须给出已读block_id及具体理由。"
                "仅用本批有原文证据的陈述，说明与其他来源可能不同的用法或解释。"
                "argument_context是按顺序综合的未审核论证语境，须保留其中的时期变化和限定；它不能充当原文证据或增加本批陈述之外的事实。"
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
            if "page_id" in target:
                page = target["pages"][0]
                _, revision = page_content(page)
                payload.update(page_id=str(page.pk), base_revision=str(revision.pk) if revision else None)
            elif target["key"] == "work":
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
    # A new lease must not retain in-memory receipts from an earlier attempt.
    run._artifact_cache = {}
    nodes = prepare(run)
    if not config.enabled:
        m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="waiting_configuration",stage=2)
        return
    m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="running",started_at=timezone.now(),model_identity=identity(config))
    analyses = []
    read_nodes = set()
    planned = list(windows(nodes, config, run.scope))
    paths = chapter_paths(run.structure, (chapter for chapter, _ in planned))
    total_characters = sum(row["end"]-row["start"] for _, rows in planned for row in source_rows(rows))
    read_characters = 0
    analysis_plan_hash = digest([PROMPT_VERSION, ANALYSIS_SCHEMA, identity(config),
        run.structure.input_hash, run.structure.parser_version, run.scope])
    # Do not temporarily reset a partially read book to zero on every resume.
    if run.coverage.get("analysis_plan_hash") != analysis_plan_hash or run.coverage.get("total_windows") != len(planned) or run.coverage.get("total_characters") != total_characters:
        run.coverage.update(total_windows=len(planned), completed_windows=0, read_nodes=0,
            total_characters=total_characters, read_characters=0, coverage_unit="unicode_code_point",
            analysis_plan_hash=analysis_plan_hash, analysis_complete=False)
        run.coverage.pop("interpretation_status", None)
        m.CurationRun.objects.filter(pk=run.pk, version=run.version).update(coverage=run.coverage)
    for index, (chapter, rows) in enumerate(planned):
        chapter_path = paths[chapter]
        model_rows = source_rows(rows)
        artifact = _model_artifact(run,2,f"window:{index}",{"revision":str(run.document_revision_id), "work_id":str(run.work_id),
            "work_title":run.work.title,
            "parser_version":run.structure.parser_version,"chapter_path":chapter_path,"ranges":model_rows},
            "按文献顺序分析全部输入段落。引文偏移采用各段给定的原始页面起点，Unicode code point，结束不含。列出研究问题、概念、方法及有直接证据的陈述。"
            "主张者不等于书籍作者；额外参与者在participants标明quoted/criticized等角色，并在entities逐一列出。conditions只填写原文支持的时间、地区、人群、研究对象和概念用法，未知留空。", ANALYSIS_SCHEMA,config,lease,
            validate=lambda output: validate_analysis(output, model_rows))
        analyses.append(artifact)
        read_nodes.update(row["node_id"] for row in rows if row["node_complete"])
        read_characters += sum(row["end"]-row["start"] for row in model_rows)
        if len(analyses) > run.coverage.get("completed_windows", 0):
            run.coverage.update(read_nodes=len(read_nodes), completed_windows=len(analyses), read_characters=read_characters)
            m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(coverage=run.coverage)
    synthesis = {"summary":"","development":[],"limitations":[]}
    summary = None
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
    cited_pages = {e["page_number"] for a in analyses for statement in a.output.get("assertions", []) for e in statement.get("evidence", [])}
    evidence_pages = dict(run.document_revision.page_snapshots.filter(page_number__in=cited_pages).values_list("page_number", "text"))
    for artifact in analyses:
        # Resolve mentions in the window that actually supplied the assertion.
        # A homonymous concept elsewhere in the book must not change attribution.
        local_names = {}
        for raw_entity in artifact.output.get("entities", []):
            local_names.setdefault(raw_entity["label"], []).append(entity_items[digest(raw_entity)])
        def mention_candidates(label):
            return list(dict.fromkeys(local_names.get(label) or names.get(label, [])))
        for raw in artifact.output.get("assertions",[]):
            participants, dependencies = [], []
            roles=list(dict.fromkeys([(role,raw.get(role)) for role in ("subject","object","claimant")]+[
                (p["role"],p["label"]) for p in raw.get("participants",[])]))
            for role, label in roles:
                candidates = mention_candidates(label)
                if label and len(candidates)==1:
                    dependencies.append(candidates[0]);participants.append({"role":role,"entity_id":{"change_item":candidates[0]}})
            payload = {"text":raw["text"],"predicate":raw["predicate"],"expression":raw["expression"],"participants":participants,
                "category":raw.get("category","proposition"),"direction":raw.get("direction","directed"),"conditions":raw.get("conditions",{}),
                "unresolved_names":list(dict.fromkeys(label for _,label in roles if label and len(mention_candidates(label)) != 1)),
                "unresolved_participants":[{"role":role,"label":label} for role,label in roles if label and len(mention_candidates(label))!=1],
                "evidence":assertion_evidence(raw["evidence"], evidence_pages)}
            claimant = mention_candidates(raw.get("claimant"))
            if len(claimant)==1: payload["attribution_id"]={"change_item":claimant[0]}
            proposals.append({"id":str(uuid5(run.pk,"assertion:"+digest(payload))),"kind":"assertion","payload":payload,
                "source_artifact_id":str(artifact.pk),"dependencies":sorted(set(dependencies))})
    _save_artifact(run,5,"assertions",{"analysis_hashes":[a.output_hash for a in analyses]}, {"proposals":proposals[len(entity_proposals):]},lease=lease)
    proposals += compile_wiki(run, proposals, config, lease, synthesis=summary)
    # Repeated mentions may yield identical proposals; their evidence identity
    # remains in the fingerprint rather than a subject/predicate unique key.
    proposals = list({p["id"]:p for p in proposals}.values())
    origin = "wiki_agent" if run.execution_mode == "agent" else "wiki_compilation" if run.scope.get("compilation_id") else "intelligence"
    changeset = submit_draft(run.document_revision,proposals,run.created_by,request_id=uuid5(run.pk,"changeset"),origin=origin,run=run)
    _save_artifact(run,7,"changeset",{"proposal_ids":[p["id"] for p in proposals]}, {"changeset_id":str(changeset.pk)},lease=lease)
    _guard(run,lease)
    missing = [page for page in run.coverage.get("missing_text_pages",[]) if page not in run.coverage["excluded_pages"]]
    complete = bool(nodes) and not missing and len(read_nodes) == len(nodes)
    m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(stage=8,
        status="partial" if not complete else "succeeded" if proposals else "empty",finished_at=timezone.now(),
        coverage={**run.coverage,"read_nodes":len(read_nodes),"analysis_complete":complete,
                  "interpretation_status":"pending_human_review"})
