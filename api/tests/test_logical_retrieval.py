"""New indexing uses immutable nodes; old projections survive failed replacement."""
from uuid import uuid4
import pytest
from catalog import models as m
from catalog.services import discovery_indexing as indexing, discovery_projection as projection
from catalog.services.discovery_sources import get_source
from catalog.services.document_intelligence import document_text_checksum
from ingestion.models import ProcessingJob
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def test_ocr_line_packing_preserves_raw_offsets_and_note_boundaries(monkeypatch):
    from catalog.services.knowledge_sources import snapshot_revision, digest
    from catalog.services.discovery_sources import logical_source_units, logical_unit_text
    _,asset,revision,generation,job,old = indexing_source()
    text = "第一行😀原文\n\n第二行原文\n\n脚注一\n\n第三行原文"
    m.Page.objects.filter(asset=asset,index=1).update(text=text, text_source="ocr")
    revision.text_checksum = document_text_checksum(asset);revision.save()
    snapshot_revision(revision)
    page = revision.page_snapshots.get(page_number=1)
    structure = m.DocumentStructure.objects.create(document_revision=revision,parser="explicit-fixture",
        parser_version="1",input_hash=digest(text))
    parent = m.DocumentNode.objects.create(document_revision=revision,structure=structure,kind="section",order=0,content_hash=digest(text))
    m.DocumentNodeSegment.objects.create(node=parent,page=page,order=0,start=0,end=len(text),content_hash=digest(text))
    start=0
    for order,line in enumerate(text.split("\n\n"),1):
        node=m.DocumentNode.objects.create(document_revision=revision,structure=structure,parent=parent,
            kind="footnote" if order==3 else "paragraph",order=order,content_hash=digest(line))
        m.DocumentNodeSegment.objects.create(node=node,page=page,order=0,start=start,end=start+len(line),content_hash=digest(line))
        start+=len(line)+2
    header=get_source("edition",asset.edition_id)[1]
    v1=list(logical_source_units(revision,structure.pk,header,projection_version=1))
    v2=list(logical_source_units(revision,structure.pk,header))
    assert len(v1)==4 and len(v2)==3
    assert v2[0]["text"]=="第一行😀原文\n\n第二行原文"
    assert v2[1]["metadata"]["node_kind"]=="footnote"
    segments={str(s.pk):s for s in m.DocumentNodeSegment.objects.filter(node__structure=structure).select_related("page","node")}
    assert logical_unit_text(v2[0]["metadata"],segments,revision.pk)==v2[0]["text"]
    corrupted={**v2[0]["metadata"],"node_segment_ids":[*v2[0]["metadata"]["node_segment_ids"],v2[2]["metadata"]["node_segment_id"]]}
    assert logical_unit_text(corrupted,segments,revision.pk) is None
    job.stats={**job.stats,"structure_id":str(structure.pk),"source_revision":header["source_revision"]};job.save()
    monkeypatch.setattr(indexing,"meili",lambda method,path,data=None,**kw: {"hits":[]} if path.endswith("/search") else {"taskUid":1})
    monkeypatch.setattr(indexing,"wait_index_task",lambda *a,**kw:None)
    assert indexing.process_source(job,generation)
    docs=list(m.DiscoveryDocument.objects.filter(generation=generation,payload__projection_layout="logical-node-v2"))
    rows=projection.validate_discovery_results("passages",[{"id":str(d.pk)} for d in docs],["public"])
    assert len(rows)==3
    from catalog.services.retrieval.locators import attach_locators
    first=next(r for r in attach_locators(rows) if r["text"]==v2[0]["text"])
    assert first["locator"]["exact"]==v2[0]["text"] and first["locator"]["segments"][0]["end"]==len(v2[0]["text"])


def indexing_source():
    edition,asset,_,old = fixture_source(2)
    revision = edition.active_catalog_revision.document_revision
    revision.text_checksum = document_text_checksum(asset)
    revision.save(update_fields=["text_checksum"])
    generation = old[0].generation
    generation.config_snapshot = {**generation.config_snapshot,"embedding_artifact":""}
    generation.save()
    header = get_source("edition",edition.pk)[1]
    m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in old]).update(source_revision=header["source_revision"],scope_token=header["scope_token"])
    job = ProcessingJob.objects.create(job_type="discovery_index",task_id=str(uuid4()),status="running",
        stats={"source_type":"edition","source_id":str(edition.pk),"source_revision":header["source_revision"]})
    m.DiscoverySourceState.objects.create(generation=generation,source_type="edition",source_id=edition.pk,job=job)
    return edition,asset,revision,generation,job,old


def test_logical_replacement_retains_history_and_verifies_snapshot(monkeypatch):
    edition,asset,revision,generation,job,old = indexing_source()
    m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in old]).update(vector_ready=False)
    deleted = []
    def meili(method,path,data=None,**kw):
        if path.endswith("/search"): return {"hits":[]}
        if path.endswith("/delete-batch"): deleted.extend(data)
        return {"taskUid":1}
    monkeypatch.setattr(indexing,"meili",meili)
    monkeypatch.setattr(indexing,"wait_index_task",lambda *a,**kw:None)
    assert indexing.process_source(job,generation)
    new = list(m.DiscoveryDocument.objects.filter(generation=generation,keyword_ready=True))
    assert new and all(d.payload["projection_layout"] == "logical-node-v2" for d in new)
    assert set(map(str,[d.pk for d in old])).issubset(deleted)
    assert m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in old],keyword_ready=False).count() == 2
    m.Page.objects.filter(asset=asset).update(text="后续未发布修改不能替换已引用原文")
    rows = projection.validate_discovery_results("passages",[{"id":str(d.pk)} for d in new],["public"])
    assert len(rows) == len(new) and rows[0]["page_text_range"]
    from catalog.services.retrieval.locators import attach_locators
    assert all(r["anchor_id"] for r in attach_locators(rows))
    asset.access_status = "private";asset.save(update_fields=["access_status"])
    assert projection.validate_discovery_results("passages",[{"id":str(d.pk)} for d in new],["public"]) == []


def test_keywords_preserve_valid_old_vectors_until_semantic_replacement(monkeypatch):
    edition,asset,revision,generation,job,old = indexing_source()
    deleted=[]
    def meili(method,path,data=None,**kw):
        if path.endswith("/search"): return {"hits":[]}
        if path.endswith("/delete-batch"): deleted.extend(data)
        return {"taskUid":1}
    monkeypatch.setattr(indexing,"meili",meili)
    monkeypatch.setattr(indexing,"wait_index_task",lambda *a,**kw:None)
    assert indexing.process_source(job,generation)
    old_ids=[d.pk for d in old]
    assert m.DiscoveryDocument.objects.filter(pk__in=old_ids,keyword_ready=True,vector_ready=True).count()==2
    assert not set(map(str,old_ids)).intersection(deleted)
    assert len(projection.validate_discovery_results("passages",[{"id":str(d)} for d in old_ids],["public"]))==2
    assert projection.discovery_coverage(["public"])["indexed_editions"]==1
    new=m.DiscoveryDocument.objects.filter(generation=generation).exclude(pk__in=old_ids)
    assert new.exists()
    new.update(vector_ready=True)
    assert indexing.process_source(job,generation)
    assert set(map(str,old_ids)).issubset(deleted)
    assert m.DiscoveryDocument.objects.filter(pk__in=old_ids,keyword_ready=False,vector_ready=False).count()==2
    assert projection.discovery_coverage(["public"])["vector_editions"]==1


def test_old_source_job_cannot_write_or_retire_new_owner(monkeypatch):
    edition,_,_,generation,job,old=indexing_source()
    newer=ProcessingJob.objects.create(job_type="discovery_index",status="pending",stats=job.stats)
    m.DiscoverySourceState.objects.filter(generation=generation,source_id=edition.pk).update(job=newer)
    writes=[]
    monkeypatch.setattr(indexing,"meili",lambda *args,**kwargs:writes.append(args))
    with pytest.raises(indexing.DiscoveryIndexError) as error:
        indexing.process_source(job,generation)
    assert error.value.code == "superseded" and not writes
    assert m.DiscoveryDocument.objects.filter(pk__in=[row.pk for row in old],keyword_ready=True).count()==2


def test_coordinator_does_not_replace_an_active_logical_job(monkeypatch):
    edition,_,_,generation,job,_=indexing_source()
    from catalog.services.discovery_sources import get_source
    source,header=get_source("edition",edition.pk)
    monkeypatch.setattr(indexing,"iter_source_headers",lambda kind: [(source,header)] if kind=="edition" else [])
    assert indexing.schedule_sources(generation)>0
    state=m.DiscoverySourceState.objects.get(generation=generation,source_id=edition.pk)
    assert state.job_id==job.pk
    assert ProcessingJob.objects.filter(job_type="discovery_index").count()==1

    # Failure recovery must retain the same current structure and checkpoints,
    # instead of selecting an older fingerprint job for the same text revision.
    job.status="failed"; job.stats={**job.stats,"structure_id":str(uuid4()),"completed_units":1}; job.save()
    monkeypatch.setattr(indexing,"_dispatch",lambda *args,**kwargs:None)
    assert indexing.schedule_sources(generation)>0
    state.refresh_from_db(); job.refresh_from_db()
    assert state.job_id==job.pk and job.status=="pending" and job.stats["completed_units"]==1
    assert ProcessingJob.objects.filter(job_type="discovery_index").count()==1


def test_failed_new_projection_keeps_previous_ready_rows(monkeypatch):
    _,_,_,generation,job,old = indexing_source()
    monkeypatch.setattr(indexing,"meili",lambda *a,**kw:{"taskUid":1})
    def failure(*a,**kw): raise projection.DiscoveryIndexError("write_failed")
    monkeypatch.setattr(indexing,"wait_index_task",failure)
    with pytest.raises(projection.DiscoveryIndexError):
        indexing.process_source(job,generation)
    assert m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in old],keyword_ready=True).count() == 2
    assert not m.DiscoveryDocument.objects.exclude(pk__in=[d.pk for d in old]).filter(keyword_ready=True).exists()
    job.refresh_from_db()
    assert not job.stats.get("completed_units")


def test_keyword_batches_wait_for_external_success(monkeypatch):
    _,asset,_,generation,job,_ = indexing_source()
    # More than one window per paragraph must share a bounded external task.
    m.Page.objects.filter(asset=asset).update(text="连续原文" * 400)
    revision = asset.document_revisions.get(is_active=True)
    revision.text_checksum = document_text_checksum(asset); revision.save()
    from catalog.services.discovery_sources import get_source
    header = get_source("edition", asset.edition_id)[1]
    job.stats["source_revision"] = header["source_revision"]; job.save()
    batches=[]
    def meili(method,path,data=None,**kw):
        if path.endswith("/search"): return {"hits":[]}
        if path.endswith("/documents"): batches.append(list(data))
        return {"taskUid":len(batches)}
    monkeypatch.setattr(indexing,"meili",meili)
    monkeypatch.setattr(indexing,"wait_index_task",lambda *a,**kw:None)
    assert indexing.process_source(job,generation)
    assert batches and all(1 <= len(batch) <= 20 for batch in batches)
    assert any(len(batch)>1 for batch in batches)
    assert all(m.DiscoveryDocument.objects.get(pk=row["id"]).keyword_ready for batch in batches for row in batch)


def test_keyword_worker_does_not_invoke_configured_embedding(monkeypatch, settings):
    _,_,_,generation,job,old = indexing_source()
    generation.config_snapshot["embedding_artifact"] = "configured-but-not-on-this-worker"
    generation.save()
    settings.DISCOVERY_INDEX_KEYWORD_ONLY = True
    def forbidden(*args, **kwargs):
        raise AssertionError("keyword worker must not invoke a semantic model")
    monkeypatch.setattr(indexing,"embed_texts",forbidden)
    monkeypatch.setattr(indexing,"meili",lambda method,path,data=None,**kw: {"hits":[]} if path.endswith("/search") else {"taskUid":1})
    monkeypatch.setattr(indexing,"wait_index_task",lambda *a,**kw:None)
    assert indexing.process_source(job,generation)
    job.refresh_from_db()
    assert job.stats["semantic_waiting"]["code"] == "keyword_worker"
    assert m.DiscoveryDocument.objects.filter(generation=generation,keyword_ready=True).exists()
    assert not m.DiscoveryDocument.objects.filter(generation=generation,vector_ready=True).exclude(pk__in=[d.pk for d in old]).exists()
    assert m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in old],vector_ready=True).count() == len(old)


def test_short_ocr_units_batch_and_resume_only_after_acknowledgement(monkeypatch):
    _,asset,revision,generation,job,old=indexing_source()
    m.Page.objects.filter(asset=asset,index=1).update(text="\n\n".join(f"原文第{i}行" for i in range(45)))
    m.Page.objects.filter(asset=asset,index=2).update(text="")
    revision.text_checksum=document_text_checksum(asset);revision.save()
    job.stats["source_revision"]=get_source("edition",asset.edition_id)[1]["source_revision"];job.save()
    batches=[]
    def meili(method,path,data=None,**kw):
        if path.endswith("/search"):return {"hits":[]}
        if path.endswith("/documents"):batches.append(list(data))
        return {"taskUid":len(batches)}
    def acknowledge(result):
        if len(batches)==2:raise projection.DiscoveryIndexError("write_failed")
    monkeypatch.setattr(indexing,"meili",meili)
    monkeypatch.setattr(indexing,"wait_index_task",acknowledge)
    with pytest.raises(projection.DiscoveryIndexError):indexing.process_source(job,generation)
    job.refresh_from_db()
    assert job.stats["completed_units"]==20
    assert m.DiscoveryDocument.objects.exclude(pk__in=[v.pk for v in old]).filter(keyword_ready=True).count()==20
    batches.clear()
    monkeypatch.setattr(indexing,"wait_index_task",lambda result:None)
    assert indexing.process_source(job,generation)
    assert [len(v) for v in batches]==[20,5]
    job.refresh_from_db()
    assert job.stats["completed_units"]==45


def test_exact_source_scope_filters_before_loading_published_headers(monkeypatch):
    edition,asset,_,_,_,_=indexing_source()
    other,_,_,_=fixture_source(1)
    original=projection.iter_edition_metadata_headers
    seen=[]
    def headers(queryset):
        seen.extend(queryset.values_list("pk",flat=True))
        yield from original(queryset)
    monkeypatch.setattr(projection,"iter_edition_metadata_headers",headers)
    filters={"work_ids":[str(edition.work_id)],"_asset_id":str(asset.pk),"_keyword_only":True}
    coverage=projection.discovery_coverage(["public"],filters)
    assert coverage["eligible_editions"]==1
    assert seen==[edition.pk] and other.pk not in seen
    assert list(projection._edition_scope_queryset(["public"],filters).values_list("pk",flat=True))==[edition.pk]


def test_unrecoverable_historical_snapshot_requires_source_repair(monkeypatch, admin_user):
    edition,asset,revision,generation,job,old=indexing_source()
    m.Page.objects.filter(asset=asset,index=1).update(text="后续内容不能冒充原修订",normalized_text="后续内容不能冒充原修订")
    job.status="pending"
    job.stats={**job.stats,"action":"source","generation_id":str(generation.pk)}
    job.save()
    indexing.run_job(job.pk,job.task_id)
    job.refresh_from_db()
    assert job.status=="failed" and job.error_kind=="manual_intervention", (job.error_code,job.error_message)
    assert job.error_code=="source_structure_unavailable" and "历史修订" in job.error_message
    assert not revision.page_snapshots.exists() and not revision.structures.exists()
    assert m.DiscoveryDocument.objects.filter(pk__in=[v.pk for v in old],keyword_ready=True).count()==2
    monkeypatch.setattr(indexing,"iter_source_headers",lambda kind:[get_source(kind,edition.pk)] if kind=="edition" else [])
    monkeypatch.setattr(indexing,"_dispatch",lambda *a,**kw:pytest.fail("must not automatically retry missing history"))
    assert indexing.schedule_sources(generation)>0
    job.refresh_from_db()
    assert job.status=="failed" and job.attempt==1
    from catalog.services import source_workspace
    monkeypatch.setattr(source_workspace,"meili",lambda *a,**kw:{})
    row=source_workspace.source_directory(admin_user,revision_id=revision.pk)["sources"][0]
    assert row["keywords"]=="partial" and "历史修订" in row["index_error"]
    m.DiscoveryDocument.objects.filter(generation=generation).update(keyword_ready=False)
    assert source_workspace.source_directory(admin_user,revision_id=revision.pk)["sources"][0]["keywords"]=="blocked"
