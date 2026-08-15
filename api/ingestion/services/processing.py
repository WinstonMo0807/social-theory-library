from __future__ import annotations

import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError as KombuOperationalError

from catalog.models import (
    Asset,
    Edition,
    OcrStatus,
    Page,
    PageLabelStatus,
    PublicationState,
    SemanticIndexStatus,
    SiteSetting,
)
from catalog.services.semantic_indexing import queue_semantic_job
from catalog.services.page_labels import infer_page_labels
from catalog.services.publication_places import detect_publication_places
from catalog.services.theory_suggestions import generate_theory_review_tasks
from ingestion.models import ProcessingJob, UploadItem

from .candidate_store import persist_metadata_candidates
from .extract import extract_ocr_page_batch, persist_page_batch
from .files import materialize_field_file
from .indexing import index_asset
from .ocr_pdf import create_searchable_ocr_pdf
from .ocr_provider import OCR_RUNTIME_KEY, ocr_runtime_config
from .provider_gateway import refresh_remote_candidates
from .taxonomy import (
    controlled_vocabulary_candidates_for_asset,
    persist_controlled_vocabulary_candidates,
)


PROCESSING_PAUSE_KEYS = {
    ProcessingJob.JobType.OCR: "ocr_processing_paused",
    ProcessingJob.JobType.EXTERNAL_ENRICHMENT: "external_enrichment_paused",
}


def processing_workload_paused(job_type: str) -> bool:
    key = PROCESSING_PAUSE_KEYS.get(job_type)
    if key is None:
        raise ValueError("该处理类型不支持全局暂停。")
    stored = SiteSetting.objects.filter(key=key).only("value").first()
    return bool(stored and stored.value is True)


def set_processing_workload_paused(job_type: str, paused: bool, *, actor=None) -> dict[str, int]:
    key = PROCESSING_PAUSE_KEYS.get(job_type)
    if key is None:
        raise ValueError("该处理类型不支持全局暂停。")
    SiteSetting.objects.update_or_create(
        key=key,
        defaults={"value": bool(paused), "public": False, "updated_by": actor},
    )
    if not paused:
        return {"jobs_paused": 0, "jobs_pause_requested": 0}

    now = timezone.now()
    pending = ProcessingJob.objects.filter(
        job_type=job_type,
        status=ProcessingJob.Status.PENDING,
    ).update(
        status=ProcessingJob.Status.PAUSED,
        task_id="",
        pause_requested_at=now,
        updated_at=now,
    )
    running = ProcessingJob.objects.filter(
        job_type=job_type,
        status=ProcessingJob.Status.RUNNING,
        pause_requested_at__isnull=True,
    ).update(pause_requested_at=now, updated_at=now)
    return {"jobs_paused": pending, "jobs_pause_requested": running}


def _pause_requested(job: ProcessingJob) -> bool:
    job.refresh_from_db(fields=["status", "task_id", "pause_requested_at", "updated_at"])
    return bool(
        job.status == ProcessingJob.Status.PAUSED
        or job.pause_requested_at
        or processing_workload_paused(job.job_type)
    )


def _mark_job_paused(job: ProcessingJob) -> ProcessingJob:
    job.status = ProcessingJob.Status.PAUSED
    job.task_id = ""
    job.pause_requested_at = job.pause_requested_at or timezone.now()
    job.finished_at = None
    job.save(
        update_fields=[
            "status",
            "task_id",
            "pause_requested_at",
            "finished_at",
            "updated_at",
        ]
    )
    return job


def request_processing_job_pause(job: ProcessingJob) -> ProcessingJob:
    if job.job_type not in PROCESSING_PAUSE_KEYS:
        raise ValueError("该任务类型不支持协作式暂停。")
    if job.status == ProcessingJob.Status.PAUSED:
        return job
    if job.status not in {ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING}:
        raise ValueError("该任务当前不能暂停。")
    job.pause_requested_at = timezone.now()
    if job.status == ProcessingJob.Status.PENDING:
        job.status = ProcessingJob.Status.PAUSED
        job.task_id = ""
    job.save(update_fields=["pause_requested_at", "status", "task_id", "updated_at"])
    return job


def resume_processing_job(job: ProcessingJob, *, actor=None) -> ProcessingJob:
    if job.job_type not in PROCESSING_PAUSE_KEYS:
        raise ValueError("该任务类型不支持恢复。")
    if processing_workload_paused(job.job_type):
        raise ValueError("该类任务仍处于全局暂停状态。")
    if job.status == ProcessingJob.Status.RUNNING and job.pause_requested_at:
        job.pause_requested_at = None
        job.save(update_fields=["pause_requested_at", "updated_at"])
        return job
    if job.status != ProcessingJob.Status.PAUSED:
        raise ValueError("只有已暂停任务可以恢复。")

    task_id = str(uuid.uuid4())
    job.status = ProcessingJob.Status.PENDING
    job.task_id = task_id
    job.pause_requested_at = None
    job.error_code = ""
    job.error_message = ""
    job.finished_at = None
    if actor is not None and job.created_by_id is None:
        job.created_by = actor
    job.save(
        update_fields=[
            "status",
            "task_id",
            "pause_requested_at",
            "error_code",
            "error_message",
            "finished_at",
            "created_by",
            "updated_at",
        ]
    )
    if job.job_type == ProcessingJob.JobType.OCR:
        transaction.on_commit(lambda: dispatch_ocr_job(str(job.id), task_id))
    else:
        transaction.on_commit(lambda: dispatch_external_enrichment_job(str(job.id), task_id))
    return job


def resume_paused_workload(job_type: str, *, actor=None, limit: int = 500) -> int:
    if processing_workload_paused(job_type):
        return 0
    queued = 0
    for job in ProcessingJob.objects.filter(
        job_type=job_type,
        status=ProcessingJob.Status.PAUSED,
    ).order_by("created_at")[:limit]:
        resume_processing_job(job, actor=actor)
        queued += 1
    return queued


def _settings_version() -> str:
    setting = SiteSetting.objects.filter(key=OCR_RUNTIME_KEY).only("updated_at").first()
    return setting.updated_at.isoformat() if setting else "environment-default"


def create_ocr_job(asset: Asset, *, upload_item=None, actor=None, force: bool = False) -> ProcessingJob:
    pending = asset.processing_jobs.filter(
        job_type=ProcessingJob.JobType.OCR,
        status__in=[
            ProcessingJob.Status.PENDING,
            ProcessingJob.Status.RUNNING,
            ProcessingJob.Status.PAUSED,
        ],
    ).first()
    if pending and not force:
        return pending
    config = ocr_runtime_config()
    paused = processing_workload_paused(ProcessingJob.JobType.OCR)
    return ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.PAUSED if paused else ProcessingJob.Status.PENDING,
        upload_item=upload_item,
        edition=asset.edition,
        asset=asset,
        engine=config["mode"],
        settings_version=_settings_version(),
        created_by=actor,
        pause_requested_at=timezone.now() if paused else None,
    )


def queue_ocr_job(asset: Asset, *, upload_item=None, actor=None, force: bool = False) -> ProcessingJob:
    job = create_ocr_job(asset, upload_item=upload_item, actor=actor, force=force)
    if job.task_id or job.status in {ProcessingJob.Status.RUNNING, ProcessingJob.Status.PAUSED}:
        return job
    task_id = str(uuid.uuid4())
    job.task_id = task_id
    job.status = ProcessingJob.Status.PENDING
    job.error_code = ""
    job.error_message = ""
    job.finished_at = None
    job.save(
        update_fields=[
            "task_id",
            "status",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )
    transaction.on_commit(lambda: dispatch_ocr_job(str(job.id), task_id))
    return job


def dispatch_ocr_job(job_id: str, task_id: str) -> bool:
    from ingestion.tasks import process_ocr_job

    try:
        process_ocr_job.apply_async(
            args=[job_id],
            task_id=task_id,
            ignore_result=True,
        )
    except (KombuOperationalError, OSError, ConnectionError, TimeoutError) as exc:
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id).update(
            status=ProcessingJob.Status.FAILED,
            error_code="queue_unavailable",
            error_message=f"OCR 任务未进入队列：{exc}"[:4000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        job = ProcessingJob.objects.filter(pk=job_id).only("edition_id").first()
        if job and job.edition_id:
            Edition.objects.filter(pk=job.edition_id).update(
                ocr_status=OcrStatus.FAILED,
                updated_at=timezone.now(),
            )
        return False
    return True


def create_external_enrichment_job(
    item: UploadItem,
    *,
    actor=None,
    force: bool = False,
) -> ProcessingJob:
    pending = item.processing_jobs.filter(
        job_type=ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
        status__in=[
            ProcessingJob.Status.PENDING,
            ProcessingJob.Status.RUNNING,
            ProcessingJob.Status.PAUSED,
        ],
    ).first()
    if pending and not force:
        return pending
    paused = processing_workload_paused(ProcessingJob.JobType.EXTERNAL_ENRICHMENT)
    return ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
        status=ProcessingJob.Status.PAUSED if paused else ProcessingJob.Status.PENDING,
        upload_item=item,
        edition=item.edition,
        asset=item.asset,
        engine="metadata-provider-gateway",
        settings_version="provider-gateway-v1",
        created_by=actor,
        pause_requested_at=timezone.now() if paused else None,
    )


def queue_external_enrichment_job(
    item: UploadItem,
    *,
    actor=None,
    force: bool = False,
) -> ProcessingJob:
    job = create_external_enrichment_job(item, actor=actor, force=force)
    if job.task_id or job.status in {ProcessingJob.Status.RUNNING, ProcessingJob.Status.PAUSED}:
        return job
    task_id = str(uuid.uuid4())
    job.task_id = task_id
    job.status = ProcessingJob.Status.PENDING
    job.pause_requested_at = None
    job.error_code = ""
    job.error_message = ""
    job.finished_at = None
    job.save(
        update_fields=[
            "task_id",
            "status",
            "pause_requested_at",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )
    transaction.on_commit(lambda: dispatch_external_enrichment_job(str(job.id), task_id))
    return job


def dispatch_external_enrichment_job(job_id: str, task_id: str) -> bool:
    from ingestion.tasks import process_external_enrichment_job

    try:
        process_external_enrichment_job.apply_async(
            args=[job_id],
            task_id=task_id,
            ignore_result=True,
        )
    except (KombuOperationalError, OSError, ConnectionError, TimeoutError) as exc:
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id).update(
            status=ProcessingJob.Status.FAILED,
            error_code="queue_unavailable",
            error_message=f"联网补充任务未进入队列：{exc}"[:4000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return False
    return True


def run_external_enrichment_job(
    job_id: str,
    *,
    task_id: str = "",
    candidate_loader=None,
) -> ProcessingJob:
    job = ProcessingJob.objects.select_related("upload_item__edition__work").get(pk=job_id)
    if task_id and task_id != job.task_id:
        return job
    if job.status == ProcessingJob.Status.CANCELED:
        return job
    if job.upload_item is None or job.upload_item.edition_id is None:
        job.status = ProcessingJob.Status.FAILED
        job.error_code = "missing_upload_item"
        job.error_message = "联网补充目标馆藏已经不存在。"
        job.finished_at = timezone.now()
        job.save()
        return job
    if _pause_requested(job):
        return _mark_job_paused(job)

    job.status = ProcessingJob.Status.RUNNING
    job.attempt += 1
    job.progress = max(5, job.progress)
    job.started_at = job.started_at or timezone.now()
    job.finished_at = None
    job.error_code = ""
    job.error_message = ""
    job.save()
    try:
        candidates, warnings = (candidate_loader or refresh_remote_candidates)(
            job.upload_item.edition,
            upload_item=job.upload_item,
            should_continue=lambda: not _pause_requested(job),
        )
        candidate_stats = persist_metadata_candidates(
            job.upload_item,
            candidates,
            selected={},
            supersede_sources={candidate.source for candidate in candidates},
        )
        job.stats = {
            "received": len(candidates),
            **candidate_stats,
            "warnings": warnings,
            "sources": sorted({candidate.source for candidate in candidates}),
            "manual_fields_preserved": True,
        }
        if _pause_requested(job):
            job.progress = min(95, max(job.progress, 10))
            job.save(update_fields=["progress", "stats", "updated_at"])
            return _mark_job_paused(job)
        job.status = ProcessingJob.Status.SUCCEEDED
        job.progress = 100
        job.pause_requested_at = None
        job.finished_at = timezone.now()
        job.save()
        return job
    except Exception as exc:
        job.status = ProcessingJob.Status.FAILED
        job.error_code = exc.__class__.__name__
        job.error_message = str(exc)[:4000]
        job.finished_at = timezone.now()
        job.save()
        raise


def queue_page_label_job(asset: Asset, *, upload_item=None, actor=None, force: bool = False) -> ProcessingJob:
    pending = asset.processing_jobs.filter(
        job_type=ProcessingJob.JobType.PAGE_LABELS,
        status__in=[ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING],
    ).first()
    if pending and not force:
        return pending
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.PAGE_LABELS,
        upload_item=upload_item,
        edition=asset.edition,
        asset=asset,
        engine="pdf-labels-and-ocr-margins",
        settings_version="page-labels-v1",
        created_by=actor,
        task_id=str(uuid.uuid4()),
    )
    transaction.on_commit(lambda: dispatch_page_label_job(str(job.id), job.task_id))
    return job


def dispatch_page_label_job(job_id: str, task_id: str) -> bool:
    from ingestion.tasks import process_page_label_job

    try:
        process_page_label_job.apply_async(
            args=[job_id],
            task_id=task_id,
            ignore_result=True,
        )
    except (KombuOperationalError, OSError, ConnectionError, TimeoutError) as exc:
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id).update(
            status=ProcessingJob.Status.FAILED,
            error_code="queue_unavailable",
            error_message=f"页码识别任务未进入队列：{exc}"[:4000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return False
    return True


def run_page_label_job(job_id: str, *, task_id: str = "") -> ProcessingJob:
    job = ProcessingJob.objects.select_related("asset__edition").get(pk=job_id)
    if task_id and job.task_id and task_id != job.task_id:
        return job
    if job.status == ProcessingJob.Status.CANCELED:
        return job
    if job.asset is None:
        job.status = ProcessingJob.Status.FAILED
        job.error_code = "missing_asset"
        job.error_message = "页码识别目标文件已经不存在。"
        job.finished_at = timezone.now()
        job.save()
        return job
    job.status = ProcessingJob.Status.RUNNING
    job.attempt += 1
    job.progress = 10
    job.started_at = timezone.now()
    job.save()
    try:
        result = infer_page_labels(job.asset)
        job.status = ProcessingJob.Status.SUCCEEDED
        job.progress = 100
        job.stats = result
        job.error_code = ""
        job.error_message = ""
        job.finished_at = timezone.now()
        job.save()
        return job
    except Exception as exc:
        job.status = ProcessingJob.Status.FAILED
        job.error_code = exc.__class__.__name__
        job.error_message = str(exc)[:4000]
        job.finished_at = timezone.now()
        job.save()
        raise


def _remaining_ocr_page_indexes(asset: Asset) -> tuple[int, int, list[int]]:
    rows = list(
        asset.pages.order_by("index").values_list("index", "text_source")
    )
    document_page_count = int(asset.page_count or (rows[-1][0] if rows else 0))
    configured_targets = (asset.validation_details or {}).get(
        "ocr_required_page_indexes"
    )
    if isinstance(configured_targets, list):
        targets = sorted(
            {
                int(index)
                for index in configured_targets
                if str(index).isdigit() and 1 <= int(index) <= document_page_count
            }
        )
    else:
        # Assets created before per-page detection deliberately keep the old
        # whole-document behavior so an in-flight OCR job never skips pages.
        targets = list(range(1, document_page_count + 1))
    completed = {
        int(index)
        for index, text_source in rows
        if text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}
    }
    remaining = [index for index in targets if index not in completed]
    return document_page_count, len(targets), remaining


def run_ocr_job(job_id: str, *, task_id: str = "") -> ProcessingJob:
    job = ProcessingJob.objects.select_related("asset__edition").get(pk=job_id)
    if task_id and task_id != job.task_id:
        return job
    if job.status == ProcessingJob.Status.CANCELED:
        return job
    if job.asset is None:
        job.status = ProcessingJob.Status.FAILED
        job.error_code = "missing_asset"
        job.error_message = "OCR 目标文件已经不存在。"
        job.finished_at = timezone.now()
        job.save()
        return job
    if job.status == ProcessingJob.Status.FAILED and job.attempt >= job.max_attempts:
        return job

    asset = job.asset
    edition = asset.edition
    if _pause_requested(job):
        edition.ocr_status = OcrStatus.PENDING
        edition.save(update_fields=["ocr_status", "updated_at"])
        return _mark_job_paused(job)
    stats = dict(job.stats or {})
    retrying_failed_batch = job.status == ProcessingJob.Status.FAILED
    if not stats.get("batch_session_started") or retrying_failed_batch:
        job.attempt += 1
    stats["batch_session_started"] = True
    job.status = ProcessingJob.Status.RUNNING
    job.started_at = job.started_at or timezone.now()
    job.finished_at = None
    job.progress = max(5, job.progress)
    job.error_code = ""
    job.error_message = ""
    job.stats = stats
    job.save()
    edition.ocr_status = OcrStatus.RUNNING
    edition.save(update_fields=["ocr_status", "updated_at"])

    cleanup = None
    next_task_id = ""
    try:
        document_page_count, target_page_count, remaining = _remaining_ocr_page_indexes(asset)
        if document_page_count <= 0:
            raise ValueError("OCR 目标文件没有可处理的页面。")

        provider = str(stats.get("engine") or asset.extraction_method or "paddleocr_nas")
        if remaining:
            batch_indexes = remaining[: settings.OCR_PAGE_BATCH_SIZE]
            local_path, cleanup = materialize_field_file(asset.file)
            pages, provider = extract_ocr_page_batch(local_path, batch_indexes)
            returned_indexes = {page.index for page in pages}
            if returned_indexes != set(batch_indexes):
                raise ValueError(
                    "OCR 批次返回页码与请求不一致："
                    f"请求 {batch_indexes[0]}-{batch_indexes[-1]}，"
                    f"返回 {sorted(returned_indexes)}。"
                )
            persist_page_batch(asset, pages)

            document_page_count, target_page_count, remaining = _remaining_ocr_page_indexes(asset)
            processed_pages = target_page_count - len(remaining)
            providers = list(stats.get("providers") or [])
            if provider not in providers:
                providers.append(provider)
            stats.update(
                {
                    "engine": provider,
                    "providers": providers,
                    "total_pages": document_page_count,
                    "target_pages": target_page_count,
                    "processed_pages": processed_pages,
                    "remaining_pages": len(remaining),
                    "page_batch_size": settings.OCR_PAGE_BATCH_SIZE,
                    "last_batch_page_indexes": batch_indexes,
                    "completed_batches": int(stats.get("completed_batches") or 0) + 1,
                }
            )
            asset.validation_details = {
                **(asset.validation_details or {}),
                "ocr_progress": {
                    "processed_pages": processed_pages,
                    "target_pages": target_page_count,
                    "document_pages": document_page_count,
                    "last_batch_page_indexes": batch_indexes,
                    "updated_at": timezone.now().isoformat(),
                },
            }
            asset.save(update_fields=["validation_details", "updated_at"])
            job.engine = provider
            job.progress = min(
                90,
                max(
                    5,
                    5
                    + round(
                        (processed_pages / max(target_page_count, 1)) * 85
                    ),
                ),
            )
            job.stats = stats
            job.save(update_fields=["progress", "engine", "stats", "updated_at"])

        # OCR is cooperative. A running batch is allowed to finish and persist
        # its pages before a pause takes effect, so resume can continue from
        # the remaining page indexes without revoking a worker task.
        if _pause_requested(job):
            edition.ocr_status = OcrStatus.PENDING
            edition.save(update_fields=["ocr_status", "updated_at"])
            return _mark_job_paused(job)

        if remaining:
            queued_task_id = str(uuid.uuid4())
            job.status = ProcessingJob.Status.PENDING
            job.task_id = queued_task_id
            job.finished_at = None
            job.save(
                update_fields=[
                    "status",
                    "task_id",
                    "finished_at",
                    "updated_at",
                ]
            )
            next_task_id = queued_task_id
        else:
            stats.update(
                {
                    "engine": provider,
                    "total_pages": document_page_count,
                    "target_pages": target_page_count,
                    "processed_pages": target_page_count,
                    "remaining_pages": 0,
                }
            )

        if not next_task_id:
            job.progress = 92
            job.stats = stats
            job.save(update_fields=["progress", "stats", "updated_at"])

        if next_task_id:
            return job

        asset.page_count = document_page_count
        asset.extraction_method = provider
        asset.validation_status = Asset.ValidationStatus.VALID
        asset.validation_details = {
            **(asset.validation_details or {}),
            "ocr_pages": target_page_count,
            "ocr_engine": provider,
            "ocr_finished_at": timezone.now().isoformat(),
        }
        asset.save(
            update_fields=[
                "page_count",
                "extraction_method",
                "validation_status",
                "validation_details",
                "updated_at",
            ]
        )

        try:
            place_evidence = detect_publication_places(
                asset,
                force=True,
                allow_targeted_ocr=False,
            )
            stats["publication_place_candidates"] = len(place_evidence)
        except Exception as exc:
            # Metadata enrichment must not turn a usable OCR result into a
            # failed reading artifact.
            stats["publication_place_warning"] = str(exc)[:2000]
        if job.upload_item_id:
            try:
                taxonomy_candidates = controlled_vocabulary_candidates_for_asset(asset)
                stats["taxonomy_candidates"] = persist_controlled_vocabulary_candidates(
                    job.upload_item,
                    taxonomy_candidates,
                )
            except Exception as exc:
                stats["taxonomy_candidate_warning"] = str(exc)[:2000]
        reason_counts = (asset.validation_details or {}).get("ocr_reason_counts") or {}
        should_build_ocr_pdf = not reason_counts or int(reason_counts.get("scanned_page") or 0) > 0
        if should_build_ocr_pdf:
            try:
                derivative = create_searchable_ocr_pdf(
                    asset,
                    processor=provider,
                    processor_version=job.settings_version or "runtime-default",
                )
                stats["ocr_pdf"] = {
                    "asset_id": str(derivative.id),
                    "version": derivative.version,
                    "sha256": derivative.sha256,
                    "validation_status": derivative.validation_status,
                }
            except Exception as exc:
                # The independent OCR text layer remains usable even when a
                # downloadable derivative cannot be produced.
                stats["ocr_pdf_warning"] = str(exc)[:2000]
        else:
            stats["ocr_pdf_skipped"] = "原文件已有视觉与原生文字，仅补充缺失文字层。"
        edition.ocr_status = OcrStatus.SUCCEEDED
        edition.page_label_status = (
            PageLabelStatus.READY
            if asset.pages.exclude(
                label_source__in=[Page.LabelSource.MANUAL, Page.LabelSource.PDF_PAGE_LABELS]
            ).exists() is False
            else PageLabelStatus.NEEDS_REVIEW
        )
        edition.semantic_index_status = SemanticIndexStatus.PENDING
        edition.save(
            update_fields=[
                "ocr_status",
                "page_label_status",
                "semantic_index_status",
                "updated_at",
            ]
        )

        index_warning = ""
        try:
            index_asset(asset, is_public=edition.state == PublicationState.PUBLISHED)
            edition.search_indexed_at = timezone.now()
            edition.save(update_fields=["search_indexed_at", "updated_at"])
        except Exception as exc:
            index_warning = str(exc)[:2000]
        try:
            stats["theory_suggestions"] = generate_theory_review_tasks(
                asset,
                actor=job.created_by,
                force=False,
            )
        except Exception as exc:
            stats["theory_suggestion_warning"] = str(exc)[:2000]
        queue_semantic_job(asset, force=True, actor=job.created_by)
        queue_page_label_job(
            asset,
            upload_item=job.upload_item,
            actor=job.created_by,
            force=True,
        )
        job.status = ProcessingJob.Status.SUCCEEDED
        job.progress = 100
        stats.update(
            {
                "pages": document_page_count,
                "target_pages": target_page_count,
                "engine": provider,
                "index_warning": index_warning,
            }
        )
        job.stats = stats
        job.finished_at = timezone.now()
        job.save()
        return job
    except Exception as exc:
        edition.ocr_status = OcrStatus.FAILED
        edition.save(update_fields=["ocr_status", "updated_at"])
        job.status = ProcessingJob.Status.FAILED
        job.error_code = exc.__class__.__name__
        job.error_message = str(exc)[:4000]
        job.finished_at = timezone.now()
        job.save()
        raise
    finally:
        if cleanup:
            cleanup()
        if next_task_id:
            dispatch_ocr_job(str(job.id), next_task_id)
            job.refresh_from_db()
