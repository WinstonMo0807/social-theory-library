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
    deleted = []
    def meili(method,path,data=None,**kw):
        if path.endswith("/search"): return {"hits":[]}
        if path.endswith("/delete-batch"): deleted.extend(data)
        return {"taskUid":1}
    monkeypatch.setattr(indexing,"meili",meili)
    monkeypatch.setattr(indexing,"wait_index_task",lambda *a,**kw:None)
    assert indexing.process_source(job,generation)
    new = list(m.DiscoveryDocument.objects.filter(generation=generation,keyword_ready=True))
    assert new and all(d.payload["projection_layout"] == "logical-node-v1" for d in new)
    assert set(map(str,[d.pk for d in old])).issubset(deleted)
    assert m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in old],keyword_ready=False).count() == 2
    m.Page.objects.filter(asset=asset).update(text="后续未发布修改不能替换已引用原文")
    rows = projection.validate_discovery_results("passages",[{"id":str(d.pk)} for d in new],["public"])
    assert len(rows) == len(new) and rows[0]["page_text_range"]
    from catalog.services.retrieval.locators import attach_locators
    assert all(r["anchor_id"] for r in attach_locators(rows))
    asset.access_status = "private";asset.save(update_fields=["access_status"])
    assert projection.validate_discovery_results("passages",[{"id":str(d.pk)} for d in new],["public"]) == []


def test_failed_new_projection_keeps_previous_ready_rows(monkeypatch):
    _,_,_,generation,job,old = indexing_source()
    monkeypatch.setattr(indexing,"meili",lambda *a,**kw:{"taskUid":1})
    def failure(*a,**kw): raise projection.DiscoveryIndexError("write_failed")
    monkeypatch.setattr(indexing,"wait_index_task",failure)
    with pytest.raises(projection.DiscoveryIndexError):
        indexing.process_source(job,generation)
    assert m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in old],keyword_ready=True).count() == 2
