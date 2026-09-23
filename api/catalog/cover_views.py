"""Edition-scoped cover choices; uses the existing candidates, media and drafts."""
from hashlib import sha256
import json
import mimetypes
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanAccessBackOffice, CanEditMetadata
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Asset, CatalogFieldDecision, CoverCandidate, Edition, EditorialRevision, Work
from catalog.serializers import CoverCandidateSerializer
from catalog.services.covers import CoverCandidateUnavailable, generate_cover_candidates, prepare_cover_page, select_cover_candidate
from catalog.services.media import ingest_image, select_work_image
from ingestion.models import AuditEvent, ProcessingAttempt, UploadItem


def cover_state(edition, request):
    work = edition.work
    draft = EditorialRevision.objects.filter(target_type="work", target_id=work.pk, status="draft").first()
    preview = draft.materialized_preview if draft else {}
    image_name = preview.get("cover", work.cover.name) or ""
    asset = edition.assets.filter(kind="normalized", is_current=True, status__in=["ready", "processing"]).order_by("-version", "-created_at", "pk").first()
    decision = CatalogFieldDecision.objects.filter(edition=edition, field_name="cover").first()
    fingerprint = sha256(json.dumps([str(edition.pk), str(work.pk), image_name,
        str(preview.get("cover_rendition", work.cover_rendition_id) or ""), str(decision.updated_at) if decision else None,
        str(asset.pk) if asset else None, asset.sha256 if asset else None], sort_keys=True).encode()).hexdigest()
    options = list(work.cover_candidates.filter(asset=asset).order_by("-selected", "-score", "page_index")) if asset else []
    attempt = ProcessingAttempt.objects.filter(upload_item__edition=edition, stage="cover_detection", invalidated_at__isnull=True).order_by("-started_at").first()
    if attempt and asset and attempt.output_summary.get("asset_id") not in (None, str(asset.pk)):
        attempt = None
    applicable = preview.get("document_type", work.document_type) in ("book", "journal_issue")
    in_queue = UploadItem.objects.filter(edition=edition).exclude(status__in=["ready", "published", "failed", "deleted", "needs_review"]).exists()
    state = "ready" if options else "waiting_for_pdf" if not asset else "failed" if attempt and attempt.status == "failed" else "processing" if attempt and attempt.status == "started" else "not_applicable" if not applicable else "not_started"
    return {"edition_id": str(edition.pk), "work_id": str(work.pk), "fingerprint": fingerprint,
        "asset_id": str(asset.pk) if asset else None, "source_checksum": asset.sha256 if asset else None,
        "page_count": (asset.page_count or max([row.metrics.get("pdf_page_count", 0) for row in options] or [0])) if asset else 0,
        "state": state, "poll": in_queue and state in ("waiting_for_pdf", "processing", "not_started"), "optional": True, "is_default": not bool(image_name),
        "has_unpublished_cover": bool(draft and ("cover" in draft.patch or "cover_rendition" in draft.patch)),
        "image_url": request.build_absolute_uri(f"/api/catalog/admin/editions/{edition.pk}/cover/?image=1&fingerprint={fingerprint}") if image_name else "",
        "results": CoverCandidateSerializer(options, many=True, context={"request": request}).data}, asset, image_name


class EditionCoverView(AdminPrivateResponseMixin, APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        return [CanAccessBackOffice()] if self.request.method in ("GET", "HEAD", "OPTIONS") else [CanEditMetadata()]

    def get(self, request, edition_id):
        edition = get_object_or_404(Edition.objects.select_related("work"), pk=edition_id)
        payload, _, image_name = cover_state(edition, request)
        if request.query_params.get("image"):
            if request.query_params.get("fingerprint") != payload["fingerprint"] or not image_name:
                return Response({"detail": "封面已更新，请刷新当前版本。"}, status=409)
            try:
                return FileResponse(edition.work.cover.storage.open(image_name, "rb"), content_type=mimetypes.guess_type(image_name)[0] or "image/jpeg")
            except (OSError, ValueError):
                return Response({"detail": "当前封面文件无法读取，可重新选择或上传。"}, status=404)
        return Response(payload)

    @transaction.atomic
    def post(self, request, edition_id):
        edition = get_object_or_404(Edition.objects.select_for_update(), pk=edition_id)
        edition.work = Work.objects.select_for_update().get(pk=edition.work_id)
        current, asset, _ = cover_state(edition, request)
        action = request.data.get("action")
        if action not in {"regenerate", "preview_page", "select", "upload", "default"}:
            return Response({"detail": "请选择准备封面、PDF页、上传图片或默认样式。"}, status=400)
        try:
            request_key = str(UUID(str(request.data.get("request_key", ""))))
        except (TypeError, ValueError):
            return Response({"detail": "请求编号缺失，请刷新后重试。"}, status=400)
        uploaded = request.FILES.get("image")
        image_hash = ""
        if uploaded:
            if uploaded.size > 12 * 1024 * 1024:
                return Response({"detail": "封面图片不能超过12 MB。"}, status=400)
            digest = sha256()
            for chunk in uploaded.chunks(): digest.update(chunk)
            image_hash = digest.hexdigest(); uploaded.seek(0)
        signature = sha256(json.dumps({key: str(request.data.get(key, "")) for key in ("action", "fingerprint", "asset_id", "source_checksum", "page_index", "candidate_id")}, sort_keys=True).encode() + image_hash.encode()).hexdigest()
        receipt = AuditEvent.objects.filter(action="catalog.cover_command", object_type="catalog.Edition", object_id=str(edition.pk), request_id=request_key).first()
        if receipt:
            if receipt.actor_id != request.user.pk or receipt.before.get("signature") != signature:
                return Response({"detail": "该请求编号已用于另一项封面操作。"}, status=409)
            return Response({**current, "replayed": True, "detail": receipt.after["detail"], "preview_candidate": next((row for row in current["results"] if row["id"] == receipt.after.get("candidate_id")), None) if action == "preview_page" else None})
        if request.data.get("fingerprint") != current["fingerprint"]:
            return Response({"detail": "当前作品、文件或编辑内容已改变。请刷新封面后重新选择，你的图片尚未提交。"}, status=409)
        if action in ("regenerate", "preview_page", "select") and (not asset or str(asset.pk) != request.data.get("asset_id") or asset.sha256 != request.data.get("source_checksum")):
            return Response({"detail": "PDF尚未准备好或已换版，请刷新当前版本。"}, status=409)
        try:
            option = None
            if action == "regenerate":
                generate_cover_candidates(asset, force=True, auto_select=False, include_non_book=True)
                detail = "封面候选已更新。尚未更改封面，请选择需要使用的一张。"
            elif action == "preview_page":
                page_index = serializers.IntegerField(min_value=1).run_validation(request.data.get("page_index"))
                option = prepare_cover_page(asset, page_index)
                detail = "这一页已准备好。核对图片后，点击用这一页作封面。"
            elif action == "select":
                option = get_object_or_404(CoverCandidate, pk=serializers.UUIDField().run_validation(request.data.get("candidate_id")), asset=asset, work=edition.work)
                select_cover_candidate(option, actor=request.user, edition_id=edition.pk)
                detail = "封面已保存；已有公开版本会等到正式发布后更新。"
            else:
                media = None
                if action == "upload":
                    if not uploaded: return Response({"detail": "请先选择封面图片。"}, status=400)
                    media, _ = ingest_image(uploaded, actor=request.user, metadata={"alt_text": f"{edition.work.title}封面"})
                select_work_image(edition.pk, media.pk if media else None, slot="cover", actor=request.user, expected_work_id=edition.work_id)
                CoverCandidate.objects.filter(asset__edition=edition).update(selected=False)
                detail = "封面图片已保存；已有公开版本会等到正式发布后更新。" if media else "已选择默认样式，不要求提供封面。原图及历史仍保留。"
        except (CoverCandidateUnavailable, ValueError, OSError, ValidationError) as error:
            transaction.set_rollback(True)
            return Response({"detail": str(error)}, status=409)
        AuditEvent.objects.create(actor=request.user, action="catalog.cover_command", object_type="catalog.Edition", object_id=str(edition.pk), request_id=request_key, before={"signature": signature}, after={"action": action, "detail": detail, "asset_id": str(asset.pk) if asset else None, "candidate_id": str(option.pk) if option else None, "page_index": option.page_index if option else None})
        edition.refresh_from_db()
        payload, _, _ = cover_state(edition, request)
        return Response({**payload, "detail": detail, "preview_candidate": CoverCandidateSerializer(option, context={"request": request}).data if action == "preview_page" else None})
