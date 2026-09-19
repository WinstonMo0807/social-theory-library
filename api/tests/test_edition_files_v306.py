from hashlib import sha256
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from catalog.models import Asset, CatalogPublicationRevision, CatalogingSession, Edition, Work
from catalog.services.cataloging_sessions import open_cataloging_session
from catalog.services.edition_files import EditionFileError, submit_edition_file
from ingestion.models import AuditEvent, FieldLock, UploadBatch, UploadItem
from ingestion.services.pipeline import _create_or_update_catalog

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n% v306 isolated upload signature fixture\n%%EOF"


@pytest.fixture(autouse=True)
def isolated_files(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STORAGES = {**settings.STORAGES, "intake": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(tmp_path / "incoming")}}}
    with patch("catalog.services.edition_files.schedule_upload_item") as schedule:
        yield schedule


def upload(content=PDF):
    return SimpleUploadedFile("edition-test.pdf", content, content_type="application/pdf")


def submit(edition, actor, **kwargs):
    return submit_edition_file(edition_id=edition.pk, actor=actor, uploaded=upload(),
                              expected_updated_at=edition.updated_at.isoformat(), **kwargs)


def published_with_file(actor):
    edition = Edition.objects.create(work=Work.objects.create(title="稳定阅读版本", language="zh-CN"), state="published")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid", sha256=sha256(PDF).hexdigest(), access_status="registered")
    asset.file.save("old.pdf", ContentFile(PDF), save=True)
    revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active", metadata_ready=True,
        reader_asset=asset, snapshot={"work": {"title": edition.work.title}}, content_fingerprint="fixture", activated_at=timezone.now())
    edition.active_catalog_revision = revision
    edition.save(update_fields=["active_catalog_revision", "updated_at"])
    return edition, asset, revision


def test_manual_supplement_preserves_session_and_exact_edition(admin_user, isolated_files):
    session, _ = open_cataloging_session(actor=admin_user, source_type="manual", title="保留手工书目")
    edition = session.edition
    item, created = submit(edition, admin_user, action="supplement", request_key=uuid4())
    assert created and item.edition_id == edition.pk
    assert item.batch.source == "edition-supplement"
    assert not item.batch.external_enrichment_enabled
    session.refresh_from_db()
    assert session.source_type == "manual" and session.upload_item_id is None
    assert Work.objects.count() == Edition.objects.count() == CatalogingSession.objects.count() == 1
    isolated_files.assert_called_once_with(str(item.pk))
    _create_or_update_catalog(item, {"title": "自动结果不能替换手工值", "language": "en"}, [], "")
    edition.work.refresh_from_db()
    assert edition.work.title == "保留手工书目"


def test_file_retry_is_idempotent_before_stale_context_check(admin_user, isolated_files):
    edition = Edition.objects.create(work=Work.objects.create(title="幂等"), publication_mode="bibliographic")
    key = uuid4()
    first, _ = submit(edition, admin_user, action="supplement", request_key=key)
    Edition.objects.filter(pk=edition.pk).update(updated_at=timezone.now())
    replay, created = submit(edition, admin_user, action="supplement", request_key=key)
    assert replay.pk == first.pk and not created
    assert UploadItem.objects.count() == UploadBatch.objects.count() == 1
    assert AuditEvent.objects.filter(action="edition_pdf_supplement_requested").count() == 1
    assert isolated_files.call_count == 1


def test_same_request_key_cannot_cross_edition_or_file(admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="请求一"))
    first, _ = submit(edition, admin_user, action="supplement", request_key=uuid4())
    other = Edition.objects.create(work=edition.work, is_primary=False)
    with pytest.raises(EditionFileError, match="不能用于"):
        submit(other, admin_user, action="supplement", request_key=first.pk)
    with pytest.raises(EditionFileError, match="不能用于"):
        submit_edition_file(edition_id=edition.pk, actor=admin_user, uploaded=upload(PDF+b"other"), action="supplement", request_key=first.pk)


def test_replace_preserves_locks_old_bytes_and_active_snapshot(admin_user):
    edition, asset, revision = published_with_file(admin_user)
    lock = FieldLock.objects.create(edition=edition, field_name="title", locked_value="人工原值", locked_by=admin_user, reason="保留原理由")
    item, _ = submit(edition, admin_user, action="replace", expected_reader_asset_id=asset.pk)
    assert item.replacement_of_asset_id == asset.pk
    assert item.batch.access_policy == "registered"
    edition.refresh_from_db(); asset.refresh_from_db(); lock.refresh_from_db()
    assert edition.active_catalog_revision_id == revision.pk and asset.is_current
    assert asset.file.read() == PDF
    assert lock.locked_value == "人工原值" and lock.reason == "保留原理由"
    assert FieldLock.objects.count() == 1


def test_replacement_rejects_wrong_reader_or_unready_publication(admin_user):
    edition, asset, _ = published_with_file(admin_user)
    with pytest.raises(EditionFileError, match="阅读文件已变化"):
        submit(edition, admin_user, action="replace", request_key=uuid4(), expected_reader_asset_id=uuid4())
    Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=None)
    edition.refresh_from_db()
    with pytest.raises(EditionFileError, match="没有正在公开"):
        submit(edition, admin_user, action="replace", expected_reader_asset_id=asset.pk)
    assert not UploadItem.objects.exists()


def test_new_file_requires_current_context_and_valid_signature(admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="并发保护"))
    with pytest.raises(EditionFileError, match="已变化"):
        submit_edition_file(edition_id=edition.pk, actor=admin_user, uploaded=upload(), action="supplement", request_key=uuid4())
    with pytest.raises(EditionFileError, match="不是 PDF"):
        submit_edition_file(edition_id=edition.pk, actor=admin_user, uploaded=upload(b"not-pdf"), action="supplement")
    assert UploadBatch.objects.count() == 0


def test_duplicate_in_another_edition_never_rebinds_manual_identity(admin_user):
    target = Edition.objects.create(work=Work.objects.create(title="手工身份不可换书"))
    other = Edition.objects.create(work=Work.objects.create(title="文件已在另一版本"))
    Asset.objects.create(edition=other, kind="original", sha256=sha256(PDF).hexdigest())
    with pytest.raises(EditionFileError, match="不会自动改绑"):
        submit(target, admin_user, action="supplement", request_key=uuid4())
    assert not UploadItem.objects.exists()
    target.refresh_from_db()
    assert target.work.title == "手工身份不可换书"


def test_edition_file_http_permission_confirm_and_retry(api_client, admin_user, reader_user):
    edition = Edition.objects.create(work=Work.objects.create(title="接口操作"))
    url = f"/api/catalog/admin/editions/{edition.pk}/files/"
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, {}).status_code == 403
    api_client.force_authenticate(admin_user)
    key = str(uuid4())
    def payload(confirm=True):
        return {"action":"supplement", "file":upload(), "request_key":key,
                "expected_updated_at":edition.updated_at.isoformat(), "confirm":confirm}
    assert api_client.post(url, payload(False), format="multipart").status_code == 400
    first = api_client.post(url, payload(), format="multipart")
    assert first.status_code == 202, first.data
    again = api_client.post(url, payload(), format="multipart")
    assert again.status_code == 200 and again.data["created"] is False
    assert again.data["edition_id"] == str(edition.pk)
    assert "#file" in again.data["workbench_url"]


def test_finished_upload_with_pending_public_file_blocks_a_second_replacement(admin_user):
    edition, asset, revision = published_with_file(admin_user)
    first, _ = submit(edition, admin_user, action="replace", request_key=uuid4(), expected_reader_asset_id=asset.pk)
    first.status = "published"  # Pipeline command accepted; public activation still pending.
    first.save(update_fields=["status"])
    staged = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid", is_current=False,
                                   sha256=sha256(PDF + b"staged").hexdigest(), version=2)
    pending = CatalogPublicationRevision.objects.create(edition=edition, revision=2, status="preparing", metadata_ready=True,
                                                         reader_asset=staged, snapshot={"work": {"title": edition.work.title}}, content_fingerprint="pending-test")
    with pytest.raises(EditionFileError, match="另一阅读文件"):
        submit_edition_file(edition_id=edition.pk, actor=admin_user, uploaded=upload(PDF + b"second"), action="replace",
                            request_key=uuid4(), expected_updated_at=edition.updated_at.isoformat(), expected_reader_asset_id=asset.pk)
    replay, created = submit(edition, admin_user, action="replace", request_key=first.pk, expected_reader_asset_id=asset.pk)
    assert replay.pk == first.pk and not created
    assert UploadItem.objects.filter(edition=edition).count() == 1
    assert CatalogPublicationRevision.objects.get(pk=pending.pk).status == "preparing"
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == revision.pk
