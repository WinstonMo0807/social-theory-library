"""Deferred acceptance definitions. No cleanup is run during implementation."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
import os
import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.test import APIClient
from catalog.models import Asset, Edition, Work
from distribution.models import StorageCleanupPlan
from distribution.storage_cleanup import scan, plan_payload, process_plan, execution_supported, retention_policy
from ingestion.models import ProcessingJob, UploadBatch, UploadItem

pytestmark = pytest.mark.django_db
URL = "/api/distribution/storage/commands/"


@pytest.fixture
def transient(superadmin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "library"
    settings.NAS_INCOMING_ROOT = tmp_path / "incoming"
    root = settings.NAS_INCOMING_ROOT / ".r2-imports"; root.mkdir(parents=True)
    content = b"%PDF-synthetic-permanent-original"
    work = Work.objects.create(title="清理边界合成样本", document_type="book")
    asset = Asset.objects.create(edition=Edition.objects.create(work=work), kind="original", sha256=sha256(content).hexdigest(), byte_size=len(content))
    asset.file.save("original.pdf", ContentFile(content), save=True)
    item = UploadItem.objects.create(batch=UploadBatch.objects.create(created_by=superadmin_user), source_filename="synthetic.pdf",
        status="ready", dispatch_status="completed", staging_backend="r2", staging_status="cleaned", asset=asset,
        sha256=asset.sha256, byte_size=len(content), staging_file_size=len(content))
    old = timezone.now()-timedelta(days=9)
    UploadItem.objects.filter(pk=item.pk).update(updated_at=old)
    path = root / f"{item.pk}.{uuid4().hex}.part"; path.write_bytes(content[:12]); os.utime(path,(old.timestamp(),old.timestamp()))
    return item, asset, path, content


def client_for(user):
    client=APIClient(); client.force_authenticate(user=user); client.credentials(HTTP_X_EDITOR_OWNER=str(user.pk)); return client


def test_scan_does_not_read_original_or_cloud_and_protects_active_or_unknown_files(superadmin_user, transient):
    item, asset, path, content = transient
    unrelated = path.parent / "unknown.part"; unrelated.write_bytes(b"keep")
    with patch("distribution.storage_cleanup.verify_cleanup_original", side_effect=AssertionError("Scan must not hash originals")):
        plan=scan(superadmin_user,uuid4())
        assert len(plan.manifest)==1 and plan.scan_summary["protected"]==1
        assert str(path.parent) not in str(plan_payload(plan)) and asset.file.name not in str(plan_payload(plan))
        ProcessingJob.objects.create(job_type="r2_staging",status="running",upload_item=item)
        protected=scan(superadmin_user,uuid4())
        assert not protected.manifest
    assert path.exists() and unrelated.exists()


def test_confirmation_versions_policy_and_receipts_require_owner(superadmin_user, admin_user, transient):
    plan=scan(superadmin_user,uuid4()); client=client_for(superadmin_user)
    detail=f"/api/distribution/storage/cleanup/{plan.pk}/"
    assert client_for(admin_user).get(detail).status_code==403
    assert APIClient().get(detail).status_code in (401,403)
    assert client.get(detail)["Cache-Control"]=="private, no-store"
    body={"operation":"queue_cleanup","request_id":str(uuid4()),"cleanup_id":str(plan.pk),"expected_version":plan.updated_at.isoformat(),
        "cleanup_items":[plan.manifest[0]["id"]],"confirmation":"different count"}
    with patch("distribution.storage_cleanup.execution_supported",return_value=True),patch("distribution.storage_tasks.enqueue_storage_cleanup"):
        assert client.post(URL,body,format="json").status_code==400
        body["confirmation"]="清理 1 个临时文件"
        accepted=client.post(URL,body,format="json"); assert accepted.status_code==200
        assert client.post(URL,body,format="json").data==accepted.data
        assert client.post(URL,{**body,"cleanup_items":["f"*24]},format="json").status_code==409
        assert client.post(URL,{"operation":"scan_cleanup","request_id":str(uuid4())},format="json").status_code==409
    plan.refresh_from_db()
    stopped=client.post(URL,{"operation":"cancel_cleanup","request_id":str(uuid4()),"cleanup_id":str(plan.pk),"expected_version":plan.updated_at.isoformat()},format="json")
    assert stopped.status_code==200
    with patch("distribution.storage_cleanup.delete_transient",side_effect=AssertionError("Cancelled task must not delete")):
        process_plan(plan.pk)
    assert transient[2].exists()
    before=retention_policy()
    changed=client.post(URL,{"operation":"save_retention","request_id":str(uuid4()),"temporary_days":30,"expected_version":before["version"]},format="json")
    assert changed.status_code==200 and retention_policy()["temporary_days"]==30
    assert client.post(URL,{"operation":"save_retention","request_id":str(uuid4()),"temporary_days":10,"expected_version":before["version"]},format="json").status_code==409
    assert transient[2].exists()


@pytest.mark.skipif(not execution_supported(),reason="Protected deletion requires POSIX directory descriptors")
@pytest.mark.parametrize("damage",[None,"original","temporary"])
def test_worker_only_unlinks_exact_selected_transient_and_preserves_original(superadmin_user, transient, damage):
    item,asset,path,content=transient
    plan=scan(superadmin_user,uuid4()); plan.selected=[plan.manifest[0]["id"]];plan.status="queued";plan.save()
    unrelated=path.parent/"unselected.keep";unrelated.write_bytes(b"keep")
    if damage=="original":
        Path(asset.file.path).write_bytes(b"x"*len(content))
    elif damage=="temporary":
        path.write_bytes(b"changed")
    with patch("ingestion.services.r2_staging.r2_client",side_effect=AssertionError("Local cleanup never calls cloud")):
        process_plan(plan.pk)
    plan.refresh_from_db()
    assert Path(asset.file.path).exists() and unrelated.read_bytes()==b"keep"
    assert path.exists()==bool(damage)
    assert plan.status==("partial" if damage else "completed")
    assert plan_payload(plan)["deleted_count"]==(0 if damage else 1)
    if not damage:
        assert Path(asset.file.path).read_bytes()==content
