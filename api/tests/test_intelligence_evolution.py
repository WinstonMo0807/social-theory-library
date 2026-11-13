"""Source alignment, durable rejections and complete long-window coverage."""
from types import SimpleNamespace
from uuid import uuid4
import pytest
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services.knowledge_sources import build_structure, locator_payload
from catalog.services.document_structure import align_text, install_structure, ADAPTER_VERSION, DOCLING_VERSION
from catalog.services.intelligence_changes import submit_draft, review


@pytest.mark.django_db
def test_rejection_follows_candidate_meaning_across_run_ids(source, admin_user):
    def proposals():
        entity, assertion = str(uuid4()),str(uuid4())
        return [{"id":entity,"kind":"entity","payload":{"kind":"person","label":"同名人物","context":"同一来源语境"},"dependencies":[]},
            {"id":assertion,"kind":"assertion","payload":{"text":"同一建议","participants":[{"role":"claimant","entity_id":{"change_item":entity}}]},"dependencies":[entity]}]
    first = submit_draft(source,proposals(),admin_user,request_id=uuid4())
    review(first.pk,[{"id":str(first.items.get(kind="assertion").pk),"decision":"rejected","note":"缺乏归属证据"}],admin_user,expected_version=1)
    second = submit_draft(source,proposals(),admin_user,request_id=uuid4())
    assert second.items.get(kind="assertion").decision == "rejected"
    assert second.items.get(kind="entity").decision == "pending"


@pytest.mark.django_db
def test_docling_alignment_keeps_cross_page_provenance_and_raw_fallback(source):
    original = build_structure(source)
    text = "跨页引文前半跨页引文后半"
    parsed = {"schema":ADAPTER_VERSION,"parser_version":DOCLING_VERSION,"source_checksum":source.source_checksum,
        "heading_hierarchy_enabled":True,"ocr_performed":False,"status":"success","pages":[1,2],"items":[
            {"ref":"#/texts/0","label":"text","text":text,"prov":[{"page_no":1,"charspan":[0,6]}, {"page_no":2,"charspan":[6,12]}]}]}
    structure = install_structure(source,parsed)
    paragraph = structure.nodes.get(source__docling_ref="#/texts/0")
    assert paragraph.segments.count() == 2
    assert structure.coverage["verified_cross_page_items"] == 1
    assert structure.coverage["unmatched_ranges"]
    assert structure.coverage["structure_status"] == "needs_structure_review"
    assert install_structure(source,parsed).pk == structure.pk
    assert original.nodes.exists()
    assert align_text("甲 \n😀乙","甲😀乙") == (0,5)
    assert align_text("甲甲","甲") is None
    assert align_text('甲 “原文” 乙','"原文"') == (2,6)
    assert align_text('“原文”以及"原文"','"原文"') is None


@pytest.mark.django_db
def test_long_paragraph_windows_cover_all_codepoints_without_model_cutting(source):
    from catalog.services.intelligence import windows
    build_structure(source)
    page = SimpleNamespace(page_number=1,text=("长段落😀。"*1800))
    part = SimpleNamespace(page=page,start=0,end=len(page.text))
    class Segments:
        def select_related(self,*a): return self
        def all(self): return [part]
    node = SimpleNamespace(pk=uuid4(),parent_id=uuid4(),kind="paragraph",segments=Segments())
    rows = [row for _,window in windows([node],SimpleNamespace(max_input_chars=16000,max_output_tokens=4096)) for row in window]
    assert len(rows) > 1 and "".join(v["text"] for v in rows) == page.text
    assert all(left["end"] == right["start"] for left,right in zip(rows,rows[1:]))
    assert sum(v["node_complete"] for v in rows) == 1 and rows[-1]["node_complete"]


@pytest.mark.django_db
def test_search_slice_anchor_uses_its_own_exact_range(source):
    from catalog.services.retrieval.locators import index_anchor, attach_locators
    build_structure(source)
    page = source.page_snapshots.first();start = page.text.index("😀")
    generation = m.SemanticIndexVersion.discovery_objects.create(index_family="discovery",uid="locator-evolution")
    doc = m.DiscoveryDocument.objects.create(generation=generation,channel="passages",source_type="edition",source_id=source.asset.edition_id,
        document_revision=source,source_revision="fixture",scope_token="fixture",text="😀",start_offset=start,end_offset=start+1,payload={"pdf_page":1})
    mapping = index_anchor(doc)
    row = attach_locators([{"id":str(doc.pk),"asset_id":str(source.asset_id),"document_revision_id":str(source.pk)}])[0]
    assert row["anchor_id"] == str(mapping.target_id)
    assert row["locator"]["exact"] == "😀" and row["node_id"]
    assert index_anchor(doc).pk == mapping.pk


@pytest.mark.django_db
def test_structure_remote_completion_is_versioned_and_idempotent(source,admin_user,monkeypatch):
    from catalog.intelligence_tasks import execute_structure
    from catalog.services.document_structure import request_structure
    from common.task_runtime import register_executor_heartbeat,claim_specific_demand
    from common.remote_worker import bind_remote_lease_context,build_remote_job,complete_remote_demand,RemoteWorkerProtocolError
    monkeypatch.setattr(execute_structure,"apply_async",lambda **kwargs:None)
    source.asset.sha256=source.source_checksum;source.asset.save()
    job=request_structure(source,admin_user,pages=[1,2],request_id=uuid4())
    register_executor_heartbeat(executor_id="structure-test",capabilities=["document_parse"],kind="remote_gpu",concurrency=1,
        metadata={"task_kinds":["document_structure"]})
    lease=claim_specific_demand(demand_id=job.stats["demand_id"],executor_id="structure-test",lease_seconds=300)
    assert lease
    bind_remote_lease_context(lease)
    assert build_remote_job(lease)["input"]["revision_id"] == str(source.pk)
    parsed={"schema":ADAPTER_VERSION,"parser_version":DOCLING_VERSION,"source_checksum":source.source_checksum,
        "heading_hierarchy_enabled":True,"ocr_performed":False,"status":"success","pages":[1,2],"items":[
        {"ref":"#/texts/0","label":"text","text":"跨页引文前半跨页引文后半","prov":[{"page_no":1,"charspan":[0,6]},{"page_no":2,"charspan":[6,12]}]}]}
    result={"parsed":parsed,"elapsed_ms":1}
    args={"executor_id":"structure-test","lease_token":lease.lease_token,"completion_id":"structure-result","result":result}
    completed=complete_remote_demand(lease.demand_id,**args)
    assert len(completed.artifact_ids)==1
    assert complete_remote_demand(lease.demand_id,**args).idempotent_replay
    job.refresh_from_db();assert job.status=="succeeded"
    with pytest.raises(RemoteWorkerProtocolError):
        complete_remote_demand(lease.demand_id,**{**args,"completion_id":"different"})


@pytest.mark.django_db
@pytest.mark.parametrize("retry,attempts,expected", [(True,1,"pending"),(False,1,"failed"),(True,3,"failed")])
def test_structure_release_preserves_failure_and_allows_recovery(source, admin_user, monkeypatch, retry, attempts, expected):
    from catalog.intelligence_tasks import execute_structure
    from catalog.services.document_structure import request_structure, control_structure
    from common.task_runtime import register_executor_heartbeat, claim_specific_demand, release_demand
    monkeypatch.setattr(execute_structure, "apply_async", lambda **kwargs: None)
    job = request_structure(source, admin_user, pages=[1, 2], request_id=uuid4())
    register_executor_heartbeat(executor_id="structure-release", capabilities=["document_parse"], kind="remote_gpu",
        concurrency=1, metadata={"task_kinds":["document_structure"]})
    lease = claim_specific_demand(demand_id=job.stats["demand_id"], executor_id="structure-release", lease_seconds=300)
    m.CapabilityDemand.objects.filter(pk=lease.demand_id).update(attempts=attempts)
    job.status="running"; job.save()
    release_demand(lease.demand_id, lease.lease_token, executor_id="structure-release",
        error_code="structure_failed", error_message="Native parser resources unavailable", retry=retry)
    job.refresh_from_db()
    assert job.status == expected
    assert job.error_code == "structure_failed"
    assert bool(job.finished_at) == (expected == "failed")
    if expected == "failed":
        from rest_framework.test import APIClient
        client=APIClient(); client.force_authenticate(admin_user)
        response=client.post("/api/ingestion/processing-center/", {"action":"retry","source":"processing_job","job_id":str(job.pk)},format="json")
        assert response.status_code == 202, response.data
        from ingestion.models import ProcessingJob
        replacement=ProcessingJob.objects.get(pk=response.data["job_id"])
        assert replacement.pk != job.pk and replacement.status == "pending"
        assert control_structure(job.pk, admin_user, "retry").pk == replacement.pk
        job.refresh_from_db(); assert job.error_code == "structure_failed"
    assert m.CapabilityExecutor.objects.get(executor_id="structure-release").current_load == 0


@pytest.mark.django_db
def test_wiki_targets_work_and_identity_without_overwriting_human_blocks(source,admin_user,monkeypatch):
    from catalog.services import intelligence
    entity_id,assertion_id=str(uuid4()),str(uuid4())
    run=m.CurationRun.objects.create(work=source.asset.edition.work,edition=source.asset.edition,document_revision=source,
        request_id=uuid4(),created_by=admin_user)
    proposals=[{"id":entity_id,"kind":"entity","payload":{"label":"概念甲","kind":"concept","context":"本书用法","candidates":[]},"dependencies":[]},
        {"id":assertion_id,"kind":"assertion","payload":{"text":"有证据的用法","predicate":"uses","participants":[{"role":"subject","entity_id":{"change_item":entity_id}}],"evidence":[]},"dependencies":[entity_id]}]
    synthesis=SimpleNamespace(output={"summary":"前章预算外描述受后章2007总额入账限定。","development":["先净额，后总额"],"limitations":["历史案例"]},
        output_hash="ordered-source-hash",unit="fold:9")
    destinations=[]
    def model(run,stage,unit,data,*args,**kwargs):
        destinations.append(data["destination"])
        assert data["argument_context"]["output"] == synthesis.output
        assert data["argument_context"]["source_artifact_hash"] == synthesis.output_hash
        assert data["argument_context"]["last_window"] == 9
        assert data["argument_context"]["interpretation_status"] == "unreviewed"
        output={"text":"来源限定的局部说明","reason":"新增来源","assertion_ids":[data["assertions"][0]["id"]]}
        kwargs["validate"](output)
        return SimpleNamespace(pk=uuid4(),output=output)
    monkeypatch.setattr(intelligence,"_model_artifact",model)
    patches=intelligence.compile_wiki(run,proposals,SimpleNamespace(max_input_chars=16000),None,synthesis=synthesis)
    assert len(patches)==2 and destinations[1]["identity_pending"]
    assert all(p["payload"]["operation"]=="add" for p in patches)
    assert patches[1]["payload"]["entity_id"]=={"change_item":entity_id}
    assert patches[1]["payload"]["block"]["references"][0]["id"]=={"change_item":assertion_id}
    assert not m.KnowledgePage.objects.exists()
    from rest_framework.exceptions import ValidationError
    synthesis.output={"summary":"不可截断"*2000,"development":[],"limitations":[]}
    with pytest.raises(ValidationError,match="全书论证语境"):
        intelligence.compile_wiki(run,proposals,SimpleNamespace(max_input_chars=16000),None,synthesis=synthesis)
    assert len(destinations)==2  # no stage was dispatched with silently sliced context


@pytest.mark.django_db
def test_wiki_patch_reads_exact_target_and_requires_manual_protection(source,admin_user,monkeypatch):
    from rest_framework.exceptions import ValidationError
    from catalog.services import intelligence
    from catalog.services.knowledge_core import apply_page_patch,page_content
    from catalog.services.knowledge_sources import digest
    page=m.KnowledgePage.objects.create(work=source.asset.edition.work,slug="protected",title="已有人工内容")
    key=str(uuid4())
    entity=m.Entity.objects.create(kind="concept",label="已有概念")
    block={"id":key,"type":"analysis","text":"人工旧文","origin":"human","human_edited":True,"references":[{"type":"entity","id":str(entity.pk)}]}
    from catalog.services.editorial_revision import create_editorial_revision
    create_editorial_revision(target_type="knowledge_page",target_id=page.pk,patch={"body_blocks":[block]},actor=admin_user,idempotency_key="protected-base")
    run=m.CurationRun.objects.create(work=source.asset.edition.work,edition=source.asset.edition,document_revision=source,request_id=uuid4(),created_by=admin_user)
    statement={"id":str(uuid4()),"kind":"assertion","payload":{"text":"新证据限定旧结论","evidence":[]},"dependencies":[]}
    def model(run,stage,unit,data,*args,**kwargs):
        output={"operation":"delete","block_id":key,"text":"","reason":"新证据不支持该段解释","assertion_ids":[data["assertions"][0]["id"]]}
        kwargs["validate"](output)
        with pytest.raises(ValidationError):kwargs["validate"]({**output,"block_id":str(uuid4())})
        return SimpleNamespace(pk=uuid4(),output=output)
    monkeypatch.setattr(intelligence,"_model_artifact",model)
    patch=intelligence.compile_wiki(run,[statement],SimpleNamespace(max_input_chars=16000),None)[0]["payload"]
    assert patch["base_hash"]==digest(page_content(page)[0][0]) and patch["human_protected"]
    with pytest.raises(ValidationError,match="人工正文"):
        apply_page_patch(patch,admin_user,request_key="no-human-consent")
    apply_page_patch({**patch,"human_edited":True},admin_user,request_key="explicit-human-review")
    assert page_content(page)[0]==[]


@pytest.mark.django_db
def test_resume_preserves_identical_stage_receipt_but_checks_changes_and_cancellation(source, admin_user):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from rest_framework.exceptions import ValidationError
    from catalog.services.intelligence import _save_artifact
    run=m.CurationRun.objects.create(work=source.asset.edition.work, edition=source.asset.edition,
        document_revision=source, request_id=uuid4(), created_by=admin_user, stage=6)
    inputs={"analysis_hashes":["chapter-one"]}
    output={"proposals":[{"text":"先前原文支持的陈述"}]}
    first=_save_artifact(run,5,"assertions",inputs,output)
    m.CurationRun.objects.filter(pk=run.pk).update(stage=6)
    stamp=first.updated_at
    with CaptureQueriesContext(connection) as queries:
        again=_save_artifact(run,5,"assertions",inputs,output)
    run.refresh_from_db()
    assert again.pk==first.pk and again.updated_at==stamp and run.stage==6
    assert not any(q['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for q in queries)
    # An unchanged analysis manifest alone is insufficient: identity resolution
    # may change the derived participants and must produce a new output receipt.
    changed=_save_artifact(run,5,"assertions",inputs,{"proposals":[{"text":"变更后的归属"}]})
    assert changed.pk==first.pk and changed.output_hash!=first.output_hash
    m.CurationRun.objects.filter(pk=run.pk).update(status="canceled")
    with pytest.raises(ValidationError, match="取消"):
        _save_artifact(run,5,"assertions",inputs,changed.output)
