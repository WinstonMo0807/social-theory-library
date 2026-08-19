from io import BytesIO
from unittest.mock import patch

from botocore.exceptions import ClientError
from django.db import IntegrityError, transaction
import pytest

from accounts.models import User
from catalog.models import Asset, Edition, Work
from ingestion.models import ProcessingJob, UploadBatch, UploadItem
from ingestion.services.r2_staging import (
    R2StagingError,
    apply_r2_cors_policy,
    cleanup_r2_staging_object,
    confirm_r2_part,
    import_r2_staging_object,
    recover_r2_staging_jobs,
)


MIB = 1024 * 1024


class FakeR2Client:
    def __init__(self):
        self.uploads = {}
        self.objects = {}
        self.aborted = []
        self.deleted = []
        self.fail_get = None
        self.fail_delete = None
        self.cors = None

    def create_multipart_upload(self, *, Bucket, Key, ContentType):
        upload_id = f"upload-{len(self.uploads) + 1}"
        self.uploads[upload_id] = {"bucket": Bucket, "key": Key, "parts": {}}
        return {"UploadId": upload_id}

    def generate_presigned_url(self, method, *, Params, ExpiresIn, HttpMethod):
        assert method == "upload_part"
        assert HttpMethod == "PUT"
        return f"https://r2.invalid/{Params['PartNumber']}?expires={ExpiresIn}"

    def list_parts(self, *, Bucket, Key, UploadId, **kwargs):
        if UploadId not in self.uploads:
            raise missing_error("NoSuchUpload", "ListParts")
        upload = self.uploads[UploadId]
        assert upload["bucket"] == Bucket
        assert upload["key"] == Key
        return {
            "Parts": [
                {"PartNumber": number, "ETag": row["etag"], "Size": len(row["payload"])}
                for number, row in sorted(upload["parts"].items())
            ],
            "IsTruncated": False,
        }

    def complete_multipart_upload(self, *, Bucket, Key, UploadId, MultipartUpload):
        upload = self.uploads.pop(UploadId)
        ordered = sorted(MultipartUpload["Parts"], key=lambda row: row["PartNumber"])
        self.objects[Key] = b"".join(
            upload["parts"][row["PartNumber"]]["payload"] for row in ordered
        )
        return {"ETag": '"multipart-final-etag"'}

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise missing_error("NoSuchKey", "HeadObject")
        return {"ContentLength": len(self.objects[Key]), "ETag": '"multipart-final-etag"'}

    def get_object(self, *, Bucket, Key):
        if self.fail_get:
            raise self.fail_get
        if Key not in self.objects:
            raise missing_error("NoSuchKey", "GetObject")
        return {"Body": BytesIO(self.objects[Key]), "ContentLength": len(self.objects[Key])}

    def abort_multipart_upload(self, *, Bucket, Key, UploadId):
        self.aborted.append((Key, UploadId))
        self.uploads.pop(UploadId, None)
        return {}

    def delete_object(self, *, Bucket, Key):
        if self.fail_delete:
            raise self.fail_delete
        self.deleted.append(Key)
        self.objects.pop(Key, None)
        return {}

    def put_part(self, item, number, payload, etag=None):
        etag = etag or f'"etag-{number}"'
        self.uploads[item.staging_upload_id]["parts"][number] = {
            "etag": etag,
            "payload": payload,
        }
        return etag

    def put_bucket_cors(self, *, Bucket, CORSConfiguration):
        self.cors = {"bucket": Bucket, "configuration": CORSConfiguration}
        return {}


def missing_error(code, operation):
    return ClientError(
        {
            "Error": {"Code": code, "Message": code},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        operation,
    )


@pytest.fixture
def r2_settings(settings):
    settings.R2_UPLOAD_STAGING_ENABLED = True
    settings.R2_ENDPOINT = "https://test-account.r2.cloudflarestorage.com"
    settings.R2_BUCKET = "library-upload-staging"
    settings.R2_ACCESS_KEY_ID = "test-access-key"
    settings.R2_SECRET_ACCESS_KEY = "test-secret-key"
    settings.R2_REGION = "auto"
    settings.R2_UPLOAD_PART_SIZE = 8 * MIB
    settings.R2_PRESIGNED_URL_TTL_SECONDS = 900
    settings.R2_MAX_ACTIVE_UPLOADS_PER_USER = 5
    settings.R2_SIGN_PART_BATCH_SIZE = 12
    settings.R2_IMPORT_CHUNK_BYTES = MIB
    settings.R2_CLEANUP_MAX_ATTEMPTS = 12
    return settings


def create_batch(user, expected_count=1):
    return UploadBatch.objects.create(created_by=user, expected_count=expected_count)


def init_session(api_client, user, batch, file_size, token="upload-token-123"):
    api_client.force_authenticate(user)
    return api_client.post(
        "/api/ingestion/uploads/r2/init/",
        {
            "batch_id": str(batch.id),
            "source_filename": "社会理论.pdf",
            "file_size": file_size,
            "file_last_modified": 1_700_000_000_000,
            "content_type": "application/pdf",
            "client_token": token,
        },
        format="json",
    )


@pytest.mark.django_db
def test_normal_multipart_upload_sorts_parts_and_allows_small_last_part(
    api_client,
    admin_user,
    r2_settings,
    django_capture_on_commit_callbacks,
):
    fake = FakeR2Client()
    batch = create_batch(admin_user)
    file_size = 8 * MIB + 3
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake), patch(
        "ingestion.services.r2_staging.queue_r2_staging_job"
    ) as queued:
        response = init_session(api_client, admin_user, batch, file_size)
        assert response.status_code == 201
        assert response.data["part_size"] == 8 * MIB
        assert response.data["total_parts"] == 2
        assert "staging_object_key" not in response.data
        assert "staging_upload_id" not in response.data
        session_id = response.data["upload_session_id"]
        item = UploadItem.objects.get(pk=session_id)
        assert item.staging_object_key == f"staging/{item.id}.pdf"

        signed = api_client.post(
            f"/api/ingestion/uploads/r2/{session_id}/parts/sign/",
            {"part_numbers": [2, 1]},
            format="json",
        )
        assert signed.status_code == 200
        assert [row["part_number"] for row in signed.data["parts"]] == [1, 2]
        assert signed.data["parts"][1]["size"] == 3

        first = b"%PDF-" + b"a" * (8 * MIB - 5)
        second = b"end"
        etag1 = fake.put_part(item, 1, first)
        etag2 = fake.put_part(item, 2, second)
        for number, payload, etag in [(1, first, etag1), (2, second, etag2)]:
            confirmed = api_client.post(
                f"/api/ingestion/uploads/r2/{session_id}/parts/confirm/",
                {"part_number": number, "etag": etag, "size": len(payload), "attempt": 1},
                format="json",
            )
            assert confirmed.status_code == 200

        with django_capture_on_commit_callbacks(execute=True):
            complete = api_client.post(
                f"/api/ingestion/uploads/r2/{session_id}/complete/",
                {
                    "parts": [
                        {"part_number": 2, "etag": etag2},
                        {"part_number": 1, "etag": etag1},
                    ]
                },
                format="json",
            )
        assert complete.status_code == 202
        assert complete.data["staging_status"] == UploadItem.StagingStatus.UPLOADED
        queued.assert_called_once()
        assert fake.objects[item.staging_object_key] == first + second


@pytest.mark.django_db
def test_etag_is_required_and_cross_user_sessions_are_hidden(
    api_client,
    admin_user,
    r2_settings,
):
    fake = FakeR2Client()
    other = User.objects.create_user(
        username="other-admin@example.org",
        email="other-admin@example.org",
        role=User.Role.ADMIN,
        password="Other-Admin-Password-2026",
    )
    batch = create_batch(admin_user)
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake):
        response = init_session(api_client, admin_user, batch, 7)
        item = UploadItem.objects.get(pk=response.data["upload_session_id"])
        fake.put_part(item, 1, b"%PDF-x", etag='"etag-1"')
        with pytest.raises(R2StagingError):
            confirm_r2_part(item, part_number=1, etag="", size=7)

        api_client.force_authenticate(other)
        hidden = api_client.get(f"/api/ingestion/uploads/r2/{item.id}/")
        assert hidden.status_code == 404
        sign = api_client.post(
            f"/api/ingestion/uploads/r2/{item.id}/parts/sign/",
            {"part_numbers": [1]},
            format="json",
        )
        assert sign.status_code == 404


@pytest.mark.django_db
def test_reader_without_upload_capability_cannot_create_session(
    api_client,
    reader_user,
    r2_settings,
):
    batch = create_batch(reader_user)
    response = init_session(api_client, reader_user, batch, 7)
    assert response.status_code == 403


def test_r2_cors_allows_browser_put_and_exposes_etag(r2_settings):
    fake = FakeR2Client()
    r2_settings.R2_UPLOAD_CORS_ALLOWED_ORIGINS = [
        "https://books.example.org",
        "http://localhost:3000",
    ]
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake):
        result = apply_r2_cors_policy()
    rule = fake.cors["configuration"]["CORSRules"][0]
    assert fake.cors["bucket"] == "library-upload-staging"
    assert rule["AllowedMethods"] == ["PUT"]
    assert rule["AllowedHeaders"] == ["Content-Type"]
    assert rule["ExposeHeaders"] == ["ETag"]
    assert result["allowed_origins"] == r2_settings.R2_UPLOAD_CORS_ALLOWED_ORIGINS


@pytest.mark.django_db
def test_invalid_object_key_is_rejected_by_database_constraint(admin_user):
    batch = create_batch(admin_user)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            UploadItem.objects.create(
                batch=batch,
                source_filename="bad.pdf",
                processing_token="bad-token-123",
                staging_backend=UploadItem.StagingBackend.R2,
                staging_status=UploadItem.StagingStatus.UPLOADING,
                staging_object_key="arbitrary/outside.pdf",
            )


@pytest.mark.django_db
def test_user_abort_is_persisted_even_when_r2_abort_fails(
    api_client,
    admin_user,
    r2_settings,
):
    fake = FakeR2Client()
    batch = create_batch(admin_user)
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake):
        response = init_session(api_client, admin_user, batch, 7)
        item = UploadItem.objects.get(pk=response.data["upload_session_id"])
        fake.uploads.pop(item.staging_upload_id)
        abort = api_client.post(f"/api/ingestion/uploads/r2/{item.id}/abort/", {}, format="json")
        assert abort.status_code == 200
        item.refresh_from_db()
        assert item.staging_status == UploadItem.StagingStatus.ABORTED


@pytest.mark.django_db
def test_r2_complete_then_stream_import_preserves_r2_until_pipeline_ready(
    admin_user,
    r2_settings,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    r2_settings.MEDIA_ROOT = tmp_path
    r2_settings.NAS_INCOMING_ROOT = tmp_path / "incoming"
    fake = FakeR2Client()
    batch = create_batch(admin_user)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="streamed.pdf",
        processing_token="stream-token-123",
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.UPLOADED,
        staging_object_key="staging/streamed.pdf",
        staging_upload_id="completed-upload",
        staging_file_size=17,
        staging_part_size=8 * MIB,
        staging_total_parts=1,
    )
    fake.objects[item.staging_object_key] = b"%PDF-streamed-pdf"
    item.staging_file_size = len(fake.objects[item.staging_object_key])
    item.save(update_fields=["staging_file_size", "updated_at"])
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake), patch(
        "ingestion.services.r2_staging.schedule_upload_item"
    ) as scheduled:
        with django_capture_on_commit_callbacks(execute=True):
            result = import_r2_staging_object(item.id)
    item.refresh_from_db()
    assert result["status"] == UploadItem.StagingStatus.IMPORTED
    assert item.staging_status == UploadItem.StagingStatus.IMPORTED
    assert item.byte_size == len(fake.objects[item.staging_object_key])
    assert item.sha256
    assert item.file
    assert fake.objects[item.staging_object_key]
    scheduled.assert_called_once_with(str(item.id))


@pytest.mark.django_db
def test_import_failure_and_database_failure_keep_staging_object(
    admin_user,
    r2_settings,
    tmp_path,
):
    r2_settings.MEDIA_ROOT = tmp_path
    r2_settings.NAS_INCOMING_ROOT = tmp_path / "incoming"
    fake = FakeR2Client()
    batch = create_batch(admin_user, expected_count=2)
    first = UploadItem.objects.create(
        batch=batch,
        source_filename="download-fail.pdf",
        processing_token="download-fail-123",
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.UPLOADED,
        staging_object_key="staging/download-fail.pdf",
        staging_upload_id="download-fail",
        staging_file_size=7,
        staging_part_size=8 * MIB,
        staging_total_parts=1,
    )
    fake.fail_get = ClientError(
        {"Error": {"Code": "SlowDown"}, "ResponseMetadata": {"HTTPStatusCode": 503}},
        "GetObject",
    )
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake):
        with pytest.raises(ClientError):
            import_r2_staging_object(first.id)
    first.refresh_from_db()
    assert first.staging_status == UploadItem.StagingStatus.IMPORT_FAILED

    fake.fail_get = None
    second_payload = b"%PDF-database-failure"
    second = UploadItem.objects.create(
        batch=batch,
        source_filename="database-fail.pdf",
        processing_token="database-fail-123",
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.UPLOADED,
        staging_object_key="staging/database-fail.pdf",
        staging_upload_id="database-fail",
        staging_file_size=len(second_payload),
        staging_part_size=8 * MIB,
        staging_total_parts=1,
    )
    fake.objects[second.staging_object_key] = second_payload
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake), patch(
        "ingestion.services.r2_staging.AuditEvent.objects.create",
        side_effect=RuntimeError("database write failed"),
    ):
        with pytest.raises(RuntimeError):
            import_r2_staging_object(second.id)
    second.refresh_from_db()
    assert second.staging_status == UploadItem.StagingStatus.IMPORT_FAILED
    assert second.staging_object_key in fake.objects
    assert not second.file


@pytest.mark.django_db
def test_cleanup_failure_is_pending_then_retry_succeeds_and_is_idempotent(
    admin_user,
    r2_settings,
):
    fake = FakeR2Client()
    batch = create_batch(admin_user)
    work = Work.objects.create(document_type="book", title="R2 cleanup")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file="archive/r2-cleanup.pdf",
        sha256="a" * 64,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="cleanup.pdf",
        processing_token="cleanup-token-123",
        file="incoming/cleanup.pdf",
        asset=asset,
        status=UploadItem.Status.READY,
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.CLEANUP_PENDING,
        staging_object_key="staging/cleanup.pdf",
        staging_upload_id="cleanup-upload",
    )
    fake.objects[item.staging_object_key] = b"%PDF-cleanup"
    fake.fail_delete = ClientError(
        {"Error": {"Code": "SlowDown"}, "ResponseMetadata": {"HTTPStatusCode": 503}},
        "DeleteObject",
    )
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake):
        with pytest.raises(ClientError):
            cleanup_r2_staging_object(item.id)
        item.refresh_from_db()
        assert item.staging_status == UploadItem.StagingStatus.CLEANUP_PENDING
        assert item.status == UploadItem.Status.READY
        fake.fail_delete = None
        result = cleanup_r2_staging_object(item.id)
        repeated = cleanup_r2_staging_object(item.id)
    item.refresh_from_db()
    assert result["status"] == UploadItem.StagingStatus.CLEANED
    assert repeated["idempotent"] is True
    assert item.staging_status == UploadItem.StagingStatus.CLEANED
    assert item.status == UploadItem.Status.READY
    assert item.file


@pytest.mark.django_db
def test_restart_recovery_requeues_uploaded_and_cleanup_pending_sessions(
    admin_user,
    r2_settings,
):
    batch = create_batch(admin_user, expected_count=2)
    uploaded = UploadItem.objects.create(
        batch=batch,
        source_filename="uploaded.pdf",
        processing_token="uploaded-token-123",
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.UPLOADED,
        staging_object_key="staging/uploaded.pdf",
        staging_upload_id="uploaded",
    )
    cleanup = UploadItem.objects.create(
        batch=batch,
        source_filename="cleanup.pdf",
        processing_token="cleanup-token-456",
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.CLEANUP_PENDING,
        staging_object_key="staging/cleanup.pdf",
        staging_upload_id="cleanup",
    )
    with patch("ingestion.services.r2_staging.dispatch_r2_staging_job", return_value=True):
        result = recover_r2_staging_jobs(limit=10)
    assert result == {"import_requeued": 1, "cleanup_requeued": 1}
    assert ProcessingJob.objects.filter(upload_item=uploaded, stats__phase="import").exists()
    assert ProcessingJob.objects.filter(upload_item=cleanup, stats__phase="cleanup").exists()


@pytest.mark.django_db
def test_lifecycle_deleted_object_is_reported_as_expired(
    admin_user,
    r2_settings,
    tmp_path,
):
    r2_settings.NAS_INCOMING_ROOT = tmp_path / "incoming"
    fake = FakeR2Client()
    batch = create_batch(admin_user)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="expired.pdf",
        processing_token="expired-token-123",
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.UPLOADED,
        staging_object_key="staging/expired.pdf",
        staging_upload_id="expired",
        staging_file_size=7,
        staging_part_size=8 * MIB,
        staging_total_parts=1,
    )
    with patch("ingestion.services.r2_staging.r2_client", return_value=fake):
        with pytest.raises(Exception):
            import_r2_staging_object(item.id)
    item.refresh_from_db()
    assert item.staging_status == UploadItem.StagingStatus.EXPIRED
    assert item.staging_error_code == "staging_object_expired"
