from datetime import timedelta
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
import os
import random
import hashlib
import re
import tarfile

import pytest
from django.core.paginator import Paginator
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog.models import Edition, Work, Asset, EvidenceSpan
from catalog.discovery_index_models import DiscoveryDocument
from catalog.services.admin_queue_query import inventory, _keys, _inventory_snapshot, CATEGORY_FIELDS
from catalog.services.admin_queue import load_admin_editions, edition_summary
from catalog.services.discovery_sessions import _deduplicate
from catalog.services import discovery_indexing as indexing, discovery_projection as projection
from catalog.services.discovery_sources import get_source, source_units
from ingestion.models import ProcessingJob, UploadBatch, UploadItem
from distribution.storage_audit import inspect_storage
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("category,page,ordering", [("all",2,"-updated_at"),("attention",0,"priority"),("exception","bad","updated_at"),("publication_ready",999,"priority")])
def test_single_inventory_query_matches_existing_category_and_page_rules(category,page,ordering,admin_user):
    for index in range(36):
        edition=Edition.objects.create(work=Work.objects.create(title=f"fixture {index}"),publication_mode="bibliographic",
            intelligence_status="failed" if index%7==0 else "draft")
        if index%4==0:
            ProcessingJob.objects.create(edition=edition,job_type="ocr",status="failed")
    batch=UploadBatch.objects.create(created_by=admin_user)
    for status in ("failed","uploaded","published"):
        UploadItem.objects.create(batch=batch,source_filename=status+".pdf",status=status)
    editions,uploads=inventory()
    with CaptureQueriesContext(connection) as queries:
        counts,ranked=_inventory_snapshot(editions,uploads,category,page,ordering)
    assert len(queries)==1
    for name in CATEGORY_FIELDS:
        assert counts[name]==_keys(editions,uploads,name).count()
        if name!="all":
            preview=sorted([row for pos,row in ranked[name] if row["preview_position"]<=12],key=lambda row:row["preview_position"])
            assert [row["queue_id"] for row in preview]==[row["queue_id"] for row in _keys(editions,uploads,name,"priority")[:12]]
    expected=Paginator(_keys(editions,uploads,category,ordering),30).get_page(page)
    offset=(expected.number-1)*30
    actual=[row["queue_id"] for pos,row in ranked[category] if offset<pos<=offset+30]
    assert actual==[row["queue_id"] for row in expected.object_list]


def test_empty_inventory_and_no_hydration_still_returns_all_counts():
    counts,ranked=_inventory_snapshot(*inventory(), "all",1,"priority")
    assert counts=={key:0 for key in CATEGORY_FIELDS}
    assert not any(ranked.values())


def test_large_history_keeps_current_job_and_recent_diagnostics_without_deleting_history():
    edition=Edition.objects.create(work=Work.objects.create(title="history"),publication_mode="bibliographic")
    jobs=[ProcessingJob(edition=edition,job_type="ocr",status="failed") for _ in range(2000)]
    ProcessingJob.objects.bulk_create(jobs)
    latest=ProcessingJob.objects.create(edition=edition,job_type="ocr",status="succeeded")
    # An older retried/updated record must not supplant latest-created success.
    ProcessingJob.objects.filter(pk=jobs[0].pk).update(updated_at=timezone.now()+timedelta(seconds=1))
    loaded=load_admin_editions(Edition.objects.filter(pk=edition.pk))[0]
    recent=list(loaded.processing_jobs.all())
    assert len(recent)<=11 and latest.pk in {j.pk for j in recent}
    row=edition_summary(loaded)
    assert row["processing_history_count"]==2001 and row["processing_history_truncated"]
    assert ProcessingJob.objects.filter(edition=edition).count()==2001


def reference_dedupe(rows):
    seen,output=set(),[]
    for row in rows:
        meta=row.get("metadata") or {}
        text=re.sub(r"\s+","",str(row.get("excerpt") or row.get("text") or ""))
        key=(str(row.get("asset_id") or meta.get("asset_id") or ""),hashlib.sha256(text.encode()).hexdigest())
        if text and key in seen:continue
        start,end=row.get("start_offset",meta.get("start_offset")),row.get("end_offset",meta.get("end_offset"))
        page=row.get("pdf_page") or meta.get("pdf_page") or meta.get("page_number")
        duplicate=False
        if isinstance(start,int) and isinstance(end,int) and end>start:
            for prior in output:
                old=prior.get("metadata") or {}
                a,b=prior.get("start_offset",old.get("start_offset")),prior.get("end_offset",old.get("end_offset"))
                if key[0]==str(prior.get("asset_id") or old.get("asset_id") or "") and page==(prior.get("pdf_page") or old.get("pdf_page") or old.get("page_number")) and isinstance(a,int) and isinstance(b,int) and b>a:
                    if max(0,min(end,b)-max(start,a))/min(end-start,b-a)>=.8:
                        duplicate=True
                        break
        if not duplicate:seen.add(key);output.append(row)
    return output


def test_bucket_dedupe_preserves_greedy_ranking_and_overlap_boundaries():
    rng=random.Random(3082)
    for _ in range(80):
        rows=[]
        for index in range(80):
            start=rng.randrange(500)
            row={"id":index,"asset_id":str(rng.randrange(4)),"pdf_page":rng.randrange(4),
                 "start_offset":start,"end_offset":start+rng.randrange(1,60),"text":str(rng.randrange(90))}
            if rng.random()<.2:row["metadata"]={k:row.pop(k) for k in ("asset_id","pdf_page","start_offset","end_offset")}
            rows.append(row)
        assert _deduplicate(rows)==reference_dedupe(rows)


@pytest.mark.parametrize("outcome",["success","failed","superseded","deadline"])
def test_index_batch_waits_for_external_success_and_current_claim(monkeypatch,outcome):
    edition,_,_,docs=fixture_source(1)
    header=get_source("edition",edition.pk)[1]
    unit=next(source_units("edition",edition,header))
    job=ProcessingJob.objects.create(edition=edition,job_type="discovery_index",status="running",task_id=str(uuid4()),
        stats={"source_type":"edition","source_id":str(edition.pk),"source_revision":header["source_revision"]})
    children=[{"start":i,"end":i+1,"text":unit["text"][i:i+1],"normalized_text":unit["text"][i:i+1],
               "embedding_text":str(i),"token_count":1} for i in range(8)]
    monkeypatch.setattr(indexing,"embed_texts",lambda *a,**k:{"vectors":[[1.0]+[0.0]*383]})
    batches=[]
    monkeypatch.setattr(indexing,"meili",lambda method,path,payload:batches.append(payload) or {"taskUid":1})
    def wait(*args):
        assert DiscoveryDocument.objects.exclude(pk=docs[0].pk).filter(keyword_ready=True).count()==0
        if outcome=="failed":raise projection.DiscoveryIndexError("write_failed")
        if outcome=="superseded":ProcessingJob.objects.filter(pk=job.pk).update(task_id=str(uuid4()))
    monkeypatch.setattr(indexing,"wait_index_task",wait)
    if outcome in {"success","deadline"}:
        indexing._write_chunks(job,docs[0].generation,header,unit,children,deadline=0 if outcome=="deadline" else None)
    else:
        with pytest.raises(projection.DiscoveryIndexError):indexing._write_chunks(job,docs[0].generation,header,unit,children)
    assert len(batches)==1 and len(batches[0])==(1 if outcome=="deadline" else 8)
    assert DiscoveryDocument.objects.exclude(pk=docs[0].pk).filter(keyword_ready=True).count()==(8 if outcome=="success" else 1 if outcome=="deadline" else 0)
    if outcome=="success":
        indexing._write_chunks(job,docs[0].generation,header,unit,children)
        assert len(batches)==1


def test_one_unit_hash_is_reused_but_modified_text_is_still_rejected(monkeypatch):
    _,_,spans,docs=fixture_source(1)
    doc=docs[0]
    doc.pk=uuid4(); doc.start_offset=1; doc.text=doc.text[1:]; doc.save()
    calls=[]
    original=projection.fingerprint
    monkeypatch.setattr(projection,"fingerprint",lambda v:calls.append(v) or original(v))
    refs=[{"id":str(d.pk)} for d in DiscoveryDocument.objects.all()]
    with CaptureQueriesContext(connection) as sql:
        assert len(projection.validate_discovery_results("passages",refs,["public"]))==2
    assert "normalized_text" not in sql[0]["sql"]
    assert len(calls)==1
    EvidenceSpan.objects.filter(pk=spans[0].pk).update(original_text="changed")
    assert projection.validate_discovery_results("passages",refs,["public"])==[]


def test_storage_audit_counts_hardlinks_once_and_does_not_follow_links(tmp_path):
    left,right=tmp_path/"original",tmp_path/"public"
    left.mkdir();right.mkdir()
    (left/"file").write_bytes(b"original bytes")
    os.link(left/"file",right/"file")
    report=inspect_storage({"original":left,"public":right})
    assert sum(r["logical_bytes"] for r in report["roots"])==28
    assert sum(r["unique_bytes"] for r in report["roots"])==14
    assert report["files_deleted"]==0 and (left/"file").read_bytes()==b"original bytes"
    assert not inspect_storage({"original":left},max_entries=1)["complete"]


def test_backup_streams_original_bytes_without_staging_copy(tmp_path,settings,monkeypatch,admin_user):
    from distribution.models import BackupJob
    from distribution.tasks import create_backup_archive
    from tests.test_distribution_backup import _fake_dump
    settings.MEDIA_ROOT=tmp_path
    settings.NAS_BACKUP_ROOT=tmp_path/"backups"
    source=tmp_path/"archive"/"fixture.pdf"
    source.parent.mkdir()
    source.write_bytes(b"immutable original fixture")
    edition=Edition.objects.create(work=Work.objects.create(title="backup"))
    Asset.objects.create(edition=edition,kind="original",file="archive/fixture.pdf",
        sha256=hashlib.sha256(source.read_bytes()).hexdigest(),byte_size=source.stat().st_size)
    job=BackupJob.objects.create(requested_by=admin_user,destination_path=str(settings.NAS_BACKUP_ROOT),include_originals=True)
    monkeypatch.setattr("distribution.tasks.create_database_dump",_fake_dump)
    monkeypatch.setattr("distribution.tasks.applied_migration_heads",lambda:[])
    def reject_copy(*args,**kwargs):raise AssertionError("Backup must not stage a duplicate original")
    monkeypatch.setattr("shutil.copy2",reject_copy)
    monkeypatch.setattr("os.link",reject_copy)
    archive=create_backup_archive.run(str(job.pk))
    with tarfile.open(archive,"r:gz") as tar:
        assert tar.extractfile("originals/archive/fixture.pdf").read()==source.read_bytes()==b"immutable original fixture"
    assert source.stat().st_nlink==1
