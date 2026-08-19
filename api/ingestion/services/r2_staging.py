"""Cloudflare R2 staging for browser-direct PDF multipart uploads.

R2 is intentionally temporary. PostgreSQL owns the upload session and the
existing intake FileField/NAS pipeline remains the permanent storage path.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import math
import re
import uuid
from urllib.parse import urlparse

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalog.services.text import sanitize_unicode
from ingestion.models import AuditEvent, ProcessingJob, UploadBatch, UploadItem

from .dispatch import schedule_upload_item
from .files import store_path_in_file_field


MIN_R2_PART_SIZE = 5 * 1024 * 1024
MAX_R2_PARTS = 10_000
ETAG_RE = re.compile(r'^"?[A-Za-z0-9][A-Za-z0-9:_-]{0,199}"?$')
CONCURRENT_STAGING_STATUSES = {
    UploadItem.StagingStatus.UPLOADING,
    UploadItem.StagingStatus.UPLOADED,
    UploadItem.StagingStatus.IMPORTING,
}
PIPELINE_READY_FOR_CLEANUP = {
    UploadItem.Status.NEEDS_REVIEW,
    UploadItem.Status.READY,
    UploadItem.Status.PUBLISHED,
}


class R2StagingError(RuntimeError):
    error_code = "r2_staging_error"
    retryable = False


class R2ConfigurationError(R2StagingError):
    error_code = "r2_not_configured"


class R2RetryableError(R2StagingError):
    error_code = "r2_temporarily_unavailable"
    retryable = True


class R2StagingExpired(R2StagingError):
    error_code = "staging_object_expired"


def _error_code(exc: Exception) -> str:
    if isinstance(exc, R2StagingError):
        return exc.error_code
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code") or "r2_client_error")[:120]
    return exc.__class__.__name__[:120]


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code") or "R2ClientError")
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return f"R2 请求失败，code={code}，status={status or 'unknown'}。"
    if isinstance(exc, BotoCoreError):
        return f"R2 连接失败，category={exc.__class__.__name__}。"
    return str(exc)[:1000]


def _is_missing(exc: Exception) -> bool:
    return isinstance(exc, ClientError) and str(
        exc.response.get("Error", {}).get("Code") or ""
    ) in {"NoSuchKey", "NoSuchUpload", "404", "NotFound"}


def _configured() -> bool:
    return bool(
        settings.R2_UPLOAD_STAGING_ENABLED
        and settings.R2_ENDPOINT
        and settings.R2_BUCKET
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
    )


def r2_staging_status() -> dict:
    return {
        "enabled": bool(settings.R2_UPLOAD_STAGING_ENABLED),
        "configured": _configured(),
        "bucket_configured": bool(settings.R2_BUCKET),
        "endpoint_configured": bool(settings.R2_ENDPOINT),
        "credential_configured": bool(
            settings.R2_ACCESS_KEY_ID and settings.R2_SECRET_ACCESS_KEY
        ),
        "part_size": settings.R2_UPLOAD_PART_SIZE,
        "presigned_url_ttl_seconds": settings.R2_PRESIGNED_URL_TTL_SECONDS,
        "secret_values_exposed": False,
    }


def r2_cors_policy() -> dict:
    origins = list(dict.fromkeys(settings.R2_UPLOAD_CORS_ALLOWED_ORIGINS))
    if not origins:
        raise R2ConfigurationError("R2 upload CORS 没有允许的浏览器 origin。")
    return {
        "CORSRules": [
            {
                "AllowedOrigins": origins,
                "AllowedMethods": ["PUT"],
                "AllowedHeaders": ["Content-Type"],
                "ExposeHeaders": ["ETag"],
                "MaxAgeSeconds": 3600,
            }
        ]
    }


def apply_r2_cors_policy() -> dict:
    policy = r2_cors_policy()
    r2_client().put_bucket_cors(
        Bucket=settings.R2_BUCKET,
        CORSConfiguration=policy,
    )
    return {
        "bucket": settings.R2_BUCKET,
        "allowed_origins": policy["CORSRules"][0]["AllowedOrigins"],
        "allowed_methods": ["PUT"],
        "expose_headers": ["ETag"],
    }


def _validate_configuration() -> None:
    if not _configured():
        raise R2ConfigurationError("R2 PDF 上传中转尚未配置。")
    parsed = urlparse(settings.R2_ENDPOINT)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not hostname:
        raise R2ConfigurationError("R2 endpoint 必须是 HTTPS S3 API 地址。")
    if not hostname.endswith(".r2.cloudflarestorage.com") and not settings.DEBUG:
        raise R2ConfigurationError("生产 R2 endpoint 不是允许的 Cloudflare S3 API 地址。")
    if settings.R2_UPLOAD_PART_SIZE < MIN_R2_PART_SIZE:
        raise R2ConfigurationError("R2 part size 不能低于 5 MiB。")


def r2_client():
    _validate_configuration()
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT,
        region_name=settings.R2_REGION,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            retries={"mode": "standard", "max_attempts": 3},
        ),
    )


def _normalize_etag(value: str) -> str:
    value = str(value or "").strip()
    if not value or "\r" in value or "\n" in value or not ETAG_RE.fullmatch(value):
        raise R2StagingError("UploadPart 响应缺少有效 ETag。")
    return value if value.startswith('"') else f'"{value}"'


def _part_size(item: UploadItem, part_number: int) -> int:
    start = (part_number - 1) * item.staging_part_size
    return max(0, min(item.staging_part_size, item.staging_file_size - start))


def _parts_by_number(item: UploadItem) -> dict[int, dict]:
    parts = {}
    for row in item.staging_parts or []:
        try:
            number = int(row.get("part_number"))
            etag = _normalize_etag(row.get("etag"))
        except (AttributeError, TypeError, ValueError, R2StagingError):
            continue
        if 1 <= number <= item.staging_total_parts:
            parts[number] = {
                "part_number": number,
                "etag": etag,
                "size": int(row.get("size") or _part_size(item, number)),
            }
    return parts


def serialize_staging_session(item: UploadItem) -> dict:
    completed = sorted(_parts_by_number(item).values(), key=lambda row: row["part_number"])
    return {
        "upload_session_id": str(item.id),
        "batch_id": str(item.batch_id),
        "source_filename": item.source_filename,
        "file_size": item.staging_file_size,
        "file_last_modified": item.staging_file_last_modified,
        "part_size": item.staging_part_size,
        "total_parts": item.staging_total_parts,
        "completed_parts": completed,
        "staging_status": item.staging_status,
        "ingestion_status": item.status,
        "stage_progress": item.stage_progress,
        "error_code": item.staging_error_code or item.error_code,
        "error_message": item.staging_error_message or item.error_message,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "staging_completed_at": item.staging_completed_at,
        "staging_imported_at": item.staging_imported_at,
        "staging_cleanup_completed_at": item.staging_cleanup_completed_at,
        "can_resume_upload": item.staging_status == UploadItem.StagingStatus.UPLOADING,
        "can_abort": item.staging_status == UploadItem.StagingStatus.UPLOADING,
        "can_retry_import": item.staging_status == UploadItem.StagingStatus.IMPORT_FAILED,
    }


def list_user_staging_sessions(user, *, limit: int = 100):
    return (
        UploadItem.objects.select_related("batch")
        .filter(batch__created_by=user, staging_backend=UploadItem.StagingBackend.R2)
        .order_by("-created_at")[: max(1, min(limit, 200))]
    )


def _owned_batch(batch_id, user, *, lock: bool = False) -> UploadBatch:
    queryset = UploadBatch.objects
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=batch_id, created_by=user)
    except UploadBatch.DoesNotExist as exc:
        raise R2StagingError("上传批次不存在或不属于当前账户。") from exc


def create_r2_upload(
    *,
    batch_id,
    user,
    source_filename: str,
    file_size: int,
    file_last_modified: int,
    client_token: str,
    request_ip: str | None = None,
) -> tuple[UploadItem, bool]:
    _validate_configuration()
    source_filename = Path(sanitize_unicode(source_filename)).name[:800]
    if not source_filename or Path(source_filename).suffix.casefold() != ".pdf":
        raise R2StagingError("只允许上传 PDF。")
    if file_size < 5 or file_size > settings.MAX_UPLOAD_BYTES:
        raise R2StagingError("PDF 大小不在允许范围内。")
    if not re.fullmatch(r"[A-Za-z0-9-]{8,80}", client_token or ""):
        raise R2StagingError("缺少有效的文件上传标识。")

    with transaction.atomic():
        batch = _owned_batch(batch_id, user, lock=True)
        existing = batch.items.filter(processing_token=client_token).first()
        if existing:
            if existing.staging_backend != UploadItem.StagingBackend.R2:
                raise R2StagingError("该上传标识已被旧上传任务使用。")
            return existing, False
        active_count = UploadItem.objects.filter(
            batch__created_by=user,
            staging_backend=UploadItem.StagingBackend.R2,
            staging_status__in=CONCURRENT_STAGING_STATUSES,
        ).count()
        if active_count >= settings.R2_MAX_ACTIVE_UPLOADS_PER_USER:
            raise R2StagingError("当前账户同时进行的 PDF 上传已达到上限。")
        if batch.items.count() >= batch.expected_count:
            raise R2StagingError("该批次已达到预定文件数量。")
        item_id = uuid.uuid4()
        part_size = settings.R2_UPLOAD_PART_SIZE
        total_parts = math.ceil(file_size / part_size)
        if total_parts < 1 or total_parts > MAX_R2_PARTS:
            raise R2StagingError("PDF 分片数量超出允许范围。")
        item = UploadItem.objects.create(
            id=item_id,
            batch=batch,
            source_filename=source_filename,
            processing_token=client_token,
            byte_size=0,
            staging_backend=UploadItem.StagingBackend.R2,
            staging_status=UploadItem.StagingStatus.UPLOADING,
            staging_object_key=f"staging/{item_id}.pdf",
            staging_file_size=file_size,
            staging_file_last_modified=max(0, file_last_modified),
            staging_part_size=part_size,
            staging_total_parts=total_parts,
            dispatch_status=UploadItem.DispatchStatus.PENDING,
        )

    try:
        response = r2_client().create_multipart_upload(
            Bucket=settings.R2_BUCKET,
            Key=item.staging_object_key,
            ContentType="application/pdf",
        )
        upload_id = str(response.get("UploadId") or "")
        if not upload_id:
            raise R2RetryableError("R2 没有返回 multipart upload ID。")
    except Exception:
        UploadItem.objects.filter(pk=item.id, staging_upload_id="").delete()
        raise

    try:
        with transaction.atomic():
            item = UploadItem.objects.select_for_update().get(pk=item.id)
            item.staging_upload_id = upload_id
            item.save(update_fields=["staging_upload_id", "updated_at"])
            AuditEvent.objects.create(
                actor=user,
                action="r2_staging_upload_created",
                object_type="UploadItem",
                object_id=str(item.id),
                after={
                    "batch_id": str(item.batch_id),
                    "file_size": file_size,
                    "part_size": part_size,
                    "total_parts": total_parts,
                    "object_namespace": "staging/",
                },
                request_ip=request_ip,
            )
    except Exception:
        try:
            r2_client().abort_multipart_upload(
                Bucket=settings.R2_BUCKET,
                Key=item.staging_object_key,
                UploadId=upload_id,
            )
        except Exception:
            pass
        raise
    return item, True


def sign_r2_parts(item: UploadItem, part_numbers: list[int]) -> list[dict]:
    if item.staging_status != UploadItem.StagingStatus.UPLOADING:
        raise R2StagingError("该上传会话当前不能生成 part URL。")
    unique_numbers = sorted(set(int(value) for value in part_numbers))
    if not unique_numbers or len(unique_numbers) > settings.R2_SIGN_PART_BATCH_SIZE:
        raise R2StagingError("请求的 part 数量无效。")
    if any(value < 1 or value > item.staging_total_parts for value in unique_numbers):
        raise R2StagingError("partNumber 超出该上传会话范围。")
    client = r2_client()
    return [
        {
            "part_number": number,
            "size": _part_size(item, number),
            "url": client.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": settings.R2_BUCKET,
                    "Key": item.staging_object_key,
                    "UploadId": item.staging_upload_id,
                    "PartNumber": number,
                },
                ExpiresIn=settings.R2_PRESIGNED_URL_TTL_SECONDS,
                HttpMethod="PUT",
            ),
            "expires_in": settings.R2_PRESIGNED_URL_TTL_SECONDS,
        }
        for number in unique_numbers
    ]


def confirm_r2_part(item: UploadItem, *, part_number: int, etag: str, size: int) -> UploadItem:
    if item.staging_status != UploadItem.StagingStatus.UPLOADING:
        raise R2StagingError("该上传会话当前不能确认 part。")
    if part_number < 1 or part_number > item.staging_total_parts:
        raise R2StagingError("partNumber 超出该上传会话范围。")
    expected_size = _part_size(item, part_number)
    if size != expected_size:
        raise R2StagingError("part 字节数与上传清单不一致。")
    etag = _normalize_etag(etag)
    with transaction.atomic():
        locked = UploadItem.objects.select_for_update().get(pk=item.pk)
        parts = _parts_by_number(locked)
        parts[part_number] = {
            "part_number": part_number,
            "etag": etag,
            "size": size,
        }
        locked.staging_parts = sorted(parts.values(), key=lambda row: row["part_number"])
        locked.staging_error_code = ""
        locked.staging_error_message = ""
        locked.save(
            update_fields=[
                "staging_parts",
                "staging_error_code",
                "staging_error_message",
                "updated_at",
            ]
        )
        return locked


def _remote_parts(item: UploadItem) -> list[dict]:
    client = r2_client()
    marker = None
    rows = []
    while True:
        params = {
            "Bucket": settings.R2_BUCKET,
            "Key": item.staging_object_key,
            "UploadId": item.staging_upload_id,
        }
        if marker:
            params["PartNumberMarker"] = marker
        response = client.list_parts(**params)
        for row in response.get("Parts") or []:
            number = int(row["PartNumber"])
            rows.append(
                {
                    "part_number": number,
                    "etag": _normalize_etag(row.get("ETag")),
                    "size": int(row.get("Size") or _part_size(item, number)),
                }
            )
        if not response.get("IsTruncated"):
            return sorted(rows, key=lambda row: row["part_number"])
        marker = response.get("NextPartNumberMarker")


def reconcile_r2_parts(item: UploadItem) -> UploadItem:
    if item.staging_status != UploadItem.StagingStatus.UPLOADING:
        return item
    try:
        parts = _remote_parts(item)
    except Exception as exc:
        if _is_missing(exc):
            UploadItem.objects.filter(pk=item.pk).update(
                staging_status=UploadItem.StagingStatus.EXPIRED,
                staging_error_code=R2StagingExpired.error_code,
                staging_error_message="R2 multipart upload 已不存在，可能已被 Lifecycle 清理。",
                updated_at=timezone.now(),
            )
            return UploadItem.objects.get(pk=item.pk)
        raise
    UploadItem.objects.filter(pk=item.pk).update(
        staging_parts=parts,
        updated_at=timezone.now(),
    )
    return UploadItem.objects.get(pk=item.pk)


def _submitted_parts(item: UploadItem, submitted: list[dict]) -> list[dict]:
    rows = {}
    for row in submitted:
        try:
            number = int(row.get("part_number"))
            etag = _normalize_etag(row.get("etag"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise R2StagingError("CompleteMultipartUpload parts 参数无效。") from exc
        if number in rows or number < 1 or number > item.staging_total_parts:
            raise R2StagingError("CompleteMultipartUpload partNumber 重复或越界。")
        rows[number] = {"part_number": number, "etag": etag}
    expected = list(range(1, item.staging_total_parts + 1))
    if sorted(rows) != expected:
        raise R2StagingError("CompleteMultipartUpload 缺少 part。")
    return [rows[number] for number in expected]


def _head_completed_object(item: UploadItem) -> dict:
    try:
        response = r2_client().head_object(
            Bucket=settings.R2_BUCKET,
            Key=item.staging_object_key,
        )
    except Exception as exc:
        if _is_missing(exc):
            raise R2StagingExpired("R2 staging object 已被 Lifecycle 删除。") from exc
        raise
    if int(response.get("ContentLength") or -1) != item.staging_file_size:
        raise R2StagingError("R2 完整对象大小与原始 PDF 不一致。")
    return response


def complete_r2_upload(item: UploadItem, submitted: list[dict]) -> tuple[UploadItem, bool]:
    if item.staging_status in {
        UploadItem.StagingStatus.UPLOADED,
        UploadItem.StagingStatus.IMPORTING,
        UploadItem.StagingStatus.IMPORTED,
        UploadItem.StagingStatus.IMPORT_FAILED,
        UploadItem.StagingStatus.CLEANUP_PENDING,
        UploadItem.StagingStatus.CLEANED,
    }:
        _head_completed_object(item) if item.staging_status == UploadItem.StagingStatus.UPLOADED else None
        return item, False
    if item.staging_status != UploadItem.StagingStatus.UPLOADING:
        raise R2StagingError("该上传会话当前不能完成 multipart upload。")
    client_parts = _submitted_parts(item, submitted)
    try:
        remote_parts = _remote_parts(item)
    except Exception as exc:
        if not _is_missing(exc):
            raise
        # The completion response may have been lost after R2 committed it.
        _head_completed_object(item)
        remote_parts = [
            {
                "part_number": row["part_number"],
                "etag": row["etag"],
                "size": _part_size(item, row["part_number"]),
            }
            for row in client_parts
        ]
    else:
        remote_map = {row["part_number"]: row for row in remote_parts}
        for row in client_parts:
            remote = remote_map.get(row["part_number"])
            if remote is None or remote["etag"] != row["etag"]:
                raise R2StagingError("浏览器提交的 ETag 与 R2 part 不一致。")
        r2_client().complete_multipart_upload(
            Bucket=settings.R2_BUCKET,
            Key=item.staging_object_key,
            UploadId=item.staging_upload_id,
            MultipartUpload={
                "Parts": [
                    {"PartNumber": row["part_number"], "ETag": row["etag"]}
                    for row in remote_parts
                ]
            },
        )
        _head_completed_object(item)

    with transaction.atomic():
        locked = UploadItem.objects.select_for_update().get(pk=item.pk)
        if locked.staging_status == UploadItem.StagingStatus.UPLOADING:
            locked.staging_status = UploadItem.StagingStatus.UPLOADED
            locked.staging_parts = remote_parts
            locked.staging_completed_at = timezone.now()
            locked.staging_error_code = ""
            locked.staging_error_message = ""
            locked.save(
                update_fields=[
                    "staging_status",
                    "staging_parts",
                    "staging_completed_at",
                    "staging_error_code",
                    "staging_error_message",
                    "updated_at",
                ]
            )
            transaction.on_commit(lambda: queue_r2_staging_job(locked, phase="import"))
        return locked, True


def abort_r2_upload(item: UploadItem, *, actor=None, request_ip: str | None = None) -> UploadItem:
    if item.staging_status == UploadItem.StagingStatus.ABORTED:
        return item
    if item.staging_status != UploadItem.StagingStatus.UPLOADING:
        raise R2StagingError("只有尚未完成的 multipart upload 可以取消。")
    abort_error = None
    try:
        r2_client().abort_multipart_upload(
            Bucket=settings.R2_BUCKET,
            Key=item.staging_object_key,
            UploadId=item.staging_upload_id,
        )
    except Exception as exc:
        abort_error = exc
    with transaction.atomic():
        locked = UploadItem.objects.select_for_update().get(pk=item.pk)
        locked.staging_status = UploadItem.StagingStatus.ABORTED
        locked.staging_error_code = _error_code(abort_error) if abort_error else ""
        locked.staging_error_message = _safe_error_message(abort_error) if abort_error else ""
        locked.save(
            update_fields=[
                "staging_status",
                "staging_error_code",
                "staging_error_message",
                "updated_at",
            ]
        )
        AuditEvent.objects.create(
            actor=actor,
            action="r2_staging_upload_aborted",
            object_type="UploadItem",
            object_id=str(locked.id),
            after={"abort_request_succeeded": abort_error is None},
            request_ip=request_ip,
        )
        return locked


def _mark_import_failure(item_id, exc: Exception) -> None:
    status = (
        UploadItem.StagingStatus.EXPIRED
        if isinstance(exc, R2StagingExpired) or _is_missing(exc)
        else UploadItem.StagingStatus.IMPORT_FAILED
    )
    UploadItem.objects.filter(pk=item_id).update(
        staging_status=status,
        staging_error_code=(
            R2StagingExpired.error_code if status == UploadItem.StagingStatus.EXPIRED else _error_code(exc)
        ),
        staging_error_message=_safe_error_message(exc),
        updated_at=timezone.now(),
    )


def import_r2_staging_object(item_id) -> dict:
    with transaction.atomic():
        item = UploadItem.objects.select_for_update().select_related("batch").get(pk=item_id)
        if item.staging_status in {
            UploadItem.StagingStatus.IMPORTED,
            UploadItem.StagingStatus.CLEANUP_PENDING,
            UploadItem.StagingStatus.CLEANED,
        } and item.file:
            schedule_upload_item(str(item.id))
            return {"id": str(item.id), "status": item.staging_status, "idempotent": True}
        if item.staging_status not in {
            UploadItem.StagingStatus.UPLOADED,
            UploadItem.StagingStatus.IMPORT_FAILED,
            UploadItem.StagingStatus.IMPORTING,
        }:
            raise R2StagingError("该上传会话当前不能导入正式存储。")
        item.staging_status = UploadItem.StagingStatus.IMPORTING
        item.staging_import_attempts += 1
        item.staging_error_code = ""
        item.staging_error_message = ""
        item.save(
            update_fields=[
                "staging_status",
                "staging_import_attempts",
                "staging_error_code",
                "staging_error_message",
                "updated_at",
            ]
        )

    import_root = (settings.NAS_INCOMING_ROOT / ".r2-imports").resolve()
    import_root.mkdir(parents=True, exist_ok=True)
    temporary_path = (import_root / f"{item.id}.{uuid.uuid4().hex}.part").resolve()
    if import_root not in temporary_path.parents:
        raise R2StagingError("R2 import 临时路径无效。")
    digest = sha256()
    byte_size = 0
    prefix = b""
    body = None
    saved_name = ""
    try:
        try:
            response = r2_client().get_object(
                Bucket=settings.R2_BUCKET,
                Key=item.staging_object_key,
            )
            body = response["Body"]
            with temporary_path.open("wb") as output:
                while chunk := body.read(settings.R2_IMPORT_CHUNK_BYTES):
                    if len(prefix) < 5:
                        prefix = (prefix + chunk)[:5]
                    output.write(chunk)
                    digest.update(chunk)
                    byte_size += len(chunk)
        except Exception as exc:
            if _is_missing(exc):
                raise R2StagingExpired("R2 staging object 已被 Lifecycle 删除。") from exc
            raise
        if byte_size != item.staging_file_size:
            raise R2StagingError("R2 staging object 大小与上传会话不一致。")
        if prefix != b"%PDF-":
            raise R2StagingError("R2 staging object 不是有效 PDF。")

        with transaction.atomic():
            locked = UploadItem.objects.select_for_update().select_related("batch").get(pk=item.id)
            if not locked.file:
                store_path_in_file_field(
                    locked,
                    "file",
                    temporary_path,
                    locked.source_filename,
                )
                saved_name = locked.file.name
            locked.sha256 = digest.hexdigest()
            locked.byte_size = byte_size
            locked.staging_status = UploadItem.StagingStatus.IMPORTED
            locked.staging_imported_at = timezone.now()
            locked.staging_error_code = ""
            locked.staging_error_message = ""
            locked.status = UploadItem.Status.RECEIVED
            locked.stage_progress = 0
            locked.error_code = ""
            locked.error_message = ""
            locked.dispatch_status = UploadItem.DispatchStatus.PENDING
            locked.save(
                update_fields=[
                    "file",
                    "sha256",
                    "byte_size",
                    "staging_status",
                    "staging_imported_at",
                    "staging_error_code",
                    "staging_error_message",
                    "status",
                    "stage_progress",
                    "error_code",
                    "error_message",
                    "dispatch_status",
                    "updated_at",
                ]
            )
            AuditEvent.objects.create(
                actor=locked.batch.created_by,
                action="r2_staging_imported_to_intake",
                object_type="UploadItem",
                object_id=str(locked.id),
                after={
                    "byte_size": byte_size,
                    "sha256": locked.sha256,
                    "storage": "existing_intake_storage",
                },
            )
            transaction.on_commit(lambda: schedule_upload_item(str(locked.id)))
        return {
            "id": str(item.id),
            "status": UploadItem.StagingStatus.IMPORTED,
            "byte_size": byte_size,
        }
    except Exception as exc:
        if saved_name:
            try:
                item.file.storage.delete(saved_name)
            except Exception:
                pass
        _mark_import_failure(item.id, exc)
        raise
    finally:
        if body is not None:
            try:
                body.close()
            except Exception:
                pass
        temporary_path.unlink(missing_ok=True)


def mark_r2_cleanup_ready(item: UploadItem) -> ProcessingJob | None:
    item = UploadItem.objects.filter(pk=item.pk).first()
    if (
        item is None
        or item.staging_backend != UploadItem.StagingBackend.R2
        or item.staging_status not in {
            UploadItem.StagingStatus.IMPORTED,
            UploadItem.StagingStatus.CLEANUP_PENDING,
        }
        or item.status not in PIPELINE_READY_FOR_CLEANUP
        or not item.file
        or not item.asset_id
    ):
        return None
    UploadItem.objects.filter(pk=item.pk).update(
        staging_status=UploadItem.StagingStatus.CLEANUP_PENDING,
        updated_at=timezone.now(),
    )
    item.staging_status = UploadItem.StagingStatus.CLEANUP_PENDING
    return queue_r2_staging_job(item, phase="cleanup")


def cleanup_r2_staging_object(item_id) -> dict:
    item = UploadItem.objects.select_related("batch").get(pk=item_id)
    if item.staging_status == UploadItem.StagingStatus.CLEANED:
        return {"id": str(item.id), "status": item.staging_status, "idempotent": True}
    if item.staging_status != UploadItem.StagingStatus.CLEANUP_PENDING:
        raise R2StagingError("该上传会话当前不需要清理 R2。")
    try:
        r2_client().delete_object(
            Bucket=settings.R2_BUCKET,
            Key=item.staging_object_key,
        )
    except Exception as exc:
        UploadItem.objects.filter(pk=item.pk).update(
            staging_status=UploadItem.StagingStatus.CLEANUP_PENDING,
            staging_cleanup_attempts=models_f_increment("staging_cleanup_attempts"),
            staging_error_code=_error_code(exc),
            staging_error_message=_safe_error_message(exc),
            updated_at=timezone.now(),
        )
        raise
    with transaction.atomic():
        locked = UploadItem.objects.select_for_update().get(pk=item.pk)
        locked.staging_status = UploadItem.StagingStatus.CLEANED
        locked.staging_cleanup_attempts += 1
        locked.staging_cleanup_completed_at = timezone.now()
        locked.staging_error_code = ""
        locked.staging_error_message = ""
        locked.save(
            update_fields=[
                "staging_status",
                "staging_cleanup_attempts",
                "staging_cleanup_completed_at",
                "staging_error_code",
                "staging_error_message",
                "updated_at",
            ]
        )
        AuditEvent.objects.create(
            actor=locked.batch.created_by,
            action="r2_staging_cleanup_completed",
            object_type="UploadItem",
            object_id=str(locked.id),
            after={"permanent_file_preserved": True},
        )
        return {"id": str(locked.id), "status": locked.staging_status}


def models_f_increment(field_name: str):
    from django.db.models import F

    return F(field_name) + 1


def _job_key(item: UploadItem, phase: str) -> str:
    marker = sha256(item.staging_upload_id.encode("utf-8")).hexdigest()[:20]
    return f"r2:{phase}:{item.id}:{marker}"[:128]


def queue_r2_staging_job(
    item: UploadItem,
    *,
    phase: str,
    actor=None,
    force: bool = False,
) -> ProcessingJob:
    if phase not in {"import", "cleanup"}:
        raise ValueError("未知 R2 staging job phase。")
    key = _job_key(item, phase)
    with transaction.atomic():
        job = ProcessingJob.objects.select_for_update().filter(idempotency_key=key).first()
        task_id = str(uuid.uuid4())
        if job is None:
            job = ProcessingJob.objects.create(
                job_type=ProcessingJob.JobType.R2_STAGING,
                status=ProcessingJob.Status.PENDING,
                upload_item=item,
                progress=0,
                engine="cloudflare-r2",
                max_attempts=(3 if phase == "import" else settings.R2_CLEANUP_MAX_ATTEMPTS),
                task_id=task_id,
                idempotency_key=key,
                correlation_id=str(item.id),
                stats={"phase": phase, "upload_session_id": str(item.id)},
                created_by=actor or item.batch.created_by,
            )
        elif job.status in {ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING} and not force:
            return job
        elif job.status == ProcessingJob.Status.SUCCEEDED and not force:
            return job
        else:
            job.status = ProcessingJob.Status.PENDING
            job.progress = 0
            job.task_id = task_id
            job.started_at = None
            job.finished_at = None
            job.error_code = ""
            job.error_message = ""
            job.error_kind = ""
            job.stats = {**(job.stats or {}), "phase": phase, "upload_session_id": str(item.id)}
            job.save(
                update_fields=[
                    "status",
                    "progress",
                    "task_id",
                    "started_at",
                    "finished_at",
                    "error_code",
                    "error_message",
                    "error_kind",
                    "stats",
                    "updated_at",
                ]
            )
        transaction.on_commit(
            lambda: dispatch_r2_staging_job(str(job.id), task_id)
        )
        return job


def dispatch_r2_staging_job(job_id: str, task_id: str) -> bool:
    from ingestion.tasks import process_r2_staging_job

    try:
        process_r2_staging_job.apply_async(
            args=[str(job_id)],
            task_id=task_id,
            ignore_result=True,
        )
        return True
    except Exception as exc:
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id).update(
            status=ProcessingJob.Status.FAILED,
            error_code="queue_unavailable",
            error_message="R2 staging 任务已保存，但队列暂时不可用。",
            error_kind=ProcessingJob.ErrorKind.RETRYABLE,
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return False


def run_r2_staging_job(job_id: str, *, task_id: str = "") -> ProcessingJob:
    with transaction.atomic():
        job = ProcessingJob.objects.select_for_update().select_related("upload_item").get(pk=job_id)
        if task_id and job.task_id and task_id != job.task_id:
            return job
        if job.status == ProcessingJob.Status.SUCCEEDED:
            return job
        if job.status not in {ProcessingJob.Status.PENDING, ProcessingJob.Status.FAILED}:
            return job
        if job.attempt >= job.max_attempts:
            return job
        job.status = ProcessingJob.Status.RUNNING
        job.attempt += 1
        job.started_at = timezone.now()
        job.finished_at = None
        job.error_code = ""
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "attempt",
                "started_at",
                "finished_at",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
    phase = str((job.stats or {}).get("phase") or "")
    try:
        if not job.upload_item_id:
            raise R2StagingError("R2 staging job 缺少 UploadItem。")
        if phase == "import":
            result = import_r2_staging_object(job.upload_item_id)
        elif phase == "cleanup":
            result = cleanup_r2_staging_object(job.upload_item_id)
        else:
            raise R2StagingError("R2 staging job phase 无效。")
    except Exception as exc:
        job.status = ProcessingJob.Status.FAILED
        job.error_code = _error_code(exc)
        job.error_message = _safe_error_message(exc)
        job.error_kind = (
            ProcessingJob.ErrorKind.RETRYABLE
            if getattr(exc, "retryable", False) or isinstance(exc, (BotoCoreError, ClientError))
            else ProcessingJob.ErrorKind.MANUAL_INTERVENTION
        )
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "error_kind",
                "finished_at",
                "updated_at",
            ]
        )
        raise
    job.status = ProcessingJob.Status.SUCCEEDED
    job.progress = 100
    job.stats = {**(job.stats or {}), "result": result}
    job.finished_at = timezone.now()
    job.save(
        update_fields=["status", "progress", "stats", "finished_at", "updated_at"]
    )
    return job


def retry_r2_import(item: UploadItem, *, actor=None) -> ProcessingJob:
    if item.staging_status == UploadItem.StagingStatus.EXPIRED:
        raise R2StagingExpired("R2 staging object 已过期，需要重新上传 PDF。")
    if item.staging_status != UploadItem.StagingStatus.IMPORT_FAILED:
        raise R2StagingError("该上传会话当前不能重试正式入库。")
    UploadItem.objects.filter(pk=item.pk).update(
        staging_status=UploadItem.StagingStatus.UPLOADED,
        staging_error_code="",
        staging_error_message="",
        updated_at=timezone.now(),
    )
    item.staging_status = UploadItem.StagingStatus.UPLOADED
    return queue_r2_staging_job(item, phase="import", actor=actor, force=True)


def recover_r2_staging_jobs(*, limit: int = 100) -> dict[str, int]:
    imported = 0
    cleanup = 0
    for item in UploadItem.objects.select_related("batch").filter(
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=UploadItem.StagingStatus.UPLOADED,
    ).order_by("updated_at")[:limit]:
        queue_r2_staging_job(item, phase="import")
        imported += 1
    cleanup_candidates = UploadItem.objects.select_related("batch").filter(
        staging_backend=UploadItem.StagingBackend.R2,
    ).filter(
        Q(staging_status=UploadItem.StagingStatus.CLEANUP_PENDING)
        | Q(
            staging_status=UploadItem.StagingStatus.IMPORTED,
            status__in=PIPELINE_READY_FOR_CLEANUP,
            asset__isnull=False,
        )
    ).order_by("updated_at")[:limit]
    for item in cleanup_candidates:
        if item.staging_cleanup_attempts >= settings.R2_CLEANUP_MAX_ATTEMPTS:
            continue
        if item.staging_status == UploadItem.StagingStatus.IMPORTED:
            UploadItem.objects.filter(pk=item.pk).update(
                staging_status=UploadItem.StagingStatus.CLEANUP_PENDING,
                updated_at=timezone.now(),
            )
            item.staging_status = UploadItem.StagingStatus.CLEANUP_PENDING
        queue_r2_staging_job(item, phase="cleanup")
        cleanup += 1
    return {"import_requeued": imported, "cleanup_requeued": cleanup}
