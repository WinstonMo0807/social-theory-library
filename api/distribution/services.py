from pathlib import Path
from decimal import Decimal
import hashlib
import os
from urllib.parse import quote

import boto3
from django.conf import settings
from django.utils import timezone

from .models import CloudBudgetPolicy, CloudObject, CloudProvider


class CloudNotReady(RuntimeError):
    pass


def s3_client(provider: CloudProvider):
    prefix = provider.credential_reference.strip() or "S3"
    access_key = os.getenv(
        f"{prefix}_ACCESS_KEY_ID",
        settings.S3_ACCESS_KEY_ID if prefix == "S3" else "",
    )
    secret_key = os.getenv(
        f"{prefix}_SECRET_ACCESS_KEY",
        settings.S3_SECRET_ACCESS_KEY if prefix == "S3" else "",
    )
    session_token = os.getenv(
        f"{prefix}_SESSION_TOKEN",
        settings.S3_SESSION_TOKEN if prefix == "S3" else "",
    )
    return boto3.client(
        "s3",
        endpoint_url=provider.endpoint_url or None,
        region_name=provider.region or None,
        aws_access_key_id=access_key or None,
        aws_secret_access_key=secret_key or None,
        aws_session_token=session_token or None,
    )


def sync_asset_to_cloud(cloud_object: CloudObject) -> CloudObject:
    cloud_object.status = CloudObject.Status.SYNCING
    cloud_object.error_message = ""
    cloud_object.save(update_fields=["status", "error_message", "updated_at"])
    asset = cloud_object.asset
    try:
        client = s3_client(cloud_object.provider)
        filename = asset.edition.canonical_filename or Path(asset.file.name).name
        with asset.file.open("rb") as file_handle:
            client.upload_fileobj(
                file_handle,
                cloud_object.provider.bucket,
                cloud_object.object_key,
                ExtraArgs={
                    "ContentType": "application/pdf",
                    "ContentDisposition": (
                        f"inline; filename*=UTF-8''{quote(filename)}"
                    ),
                    # Cloud objects use content-addressed keys. Replacing a PDF
                    # creates a new object, so long-lived edge caching is safe.
                    "CacheControl": "public, max-age=31536000, immutable",
                    "Metadata": {"sha256": asset.sha256},
                },
            )
        head = client.head_object(Bucket=cloud_object.provider.bucket, Key=cloud_object.object_key)
        cloud_object.etag = head.get("ETag", "").strip('"')
        cloud_object.byte_size = head.get("ContentLength", asset.byte_size)
        cloud_object.status = CloudObject.Status.READY
        cloud_object.last_verified_at = timezone.now()
        cloud_object.save(
            update_fields=[
                "etag",
                "byte_size",
                "status",
                "last_verified_at",
                "updated_at",
            ]
        )
        return cloud_object
    except Exception as exc:
        cloud_object.status = CloudObject.Status.FAILED
        cloud_object.error_message = str(exc)[:2000]
        cloud_object.save(update_fields=["status", "error_message", "updated_at"])
        raise


def signed_read_url(
    cloud_object: CloudObject,
    expires_in: int = 900,
    *,
    download_filename: str = "",
    attachment: bool = False,
) -> str:
    if cloud_object.status != CloudObject.Status.READY:
        raise CloudNotReady("云端阅读副本尚未就绪。")
    # Public works may explicitly opt in to a cacheable custom domain. This is
    # the fast path for PDF.js and avoids sending every Range request through
    # the NAS and Cloudflare Tunnel. Downloads still use a short-lived signed
    # S3-compatible URL so the browser receives an attachment disposition.
    if (
        not attachment
        and cloud_object.cdn_enabled
        and cloud_object.provider.public_base_url
    ):
        base_url = cloud_object.provider.public_base_url.rstrip("/")
        object_path = quote(cloud_object.object_key.lstrip("/"), safe="/")
        return f"{base_url}/{object_path}"

    params = {
        "Bucket": cloud_object.provider.bucket,
        "Key": cloud_object.object_key,
        "ResponseContentType": "application/pdf",
    }
    if download_filename:
        disposition = "attachment" if attachment else "inline"
        params["ResponseContentDisposition"] = (
            f"{disposition}; filename*=UTF-8''{quote(download_filename)}"
        )
    return s3_client(cloud_object.provider).generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
    )


def cloud_budget_allows_new_publication(provider: CloudProvider) -> bool:
    try:
        policy = provider.budget_policy
    except CloudBudgetPolicy.DoesNotExist:
        return True
    if policy.monthly_budget is None:
        return True
    period = timezone.now().strftime("%Y-%m")
    snapshot = provider.usage_snapshots.filter(period=period).order_by("-created_at").first()
    if snapshot is None:
        return True
    stop_ratio = Decimal(str(policy.stop_new_publications_ratio))
    return snapshot.estimated_cost < policy.monthly_budget * stop_ratio
