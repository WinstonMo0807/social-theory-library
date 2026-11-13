"""Important lifecycle contracts. Fixtures do not count as book validation."""
from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services import intelligence as runner
from catalog.services import knowledge_compilation as compilation

pytestmark = pytest.mark.django_db


def setup(source, admin_user, monkeypatch):
    monkeypatch.setattr(runner, "schedule", lambda run:None)
    return compilation.configure(source, admin_user, execution_mode="agent")


def next_packet(subscription, admin_user):
    subscription.refresh_from_db()
    run = subscription.latest_run
    try:
        runner.execute(run, compilation.run_configuration(run), None)
    except compilation.AgentStagePending:
        pass
    return run.artifacts.filter(status="waiting_agent").first()


def submit(artifact, admin_user, output):
    return compilation.submit_agent_result(artifact.pk, admin_user, input_hash=artifact.cache_key,
        run_version=artifact.execution_request["run_version"], output=output, executor_label="test fixture")


def test_agent_cannot_submit_unread_or_obsolete_evidence(source, admin_user, monkeypatch):
    policy = setup(source, admin_user, monkeypatch)
    assert policy.latest_run_id and policy.latest_run.execution_mode == "agent"
    artifact = next_packet(policy, admin_user)
    packet = compilation.agent_packet(artifact, admin_user)
    assert packet["input"]["ranges"] and packet["stage"] == 2
    output = {"summary":"fixture", "questions":[], "entities":[], "assertions":[{
        "text":"fixture", "predicate":"uses", "expression":"author_claim", "claimant":"", "subject":"", "object":"",
        "evidence":[{"page_number":1, "start":0, "end":2, "exact":"假文", "stance":"supports"}]}]}
    with pytest.raises(ValidationError):
        submit(artifact, admin_user, output)
    artifact.refresh_from_db()
    assert artifact.status == "waiting_agent" and not artifact.output
    runner.control_run(policy.latest_run_id, admin_user, "cancel")
    with pytest.raises(ValidationError):
        submit(artifact, admin_user, {**output,"assertions":[]})


def test_complete_empty_book_cache_and_idempotent_agent_receipts(source, admin_user, monkeypatch):
    policy = setup(source, admin_user, monkeypatch)
    receipts = []
    for _ in range(30):
        artifact = next_packet(policy, admin_user)
        if artifact is None:
            break
        output = ({"summary":"fixture", "questions":[], "entities":[], "assertions":[]} if artifact.stage == 2
            else {"summary":"fixture", "development":[], "limitations":[]})
        saved = submit(artifact, admin_user, output)
        assert submit(artifact, admin_user, output).pk == saved.pk
        with pytest.raises(ValidationError):
            submit(artifact, admin_user, {**output,"summary":"different"})
        receipts.append(saved.pk)
    else:
        pytest.fail("Compilation did not finish within its actual windows")
    policy.refresh_from_db()
    run = policy.latest_run
    assert run.status == "empty" and run.coverage["analysis_complete"]
    assert run.coverage["read_characters"] == run.coverage["total_characters"]
    assert run.coverage["completed_windows"] == run.coverage["total_windows"]
    assert run.artifacts.filter(stage=2, status="empty").exists()
    assert all(a.usage["model_calls"] == 0 for a in run.artifacts.filter(pk__in=receipts))
    assert compilation.configure(source, admin_user, execution_mode="agent").latest_run_id == run.pk
    # A new run can reuse identical interpreted source ranges, including empty results.
    second = runner.create_run(source, admin_user, request_id=uuid4(), execution_mode="agent")
    runner.execute(second, compilation.run_configuration(second), None)
    second.refresh_from_db()
    assert second.status == "empty" and not second.artifacts.filter(status="waiting_agent").exists()


def test_policy_pausing_preserves_products_and_blocks_late_write(source, admin_user, monkeypatch):
    policy = setup(source, admin_user, monkeypatch)
    artifact = next_packet(policy, admin_user)
    stopped = compilation.configure(source, admin_user, enabled=False, execution_mode="agent")
    assert not stopped.enabled and stopped.latest_run.status == "canceled"
    assert m.CurationArtifact.objects.filter(pk=artifact.pk).exists()
    with pytest.raises(ValidationError):
        submit(artifact, admin_user, {"summary":"fixture","questions":[],"entities":[],"assertions":[]})


def test_changed_wiki_context_reuses_source_analysis(source, admin_user, monkeypatch):
    policy = setup(source, admin_user, monkeypatch)
    artifact = next_packet(policy, admin_user)
    output = {"summary":"fixture", "questions":[], "entities":[], "assertions":[]}
    submit(artifact, admin_user, output)
    page = m.KnowledgePage.objects.create(title="专题", slug="compilation-test")
    newer = compilation.configure(source, admin_user, execution_mode="agent", target_page_ids=[page.pk])
    assert newer.latest_run_id != policy.latest_run_id
    next_packet(newer, admin_user)
    copied = newer.latest_run.artifacts.get(stage=2, unit=artifact.unit)
    assert copied.output == output and copied.status == "empty"
    assert copied.usage["model_calls"] == 0
    assert copied.usage["reused_from_artifact_id"] == str(artifact.pk)
    assert copied.usage["reused_output_hash"] == copied.output_hash


def test_long_resume_reuses_own_receipts_without_rewriting_or_per_window_queries(source, admin_user, monkeypatch):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from catalog.services.knowledge_sources import digest
    from catalog.services.intelligence_provider import identity
    policy = setup(source, admin_user, monkeypatch)
    run = policy.latest_run
    config = compilation.run_configuration(run)
    earlier = runner.create_run(source, admin_user, request_id=uuid4(), execution_mode="agent")
    output = {"summary":"fixture", "questions":[], "entities":[], "assertions":[]}
    records, inputs = [], []
    for i in range(80):
        data = {"revision":str(source.pk), "work_id":str(run.work_id), "window":i}
        key = digest([runner.PROMPT_VERSION, 2, {k:v for k,v in data.items() if k!="revision"},
            "fixture prompt", runner.ANALYSIS_SCHEMA, identity(config)])
        inputs.append(data)
        for owner in (earlier, run):
            records.append(m.CurationArtifact(run=owner, stage=2, unit=f"window:{i}", cache_key=key,
                status="empty", output=output, output_hash=digest(output),
                usage={"model_calls":0, "agent_responses":1}, executor_id="original agent"))
    m.CurationArtifact.objects.bulk_create(records)
    own = {a.unit:a.pk for a in records if a.run_id==run.pk}
    validated = []
    with CaptureQueriesContext(connection) as queries:
        for i, data in enumerate(inputs):
            result = runner._model_artifact(run, 2, f"window:{i}", data, "fixture prompt",
                runner.ANALYSIS_SCHEMA, config, None, validate=lambda value:validated.append(value))
            assert result.pk == own[f"window:{i}"] and result.status == "empty"
    assert len(validated) == 80
    assert len(queries) <= 2
    assert not any(q["sql"].lstrip().startswith(("UPDATE", "INSERT")) for q in queries)
    # The same unit with changed input cannot inherit the completed receipt.
    with pytest.raises(compilation.AgentStagePending):
        runner._model_artifact(run, 2, "window:0", {**inputs[0],"window":"changed"},
            "fixture prompt", runner.ANALYSIS_SCHEMA, config, None)
    pending = run.artifacts.get(stage=2, unit="window:0")
    assert pending.status == "waiting_agent" and pending.input_manifest["window"] == "changed"


def test_long_window_chapter_paths_batch_unique_ancestors(source):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from catalog.services.knowledge_sources import build_structure
    structure = build_structure(source)
    root = structure.nodes.get(kind="document")
    chapters = [m.DocumentNode(structure=structure, document_revision=source, parent=root,
        kind="chapter", title=f"章{i}", order=1000+i) for i in range(3)]
    m.DocumentNode.objects.bulk_create(chapters)
    sections = [m.DocumentNode(structure=structure, document_revision=source, parent=chapters[i%3],
        kind="section", title=f"节{i}", order=1100+i) for i in range(15)]
    m.DocumentNode.objects.bulk_create(sections)
    with CaptureQueriesContext(connection) as queries:
        paths = runner.chapter_paths(structure, [str(s.pk) for s in sections]*20)
    assert len(queries) <= 3
    for i, section in enumerate(sections):
        assert paths[str(section.pk)] == [root.title, f"章{i%3}", f"节{i}"]


def test_human_destination_edit_queues_only_related_subscription(source, admin_user, monkeypatch):
    from catalog.services.knowledge_core import apply_page_patch, page_metadata
    from catalog.services.knowledge_sources import digest
    policy = setup(source, admin_user, monkeypatch)
    page = m.KnowledgePage.objects.create(work=source.asset.edition.work,title="作品页",slug="destination-refresh")
    identity = m.Entity.objects.create(kind="topic", label="人工讨论主题")
    refs = [{"type":"entity", "id":str(identity.pk)}]
    assert not policy.target_pages.exists() and not page.dependencies.exists()
    apply_page_patch({"page_id":str(page.pk),"operation":"add","block_id":str(uuid4()),
        "block":{"type":"analysis","text":"管理员补写内容","references":refs}}, admin_user,
        request_key=str(uuid4()),origin="human")
    policy.refresh_from_db()
    assert policy.pending_refresh
    before = policy.latest_run_id
    compilation.reconcile_pending()
    policy.refresh_from_db()
    assert not policy.pending_refresh and policy.latest_run_id != before
    before = policy.latest_run_id
    apply_page_patch({"page_id":str(page.pk),"operation":"metadata","title":"修订讨论范围",
        "scope":"限定讨论对象", "base_hash":digest(page_metadata(page,draft=True))}, admin_user,
        request_key=str(uuid4()),origin="human")
    compilation.reconcile_pending()
    policy.refresh_from_db()
    assert not policy.pending_refresh and policy.latest_run_id != before
    # Applying a generated addition does not recursively schedule its own run.
    apply_page_patch({"page_id":str(page.pk),"operation":"add","block_id":str(uuid4()),
        "block":{"type":"analysis","text":"待审产物已接受","references":refs}}, admin_user,
        request_key=str(uuid4()),origin="wiki_compilation")
    policy.refresh_from_db()
    assert not policy.pending_refresh


def test_reader_cannot_enable_or_read_agent_inputs(source, admin_user, reader_user, monkeypatch):
    from rest_framework.test import APIClient
    policy = setup(source, admin_user, monkeypatch)
    artifact = next_packet(policy, admin_user)
    client=APIClient(); client.force_authenticate(reader_user)
    assert client.get(f"/api/knowledge/compilation-artifacts/{artifact.pk}/").status_code == 403
    assert client.post("/api/knowledge/compilations/", {"document_revision_id":str(source.pk), "execution_mode":"agent"}, format="json").status_code == 403


def test_source_update_only_enqueues_opted_in_edition(source, admin_user, monkeypatch):
    monkeypatch.setattr(runner, "schedule", lambda run:None)
    assert compilation.reconcile(source) is None
    policy = setup(source, admin_user, monkeypatch)
    assert compilation.reconcile(source).pk == policy.latest_run_id
    assert m.CurationRun.objects.count() == 1


def test_ocr_line_packing_preserves_codepoint_ranges_and_note_boundaries():
    from types import SimpleNamespace as Row
    from catalog.services.intelligence import windows, source_rows
    text="甲😀乙\n\n" + "一段正文。"*120 + "\n\n注释正文"
    page=Row(page_number=1,text=text)
    bounds=[(0,3,"paragraph"),(5,len(text)-6,"paragraph"),(len(text)-4,len(text),"footnote")]
    nodes=[]
    for i,(start,end,kind) in enumerate(bounds):
        segment=Row(page=page,start=start,end=end)
        nodes.append(Row(pk=str(i),parent_id="chapter",kind=kind,segments=Row(all=lambda s=segment:[s])))
    planned=list(windows(nodes,Row(max_input_chars=20000,max_output_tokens=4096)))
    packed=source_rows(planned[0][1])
    assert len(packed)==2 and packed[0]["text"]==text[:bounds[1][1]]
    assert packed[0]["start"]==0 and packed[0]["end"]==bounds[1][1]
    assert packed[1]["kind"]=="footnote" and packed[1]["text"]=="注释正文"


def test_outline_mapping_uses_verified_body_title_and_ignores_only_repeated_generated_headers():
    from catalog.services.knowledge_sources import _outline_heading,_running_headers
    text="第2章\n\n国家治理逻辑与中国官僚体制：\n\n一个韦伯理论视角\n\n正文"
    title,offset=_outline_heading(text,{"title":"第2章 国家治理逻辑与中国官僚体制：一个韦伯理论视角… 053","printed_label":"053"})
    assert offset==0 and title.endswith("理论视角")
    nodes=[{"id":str(i),"title":"第三部分|第二章规训的手段","pdf_page":201+i*2,
        "source":"generated_heading","source_locator":{"geometry_status":"validated","normalized_bbox":[.4,.1,.8,.12]}} for i in range(3)]
    nodes.append({**nodes[0],"id":"human","source":"manual"})
    assert _running_headers(nodes)=={"0","1","2"}

def test_assertion_quotes_join_only_verified_raw_whitespace():
    from catalog.services.intelligence import assertion_evidence
    text='甲😀\n\n乙，中间句\n丙'
    def part(start,end,stance='supports'):
        return dict(page_number=1,start=start,end=end,exact=text[start:end],stance=stance)
    rows=assertion_evidence([part(0,2),part(4,5),part(10,11),part(0,2,'qualifies')],{1:text})
    assert rows[0]['segments']==[dict(page_number=1,start=0,end=5,exact='甲😀\n\n乙')]
    assert len(rows)==3 and rows[-1]['stance']=='qualifies'

def test_compilation_missing_pages_are_limited_to_selected_range(source, admin_user, monkeypatch):
    monkeypatch.setattr(runner,'schedule',lambda run:None)
    policy=compilation.configure(source,admin_user,scope={'mode':'pages','start':1,'end':1},execution_mode='agent')
    run=policy.latest_run
    run.coverage={'missing_text_pages':[2],'included_nodes':[{'internal':'ledger'}]}
    run.save(update_fields=['coverage'])
    data=compilation.compilation_data(policy,admin_user)
    assert data['coverage']['missing_text_pages']==[] and 'included_nodes' not in data['coverage']
    run.refresh_from_db()
    assert run.coverage['missing_text_pages']==[2]


def test_resume_retains_coverage_without_rewriting_long_source_ledger(source, admin_user, monkeypatch):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    policy = setup(source, admin_user, monkeypatch)
    artifact = next_packet(policy, admin_user)
    submit(artifact, admin_user, {"summary":"fixture", "questions":[], "entities":[], "assertions":[]})
    next_packet(policy, admin_user)
    run = m.CurationRun.objects.get(pk=policy.latest_run_id)
    assert run.coverage["completed_windows"] >= 1
    previous = dict(run.coverage)
    source_artifact = run.artifacts.get(stage=1, unit="source")
    source_output = source_artifact.output
    assert source_output["included_nodes"] and "included_nodes" not in previous
    assert previous["source_artifact_id"] == str(source_artifact.pk)
    assert previous["source_manifest_hash"] == source_artifact.output_hash
    with CaptureQueriesContext(connection) as queries:
        runner.prepare(run)
    assert run.coverage == previous
    assert not any(q["sql"].lstrip().startswith(("UPDATE", "INSERT")) and
                   ("catalog_curationrun" in q["sql"] or "catalog_curationartifact" in q["sql"]) for q in queries)
    source_artifact.refresh_from_db()
    assert source_artifact.output == source_output
    # Existing rows are compacted without discarding either progress or ranges.
    run.coverage["included_nodes"] = source_output["included_nodes"]
    run.save(update_fields=["coverage"])
    runner.prepare(run)
    run.refresh_from_db()
    assert run.coverage == previous
    source_artifact.refresh_from_db()
    assert source_artifact.output == source_output
    # Prompt changes invalidate coverage even with an unchanged model identity.
    with monkeypatch.context() as changed:
        changed.setattr(runner, "PROMPT_VERSION", runner.PROMPT_VERSION + "-test")
        with pytest.raises(compilation.AgentStagePending):
            runner.execute(run, compilation.run_configuration(run), None)
        run.refresh_from_db()
        assert run.coverage["completed_windows"] == run.coverage["read_characters"] == 0
    run.coverage = previous
    run.save(update_fields=["coverage"])
    # A genuinely different model configuration cannot inherit read coverage.
    config = compilation.run_configuration(run)
    config.temperature = 1
    with pytest.raises(compilation.AgentStagePending):
        runner.execute(run, config, None)
    run.refresh_from_db()
    assert run.coverage["completed_windows"] == run.coverage["read_characters"] == 0


@pytest.mark.parametrize("origin", ["wiki_agent", "wiki_compilation", "intelligence", "external"])
def test_generated_patch_cannot_self_certify_human_edit(source, admin_user, origin):
    from catalog.services import intelligence_changes as changes
    from catalog.services.knowledge_core import page_content, apply_page_patch
    from catalog.services.knowledge_sources import digest
    page = m.KnowledgePage.objects.create(work=source.asset.edition.work, slug="protected", title="人工正文")
    block_id, item_id = str(uuid4()), str(uuid4())
    entity = m.Entity.objects.create(kind="concept", label="来源概念")
    block = {"id":block_id, "type":"analysis", "text":"人工保留的解释",
        "references":[{"type":"entity", "id":str(entity.pk)}]}
    apply_page_patch({"page_id":str(page.pk), "operation":"add", "block_id":block_id,
        "block":block, "human_edited":True}, admin_user, request_key="human-original", origin="human")
    original = page_content(page)[0][0]
    payload = {"page_id":str(page.pk), "operation":"replace", "block_id":block_id,
        "base_hash":digest(original), "block":{**block,"text":"机器建议"}, "human_edited":True}
    draft = changes.submit_draft(source, [{"id":item_id, "kind":"wiki_patch", "payload":payload}],
        admin_user, request_id=uuid4(), origin=origin)
    assert not draft.items.get().payload.get("human_edited")
    draft = changes.review(draft.pk,[{"id":item_id,"decision":"accepted"}],admin_user,expected_version=draft.version)
    result = changes.apply(draft.pk,[item_id],admin_user,request_id=uuid4(),expected_version=draft.version)
    assert item_id in result["blocked"] and not result["saved"]
    assert page_content(page)[0][0] == original
    draft.refresh_from_db()
    edited = {**draft.items.get().payload,"block":{**block,"text":"管理员核对后的修改"}}
    draft = changes.review(draft.pk,[{"id":item_id,"decision":"accepted","payload":edited}],admin_user,expected_version=draft.version)
    result = changes.apply(draft.pk,[item_id],admin_user,request_id=uuid4(),expected_version=draft.version)
    assert item_id in result["saved"] and not result["blocked"]
    assert page_content(page)[0][0]["human_edited"]
