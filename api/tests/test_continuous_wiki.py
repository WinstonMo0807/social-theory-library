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
    assert copied.output == output and copied.status in {"succeeded","empty"}
    assert copied.usage["model_calls"] == 0


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
