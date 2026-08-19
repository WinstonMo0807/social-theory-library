from datetime import datetime, timedelta
from hashlib import sha256
import json
import logging
from pathlib import Path
import re
import shutil
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.http import FileResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import (
    Asset,
    Contribution,
    Discipline,
    Edition,
    OcrStatus,
    PageLabelStatus,
    Person,
    PublicationMetadataRevision,
    PublicationState,
    PublicationPlaceEvidence,
    RelationReviewStatus,
    ReviewStatus,
    ScholarProfile,
    SemanticIndexJob,
    SemanticIndexStatus,
    Subdiscipline,
    TheorySchool,
    Topic,
    WorkDisciplineRelation,
    WorkKnowledgeRelation,
    WorkSubdisciplineRelation,
)
from catalog.services.knowledge import demote_orphaned_knowledge_objects
from catalog.services.covers import generate_cover_candidates, generate_recommendation_image
from catalog.services.semantic_indexing import (
    queue_semantic_job,
    remove_semantic_asset,
    request_semantic_job_pause,
    resume_semantic_job,
)
from catalog.services.publication_places import (
    confirm_publication_place,
    detect_publication_places,
    record_manual_publication_places,
    serialize_publication_place_evidence,
)
from common.permissions import CanUpload, IsCatalogEditor, IsLibraryAdmin, IsLibraryStaff
from common.capabilities import Capability, has_capability

from .models import (
    AuditEvent,
    DecisionLog,
    EntityResolutionCandidate,
    FieldLock,
    MetadataCandidate,
    ProcessingJob,
    ReviewTask,
    UploadBatch,
    UploadItem,
)
from .serializers import (
    EntityResolutionCandidateSerializer,
    EntityResolutionDecisionSerializer,
    EntityResolutionRevertSerializer,
    MetadataImportRequestSerializer,
    MetadataCandidateSerializer,
    MetadataReviewSerializer,
    R2CompleteSerializer,
    R2PartConfirmSerializer,
    R2PartFailureSerializer,
    R2PartSignSerializer,
    R2StagingInitSerializer,
    ReviewTaskActionSerializer,
    ReviewTaskSerializer,
    UploadBatchCreateSerializer,
    UploadBatchSerializer,
    UploadItemSerializer,
    WithdrawSerializer,
)
from .services.files import canonical_pdf_filename, store_path_in_file_field
from .services.candidate_decisions import accept_candidates_from_review, set_candidate_decision
from .services.entity_resolution_decisions import (
    ResolutionDecisionError,
    decide_entity_resolution,
    revert_entity_resolution_decision,
)
from .services.metadata import authority_verification_links
from .services.metadata_import import import_bibliographic_metadata
from .services.metadata_import_formats import MetadataImportError
from .services.provider_gateway import refresh_remote_candidates
from .services.indexing import index_asset, remove_asset_from_index
from .services.dispatch import schedule_upload_item
from .services.pipeline import refresh_batch
from .services.r2_staging import (
    R2ConfigurationError,
    R2StagingError,
    R2StagingExpired,
    abort_r2_upload,
    complete_r2_upload,
    confirm_r2_part,
    create_r2_upload,
    list_user_staging_sessions,
    queue_r2_staging_job,
    reconcile_r2_parts,
    retry_r2_import,
    serialize_staging_session,
    sign_r2_parts,
)
from .services.processing import (
    PROCESSING_PAUSE_KEYS,
    create_external_enrichment_job,
    processing_workload_paused,
    queue_external_enrichment_job,
    queue_ocr_job,
    queue_page_label_job,
    request_processing_job_pause,
    resume_paused_workload,
    resume_processing_job,
    run_external_enrichment_job,
    set_processing_workload_paused,
)
from .services.review_tasks import ReviewTaskActionError, apply_review_task_action
from .services.publication import (
    PublicationBlocked,
    PublicationWarningsRequireConfirmation,
    invalidate_public_recommendations,
    publication_preflight,
    publication_readiness,
    publish_edition,
    withdraw_edition,
)
from .services.workflow import transition_upload_item


logger = logging.getLogger(__name__)


def _request_ip(request):
    return request.META.get("HTTP_X_FORWARDED_FOR", request.META.get("REMOTE_ADDR", "")).split(",")[0].strip() or None


class ReviewTaskListView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request):
        rows = ReviewTask.objects.select_related(
            "upload_item__edition__work",
            "assigned_to",
            "created_by",
            "completed_by",
        )
        task_type = str(request.query_params.get("type") or "").strip()
        status_value = str(request.query_params.get("status") or "").strip()
        assigned = str(request.query_params.get("assigned") or "").strip()
        if task_type:
            rows = rows.filter(task_type=task_type)
        counts = {
            value: rows.filter(status=value).count()
            for value in ReviewTask.Status.values
        }
        if status_value in ReviewTask.Status.values:
            rows = rows.filter(status=status_value)
        if assigned == "me":
            rows = rows.filter(assigned_to=request.user)
        elif assigned == "unassigned":
            rows = rows.filter(assigned_to__isnull=True)
        try:
            page_size = min(200, max(1, int(request.query_params.get("page_size") or 100)))
        except (TypeError, ValueError):
            page_size = 100
        return Response(
            {
                "count": rows.count(),
                "counts": counts,
                "can_manage": IsCatalogEditor().has_permission(request, self),
                "results": ReviewTaskSerializer(rows[:page_size], many=True).data,
            }
        )


class ReviewTaskActionView(APIView):
    permission_classes = [IsCatalogEditor]

    def post(self, request, task_id):
        task = get_object_or_404(ReviewTask, pk=task_id)
        serializer = ReviewTaskActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        correlation_id = str(request.META.get("HTTP_X_REQUEST_ID") or "")[:128]
        try:
            result = apply_review_task_action(
                task,
                action=serializer.validated_data["action"],
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
                correlation_id=correlation_id,
            )
        except ReviewTaskActionError as exc:
            return Response({"detail": str(exc)}, status=409)
        if not result.idempotent:
            AuditEvent.objects.create(
                actor=request.user,
                action=f"review_task_{serializer.validated_data['action']}",
                object_type="ReviewTask",
                object_id=str(task.id),
                after={"status": result.task.status},
                request_ip=_request_ip(request),
                request_id=correlation_id,
            )
        return Response(
            {
                "task": ReviewTaskSerializer(result.task).data,
                "idempotent": result.idempotent,
            }
        )


def _locked_upload_items(*related):
    return UploadItem.objects.select_for_update(of=("self",)).select_related(*related)


def _knowledge_slug(model, name, *, field_name="slug", exclude_pk=None):
    base = slugify(name)[:120] or f"item-{abs(hash(name))}"
    candidate = base
    suffix = 1
    queryset = model.objects.all()
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    while queryset.filter(**{field_name: candidate}).exists():
        suffix += 1
        candidate = f"{base}-{suffix}"
    return candidate


_UPLOAD_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,80}$")


def _upload_chunk_directory(batch_id, client_token: str) -> Path:
    root = (settings.NAS_INCOMING_ROOT / ".upload-chunks").resolve()
    target = (root / str(batch_id) / client_token).resolve()
    if root != target and root not in target.parents:
        raise ValueError("无效的分段上传路径。")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_uploaded_chunk(uploaded, chunk_path: Path) -> int:
    """Replace one persisted chunk only after the complete request body is written."""

    temporary_path = chunk_path.with_name(
        f".{chunk_path.name}.{uuid.uuid4().hex}.tmp"
    )
    written = 0
    try:
        with temporary_path.open("wb") as output:
            for piece in uploaded.chunks():
                output.write(piece)
                written += len(piece)
        if written != uploaded.size:
            raise OSError("分段写入的字节数与请求不一致。")
        temporary_path.replace(chunk_path)
        return written
    finally:
        temporary_path.unlink(missing_ok=True)


def _assemble_uploaded_chunks(
    chunk_directory: Path,
    *,
    total_chunks: int,
) -> tuple[Path, str, int]:
    """Build the complete PDF atomically so an interrupted merge stays resumable."""

    assembled_path = chunk_directory / "assembled.pdf"
    temporary_path = chunk_directory / f".assembled.{uuid.uuid4().hex}.tmp"
    digest = sha256()
    byte_size = 0
    try:
        with temporary_path.open("wb") as assembled:
            for index in range(total_chunks):
                part_path = chunk_directory / f"{index:04d}.part"
                if not part_path.is_file():
                    raise FileNotFoundError(index)
                with part_path.open("rb") as part:
                    while piece := part.read(8 * 1024 * 1024):
                        assembled.write(piece)
                        digest.update(piece)
                        byte_size += len(piece)
        temporary_path.replace(assembled_path)
        return assembled_path, digest.hexdigest(), byte_size
    finally:
        temporary_path.unlink(missing_ok=True)


def _store_assembled_upload(item: UploadItem, assembled_path: Path, original_name: str) -> str:
    return store_path_in_file_field(item, "file", assembled_path, original_name)


def _enqueue_review_processing(item_id: str) -> bool:
    return bool(
        schedule_upload_item(
            item_id,
            kind=UploadItem.DispatchKind.REVIEWED,
            force=True,
        )
    )


def _schedule_publication_background_tasks(item, asset, actor) -> tuple[list[dict], list[str]]:
    """Ensure the independent post-publication work exists without gating publication."""

    edition = item.edition
    scheduled: list[dict] = []
    warnings: list[str] = []

    def remember(label: str, job) -> None:
        scheduled.append(
            {
                "type": label,
                "job_id": str(job.id),
                "status": job.status,
                "existing": bool(
                    getattr(job, "started_at", None)
                    or getattr(job, "attempt", 0)
                    or getattr(job, "attempts", 0)
                ),
            }
        )

    try:
        if edition.ocr_status == OcrStatus.PENDING:
            remember(
                "ocr",
                queue_ocr_job(
                    asset,
                    upload_item=item,
                    actor=actor,
                    force=False,
                ),
            )
        elif edition.ocr_status == OcrStatus.RUNNING:
            current = asset.processing_jobs.filter(
                job_type=ProcessingJob.JobType.OCR,
                status__in=[ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING],
            ).first()
            if current:
                remember("ocr", current)
            else:
                warnings.append("OCR 状态为处理中，但没有找到活动任务，请在处理中心检查。")
        elif edition.ocr_status == OcrStatus.FAILED:
            warnings.append("OCR 已失败，系统没有自动无限重试；可在处理中心人工重试。")
    except Exception as exc:
        warnings.append(f"OCR 任务排队失败：{str(exc)[:500]}")

    text_ready = edition.ocr_status in {
        OcrStatus.NOT_REQUIRED,
        OcrStatus.SUCCEEDED,
    }
    if edition.page_label_status != PageLabelStatus.READY:
        try:
            remember(
                "page_labels",
                queue_page_label_job(
                    asset,
                    upload_item=item,
                    actor=actor,
                    force=False,
                ),
            )
        except Exception as exc:
            warnings.append(f"页码任务排队失败：{str(exc)[:500]}")
    if text_ready:
        if edition.semantic_index_status != SemanticIndexStatus.READY:
            try:
                remember(
                    "semantic_index",
                    queue_semantic_job(asset, force=False, actor=actor),
                )
            except Exception as exc:
                warnings.append(f"语义索引任务排队失败：{str(exc)[:500]}")
    return scheduled, warnings


class BatchListView(generics.ListAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = UploadBatchSerializer
    queryset = UploadBatch.objects.prefetch_related(
        "items__attempts",
        "items__metadata_candidates",
        "items__edition__work",
    ).order_by("-created_at")


class BatchDetailView(generics.RetrieveAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = UploadBatchSerializer
    queryset = BatchListView.queryset


class BatchCreateView(APIView):
    permission_classes = [IsCatalogEditor]

    def post(self, request):
        serializer = UploadBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        batch = UploadBatch.objects.create(
            created_by=request.user,
            **values,
        )
        AuditEvent.objects.create(
            actor=request.user,
            action="batch_created",
            object_type="UploadBatch",
            object_id=str(batch.id),
            after={
                "expected_count": batch.expected_count,
                "label": batch.label,
                "access_policy": batch.access_policy,
                "ocr_strategy": batch.ocr_strategy,
                "duplicate_policy": batch.duplicate_policy,
                "external_enrichment_enabled": batch.external_enrichment_enabled,
                "ai_suggestions_enabled": batch.ai_suggestions_enabled,
            },
            request_ip=_request_ip(request),
        )
        return Response(UploadBatchSerializer(batch).data, status=201)


def _owned_r2_upload(user, session_id, *, lock: bool = False) -> UploadItem:
    queryset = UploadItem.objects.select_related("batch")
    if lock:
        queryset = queryset.select_for_update()
    return get_object_or_404(
        queryset,
        pk=session_id,
        batch__created_by=user,
        staging_backend=UploadItem.StagingBackend.R2,
    )


def _r2_error_response(exc: Exception, *, stage: str, session_id: str = "", part_number=None):
    request_id = uuid.uuid4().hex[:12]
    logger.warning(
        "r2_upload_error request_id=%s upload_session_id=%s part_number=%s stage=%s category=%s",
        request_id,
        session_id or "unassigned",
        part_number if part_number is not None else "none",
        stage,
        exc.__class__.__name__,
    )
    if isinstance(exc, R2StagingExpired):
        status_code = status.HTTP_410_GONE
    elif isinstance(exc, R2ConfigurationError):
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif isinstance(exc, R2StagingError):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(
        {
            "detail": str(exc) if isinstance(exc, R2StagingError) else "R2 上传服务暂时不可用。",
            "error_code": getattr(exc, "error_code", exc.__class__.__name__),
            "request_id": request_id,
        },
        status=status_code,
    )


class R2StagingUploadListView(APIView):
    permission_classes = [CanUpload]

    def get(self, request):
        return Response(
            {
                "results": [
                    serialize_staging_session(item)
                    for item in list_user_staging_sessions(request.user)
                ]
            }
        )


class R2StagingUploadInitView(APIView):
    permission_classes = [CanUpload]

    def post(self, request):
        serializer = R2StagingInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            item, created = create_r2_upload(
                batch_id=values["batch_id"],
                user=request.user,
                source_filename=values["source_filename"],
                file_size=values["file_size"],
                file_last_modified=values["file_last_modified"],
                client_token=values["client_token"],
                request_ip=_request_ip(request),
            )
        except Exception as exc:
            return _r2_error_response(exc, stage="init")
        return Response(
            serialize_staging_session(item),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class R2StagingUploadDetailView(APIView):
    permission_classes = [CanUpload]

    def get(self, request, session_id):
        item = _owned_r2_upload(request.user, session_id)
        if item.staging_status == UploadItem.StagingStatus.UPLOADING:
            try:
                item = reconcile_r2_parts(item)
            except Exception as exc:
                return _r2_error_response(
                    exc,
                    stage="list_parts",
                    session_id=str(item.id),
                )
        return Response(serialize_staging_session(item))


class R2StagingPartSignView(APIView):
    permission_classes = [CanUpload]

    def post(self, request, session_id):
        item = _owned_r2_upload(request.user, session_id)
        serializer = R2PartSignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            parts = sign_r2_parts(item, serializer.validated_data["part_numbers"])
        except Exception as exc:
            return _r2_error_response(
                exc,
                stage="sign_parts",
                session_id=str(item.id),
            )
        return Response({"parts": parts})


class R2StagingPartConfirmView(APIView):
    permission_classes = [CanUpload]

    def post(self, request, session_id):
        item = _owned_r2_upload(request.user, session_id)
        serializer = R2PartConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        try:
            item = confirm_r2_part(
                item,
                part_number=values["part_number"],
                etag=values["etag"],
                size=values["size"],
            )
        except Exception as exc:
            return _r2_error_response(
                exc,
                stage="confirm_part",
                session_id=str(item.id),
                part_number=values.get("part_number"),
            )
        return Response(serialize_staging_session(item))


class R2StagingPartFailureView(APIView):
    permission_classes = [CanUpload]

    def post(self, request, session_id):
        item = _owned_r2_upload(request.user, session_id)
        serializer = R2PartFailureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        AuditEvent.objects.create(
            actor=request.user,
            action="r2_staging_part_failed",
            object_type="UploadItem",
            object_id=str(item.id),
            after={
                "part_number": values["part_number"],
                "attempt": values["attempt"],
                "http_status": values["http_status"],
                "error_code": values["error_code"],
                "stage": "browser_upload_part",
            },
            request_ip=_request_ip(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class R2StagingUploadCompleteView(APIView):
    permission_classes = [CanUpload]

    def post(self, request, session_id):
        item = _owned_r2_upload(request.user, session_id)
        serializer = R2CompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item, completed = complete_r2_upload(item, serializer.validated_data["parts"])
        except Exception as exc:
            return _r2_error_response(
                exc,
                stage="complete",
                session_id=str(item.id),
            )
        return Response(
            {**serialize_staging_session(item), "completed": completed},
            status=status.HTTP_202_ACCEPTED,
        )


class R2StagingUploadAbortView(APIView):
    permission_classes = [CanUpload]

    def post(self, request, session_id):
        item = _owned_r2_upload(request.user, session_id)
        try:
            item = abort_r2_upload(
                item,
                actor=request.user,
                request_ip=_request_ip(request),
            )
        except Exception as exc:
            return _r2_error_response(
                exc,
                stage="abort",
                session_id=str(item.id),
            )
        return Response(serialize_staging_session(item))


class R2StagingRetryImportView(APIView):
    permission_classes = [CanUpload]

    def post(self, request, session_id):
        item = _owned_r2_upload(request.user, session_id)
        try:
            job = retry_r2_import(item, actor=request.user)
        except Exception as exc:
            return _r2_error_response(
                exc,
                stage="retry_import",
                session_id=str(item.id),
            )
        item.refresh_from_db()
        return Response(
            {**serialize_staging_session(item), "job_id": str(job.id)},
            status=status.HTTP_202_ACCEPTED,
        )


class BatchItemUploadView(APIView):
    permission_classes = [IsCatalogEditor]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            UploadBatch.objects.select_for_update(),
            pk=batch_id,
        )
        client_token = str(request.data.get("client_token", "")).strip()[:80]
        if len(client_token) < 8:
            return Response({"client_token": ["缺少有效的文件上传标识。"]}, status=400)
        existing = batch.items.filter(processing_token=client_token).first()
        if existing:
            return Response(
                {
                    "accepted": existing.status != UploadItem.Status.FAILED,
                    "item": UploadItemSerializer(existing).data,
                    "idempotent": True,
                }
            )
        if batch.items.count() >= batch.expected_count:
            return Response({"detail": "该批次已达到预定文件数量。"}, status=409)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"file": ["请选择一个 PDF。"]}, status=400)
        original_name = Path(uploaded.name).name
        signature = uploaded.read(5)
        uploaded.seek(0)
        rejection_reason = ""
        if uploaded.size > settings.MAX_UPLOAD_BYTES:
            rejection_reason = "文件超过单文件上限。"
        elif Path(original_name).suffix.casefold() != ".pdf" or signature != b"%PDF-":
            rejection_reason = "扩展名或文件内容不是 PDF。"

        if rejection_reason:
            item = UploadItem.objects.create(
                batch=batch,
                source_filename=original_name,
                processing_token=client_token,
                status=UploadItem.Status.FAILED,
                error_code="upload_rejected",
                error_message=rejection_reason,
                dispatch_status=UploadItem.DispatchStatus.COMPLETED,
            )
        else:
            item = UploadItem.objects.create(
                batch=batch,
                source_filename=original_name,
                file=uploaded,
                processing_token=client_token,
            )
            schedule_upload_item(str(item.id))
        AuditEvent.objects.create(
            actor=request.user,
            action="batch_item_received",
            object_type="UploadItem",
            object_id=str(item.id),
            after={
                "batch_id": str(batch.id),
                "source_filename": original_name,
                "accepted": not rejection_reason,
                "reason": rejection_reason,
            },
            request_ip=_request_ip(request),
        )
        refresh_batch(batch)
        return Response(
            {
                "accepted": not rejection_reason,
                "item": UploadItemSerializer(item).data,
                "idempotent": False,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class BatchItemChunkUploadView(APIView):
    """Receive resumable browser chunks for slow public connections."""

    permission_classes = [IsCatalogEditor]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, batch_id):
        """Report safely persisted chunks so a browser can resume an upload."""

        client_token = str(request.query_params.get("client_token", "")).strip()
        if not _UPLOAD_TOKEN_PATTERN.fullmatch(client_token):
            return Response({"client_token": ["缺少有效的文件上传标识。"]}, status=400)
        batch = get_object_or_404(UploadBatch, pk=batch_id)
        existing = batch.items.filter(processing_token=client_token).first()
        if existing:
            return Response(
                {
                    "complete": True,
                    "received_indices": [],
                    "item": UploadItemSerializer(existing).data,
                    "max_chunk_size": settings.MAX_UPLOAD_CHUNK_BYTES,
                }
            )
        chunk_directory = _upload_chunk_directory(batch.id, client_token)
        manifest = {}
        manifest_path = chunk_directory / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                manifest = {}
        received_indices = []
        for chunk_path in chunk_directory.glob("*.part"):
            try:
                received_indices.append(int(chunk_path.stem))
            except ValueError:
                continue
        return Response(
            {
                "complete": False,
                "received_indices": sorted(set(received_indices)),
                "source_filename": manifest.get("source_filename", ""),
                "total_size": manifest.get("total_size"),
                "total_chunks": manifest.get("total_chunks"),
                "chunk_size": manifest.get("chunk_size"),
                "max_chunk_size": settings.MAX_UPLOAD_CHUNK_BYTES,
            }
        )

    def post(self, request, batch_id):
        client_token = str(request.data.get("client_token", "")).strip()
        if not _UPLOAD_TOKEN_PATTERN.fullmatch(client_token):
            return Response({"client_token": ["缺少有效的文件上传标识。"]}, status=400)
        original_name = Path(str(request.data.get("source_filename", ""))).name[:800]
        try:
            chunk_index = int(request.data.get("chunk_index", -1))
            total_chunks = int(request.data.get("total_chunks", 0))
            total_size = int(request.data.get("total_size", 0))
            supplied_chunk_size = request.data.get("chunk_size")
            chunk_size = int(supplied_chunk_size) if supplied_chunk_size not in {None, ""} else None
        except (TypeError, ValueError):
            return Response({"detail": "分段参数无效。"}, status=400)
        if (
            not original_name
            or Path(original_name).suffix.casefold() != ".pdf"
            or total_chunks < 1
            or total_chunks > 2048
            or chunk_index < 0
            or chunk_index >= total_chunks
            or total_size < 5
            or total_size > settings.MAX_UPLOAD_BYTES
            or (chunk_size is not None and chunk_size < 1)
            or (chunk_size is not None and chunk_size > settings.MAX_UPLOAD_CHUNK_BYTES)
            or (
                chunk_size is not None
                and total_chunks != (total_size + chunk_size - 1) // chunk_size
            )
        ):
            return Response({"detail": "文件名、大小或分段编号无效。"}, status=400)
        uploaded = request.FILES.get("chunk")
        if uploaded is None:
            return Response({"chunk": ["缺少文件分段。"]}, status=400)
        if uploaded.size > settings.MAX_UPLOAD_CHUNK_BYTES:
            limit_mb = settings.MAX_UPLOAD_CHUNK_BYTES / 1024 / 1024
            return Response(
                {"chunk": [f"单个分段不得超过 {limit_mb:g} MB。"]},
                status=400,
            )
        if chunk_size is not None:
            expected_size = min(chunk_size, total_size - chunk_index * chunk_size)
            if uploaded.size != expected_size:
                return Response(
                    {"chunk": ["分段字节数与上传清单不一致。"]},
                    status=400,
                )

        batch = get_object_or_404(UploadBatch, pk=batch_id)
        existing = batch.items.filter(processing_token=client_token).first()
        if existing:
            return Response(
                {
                    "accepted": existing.status != UploadItem.Status.FAILED,
                    "complete": True,
                    "item": UploadItemSerializer(existing).data,
                    "idempotent": True,
                    "max_chunk_size": settings.MAX_UPLOAD_CHUNK_BYTES,
                }
            )

        chunk_directory = _upload_chunk_directory(batch.id, client_token)
        manifest_path = chunk_directory / "manifest.json"
        manifest = {
            "source_filename": original_name,
            "total_size": total_size,
            "total_chunks": total_chunks,
        }
        if chunk_size is not None:
            manifest["chunk_size"] = chunk_size
        if manifest_path.is_file():
            try:
                existing_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                existing_manifest = None
            core_keys = ("source_filename", "total_size", "total_chunks")
            manifest_conflict = not isinstance(existing_manifest, dict) or any(
                existing_manifest.get(key) != manifest[key] for key in core_keys
            )
            if (
                not manifest_conflict
                and chunk_size is not None
                and existing_manifest.get("chunk_size") not in {None, chunk_size}
            ):
                manifest_conflict = True
            if manifest_conflict:
                return Response(
                    {
                        "detail": (
                            "恢复记录与当前文件不一致。请移除该文件后重新选择，"
                            "系统不会把不同 PDF 的分段合并。"
                        )
                    },
                    status=409,
                )
            if chunk_size is not None and existing_manifest.get("chunk_size") is None:
                existing_manifest["chunk_size"] = chunk_size
                temporary_manifest = chunk_directory / "manifest.json.tmp"
                temporary_manifest.write_text(
                    json.dumps(existing_manifest, ensure_ascii=False),
                    encoding="utf-8",
                )
                temporary_manifest.replace(manifest_path)
        else:
            temporary_manifest = chunk_directory / "manifest.json.tmp"
            temporary_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary_manifest.replace(manifest_path)
        chunk_path = chunk_directory / f"{chunk_index:04d}.part"
        _write_uploaded_chunk(uploaded, chunk_path)

        received_chunks = sum(1 for _ in chunk_directory.glob("*.part"))
        if received_chunks < total_chunks:
            return Response(
                {
                    "accepted": True,
                    "complete": False,
                    "received_chunks": received_chunks,
                    "total_chunks": total_chunks,
                    "max_chunk_size": settings.MAX_UPLOAD_CHUNK_BYTES,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        try:
            assembled_path, assembled_sha256, assembled_size = _assemble_uploaded_chunks(
                chunk_directory,
                total_chunks=total_chunks,
            )
        except FileNotFoundError:
            return Response(
                {
                    "accepted": True,
                    "complete": False,
                    "received_chunks": received_chunks,
                    "total_chunks": total_chunks,
                    "max_chunk_size": settings.MAX_UPLOAD_CHUNK_BYTES,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        rejection_reason = ""
        if assembled_size != total_size:
            rejection_reason = "分段合并后的文件大小不一致。"
        else:
            with assembled_path.open("rb") as assembled:
                if assembled.read(5) != b"%PDF-":
                    rejection_reason = "文件内容不是 PDF。"

        with transaction.atomic():
            locked_batch = get_object_or_404(
                UploadBatch.objects.select_for_update(),
                pk=batch.id,
            )
            existing = locked_batch.items.filter(processing_token=client_token).first()
            if existing is None:
                if locked_batch.items.count() >= locked_batch.expected_count:
                    return Response({"detail": "该批次已达到预定文件数量。"}, status=409)
                item = UploadItem(
                    batch=locked_batch,
                    source_filename=original_name,
                    processing_token=client_token,
                    status=(UploadItem.Status.FAILED if rejection_reason else UploadItem.Status.RECEIVED),
                    error_code="upload_rejected" if rejection_reason else "",
                    error_message=rejection_reason,
                    dispatch_status=(
                        UploadItem.DispatchStatus.COMPLETED
                        if rejection_reason
                        else UploadItem.DispatchStatus.PENDING
                    ),
                    sha256=assembled_sha256,
                    byte_size=assembled_size,
                )
                storage_write = "rejected"
                try:
                    if not rejection_reason:
                        storage_write = _store_assembled_upload(item, assembled_path, original_name)
                    item.save()
                except Exception:
                    if item.file and item.file.name:
                        item.file.delete(save=False)
                    raise
                AuditEvent.objects.create(
                    actor=request.user,
                    action="chunked_batch_item_received",
                    object_type="UploadItem",
                    object_id=str(item.id),
                    after={
                        "batch_id": str(locked_batch.id),
                        "source_filename": original_name,
                        "accepted": not rejection_reason,
                        "total_chunks": total_chunks,
                        "chunk_size": chunk_size,
                        "sha256": assembled_sha256,
                        "byte_size": assembled_size,
                        "storage_write": storage_write,
                    },
                    request_ip=_request_ip(request),
                )
                if not rejection_reason:
                    schedule_upload_item(str(item.id))
                refresh_batch(locked_batch)
            else:
                item = existing

        shutil.rmtree(chunk_directory, ignore_errors=True)
        return Response(
            {
                "accepted": not rejection_reason,
                "complete": True,
                "item": UploadItemSerializer(item).data,
                "idempotent": existing is not None,
                "max_chunk_size": settings.MAX_UPLOAD_CHUNK_BYTES,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class BatchItemFailureView(APIView):
    permission_classes = [IsCatalogEditor]

    @transaction.atomic
    def post(self, request, batch_id):
        batch = get_object_or_404(
            UploadBatch.objects.select_for_update(),
            pk=batch_id,
        )
        client_token = str(request.data.get("client_token", "")).strip()[:80]
        source_filename = Path(str(request.data.get("source_filename", ""))).name[:800]
        if len(client_token) < 8 or not source_filename:
            return Response(
                {"detail": "缺少文件名或文件上传标识。"},
                status=400,
            )
        item = batch.items.filter(processing_token=client_token).first()
        created = False
        if item is None:
            if batch.items.count() >= batch.expected_count:
                return Response({"detail": "该批次已达到预定文件数量。"}, status=409)
            item = UploadItem.objects.create(
                batch=batch,
                source_filename=source_filename,
                processing_token=client_token,
                status=UploadItem.Status.FAILED,
                error_code="client_upload_failed",
                error_message=str(request.data.get("reason", "客户端上传中断"))[:2000],
                dispatch_status=UploadItem.DispatchStatus.COMPLETED,
            )
            created = True
        refresh_batch(batch)
        return Response(
            {
                "item": UploadItemSerializer(item).data,
                "created": created,
            },
            status=201 if created else 200,
        )


class BatchUploadView(APIView):
    permission_classes = [IsCatalogEditor]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        files = request.FILES.getlist("files")
        if not files:
            return Response({"files": ["请选择至少一个 PDF。"]}, status=400)
        if len(files) > 100:
            return Response({"files": ["单个批次最多接收 100 个 PDF。"]}, status=400)

        policy_serializer = UploadBatchCreateSerializer(
            data={**request.data.dict(), "expected_count": len(files)}
        )
        policy_serializer.is_valid(raise_exception=True)
        batch = UploadBatch.objects.create(
            created_by=request.user,
            **policy_serializer.validated_data,
        )
        accepted = []
        rejected = []
        for uploaded in files:
            original_name = Path(uploaded.name).name
            signature = uploaded.read(5)
            uploaded.seek(0)
            rejection_reason = ""
            if uploaded.size > settings.MAX_UPLOAD_BYTES:
                rejection_reason = "文件超过单文件上限。"
            elif Path(original_name).suffix.casefold() != ".pdf" or signature != b"%PDF-":
                rejection_reason = "扩展名或文件内容不是 PDF。"
            if rejection_reason:
                item = UploadItem.objects.create(
                    batch=batch,
                    source_filename=original_name,
                    status=UploadItem.Status.FAILED,
                    error_code="upload_rejected",
                    error_message=rejection_reason,
                    dispatch_status=UploadItem.DispatchStatus.COMPLETED,
                )
                rejected.append(
                    {
                        "id": str(item.id),
                        "filename": original_name,
                        "reason": rejection_reason,
                    }
                )
                continue
            item = UploadItem.objects.create(
                batch=batch,
                source_filename=original_name,
                file=uploaded,
            )
            accepted.append(item)
            schedule_upload_item(str(item.id))

        batch.expected_count = len(files)
        batch.failed_count = len(rejected)
        batch.status = UploadBatch.Status.PROCESSING if accepted else UploadBatch.Status.FAILED
        batch.save(update_fields=["expected_count", "failed_count", "status", "updated_at"])
        AuditEvent.objects.create(
            actor=request.user,
            action="batch_upload",
            object_type="UploadBatch",
            object_id=str(batch.id),
            after={"accepted": len(accepted), "rejected": rejected},
            request_ip=_request_ip(request),
        )
        return Response(
            {
                "batch": UploadBatchSerializer(batch).data,
                "accepted": [str(item.id) for item in accepted],
                "rejected": rejected,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class UploadItemDetailView(generics.RetrieveAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = UploadItemSerializer
    queryset = UploadItem.objects.prefetch_related("attempts", "metadata_candidates").select_related("edition__work")


class UploadItemListView(generics.ListAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = UploadItemSerializer
    filterset_fields = ("status",)
    search_fields = ("source_filename", "edition__work__title")
    ordering_fields = ("created_at", "updated_at", "status")
    queryset = (
        UploadItem.objects.select_related(
            "batch__created_by",
            "edition__work",
        )
        .prefetch_related("attempts", "metadata_candidates")
        .order_by("-created_at")
    )

    def get_queryset(self):
        queryset = super().get_queryset()
        include_deleted = self.request.query_params.get("include_deleted", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not include_deleted:
            queryset = queryset.exclude(status=UploadItem.Status.DELETED)
        scope = self.request.query_params.get("scope", "").strip()
        if scope == "review":
            queryset = queryset.filter(
                status__in=[
                    UploadItem.Status.NEEDS_REVIEW,
                    UploadItem.Status.FAILED,
                    UploadItem.Status.READY,
                ]
            )
        elif scope == "processing":
            queryset = queryset.exclude(
                status__in=[
                    UploadItem.Status.PUBLISHED,
                    UploadItem.Status.WITHDRAWN,
                    UploadItem.Status.DELETED,
                ]
            )
        elif scope == "publication":
            queryset = queryset.filter(edition__isnull=False).exclude(
                status=UploadItem.Status.DELETED,
            )
        return queryset


class UploadItemPreviewView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request, pk):
        item = get_object_or_404(
            UploadItem.objects.select_related("edition"),
            pk=pk,
        )
        asset = None
        if item.edition_id:
            asset = item.edition.assets.filter(
                kind=Asset.Kind.NORMALIZED,
                is_current=True,
            ).first()
        file_field = item.file if item.file else asset.file if asset and asset.file else None
        if not file_field:
            return Response({"detail": "该项目没有可预览的 PDF。"}, status=404)
        response = FileResponse(
            file_field.open("rb"),
            content_type="application/pdf",
            as_attachment=False,
            filename=item.source_filename,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class RetryUploadItemView(APIView):
    permission_classes = [IsCatalogEditor]

    @transaction.atomic
    def post(self, request, item_id):
        item = get_object_or_404(
            _locked_upload_items("edition"),
            pk=item_id,
        )
        if item.status in {
            UploadItem.Status.PUBLISHED,
            UploadItem.Status.WITHDRAWN,
            UploadItem.Status.DELETED,
        }:
            return Response({"detail": "已发布、已下架或已删除记录不能从入库预检阶段重试。"}, status=409)
        stalled_seconds = max(
            0,
            int((timezone.now() - item.updated_at).total_seconds()),
        )
        stalled = stalled_seconds >= (
            settings.INGESTION_QUEUE_STALLED_SECONDS
            if item.status == UploadItem.Status.RECEIVED
            else settings.INGESTION_STAGE_STALLED_SECONDS
        )
        if (
            item.status == UploadItem.Status.RECEIVED
            and item.dispatch_status in {
                UploadItem.DispatchStatus.PENDING,
                UploadItem.DispatchStatus.QUEUED,
                UploadItem.DispatchStatus.RUNNING,
            }
            and not stalled
        ):
            return Response(
                {
                    "detail": "该文件已经进入入库队列，无需重复提交。",
                    "queue_mode": "inline" if settings.CELERY_TASK_ALWAYS_EAGER else "worker",
                    "task_id": item.dispatch_task_id,
                    "dispatch_status": item.dispatch_status,
                    "reused": True,
                },
                status=202,
            )
        if item.status in {
            UploadItem.Status.VALIDATING,
            UploadItem.Status.DEDUPLICATING,
            UploadItem.Status.EXTRACTING,
            UploadItem.Status.OCR,
            UploadItem.Status.METADATA,
            UploadItem.Status.LINKING,
            UploadItem.Status.INDEXING,
            UploadItem.Status.PREPARING_PUBLIC_ASSET,
            UploadItem.Status.SYNCING_CLOUD,
        } and not stalled:
            return Response({"detail": "该文件正在处理，请勿重复提交。"}, status=409)
        item.status = UploadItem.Status.RECEIVED
        item.stage_progress = 0
        item.retry_count += 1
        item.error_code = ""
        item.error_message = ""
        item.save(
            update_fields=[
                "status",
                "stage_progress",
                "retry_count",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        transition_upload_item(
            item,
            UploadItem.WorkflowState.PREFLIGHT,
            actor=request.user,
            reason="管理员请求从安全预检阶段重试",
            force=True,
        )
        task_id = schedule_upload_item(str(item.id), force=True)
        item.refresh_from_db()
        return Response(
            {
                "detail": (
                    "已在本地同步处理。"
                    if settings.CELERY_TASK_ALWAYS_EAGER
                    else (
                        "任务已进入后台队列。"
                        if item.dispatch_status != UploadItem.DispatchStatus.FAILED
                        else "PDF 已安全保存。队列恢复后系统会自动继续处理。"
                    )
                ),
                "queue_mode": (
                    "inline"
                    if settings.CELERY_TASK_ALWAYS_EAGER
                    else "worker"
                ),
                "task_id": task_id,
                "dispatch_status": item.dispatch_status,
            },
            status=202,
        )


class QueueHealthView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request):
        now = timezone.now()
        active = UploadItem.objects.filter(
            status__in=[
                UploadItem.Status.RECEIVED,
                UploadItem.Status.VALIDATING,
                UploadItem.Status.DEDUPLICATING,
                UploadItem.Status.EXTRACTING,
                UploadItem.Status.OCR,
                UploadItem.Status.METADATA,
                UploadItem.Status.LINKING,
                UploadItem.Status.INDEXING,
                UploadItem.Status.PREPARING_PUBLIC_ASSET,
                UploadItem.Status.SYNCING_CLOUD,
            ]
        )
        queue_cutoff = now - timedelta(
            seconds=settings.INGESTION_QUEUE_STALLED_SECONDS
        )
        stage_cutoff = now - timedelta(
            seconds=settings.INGESTION_STAGE_STALLED_SECONDS
        )
        stalled = active.filter(
            Q(
                status=UploadItem.Status.RECEIVED,
                updated_at__lte=queue_cutoff,
            )
            | Q(
                updated_at__lte=stage_cutoff,
            )
        ).count()
        inline = settings.CELERY_TASK_ALWAYS_EAGER
        from ingestion.services.health import (
            cache_health,
            celery_broker_health,
            http_service_health,
            worker_runtime_status,
        )

        cache_status = cache_health(probe_key="ingestion:api-health-probe")
        broker_status = celery_broker_health()
        worker_status = worker_runtime_status(max_age_seconds=150)
        broker_reachable = broker_status["reachable"]
        worker_online = inline or worker_status["online"]
        ocr = http_service_health(settings.PADDLEOCR_SERVICE_URL, "/ready", timeout=5)
        search = http_service_health(settings.MEILISEARCH_URL, "/health", timeout=2)
        pending_dispatches = UploadItem.objects.filter(
            dispatch_status__in=[
                UploadItem.DispatchStatus.PENDING,
                UploadItem.DispatchStatus.FAILED,
            ]
        ).exclude(
            status__in=[
                UploadItem.Status.PUBLISHED,
                UploadItem.Status.WITHDRAWN,
                UploadItem.Status.DELETED,
                UploadItem.Status.NEEDS_REVIEW,
                UploadItem.Status.FAILED,
            ]
        ).count()
        healthy = bool(inline or (cache_status["reachable"] and broker_reachable and worker_online))
        return Response(
            {
                "mode": "inline" if inline else "worker",
                "worker_required": not inline,
                "stalled_count": stalled,
                "pending_dispatches": pending_dispatches,
                "healthy": healthy,
                "cache_reachable": cache_status["reachable"],
                "broker_reachable": broker_reachable,
                "worker_online": worker_online,
                "worker_heartbeat_at": worker_status["heartbeat_at"],
                "worker_probe_source": worker_status["source"],
                "cache_error": "" if cache_status["reachable"] else cache_status["detail"],
                "broker_error": "" if broker_reachable else broker_status["detail"],
                "ocr": ocr,
                "search": search,
                "message": (
                    "本地同步处理已启用，上传请求会直接执行识别流程。"
                    if inline
                    else (
                        "后台 worker 正常，上传任务会自动处理。"
                        if healthy
                        else "后台 worker 暂时不可用。PDF 已保留，服务恢复后会自动重新派发。"
                    )
                ),
            }
        )


class ResumeUploadItemView(APIView):
    permission_classes = [IsCatalogEditor]

    @transaction.atomic
    def post(self, request, item_id):
        item = get_object_or_404(
            _locked_upload_items("edition"),
            pk=item_id,
        )
        if item.status in {
            UploadItem.Status.VALIDATING,
            UploadItem.Status.EXTRACTING,
            UploadItem.Status.OCR,
            UploadItem.Status.INDEXING,
            UploadItem.Status.SYNCING_CLOUD,
        }:
            return Response({"detail": "该文件正在处理，请勿重复提交。"}, status=409)
        if item.edition_id is None or not item.edition.field_locks.exists():
            return Response(
                {"detail": "该记录尚未完成人工复核，请先进入元数据复核页。"},
                status=409,
            )
        item.status = UploadItem.Status.READY
        item.error_code = ""
        item.error_message = ""
        item.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        _enqueue_review_processing(str(item.id))
        item.refresh_from_db()
        return Response(
            {
                "detail": (
                    "已从全文索引与发布检查阶段继续处理。"
                    if item.dispatch_status != UploadItem.DispatchStatus.FAILED
                    else "复核数据已保存。队列恢复后系统会自动继续发布。"
                ),
                "dispatch_status": item.dispatch_status,
            },
            status=202,
        )


class ReplaceUploadItemView(APIView):
    permission_classes = [IsCatalogEditor]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, item_id):
        target_item = get_object_or_404(
            _locked_upload_items(
                "edition__work",
                "batch",
            ),
            pk=item_id,
        )
        if target_item.edition is None:
            return Response({"detail": "该上传记录没有可替换的文献。"}, status=409)
        if target_item.edition.state != PublicationState.PUBLISHED:
            return Response({"detail": "仅已发布文献可以替换 PDF。"}, status=409)
        active_replacement = (
            UploadItem.objects.filter(
                edition=target_item.edition,
                replacement_of_asset__isnull=False,
            )
            .exclude(
                status__in=[
                    UploadItem.Status.PUBLISHED,
                    UploadItem.Status.FAILED,
                    UploadItem.Status.NEEDS_REVIEW,
                    UploadItem.Status.WITHDRAWN,
                    UploadItem.Status.DELETED,
                ]
            )
            .exists()
        )
        if active_replacement:
            return Response(
                {"detail": "该文献已有替换任务，请先等待处理或解决待复核项。"},
                status=409,
            )
        old_asset = target_item.edition.assets.select_for_update().filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).first()
        if old_asset is None:
            return Response({"detail": "当前规范阅读文件未就绪。"}, status=409)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            return Response({"file": ["请选择一个 PDF。"]}, status=400)
        original_name = Path(uploaded.name).name
        signature = uploaded.read(5)
        uploaded.seek(0)
        if uploaded.size > settings.MAX_UPLOAD_BYTES:
            return Response({"file": ["文件超过单文件上限。"]}, status=400)
        if Path(original_name).suffix.casefold() != ".pdf" or signature != b"%PDF-":
            return Response({"file": ["扩展名或文件内容不是 PDF。"]}, status=400)

        edition = target_item.edition
        work = edition.work
        authors = list(
            edition.contributions.filter(
                role=Contribution.Role.AUTHOR,
                approved=True,
            )
            .order_by("order")
            .values_list("person__preferred_name", flat=True)
        )
        theory_schools = list(
            work.knowledge_relations.filter(
                kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
                approved=True,
            ).values_list("theory_school__name", flat=True)
        )
        topics = list(
            work.knowledge_relations.filter(
                kind=WorkKnowledgeRelation.Kind.TOPIC,
                approved=True,
            ).values_list("topic__name", flat=True)
        )
        locked_values = {
            "title": work.title,
            "document_type": work.document_type,
            "language": work.language,
            "abstract": work.abstract,
            "authors": authors,
            "publication_year": edition.publication_year,
            "publisher": edition.publisher,
            "publisher-place": edition.publication_place,
            "publication_place": edition.publication_place,
            "journal_title": edition.journal_title,
            "volume": edition.volume,
            "issue": edition.issue,
            "page_range": edition.page_range,
            "degree_institution": edition.degree_institution,
            "degree_type": edition.degree_type,
            "report_institution": edition.report_institution,
            "isbn": edition.isbn,
            "doi": edition.doi,
            "theory_schools": theory_schools,
            "topics": topics,
        }
        for field_name, value in locked_values.items():
            FieldLock.objects.update_or_create(
                edition=edition,
                field_name=field_name,
                defaults={
                    "locked_by": request.user,
                    "locked_value": value,
                    "reason": "替换 PDF 时保护已发布元数据",
                },
            )

        batch = UploadBatch.objects.create(
            created_by=request.user,
            source="replacement",
            expected_count=1,
            status=UploadBatch.Status.PROCESSING,
            notes=f"替换已发布文献：{work.title}",
        )
        replacement = UploadItem.objects.create(
            batch=batch,
            source_filename=original_name,
            file=uploaded,
            edition=edition,
            replacement_of_asset=old_asset,
        )
        AuditEvent.objects.create(
            actor=request.user,
            action="pdf_replacement_requested",
            object_type="Edition",
            object_id=str(edition.id),
            before={
                "asset_id": str(old_asset.id),
                "version": old_asset.version,
            },
            after={
                "upload_item_id": str(replacement.id),
                "source_filename": original_name,
            },
            request_ip=_request_ip(request),
        )
        schedule_upload_item(str(replacement.id))
        return Response(
            UploadItemSerializer(replacement).data,
            status=status.HTTP_202_ACCEPTED,
        )


class MetadataReviewView(APIView):
    permission_classes = [IsLibraryStaff]

    @transaction.atomic
    def put(self, request, item_id):
        item = get_object_or_404(
            _locked_upload_items(
                "batch",
            ),
            pk=item_id,
        )
        if item.edition_id is None:
            return Response({"detail": "识别流程尚未建立文献记录。"}, status=409)
        # UploadItem coordinates one review request. Edition and Work are also
        # mutated below and can be shared by replacement or duplicate intake
        # records, so lock both explicitly through their non-null inner join.
        edition = (
            Edition.objects.select_for_update(of=("self", "work"))
            .select_related("work")
            .get(pk=item.edition_id)
        )
        item.edition = edition
        serializer = MetadataReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        work = edition.work
        was_published = edition.state == PublicationState.PUBLISHED
        previous_title = work.title
        before = {
            "title": work.title,
            "document_type": work.document_type,
            "publication_year": edition.publication_year,
        }

        work.title = data["title"].strip()
        work.normalized_title = work.title.casefold()
        work.subtitle = data.get("subtitle", "")
        work.document_type = data["document_type"]
        work.language = data["language"]
        work.abstract = data.get("abstract", "")
        work.save()
        if (
            edition.state != PublicationState.PUBLISHED
            and previous_title.casefold().strip() != work.title.casefold().strip()
        ):
            edition.public_slug = _knowledge_slug(
                Edition,
                work.title,
                field_name="public_slug",
                exclude_pk=edition.pk,
            )
        edition_fields = (
            "version_label",
            "publication_year",
            "publisher",
            "publication_place",
            "journal_title",
            "volume",
            "issue",
            "page_range",
            "degree_institution",
            "degree_type",
            "report_institution",
            "isbn",
            "doi",
        )
        for field_name in edition_fields:
            if field_name in data:
                setattr(edition, field_name, data[field_name])
        edition.metadata_confidence = 1

        edition.contributions.filter(role=Contribution.Role.AUTHOR).delete()
        author_names = []
        selected_people = []
        seen_people = set()
        profiles_by_id = ScholarProfile.objects.select_related("person").in_bulk(
            data.get("author_ids", [])
        )
        for profile_id in data.get("author_ids", []):
            profile = profiles_by_id.get(profile_id)
            if profile is None:
                continue
            if profile.person_id not in seen_people:
                selected_people.append(profile.person)
                seen_people.add(profile.person_id)
        people_by_id = Person.objects.in_bulk(data.get("author_person_ids", []))
        for person_id in data.get("author_person_ids", []):
            person = people_by_id.get(person_id)
            if person is None:
                continue
            if person.id not in seen_people:
                selected_people.append(person)
                seen_people.add(person.id)
        for author_name in data.get("authors", []):
            author_name = " ".join(author_name.split()).strip()
            if not author_name:
                continue
            # Free text means "create a new draft". Existing authorities are
            # only linked through an explicit author_id selection.
            person = Person.objects.create(
                preferred_name=author_name,
                sort_name=author_name,
                authority_status=Person.AuthorityStatus.DRAFT,
            )
            if person.id not in seen_people:
                selected_people.append(person)
                seen_people.add(person.id)
        for order, person in enumerate(selected_people):
            Contribution.objects.create(
                edition=edition,
                person=person,
                role=Contribution.Role.AUTHOR,
                order=order,
                source="manual_review",
                confidence=1,
                approved=True,
            )
            ScholarProfile.objects.get_or_create(
                person=person,
                defaults={
                    "slug": _knowledge_slug(ScholarProfile, person.preferred_name),
                    "short_description": "本馆收录作者",
                    "editorial_status": "draft",
                },
            )
            author_names.append(person.preferred_name)

        previous_theory_ids = list(
            work.knowledge_relations.filter(
                kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
                theory_school__isnull=False,
            ).values_list("theory_school_id", flat=True)
        )
        previous_topic_ids = list(
            work.knowledge_relations.filter(
                kind=WorkKnowledgeRelation.Kind.TOPIC,
                topic__isnull=False,
            ).values_list("topic_id", flat=True)
        )
        theory_assignments = {
            entry["id"]: entry
            for entry in data.get("theory_assignments", [])
        }
        requested_theory_ids = list(dict.fromkeys([
            *data.get("theory_school_ids", []),
            *theory_assignments.keys(),
        ]))
        theories_by_id = TheorySchool.objects.in_bulk(requested_theory_ids)
        selected_theories = [
            theories_by_id[theory_id]
            for theory_id in requested_theory_ids
            if theory_id in theories_by_id
        ]
        selected_theory_ids = {target.id for target in selected_theories}
        for name in data.get("theory_schools", []):
            name = " ".join(name.split()).strip()
            if not name:
                continue
            target = TheorySchool.objects.filter(name__iexact=name).first()
            if target is None:
                target = TheorySchool.objects.create(
                    name=name,
                    slug=_knowledge_slug(TheorySchool, name),
                    editorial_status="draft",
                )
            if target.id not in selected_theory_ids:
                selected_theories.append(target)
                selected_theory_ids.add(target.id)
        selected_theory_ids = {target.id for target in selected_theories}
        work.knowledge_relations.filter(
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
        ).exclude(theory_school_id__in=selected_theory_ids).delete()
        for index, target in enumerate(selected_theories):
            assignment = theory_assignments.get(target.id, {})
            WorkKnowledgeRelation.objects.update_or_create(
                work=work,
                kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
                theory_school=target,
                defaults={
                    "source": "manual_review",
                    "confidence": 1,
                    "approved": True,
                    "review_status": RelationReviewStatus.APPROVED,
                    "reviewed_by": request.user,
                    "reviewed_at": timezone.now(),
                    "is_primary": assignment.get("is_primary", index == 0),
                    "role": assignment.get("role", "local_mention"),
                    "strength": assignment.get("strength", "medium"),
                    "evidence_page": assignment.get("evidence_page"),
                    "evidence_printed_label": assignment.get("evidence_printed_label", ""),
                    "evidence_text": assignment.get("evidence_text", ""),
                },
            )
        topic_assignments = {
            entry["id"]: entry
            for entry in data.get("topic_assignments", [])
        }
        requested_topic_ids = list(dict.fromkeys([
            *data.get("topic_ids", []),
            *topic_assignments.keys(),
        ]))
        topics_by_id = Topic.objects.in_bulk(requested_topic_ids)
        selected_topics = [
            topics_by_id[topic_id]
            for topic_id in requested_topic_ids
            if topic_id in topics_by_id
        ]
        selected_topic_ids = {target.id for target in selected_topics}
        for name in data.get("topics", []):
            name = " ".join(name.split()).strip()
            if not name:
                continue
            target = Topic.objects.filter(name__iexact=name).first()
            if target is None:
                target = Topic.objects.create(
                    name=name,
                    slug=_knowledge_slug(Topic, name),
                    editorial_status="draft",
                )
            if target.id not in selected_topic_ids:
                selected_topics.append(target)
                selected_topic_ids.add(target.id)
        selected_topic_ids = {target.id for target in selected_topics}
        work.knowledge_relations.filter(
            kind=WorkKnowledgeRelation.Kind.TOPIC,
        ).exclude(topic_id__in=selected_topic_ids).delete()
        for index, target in enumerate(selected_topics):
            assignment = topic_assignments.get(target.id, {})
            WorkKnowledgeRelation.objects.update_or_create(
                work=work,
                kind=WorkKnowledgeRelation.Kind.TOPIC,
                topic=target,
                defaults={
                    "source": "manual_review",
                    "confidence": 1,
                    "approved": True,
                    "review_status": RelationReviewStatus.APPROVED,
                    "reviewed_by": request.user,
                    "reviewed_at": timezone.now(),
                    "is_primary": assignment.get("is_primary", index == 0),
                    "evidence_page": assignment.get("evidence_page"),
                    "evidence_printed_label": assignment.get("evidence_printed_label", ""),
                    "evidence_text": assignment.get("evidence_text", ""),
                },
            )

        discipline_assignments = {
            entry["id"]: entry
            for entry in data.get("discipline_assignments", [])
        }
        requested_discipline_ids = list(dict.fromkeys([
            *data.get("discipline_ids", []),
            *discipline_assignments.keys(),
        ]))
        disciplines_by_id = Discipline.objects.in_bulk(requested_discipline_ids)
        selected_disciplines = [
            disciplines_by_id[identifier]
            for identifier in requested_discipline_ids
            if identifier in disciplines_by_id
        ]
        work.discipline_relations.exclude(
            discipline_id__in=[target.id for target in selected_disciplines],
        ).delete()
        for index, target in enumerate(selected_disciplines):
            assignment = discipline_assignments.get(target.id, {})
            WorkDisciplineRelation.objects.update_or_create(
                work=work,
                discipline=target,
                defaults={
                    "is_primary": assignment.get("is_primary", index == 0),
                    "source": "manual_review",
                    "confidence": 1,
                    "review_status": RelationReviewStatus.APPROVED,
                    "reviewed_by": request.user,
                    "reviewed_at": timezone.now(),
                    "evidence_page": assignment.get("evidence_page"),
                    "evidence_printed_label": assignment.get("evidence_printed_label", ""),
                    "evidence_text": assignment.get("evidence_text", ""),
                },
            )

        subdiscipline_assignments = {
            entry["id"]: entry
            for entry in data.get("subdiscipline_assignments", [])
        }
        requested_subdiscipline_ids = list(dict.fromkeys([
            *data.get("subdiscipline_ids", []),
            *subdiscipline_assignments.keys(),
        ]))
        subdisciplines_by_id = Subdiscipline.objects.in_bulk(requested_subdiscipline_ids)
        selected_subdisciplines = [
            subdisciplines_by_id[identifier]
            for identifier in requested_subdiscipline_ids
            if identifier in subdisciplines_by_id
        ]
        work.subdiscipline_relations.exclude(
            subdiscipline_id__in=[target.id for target in selected_subdisciplines],
        ).delete()
        for index, target in enumerate(selected_subdisciplines):
            assignment = subdiscipline_assignments.get(target.id, {})
            WorkSubdisciplineRelation.objects.update_or_create(
                work=work,
                subdiscipline=target,
                defaults={
                    "is_primary": assignment.get("is_primary", index == 0),
                    "strength": assignment.get("strength", "medium"),
                    "source": "manual_review",
                    "confidence": 1,
                    "review_status": RelationReviewStatus.APPROVED,
                    "reviewed_by": request.user,
                    "reviewed_at": timezone.now(),
                    "evidence_page": assignment.get("evidence_page"),
                    "evidence_printed_label": assignment.get("evidence_printed_label", ""),
                    "evidence_text": assignment.get("evidence_text", ""),
                },
            )
        demote_orphaned_knowledge_objects(
            theory_ids=previous_theory_ids,
            topic_ids=previous_topic_ids,
        )

        edition.canonical_filename = canonical_pdf_filename(
            work.title,
            author_names,
            edition.publication_year,
        )
        edition.citation_data = {
            "id": str(edition.id),
            "type": {
                "book": "book",
                "journal_article": "article-journal",
                "thesis": "thesis",
                "report": "report",
            }[work.document_type],
            "title": work.title,
            "author": [{"literal": name} for name in author_names],
            "issued": {"date-parts": [[edition.publication_year]]} if edition.publication_year else {},
            "publisher": edition.publisher,
            "container-title": edition.journal_title,
            "volume": edition.volume,
            "issue": edition.issue,
            "page": edition.page_range,
            "DOI": edition.doi,
            "ISBN": edition.isbn,
        }
        edition.search_indexed_at = None
        review_checks = [
            bool(work.title.strip()),
            bool(author_names),
            bool(edition.publication_year),
            bool(edition.citation_data),
            bool(edition.canonical_filename),
        ]
        if work.document_type == "book":
            review_checks.append(bool(edition.publisher.strip()))
        elif work.document_type == "journal_article":
            review_checks.append(bool(edition.journal_title.strip()))
        elif work.document_type == "thesis":
            review_checks.extend(
                [bool(edition.degree_institution.strip()), bool(edition.degree_type.strip())]
            )
        elif work.document_type == "report":
            review_checks.append(
                bool(edition.report_institution.strip() or edition.publisher.strip())
            )
        edition.review_progress = round(sum(review_checks) / len(review_checks) * 100)
        edition.review_status = (
            ReviewStatus.COMPLETED
            if edition.review_progress == 100
            else ReviewStatus.IN_PROGRESS
        )
        edition.save()
        record_manual_publication_places(
            edition,
            data.get("publication_place", ""),
            actor=request.user,
        )

        for field_name in set(data.get("lock_fields", [])) | {
            "title",
            "document_type",
            "authors",
            "theory_schools",
            "topics",
            "disciplines",
            "subdisciplines",
        }:
            FieldLock.objects.update_or_create(
                edition=edition,
                field_name=field_name,
                defaults={
                    "locked_by": request.user,
                    "locked_value": data.get(field_name, True),
                    "reason": "人工元数据复核",
                },
            )
        accepted_candidate_count = accept_candidates_from_review(
            item,
            data,
            actor=request.user,
            locked_fields=set(data.get("lock_fields", [])) | {
                "title",
                "document_type",
                "authors",
                "theory_schools",
                "topics",
                "disciplines",
                "subdisciplines",
            },
        )

        item.status = (
            UploadItem.Status.PUBLISHED
            if was_published
            else UploadItem.Status.READY
        )
        item.stage_progress = 100 if was_published else max(item.stage_progress, 78)
        item.error_code = ""
        item.error_message = ""
        transition_upload_item(
            item,
            (
                UploadItem.WorkflowState.PUBLISHED
                if was_published
                else UploadItem.WorkflowState.READY
            ),
            actor=request.user,
            reason="人工元数据复核已保存",
            force=True,
        )
        item.save(
            update_fields=[
                "status",
                "stage_progress",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        AuditEvent.objects.create(
            actor=request.user,
            action="published_metadata_edit" if was_published else "metadata_review",
            object_type="Edition",
            object_id=str(edition.id),
            before=before,
            after={
                "title": work.title,
                "document_type": work.document_type,
                "publication_year": edition.publication_year,
                "authors": author_names,
                "theory_schools": [target.name for target in selected_theories],
                "topics": [target.name for target in selected_topics],
                "disciplines": [target.name for target in selected_disciplines],
                "subdisciplines": [target.name for target in selected_subdisciplines],
                "accepted_candidate_count": accepted_candidate_count,
            },
            request_ip=_request_ip(request),
        )
        refresh_batch(item.batch)
        normalized = edition.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).first()
        if normalized:
            if work.document_type == "book":
                transaction.on_commit(
                    lambda asset=normalized: generate_cover_candidates(asset),
                    robust=True,
                )
            else:
                transaction.on_commit(
                    lambda asset=normalized: generate_recommendation_image(asset),
                    robust=True,
                )
        if was_published and normalized:
            transaction.on_commit(
                invalidate_public_recommendations,
                robust=True,
            )
            transaction.on_commit(
                lambda asset=normalized: index_asset(asset, is_public=True),
                robust=True,
            )
            transaction.on_commit(
                lambda asset=normalized: queue_semantic_job(
                    asset,
                    force=True,
                    actor=request.user,
                ),
                robust=True,
            )
        elif data["retry_publication"]:
            transaction.on_commit(
                lambda: _enqueue_review_processing(str(item.id)),
                robust=True,
            )
        return Response(
            UploadItemSerializer(item, context={"request": request}).data
        )


class PublicationPlaceReviewView(APIView):
    permission_classes = [IsLibraryStaff]

    def _item(self, item_id):
        return get_object_or_404(
            UploadItem.objects.select_related("edition__work"),
            pk=item_id,
            edition__isnull=False,
        )

    def get(self, request, item_id):
        item = self._item(item_id)
        return Response(
            {
                "publication_place": item.edition.publication_place,
                "results": [
                    serialize_publication_place_evidence(evidence)
                    for evidence in item.edition.publication_place_evidence.order_by(
                        "display_order",
                        "-confidence",
                    )
                ],
            }
        )

    def post(self, request, item_id):
        item = self._item(item_id)
        action = str(request.data.get("action") or "").strip()
        if action == "reanalyze":
            asset = item.edition.assets.filter(
                kind=Asset.Kind.NORMALIZED,
                status=Asset.Status.READY,
                is_current=True,
            ).first()
            if asset is None:
                return Response({"detail": "规范阅读 PDF 尚未就绪。"}, status=409)
            results = detect_publication_places(asset, force=True)
            return Response({"results": [serialize_publication_place_evidence(value) for value in results]})
        if action in {"confirm", "correct"}:
            evidence = get_object_or_404(
                PublicationPlaceEvidence,
                pk=request.data.get("evidence_id"),
                edition=item.edition,
            )
            corrected = str(request.data.get("value") or "").strip() if action == "correct" else ""
            if action == "correct" and not corrected:
                return Response({"value": ["人工修改时必须填写出版地。"]}, status=400)
            evidence = confirm_publication_place(
                evidence,
                actor=request.user,
                corrected_value=corrected,
                reason=str(request.data.get("reason") or "").strip()[:1000],
            )
            item.edition.refresh_from_db()
            return Response(
                {
                    "publication_place": item.edition.publication_place,
                    "result": serialize_publication_place_evidence(evidence),
                }
            )
        return Response({"action": ["请选择重新识别、确认或人工修改。"]}, status=400)


class MetadataSuggestionRefreshView(APIView):
    permission_classes = [IsCatalogEditor]

    def post(self, request, item_id):
        item = get_object_or_404(
            UploadItem.objects.select_related("edition__work"),
            pk=item_id,
            edition__isnull=False,
        )
        job = create_external_enrichment_job(item, actor=request.user)
        if job.status == ProcessingJob.Status.PAUSED:
            AuditEvent.objects.create(
                actor=request.user,
                action="metadata_suggestions_queued_while_paused",
                object_type="UploadItem",
                object_id=str(item.id),
                after={"job_id": str(job.id), "network_requested": False},
                request_ip=_request_ip(request),
            )
            return Response(
                {
                    "added": 0,
                    "queued": True,
                    "job_id": str(job.id),
                    "warnings": ["联网补充当前已暂停。任务已保留，恢复后会继续生成缺失候选。"],
                    "authority_links": authority_verification_links(
                        title=item.edition.work.title,
                        isbn=item.edition.isbn,
                        doi=item.edition.doi,
                        document_type=item.edition.work.document_type,
                    ),
                    "results": MetadataCandidateSerializer(
                        item.metadata_candidates.order_by("field_name", "-confidence", "created_at"),
                        many=True,
                    ).data,
                    "locked_fields": list(
                        item.edition.field_locks.values_list("field_name", flat=True)
                    ),
                },
                status=202,
            )
        if job.task_id and job.status in {
            ProcessingJob.Status.PENDING,
            ProcessingJob.Status.RUNNING,
        }:
            return Response(
                {
                    "added": 0,
                    "queued": True,
                    "job_id": str(job.id),
                    "warnings": ["已有联网补充任务正在等待或运行。"],
                    "results": MetadataCandidateSerializer(
                        item.metadata_candidates.order_by("field_name", "-confidence", "created_at"),
                        many=True,
                    ).data,
                    "locked_fields": list(
                        item.edition.field_locks.values_list("field_name", flat=True)
                    ),
                },
                status=202,
            )

        task_id = str(uuid.uuid4())
        job.task_id = task_id
        job.save(update_fields=["task_id", "updated_at"])
        job = run_external_enrichment_job(
            str(job.id),
            task_id=task_id,
            candidate_loader=refresh_remote_candidates,
        )
        candidate_stats = dict(job.stats or {})
        warnings = list(candidate_stats.get("warnings") or [])
        AuditEvent.objects.create(
            actor=request.user,
            action="metadata_suggestions_refreshed",
            object_type="UploadItem",
            object_id=str(item.id),
            after={
                "job_id": str(job.id),
                "received": candidate_stats.get("received", 0),
                "added": candidate_stats.get("added", 0),
                "updated": candidate_stats.get("updated", 0),
                "preserved": candidate_stats.get("preserved", 0),
                "superseded": candidate_stats.get("superseded", 0),
                "warnings": warnings,
                "sources": candidate_stats.get("sources", []),
                "manual_fields_preserved": True,
            },
            request_ip=_request_ip(request),
        )
        links = authority_verification_links(
            title=item.edition.work.title,
            isbn=item.edition.isbn,
            doi=item.edition.doi,
            document_type=item.edition.work.document_type,
        )
        return Response(
            {
                "added": candidate_stats.get("added", 0),
                "queued": job.status == ProcessingJob.Status.PAUSED,
                "job_id": str(job.id),
                "warnings": warnings,
                "authority_links": links,
                "results": MetadataCandidateSerializer(
                    item.metadata_candidates.order_by("field_name", "-confidence", "created_at"),
                    many=True,
                ).data,
                "locked_fields": list(
                    item.edition.field_locks.values_list("field_name", flat=True)
                ),
            }
        )


class MetadataCandidateDecisionView(APIView):
    permission_classes = [IsLibraryStaff]

    def post(self, request, item_id, candidate_id):
        candidate = get_object_or_404(
            MetadataCandidate.objects.select_related("upload_item"),
            pk=candidate_id,
            upload_item_id=item_id,
        )
        action = str(request.data.get("action") or "").strip().casefold()
        try:
            candidate = set_candidate_decision(
                candidate,
                action=action,
                actor=request.user,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        AuditEvent.objects.create(
            actor=request.user,
            action=f"metadata_candidate_{action}",
            object_type="MetadataCandidate",
            object_id=str(candidate.id),
            after={"lifecycle": candidate.lifecycle},
            request_ip=_request_ip(request),
        )
        return Response(MetadataCandidateSerializer(candidate).data)


class EntityResolutionDecisionView(APIView):
    permission_classes = [IsCatalogEditor]

    def post(self, request, item_id, candidate_id):
        candidate = get_object_or_404(
            EntityResolutionCandidate.objects.select_related("upload_item__edition"),
            pk=candidate_id,
            upload_item_id=item_id,
        )
        serializer = EntityResolutionDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        correlation_id = str(request.META.get("HTTP_X_REQUEST_ID") or "")[:128]
        before = {
            "status": candidate.status,
            "candidate_entity_type": candidate.candidate_entity_type,
            "candidate_entity_id": candidate.candidate_entity_id,
        }
        try:
            result = decide_entity_resolution(
                candidate,
                action=serializer.validated_data["action"],
                target_type=serializer.validated_data["target_type"],
                target_id=str(serializer.validated_data.get("target_id") or ""),
                confirm_identity=serializer.validated_data["confirm_identity"],
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
                correlation_id=correlation_id,
            )
        except ResolutionDecisionError as exc:
            return Response({"detail": str(exc)}, status=409)

        if not result.idempotent:
            AuditEvent.objects.create(
                actor=request.user,
                action=f"entity_resolution_{serializer.validated_data['action']}",
                object_type="EntityResolutionCandidate",
                object_id=str(result.candidate.id),
                before=before,
                after={
                    "status": result.candidate.status,
                    "target_type": result.candidate.target_type,
                    "candidate_entity_type": result.candidate.candidate_entity_type,
                    "candidate_entity_id": result.candidate.candidate_entity_id,
                    "review_task_id": str(result.review_task.id) if result.review_task else "",
                },
                request_ip=_request_ip(request),
                request_id=correlation_id,
            )
        return Response(
            {
                "candidate": EntityResolutionCandidateSerializer(result.candidate).data,
                "group": EntityResolutionCandidateSerializer(result.group, many=True).data,
                "review_task_status": result.review_task.status if result.review_task else None,
                "idempotent": result.idempotent,
            }
        )


class EntityResolutionDecisionRevertView(APIView):
    permission_classes = [IsCatalogEditor]

    def post(self, request, item_id, decision_id):
        decision = get_object_or_404(
            DecisionLog.objects.select_related("resolution_candidate__upload_item"),
            pk=decision_id,
            upload_item_id=item_id,
            resolution_candidate__isnull=False,
        )
        serializer = EntityResolutionRevertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        correlation_id = str(request.META.get("HTTP_X_REQUEST_ID") or "")[:128]
        try:
            result = revert_entity_resolution_decision(
                decision,
                actor=request.user,
                reason=serializer.validated_data["reason"],
                correlation_id=correlation_id,
            )
        except ResolutionDecisionError as exc:
            return Response({"detail": str(exc)}, status=409)
        if not result.idempotent:
            AuditEvent.objects.create(
                actor=request.user,
                action="entity_resolution_reverted",
                object_type="DecisionLog",
                object_id=str(result.decision.id),
                before={"action": result.decision.action},
                after={
                    "candidate_id": str(result.candidate.id),
                    "candidate_status": result.candidate.status,
                    "reversal_id": str(result.reversal.id),
                },
                request_ip=_request_ip(request),
                request_id=correlation_id,
            )
        return Response(
            {
                "candidate": EntityResolutionCandidateSerializer(result.candidate).data,
                "group": EntityResolutionCandidateSerializer(result.group, many=True).data,
                "review_task_status": result.review_task.status if result.review_task else None,
                "decision_id": str(result.decision.id),
                "reversal_id": str(result.reversal.id),
                "idempotent": result.idempotent,
            }
        )


class MetadataImportView(APIView):
    permission_classes = [IsCatalogEditor]

    def post(self, request, item_id):
        item = get_object_or_404(
            UploadItem.objects.select_related("edition", "asset"),
            pk=item_id,
        )
        serializer = MetadataImportRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        try:
            result = import_bibliographic_metadata(
                item,
                uploaded.read(),
                filename=uploaded.name,
                format_hint=serializer.validated_data.get("format", ""),
            )
        except MetadataImportError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=400,
            )
        AuditEvent.objects.create(
            actor=request.user,
            action="metadata_file_import",
            object_type="UploadItem",
            object_id=str(item.id),
            after={
                "format": result["format"],
                "filename": result["filename"],
                "source_record_id": str(result["source_record"].id),
                "reused_source": result["reused_source"],
                "stats": result["stats"],
                "normalized_record_sha256": result["normalized_record_sha256"],
                "candidates_only": True,
            },
            request_ip=_request_ip(request),
        )
        return Response(
            {
                "format": result["format"],
                "filename": result["filename"],
                "source_record": str(result["source_record"].id),
                "reused_source": result["reused_source"],
                "stats": result["stats"],
                "normalized_record_sha256": result["normalized_record_sha256"],
                "candidates": MetadataCandidateSerializer(result["candidates"], many=True).data,
            },
            status=200 if result["reused_source"] else 201,
        )


class PublishUploadItemView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get_permissions(self):
        permission_classes = [IsLibraryStaff] if self.request.method == "GET" else [IsLibraryAdmin]
        return [permission() for permission in permission_classes]

    def _item(self, item_id):
        return get_object_or_404(
            UploadItem.objects.select_related("edition__work", "batch"),
            pk=item_id,
        )

    def get(self, request, item_id):
        item = self._item(item_id)
        if item.edition is None:
            return Response({"detail": "文献记录尚未建立。"}, status=409)
        return Response(publication_preflight(item.edition))

    def post(self, request, item_id):
        item = self._item(item_id)
        if item.edition is None:
            return Response({"detail": "文献记录尚未建立。"}, status=409)
        if item.replacement_of_asset_id:
            return Response(
                {"detail": "替换文件必须完成处理后自动切换，不能跳过处理直接发布。"},
                status=409,
            )
        asset = item.edition.assets.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).first()
        preflight = publication_preflight(item.edition)
        if preflight["blockers"]:
            return Response(
                {"detail": "存在阻止发布的技术问题。", **preflight},
                status=409,
            )
        if asset is None:
            return Response(
                {"detail": "存在阻止发布的技术问题。", "blockers": ["公开阅读锚点文件未就绪"]},
                status=409,
            )
        confirmation = request.data.get("confirm_warnings")
        confirmed = confirmation is True or str(confirmation).casefold() in {"1", "true", "yes"}
        if preflight["warnings"] and not confirmed:
            return Response(
                {
                    "detail": "发布前请确认警告。",
                    "confirmation_required": True,
                    **preflight,
                },
                status=409,
            )
        try:
            transition_upload_item(
                item,
                UploadItem.WorkflowState.APPROVED,
                actor=request.user,
                reason="管理员确认发布预检",
                force=True,
            )
            transition_upload_item(
                item,
                UploadItem.WorkflowState.INDEXING,
                actor=request.user,
                reason="刷新公开索引",
            )
            published_edition = publish_edition(
                item.edition,
                actor=request.user,
                idempotency_key=f"manual:{item.id}:publish:{item.edition.updated_at.isoformat()}",
                allow_low_confidence=True,
                confirm_warnings=confirmed,
            )
        except PublicationBlocked as exc:
            transition_upload_item(
                item,
                UploadItem.WorkflowState.NEEDS_REVIEW,
                actor=request.user,
                reason="发布预检出现技术阻断",
                force=True,
            )
            return Response({"detail": "存在阻止发布的技术问题。", "blockers": exc.reasons}, status=409)
        except PublicationWarningsRequireConfirmation as exc:
            transition_upload_item(
                item,
                UploadItem.WorkflowState.NEEDS_REVIEW,
                actor=request.user,
                reason="发布警告尚未由管理员确认",
                force=True,
            )
            return Response(
                {"detail": "发布前请确认警告。", "warnings": exc.warnings, "confirmation_required": True},
                status=409,
            )
        index_warning = ""
        try:
            index_asset(asset, is_public=True)
            item.edition.search_indexed_at = timezone.now()
            item.edition.save(update_fields=["search_indexed_at", "updated_at"])
        except Exception as exc:
            index_warning = str(exc)[:2000]
            AuditEvent.objects.create(
                actor=request.user,
                action="public_index_refresh_failed",
                object_type="Edition",
                object_id=str(item.edition_id),
                after={"error": index_warning, "publication_preserved": True},
                request_ip=_request_ip(request),
            )
        item.status = UploadItem.Status.PUBLISHED
        item.stage_progress = 100
        transition_upload_item(
            item,
            UploadItem.WorkflowState.PUBLISHED,
            actor=request.user,
            reason="馆藏已由管理员发布",
        )
        item.save(update_fields=["status", "stage_progress", "updated_at"])
        refresh_batch(item.batch)
        scheduled_tasks, background_warnings = _schedule_publication_background_tasks(
            item,
            asset,
            request.user,
        )
        if background_warnings:
            AuditEvent.objects.create(
                actor=request.user,
                action="publication_background_warning",
                object_type="Edition",
                object_id=str(item.edition_id),
                after={
                    "warnings": background_warnings,
                    "publication_preserved": True,
                },
                request_ip=_request_ip(request),
            )
        return Response(
            {
                "detail": "文献已发布。",
                "preflight": preflight,
                "index_warning": index_warning,
                "scheduled_tasks": scheduled_tasks,
                "background_warnings": background_warnings,
            }
        )


class WithdrawUploadItemView(APIView):
    permission_classes = [IsLibraryAdmin]

    def post(self, request, item_id):
        item = get_object_or_404(UploadItem.objects.select_related("edition", "batch"), pk=item_id)
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if item.edition is None:
            return Response({"detail": "该上传记录没有可下架的文献。"}, status=409)
        edition = withdraw_edition(item.edition, actor=request.user, reason=serializer.validated_data.get("reason", ""))
        index_warnings = []
        for asset in edition.assets.filter(kind=Asset.Kind.NORMALIZED):
            try:
                remove_asset_from_index(asset)
            except Exception as exc:
                index_warnings.append(f"全文索引移除失败：{str(exc)[:500]}")
            try:
                remove_semantic_asset(str(asset.id))
            except Exception as exc:
                index_warnings.append(f"语义索引移除失败：{str(exc)[:500]}")
        affected_batches = list(
            UploadBatch.objects.filter(items__edition=edition).distinct()
        )
        related_items = list(UploadItem.objects.filter(edition=edition))
        for related_item in related_items:
            transition_upload_item(
                related_item,
                UploadItem.WorkflowState.ARCHIVED,
                actor=request.user,
                reason="管理员下架馆藏",
                force=True,
            )
            related_item.status = UploadItem.Status.WITHDRAWN
            related_item.save(update_fields=["status", "updated_at"])
        for batch in affected_batches:
            refresh_batch(batch)
        if index_warnings:
            AuditEvent.objects.create(
                actor=request.user,
                action="withdraw_index_cleanup_warning",
                object_type="Edition",
                object_id=str(edition.id),
                after={
                    "warnings": index_warnings,
                    "withdrawal_preserved": True,
                },
                request_ip=_request_ip(request),
            )
        return Response(
            {
                "detail": "文献已下架。公开接口会立即按发布状态排除该馆藏，PDF、OCR、索引记录和云端文件均已保留。",
                "index_warnings": index_warnings,
            }
        )


class ProcessingCenterView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request):
        job_type = str(request.query_params.get("job_type") or "").strip()
        status_filter = str(request.query_params.get("status") or "").strip()
        jobs = ProcessingJob.objects.select_related(
            "edition__work",
            "asset",
            "upload_item",
        )
        if job_type:
            jobs = jobs.filter(job_type=job_type)
        if status_filter:
            jobs = jobs.filter(status=status_filter)
        rows = [
            {
                "id": str(job.id),
                "source": "processing_job",
                "job_type": job.job_type,
                "item_id": str(job.upload_item_id) if job.upload_item_id else None,
                "asset_id": str(job.asset_id) if job.asset_id else None,
                "title": job.edition.work.title if job.edition_id else "",
                "status": job.status,
                "progress": job.progress,
                "engine": job.engine,
                "attempt": job.attempt,
                "max_attempts": job.max_attempts,
                "settings_version": job.settings_version,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "duration_seconds": (
                    round(((job.finished_at or timezone.now()) - job.started_at).total_seconds(), 2)
                    if job.started_at
                    else None
                ),
                "last_error": job.error_message,
                "error_code": job.error_code,
                "stats": job.stats,
            }
            for job in jobs[:300]
        ]
        semantic_jobs = SemanticIndexJob.objects.select_related("asset__edition__work")
        if job_type and job_type != ProcessingJob.JobType.SEMANTIC_INDEX:
            semantic_jobs = semantic_jobs.none()
        semantic_status_map = {
            SemanticIndexJob.Status.QUEUED: ProcessingJob.Status.PENDING,
            SemanticIndexJob.Status.RUNNING: ProcessingJob.Status.RUNNING,
            SemanticIndexJob.Status.COMPLETED: ProcessingJob.Status.SUCCEEDED,
            SemanticIndexJob.Status.PARTIAL: ProcessingJob.Status.FAILED,
            SemanticIndexJob.Status.FAILED: ProcessingJob.Status.FAILED,
            SemanticIndexJob.Status.CANCELED: ProcessingJob.Status.CANCELED,
            SemanticIndexJob.Status.PAUSED: ProcessingJob.Status.PAUSED,
        }
        for job in semantic_jobs[:300]:
            mapped_status = semantic_status_map[job.status]
            if status_filter and mapped_status != status_filter:
                continue
            rows.append(
                {
                    "id": str(job.id),
                    "source": "semantic_index_job",
                    "job_type": ProcessingJob.JobType.SEMANTIC_INDEX,
                    "item_id": None,
                    "asset_id": str(job.asset_id) if job.asset_id else None,
                    "title": job.asset.edition.work.title if job.asset_id else "",
                    "status": mapped_status,
                    "progress": job.progress,
                    "engine": job.model_name,
                    "attempt": job.attempts,
                    "max_attempts": 3,
                    "settings_version": job.chunk_version,
                    "created_at": job.created_at,
                    "started_at": job.started_at,
                    "finished_at": job.finished_at,
                    "duration_seconds": (
                        round(((job.finished_at or timezone.now()) - job.started_at).total_seconds(), 2)
                        if job.started_at
                        else None
                    ),
                    "last_error": job.error_message,
                    "error_code": job.error_code,
                    "stats": job.stats,
                }
            )
        rows.sort(key=lambda row: row["created_at"], reverse=True)
        return Response(
            {
                "results": rows[:300],
                "counts": {
                    value: sum(1 for row in rows if row["status"] == value)
                    for value in ProcessingJob.Status.values
                },
                "workloads": {
                    job_type: {"paused": processing_workload_paused(job_type)}
                    for job_type in PROCESSING_PAUSE_KEYS
                },
            }
        )

    def post(self, request):
        if not has_capability(request.user, Capability.RETRY_JOBS):
            return Response({"detail": "只有管理员可以暂停、恢复、重试或取消处理任务。"}, status=403)
        action = str(request.data.get("action") or "").strip()
        workload_job_type = str(request.data.get("job_type") or "").strip()
        if action in {"pause_workload", "resume_workload"}:
            if workload_job_type not in PROCESSING_PAUSE_KEYS:
                return Response({"job_type": ["请选择 OCR 或联网补充任务。"]}, status=400)
            paused = action == "pause_workload"
            counts = set_processing_workload_paused(
                workload_job_type,
                paused,
                actor=request.user,
            )
            queued = 0
            if not paused:
                queued = resume_paused_workload(workload_job_type, actor=request.user)
            return Response(
                {
                    "job_type": workload_job_type,
                    "paused": paused,
                    "queued": queued,
                    **counts,
                }
            )
        source = str(request.data.get("source") or "processing_job").strip()
        job_id = request.data.get("job_id")
        if source == "semantic_index_job":
            job = get_object_or_404(
                SemanticIndexJob.objects.select_related("asset", "index_version"),
                pk=job_id,
            )
            if action == "cancel" and job.status in {
                SemanticIndexJob.Status.QUEUED,
                SemanticIndexJob.Status.PAUSED,
            }:
                job.status = SemanticIndexJob.Status.CANCELED
                job.finished_at = timezone.now()
                job.save(update_fields=["status", "finished_at", "updated_at"])
                return Response({"status": job.status})
            if action == "pause":
                try:
                    job = request_semantic_job_pause(job)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=409)
                return Response({"job_id": str(job.id), "status": job.status}, status=202)
            if action == "resume":
                try:
                    job = resume_semantic_job(job, actor=request.user)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=409)
                return Response({"job_id": str(job.id), "status": job.status}, status=202)
            if action == "retry" and job.asset_id:
                job.status = SemanticIndexJob.Status.CANCELED
                job.finished_at = timezone.now()
                job.save(update_fields=["status", "finished_at", "updated_at"])
                replacement = queue_semantic_job(
                    job.asset,
                    force=True,
                    actor=request.user,
                    index_version=job.index_version,
                )
                return Response({"job_id": str(replacement.id), "status": replacement.status}, status=202)
            return Response({"detail": "该语义任务当前不能执行所选操作。"}, status=409)
        job = get_object_or_404(
            ProcessingJob.objects.select_related("asset", "upload_item"),
            pk=job_id,
        )
        if action == "pause":
            try:
                job = request_processing_job_pause(job)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=409)
            return Response({"job_id": str(job.id), "status": job.status}, status=202)
        if action == "resume":
            try:
                job = resume_processing_job(job, actor=request.user)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=409)
            return Response({"job_id": str(job.id), "status": job.status}, status=202)
        if action == "cancel" and job.status in {
            ProcessingJob.Status.PENDING,
            ProcessingJob.Status.PAUSED,
        }:
            job.status = ProcessingJob.Status.CANCELED
            job.task_id = ""
            job.pause_requested_at = None
            job.finished_at = timezone.now()
            job.save(
                update_fields=[
                    "status",
                    "task_id",
                    "pause_requested_at",
                    "finished_at",
                    "updated_at",
                ]
            )
            return Response({"status": job.status})
        if action == "retry" and (job.asset_id or job.upload_item_id):
            job.status = ProcessingJob.Status.CANCELED
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "finished_at", "updated_at"])
            if job.job_type == ProcessingJob.JobType.OCR:
                replacement = queue_ocr_job(
                    job.asset,
                    upload_item=job.upload_item,
                    actor=request.user,
                    force=True,
                )
            elif job.job_type == ProcessingJob.JobType.PAGE_LABELS:
                replacement = queue_page_label_job(
                    job.asset,
                    upload_item=job.upload_item,
                    actor=request.user,
                    force=True,
                )
            elif (
                job.job_type == ProcessingJob.JobType.EXTERNAL_ENRICHMENT
                and job.upload_item_id
            ):
                replacement = queue_external_enrichment_job(
                    job.upload_item,
                    actor=request.user,
                    force=True,
                )
            elif (
                job.job_type == ProcessingJob.JobType.R2_STAGING
                and job.upload_item_id
            ):
                phase = str((job.stats or {}).get("phase") or "")
                if (
                    phase == "import"
                    and job.upload_item.staging_status == UploadItem.StagingStatus.IMPORT_FAILED
                ):
                    replacement = retry_r2_import(job.upload_item, actor=request.user)
                elif phase in {"import", "cleanup"}:
                    replacement = queue_r2_staging_job(
                        job.upload_item,
                        phase=phase,
                        actor=request.user,
                        force=True,
                    )
                else:
                    return Response({"detail": "R2 staging 任务缺少有效阶段。"}, status=409)
            else:
                return Response({"detail": "该任务类型尚不支持人工重试。"}, status=409)
            return Response({"job_id": str(replacement.id), "status": replacement.status}, status=202)
        return Response({"detail": "该任务当前不能执行所选操作。"}, status=409)


class SystemHealthView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        from .services.system_health import system_health_snapshot

        return Response(system_health_snapshot())

    def post(self, request):
        if str(request.data.get("action") or "").strip() != "self_test":
            return Response({"action": ["请选择端到端自检。"]}, status=400)
        from .services.system_health import run_end_to_end_self_test

        return Response(run_end_to_end_self_test())


class DeleteUploadItemView(APIView):
    """Soft-delete an intake record while preserving NAS files and the audit trail."""

    permission_classes = [IsLibraryAdmin]

    def post(self, request, item_id):
        item = get_object_or_404(
            UploadItem.objects.select_related("edition__work", "batch"),
            pk=item_id,
        )
        duplicate_intake = item.error_code == "duplicate_document"
        if (
            item.edition_id
            and item.edition.state == PublicationState.PUBLISHED
            and not duplicate_intake
        ):
            return Response({"detail": "公开文献必须先下架，再删除处理记录。"}, status=409)
        expected = item.edition.work.title if item.edition_id else item.source_filename
        legacy_confirmation = str(request.data.get("confirmation", "")).strip()
        confirmed = request.data.get("confirmed") is True or legacy_confirmation == expected
        if not confirmed:
            return Response(
                {"confirmed": ["请在确认框中确认移除处理记录。"]},
                status=400,
            )
        before = {
            "status": item.status,
            "source_filename": item.source_filename,
            "edition_id": str(item.edition_id or ""),
        }
        item.status = UploadItem.Status.DELETED
        item.stage_progress = 0
        item.error_code = ""
        item.error_message = "管理员已从处理队列移除。NAS 原始文件和审计记录仍保留。"
        item.processing_token = ""
        transition_upload_item(
            item,
            UploadItem.WorkflowState.ARCHIVED,
            actor=request.user,
            reason="管理员移除处理记录",
            force=True,
        )
        item.save(
            update_fields=[
                "status",
                "stage_progress",
                "error_code",
                "error_message",
                "processing_token",
                "updated_at",
            ]
        )
        refresh_batch(item.batch)
        AuditEvent.objects.create(
            actor=request.user,
            action="upload_item_delete",
            object_type="UploadItem",
            object_id=str(item.id),
            before=before,
            after={
                "status": UploadItem.Status.DELETED,
                "files_preserved": True,
                "linked_publication_preserved": duplicate_intake,
            },
            request_ip=_request_ip(request),
        )
        return Response({"detail": "记录已从待处理和复核列表移除，NAS 文件仍保留。"})


class DashboardView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request):
        edition_stats = Edition.objects.aggregate(
            total=Count("id"),
            published=Count("id", filter=Q(state=PublicationState.PUBLISHED)),
            withdrawn=Count("id", filter=Q(state=PublicationState.WITHDRAWN)),
        )
        return Response(
            {
                "documents": edition_stats,
                "pdf_assets": Asset.objects.filter(kind=Asset.Kind.NORMALIZED).count(),
                "theory_schools": TheorySchool.objects.count(),
                "scholars": ScholarProfile.objects.count(),
                "users": get_user_model().objects.count(),
                "needs_review": UploadItem.objects.filter(status=UploadItem.Status.NEEDS_REVIEW).count(),
                "processing": UploadItem.objects.exclude(
                    status__in=[
                        UploadItem.Status.PUBLISHED,
                        UploadItem.Status.NEEDS_REVIEW,
                        UploadItem.Status.FAILED,
                        UploadItem.Status.WITHDRAWN,
                        UploadItem.Status.DELETED,
                    ]
                ).count(),
                "recent_batches": UploadBatchSerializer(
                    UploadBatch.objects.order_by("-created_at")[:5],
                    many=True,
                ).data,
                "recent_items": UploadItemSerializer(
                    UploadItem.objects.select_related(
                        "batch__created_by",
                        "edition__work",
                    ).exclude(status=UploadItem.Status.DELETED).order_by("-created_at")[:8],
                    many=True,
                ).data,
                "status_counts": {
                    row["status"]: row["count"]
                    for row in UploadItem.objects.values("status").annotate(count=Count("id"))
                },
            }
        )
