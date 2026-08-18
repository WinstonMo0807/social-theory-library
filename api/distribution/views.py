from pathlib import Path
from urllib.parse import quote

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.cache import patch_vary_headers
from django.utils.http import content_disposition_header
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Asset, OcrStatus, PublicationState, ReaderRenditionPolicy
from common.permissions import IsLibraryAdmin

from .models import BackupJob, CloudBudgetPolicy, CloudObject, CloudProvider, CloudUsageSnapshot
from .serializers import BackupJobSerializer, CloudProviderSerializer, CloudUsageSnapshotSerializer
from .services import CloudNotReady, signed_read_url


def _public_asset(asset_id, request=None):
    """Resolve the stable public reader anchor.

    Public URLs continue to use the current normalized asset id because pages,
    passages and reader notes already reference it.  The file selected for the
    visual layer is resolved separately and can safely fall back.
    """
    asset = get_object_or_404(
        Asset,
        pk=asset_id,
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        edition__state=PublicationState.PUBLISHED,
        is_current=True,
    )
    access_status = asset.access_status
    if access_status == Asset.AccessStatus.REGISTERED and not (
        request and request.user and request.user.is_authenticated
    ):
        from rest_framework.exceptions import NotAuthenticated

        raise NotAuthenticated("该文献仅向登录读者开放。")
    if access_status in {Asset.AccessStatus.PRIVATE, Asset.AccessStatus.RESTRICTED}:
        role = getattr(getattr(request, "user", None), "role", "")
        if role not in {"admin", "editor", "reviewer"}:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("该文献仅向书库工作人员开放。")
    return asset


def _reader_file_asset(anchor: Asset) -> tuple[Asset, str]:
    policy = anchor.edition.reader_rendition_policy
    if policy == ReaderRenditionPolicy.OCR:
        ocr_asset = anchor.edition.assets.filter(
            kind=Asset.Kind.OCR_PDF,
            status=Asset.Status.READY,
            validation_status=Asset.ValidationStatus.VALID,
            is_current=True,
        ).order_by("-version", "-created_at").first()
        if ocr_asset is not None:
            return ocr_asset, ""
        return anchor, "管理员指定了 OCR PDF，但没有通过验证的版本，已回退到原始阅读副本。"
    # AUTO intentionally keeps the visual canvas on the immutable source copy.
    # OCR is delivered by the independent page text layer.
    return anchor, ""


def _download_file_asset(anchor: Asset) -> tuple[Asset, str]:
    if anchor.edition.ocr_status == OcrStatus.SUCCEEDED:
        ocr_asset = anchor.edition.assets.filter(
            kind=Asset.Kind.OCR_PDF,
            status=Asset.Status.READY,
            validation_status=Asset.ValidationStatus.VALID,
            is_current=True,
        ).order_by("-version", "-created_at").first()
        if ocr_asset is not None:
            return ocr_asset, ""
        return anchor, "OCR 文字已完成，但可搜索下载副本尚未通过验证，已提供原始 PDF。"
    return anchor, ""


def _download_mode(request) -> str:
    value = str(request.query_params.get("download") or "").strip().casefold()
    if value == "original":
        return "original"
    if value in {"1", "true"}:
        return "preferred"
    return ""


def _access_metadata(anchor: Asset, served: Asset, fallback_reason: str) -> dict:
    edition = anchor.edition
    source = anchor.source_asset
    return {
        "requested_asset_id": str(anchor.id),
        "served_asset_id": str(served.id),
        "source_artifact_id": str(source.id) if source else None,
        "rendition": served.kind,
        "reader_rendition_policy": edition.reader_rendition_policy,
        "reader_fallback_reason": fallback_reason,
        "sha256": served.sha256,
        "page_count": served.page_count or anchor.page_count,
        "ocr_status": edition.ocr_status,
        "ocr_text_available": edition.ocr_status == OcrStatus.SUCCEEDED,
        "page_label_status": edition.page_label_status,
        "semantic_index_status": edition.semantic_index_status,
    }


def _range_bounds(value: str, size: int):
    if not value.startswith("bytes=") or "," in value:
        return None
    raw_start, separator, raw_end = value.removeprefix("bytes=").partition("-")
    if not separator:
        return None
    try:
        if raw_start:
            start = int(raw_start)
            end = int(raw_end) if raw_end else size - 1
        else:
            suffix = int(raw_end)
            if suffix <= 0:
                return None
            start = max(size - suffix, 0)
            end = size - 1
    except ValueError:
        return None
    if start < 0 or start >= size or end < start:
        return None
    return start, min(end, size - 1)


def _file_chunk_iterator(path: Path, start: int, length: int, chunk_size: int = 64 * 1024):
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining:
            chunk = handle.read(min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _asset_file_headers(response, *, sha256: str, access_status: str):
    response["Accept-Ranges"] = "bytes"
    response["X-Content-Type-Options"] = "nosniff"
    response["ETag"] = f'"{sha256}"'
    if access_status in {Asset.AccessStatus.PUBLIC, Asset.AccessStatus.INHERIT}:
        # Local public delivery remains easy to revoke. Long-lived immutable
        # caching is reserved for explicitly public content-addressed objects.
        response["Cache-Control"] = "public, max-age=300, must-revalidate, no-transform"
    else:
        # Registered and staff-only PDFs must never enter a shared proxy cache.
        response["Cache-Control"] = "private, no-store, no-transform"
        patch_vary_headers(response, ("Cookie",))
    return response


def _x_accel_response(
    path: Path,
    *,
    filename: str,
    as_attachment: bool,
    sha256: str,
    access_status: str,
):
    try:
        relative_path = path.resolve().relative_to(settings.NAS_PUBLIC_ROOT.resolve())
    except ValueError:
        return None
    prefix = settings.X_ACCEL_REDIRECT_PREFIX.rstrip("/") + "/"
    response = HttpResponse(status=200, content_type="application/pdf")
    response["X-Accel-Redirect"] = prefix + quote(relative_path.as_posix(), safe="/")
    response["Content-Length"] = str(path.stat().st_size)
    disposition = content_disposition_header(as_attachment, filename)
    if disposition:
        response["Content-Disposition"] = disposition
    return _asset_file_headers(
        response,
        sha256=sha256,
        access_status=access_status,
    )


class AssetAccessView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, asset_id):
        anchor = _public_asset(asset_id, request)
        download_mode = _download_mode(request)
        downloading = bool(download_mode)
        if download_mode == "original":
            asset, fallback_reason = anchor, ""
        elif download_mode == "preferred":
            asset, fallback_reason = _download_file_asset(anchor)
        else:
            asset, fallback_reason = _reader_file_asset(anchor)
        cloud_object = asset.cloud_objects.filter(status=CloudObject.Status.READY).select_related("provider").first()
        if (
            cloud_object is None
            and asset.pk != anchor.pk
            and (
                settings.REQUIRE_CLOUD_FOR_PUBLICATION
                or not settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS
            )
        ):
            asset = anchor
            fallback_reason = "所选派生文件没有可用公开副本，已回退到原始阅读副本。"
            cloud_object = asset.cloud_objects.filter(status=CloudObject.Status.READY).select_related("provider").first()
        metadata = _access_metadata(anchor, asset, fallback_reason)
        if cloud_object:
            try:
                expires_in = settings.S3_SIGNED_URL_TTL_SECONDS
                url = signed_read_url(
                    cloud_object,
                    expires_in=expires_in,
                    download_filename=asset.edition.canonical_filename,
                    attachment=downloading,
                )
                preferred_download, _download_fallback = _download_file_asset(anchor)
                download_object = preferred_download.cloud_objects.filter(
                    status=CloudObject.Status.READY,
                ).select_related("provider").first()
                download_url = (
                    signed_read_url(
                        download_object,
                        expires_in=expires_in,
                        download_filename=preferred_download.edition.canonical_filename,
                        attachment=True,
                    )
                    if download_object
                    else url
                )
                download_asset = preferred_download if download_object else asset
                original_object = anchor.cloud_objects.filter(
                    status=CloudObject.Status.READY,
                ).select_related("provider").first()
                original_download_url = (
                    signed_read_url(
                        original_object,
                        expires_in=expires_in,
                        download_filename=anchor.edition.canonical_filename,
                        attachment=True,
                    )
                    if original_object
                    else download_url
                )
            except CloudNotReady as exc:
                return Response({"detail": str(exc)}, status=503)
            return Response(
                {
                    "url": url,
                    "download_url": download_url,
                    "original_download_url": original_download_url,
                    "download_rendition": download_asset.kind,
                    "source": "cloud",
                    "expires_in": expires_in,
                    "supports_range": True,
                    "download_filename": asset.edition.canonical_filename,
                    "edition_id": str(asset.edition_id),
                    **metadata,
                }
            )
        if settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS and not settings.REQUIRE_CLOUD_FOR_PUBLICATION:
            file_url = request.build_absolute_uri(
                reverse("asset-file", kwargs={"asset_id": anchor.id}),
            )
            if download_mode:
                file_url = f"{file_url}?download={'original' if download_mode == 'original' else '1'}"
            download_url = request.build_absolute_uri(
                reverse("asset-file", kwargs={"asset_id": anchor.id}),
            ) + "?download=1"
            original_download_url = request.build_absolute_uri(
                reverse("asset-file", kwargs={"asset_id": anchor.id}),
            ) + "?download=original"
            preferred_download, _download_fallback = _download_file_asset(anchor)
            return Response(
                {
                    "url": file_url,
                    "download_url": download_url,
                    "original_download_url": original_download_url,
                    "download_rendition": preferred_download.kind,
                    "source": "local-nas",
                    "expires_in": None,
                    "supports_range": True,
                    "download_filename": asset.edition.canonical_filename,
                    "edition_id": str(asset.edition_id),
                    **metadata,
                }
            )
        return Response({"detail": "公开阅读副本尚未就绪。"}, status=503)


class AssetFileView(APIView):
    permission_classes = [AllowAny]

    def head(self, request, asset_id):
        if settings.REQUIRE_CLOUD_FOR_PUBLICATION or not settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS:
            return Response({"detail": "本地阅读副本未开放。"}, status=404)
        anchor = _public_asset(asset_id, request)
        download_mode = _download_mode(request)
        asset, _fallback_reason = (
            (anchor, "")
            if download_mode == "original"
            else _download_file_asset(anchor)
            if download_mode == "preferred"
            else _reader_file_asset(anchor)
        )
        try:
            path = Path(asset.file.path)
        except (NotImplementedError, ValueError):
            return Response({"detail": "本地阅读副本不可用。"}, status=404)
        if not path.is_file():
            return Response({"detail": "本地阅读副本不存在。"}, status=404)
        response = HttpResponse(status=200, content_type="application/pdf")
        response["Content-Length"] = str(path.stat().st_size)
        _asset_file_headers(
            response,
            sha256=asset.sha256,
            access_status=anchor.access_status,
        )
        disposition = content_disposition_header(
            bool(download_mode),
            asset.edition.canonical_filename or path.name,
        )
        if disposition:
            response["Content-Disposition"] = disposition
        return response

    def get(self, request, asset_id):
        if settings.REQUIRE_CLOUD_FOR_PUBLICATION or not settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS:
            return Response({"detail": "本地阅读副本未开放。"}, status=404)
        anchor = _public_asset(asset_id, request)
        download_mode = _download_mode(request)
        asset, _fallback_reason = (
            (anchor, "")
            if download_mode == "original"
            else _download_file_asset(anchor)
            if download_mode == "preferred"
            else _reader_file_asset(anchor)
        )
        try:
            path = Path(asset.file.path)
        except (NotImplementedError, ValueError):
            return Response({"detail": "本地阅读副本不可用。"}, status=404)
        if not path.is_file():
            return Response({"detail": "本地阅读副本不存在。"}, status=404)

        filename = asset.edition.canonical_filename or path.name
        as_attachment = bool(download_mode)
        if (
            settings.X_ACCEL_REDIRECT_ENABLED
            and request.headers.get("X-Use-X-Accel") == "1"
        ):
            response = _x_accel_response(
                path,
                filename=filename,
                as_attachment=as_attachment,
                sha256=asset.sha256,
                access_status=anchor.access_status,
            )
            if response is None:
                return Response({"detail": "本地阅读副本路径不在允许目录内。"}, status=503)
            return response
        if settings.PUBLIC_DEPLOYMENT_MODE:
            return Response(
                {"detail": "公网文件请求必须经过受信任的文件代理。"},
                status=503,
            )
        disposition = content_disposition_header(as_attachment, filename)
        size = path.stat().st_size
        range_value = request.headers.get("Range", "").strip()
        if not range_value:
            response = FileResponse(
                path.open("rb"),
                content_type="application/pdf",
                as_attachment=as_attachment,
                filename=filename,
            )
            response["Content-Length"] = str(size)
            return _asset_file_headers(
                response,
                sha256=asset.sha256,
                access_status=anchor.access_status,
            )

        bounds = _range_bounds(range_value, size)
        if bounds is None:
            response = Response(status=416)
            response["Content-Range"] = f"bytes */{size}"
            response["Accept-Ranges"] = "bytes"
            return response
        start, end = bounds
        response = StreamingHttpResponse(
            _file_chunk_iterator(path, start, end - start + 1),
            status=206,
            content_type="application/pdf",
        )
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(end - start + 1)
        if disposition:
            response["Content-Disposition"] = disposition
        return _asset_file_headers(
            response,
            sha256=asset.sha256,
            access_status=anchor.access_status,
        )


class CloudProviderListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryAdmin]
    serializer_class = CloudProviderSerializer
    queryset = CloudProvider.objects.all().order_by("-is_default", "name")


class CloudProviderDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryAdmin]
    serializer_class = CloudProviderSerializer
    queryset = CloudProvider.objects.all()


class CloudUsageListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryAdmin]
    serializer_class = CloudUsageSnapshotSerializer

    def get_queryset(self):
        return CloudUsageSnapshot.objects.filter(
            provider_id=self.kwargs["provider_id"],
        ).order_by("-period", "-created_at")

    def perform_create(self, serializer):
        provider = get_object_or_404(CloudProvider, pk=self.kwargs["provider_id"])
        previous = provider.usage_snapshots.filter(
            period=serializer.validated_data["period"],
        ).order_by("-created_at").first()
        snapshot = serializer.save(provider=provider)
        try:
            policy = provider.budget_policy
        except CloudBudgetPolicy.DoesNotExist:
            return
        if not policy.monthly_budget or not policy.notification_emails:
            return
        threshold = policy.monthly_budget * policy.warning_ratio
        previous_cost = previous.estimated_cost if previous else 0
        if previous_cost < threshold <= snapshot.estimated_cost:
            send_mail(
                f"{provider.name} 云端费用告警",
                (
                    f"{snapshot.period} 估算费用已达到 {snapshot.estimated_cost}，"
                    f"月度预算为 {policy.monthly_budget}。请登录书库后台检查流量和发布设置。"
                ),
                None,
                policy.notification_emails,
                fail_silently=True,
            )


class BackupJobListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryAdmin]
    serializer_class = BackupJobSerializer
    queryset = BackupJob.objects.all().order_by("-created_at")

    def perform_create(self, serializer):
        destination = Path(serializer.validated_data["destination_path"]).resolve()
        allowed_root = settings.NAS_BACKUP_ROOT.resolve()
        if allowed_root != destination and allowed_root not in destination.parents:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"destination_path": "备份目录必须位于配置的 NAS 备份根目录内。"})
        job = serializer.save(requested_by=self.request.user)
        from .tasks import create_backup_archive

        transaction.on_commit(
            lambda: create_backup_archive.apply_async(
                args=[str(job.id)],
                ignore_result=True,
            )
        )
