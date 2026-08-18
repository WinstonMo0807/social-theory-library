from contextlib import contextmanager
from pathlib import Path
import re
import socket

from django.conf import settings
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import (
    Asset,
    Contribution,
    Edition,
    OcrStatus,
    OrganizationContribution,
    Page,
    PageLabelStatus,
    PublicationState,
    SemanticIndexStatus,
    Work,
)
from distribution.models import CloudObject, CloudProvider
from distribution.services import cloud_budget_allows_new_publication
from distribution.tasks import sync_cloud_object
from catalog.services.covers import generate_cover_candidates, generate_recommendation_image
from catalog.services.semantic_indexing import queue_semantic_job, remove_semantic_asset
from catalog.services.publication_places import detect_publication_places
from catalog.services.theory_suggestions import generate_theory_review_tasks
from ingestion.models import (
    AuditEvent,
    FieldLock,
    MetadataCandidate,
    ProcessingAttempt,
    UploadBatch,
    UploadItem,
)

from .ai_metadata import metadata_candidates_from_ai
from .candidate_store import persist_metadata_candidates
from .catalog_reconciliation import find_catalog_match, normalize_doi, normalize_isbn
from .extract import extract_native_pages, ocr_required_page_indexes, persist_pages
from .files import (
    canonical_pdf_filename,
    is_pdf,
    materialize_field_file,
    rename_normalized_asset,
    sha256_file,
    validate_pdf_structure,
)
from .indexing import index_asset, remove_asset_from_index
from .metadata import (
    Candidate,
    extract_local_candidates,
    extract_text_candidates,
    overall_confidence,
    select_best,
)
from .provider_gateway import enrich_candidates_with_gateway
from .reconciliation import persist_resolution_candidates, propose_author_reconciliation
from .publication import PublicationBlocked, publication_readiness, publish_edition
from .processing import queue_ocr_job, queue_page_label_job
from .taxonomy import controlled_vocabulary_candidates, suggest_relations
from .workflow import idempotency_key_for_stage, legacy_workflow_state, transition_upload_item


class DuplicateDocument(RuntimeError):
    def __init__(self, asset: Asset):
        self.asset = asset
        super().__init__(f"该 PDF 已作为馆藏文件存在：{asset.edition.work.title}")


def _batch_asset_access_status(batch: UploadBatch) -> str:
    return {
        UploadBatch.AccessPolicy.PUBLIC: Asset.AccessStatus.PUBLIC,
        UploadBatch.AccessPolicy.REGISTERED: Asset.AccessStatus.REGISTERED,
        UploadBatch.AccessPolicy.RESTRICTED: Asset.AccessStatus.RESTRICTED,
    }[batch.access_policy]


@contextmanager
def processing_attempt(
    item: UploadItem,
    stage: str,
    *,
    reuse_completed: bool = True,
):
    attempt_number = item.attempts.filter(stage=stage).count() + 1
    input_fingerprint = item.sha256 or item.processing_token or str(item.id)
    idempotency_key = idempotency_key_for_stage(item, stage, input_fingerprint)
    attempt, created = ProcessingAttempt.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={
            "upload_item": item,
            "stage": stage,
            "attempt_number": attempt_number,
            "worker_id": socket.gethostname(),
            "input_fingerprint": input_fingerprint,
        },
    )
    reusable = (
        not created
        and reuse_completed
        and attempt.status == "completed"
        and attempt.invalidated_at is None
    )
    attempt._should_run = not reusable
    if reusable:
        yield attempt
        return
    if not created:
        attempt.status = "started"
        attempt.attempt_number = attempt_number
        attempt.worker_id = socket.gethostname()
        attempt.error_code = ""
        attempt.error_message = ""
        attempt.error_kind = ""
        attempt.started_at = timezone.now()
        attempt.finished_at = None
        attempt.invalidated_at = None
        attempt.output_summary = {}
        attempt.save(
            update_fields=[
                "status",
                "attempt_number",
                "worker_id",
                "error_code",
                "error_message",
                "error_kind",
                "started_at",
                "finished_at",
                "invalidated_at",
                "output_summary",
                "updated_at",
            ]
        )
    try:
        yield attempt
    except Exception as exc:
        attempt.status = "failed"
        attempt.error_code = exc.__class__.__name__
        attempt.error_message = str(exc)[:4000]
        attempt.finished_at = timezone.now()
        attempt.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "finished_at",
                "updated_at",
            ]
        )
        raise
    else:
        attempt.status = "completed"
        attempt.finished_at = timezone.now()
        attempt.save(update_fields=["status", "finished_at", "updated_at"])


class ProcessingCancelled(Exception):
    """Raised when an administrator removed an item while a worker still held it."""


def set_stage(item: UploadItem, status: str, progress: int) -> None:
    current = UploadItem.objects.filter(pk=item.pk).values(
        "status",
        "dispatch_task_id",
    ).first()
    if current and current["status"] == UploadItem.Status.DELETED:
        item.status = UploadItem.Status.DELETED
        raise ProcessingCancelled
    if (
        current
        and item.dispatch_task_id
        and current["dispatch_task_id"]
        and item.dispatch_task_id != current["dispatch_task_id"]
    ):
        # Recovery assigns a new durable task token. An older worker that
        # resumes after being considered stalled must stop before the next
        # stage instead of writing over the recovered execution.
        raise ProcessingCancelled
    target_workflow = legacy_workflow_state(status)
    transition_upload_item(
        item,
        target_workflow,
        actor=item.batch.created_by,
        reason=f"处理阶段进入 {status}",
        correlation_id=item.dispatch_task_id,
    )
    item.status = status
    item.stage_progress = progress
    item.error_code = ""
    item.error_message = ""
    item.save(
        update_fields=[
            "status",
            "stage_progress",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )


def refresh_batch(batch: UploadBatch) -> None:
    total = batch.items.count()
    expected = max(batch.expected_count, total)
    completed = batch.items.filter(
        status__in=[
            UploadItem.Status.PUBLISHED,
            UploadItem.Status.READY,
            UploadItem.Status.WITHDRAWN,
            UploadItem.Status.DELETED,
        ]
    ).count()
    failed = batch.items.filter(status__in=[UploadItem.Status.FAILED, UploadItem.Status.NEEDS_REVIEW]).count()
    if total < expected or completed + failed < total:
        status_value = UploadBatch.Status.PROCESSING
    elif failed == 0:
        status_value = UploadBatch.Status.COMPLETED
    elif completed == 0:
        status_value = UploadBatch.Status.FAILED
    else:
        status_value = UploadBatch.Status.PARTIAL
    UploadBatch.objects.filter(pk=batch.pk).update(
        expected_count=expected,
        completed_count=completed,
        failed_count=failed,
        status=status_value,
        updated_at=timezone.now(),
    )


def _unique_slug(model, value: str, fallback: str, field_name: str = "slug") -> str:
    base = slugify(value)[:120] or fallback
    slug = base
    suffix = 1
    while model.objects.filter(**{field_name: slug}).exists():
        suffix += 1
        slug = f"{base}-{suffix}"
    return slug


def _persist_candidates(item: UploadItem, candidates: list[Candidate], selected: dict) -> None:
    persist_metadata_candidates(item, candidates, selected)


def _reload_candidates(item: UploadItem) -> list[Candidate]:
    """Rehydrate accepted/proposed candidates when a completed stage is reused."""

    return [
        Candidate(
            field_name=row.field_name,
            value=row.value,
            source=row.source,
            confidence=row.confidence,
            evidence=dict(row.evidence or {}),
        )
        for row in item.metadata_candidates.exclude(
            lifecycle__in=[
                MetadataCandidate.Lifecycle.REJECTED,
                MetadataCandidate.Lifecycle.SUPERSEDED,
            ]
        ).order_by("field_name", "-confidence", "created_at")
    ]


def _propose_people(item: UploadItem, authors: list[str]) -> int:
    """Generate reconciliation choices without creating or publishing authority entities."""

    return propose_author_reconciliation(item, authors)


@transaction.atomic
def _create_or_update_catalog(item: UploadItem, selected: dict, candidates: list[Candidate], first_text: str):
    reused_existing_edition = False
    if item.edition_id:
        edition = Edition.objects.select_for_update().select_related("work").get(pk=item.edition_id)
        work = edition.work
    else:
        title = str(selected.get("title", "")).strip()
        if title:
            persist_resolution_candidates(
                item,
                target_type="work",
                source_name=title,
            )
        catalog_match = find_catalog_match(selected)
        if catalog_match.mode == "existing_edition" and catalog_match.edition is not None:
            edition = Edition.objects.select_for_update().select_related("work").get(
                pk=catalog_match.edition.pk
            )
            work = edition.work
            reused_existing_edition = True
        elif catalog_match.mode == "existing_work" and catalog_match.work is not None:
            work = Work.objects.select_for_update().get(pk=catalog_match.work.pk)
            edition = Edition.objects.create(work=work)
        else:
            work = Work.objects.create(
                document_type=selected.get("document_type", "book"),
                title=title,
                normalized_title=title.casefold(),
            )
            edition = Edition.objects.create(work=work)
        item.edition = edition
        item.preflight_summary = {
            **(item.preflight_summary or {}),
            "catalog_reconciliation": {
                "mode": catalog_match.mode,
                "work_id": str(work.id),
                "edition_id": str(edition.id),
                "confidence": catalog_match.confidence,
                "reasons": list(catalog_match.reasons),
                "conflicts": list(catalog_match.conflicts),
                "requires_review": catalog_match.mode == "ambiguous",
            },
        }
        item.save(update_fields=["edition", "preflight_summary", "updated_at"])

    if reused_existing_edition:
        return edition

    locked_fields = set(edition.field_locks.values_list("field_name", flat=True))
    if "title" not in locked_fields and selected.get("title"):
        work.title = str(selected["title"]).strip()
        work.normalized_title = work.title.casefold()
    if "document_type" not in locked_fields and selected.get("document_type"):
        work.document_type = selected["document_type"]
    if "language" not in locked_fields and selected.get("language"):
        work.language = selected["language"]
    if "abstract" not in locked_fields and selected.get("abstract"):
        work.abstract = str(selected["abstract"]).strip()
    work.save()

    field_map = {
        "publication_year": "publication_year",
        "publisher": "publisher",
        "publication_place": "publication_place",
        "journal_title": "journal_title",
        "volume": "volume",
        "issue": "issue",
        "page_range": "page_range",
        "degree_institution": "degree_institution",
        "degree_type": "degree_type",
        "report_institution": "report_institution",
        "isbn": "isbn",
        "doi": "doi",
    }
    for source_name, model_name in field_map.items():
        if source_name not in locked_fields and selected.get(source_name) not in (None, ""):
            setattr(edition, model_name, selected[source_name])
    normalized_isbn = normalize_isbn(selected.get("isbn"))
    if "isbn" not in locked_fields and normalized_isbn:
        if len(normalized_isbn) == 10:
            edition.isbn10 = normalized_isbn
        elif len(normalized_isbn) == 13:
            edition.isbn13 = normalized_isbn
    if "doi" not in locked_fields and selected.get("doi"):
        edition.doi = normalize_doi(selected["doi"])
    edition.metadata_confidence = max(
        edition.metadata_confidence,
        overall_confidence(candidates, selected),
    )
    if not edition.public_slug:
        edition.public_slug = _unique_slug(
            Edition,
            work.title,
            f"work-{str(edition.id)[:8]}",
            field_name="public_slug",
        )
    if "authors" not in locked_fields:
        _propose_people(item, selected.get("authors", []))
    if "publisher" not in locked_fields and selected.get("publisher"):
        persist_resolution_candidates(
            item,
            target_type="publisher",
            source_name=str(selected["publisher"]),
        )
    if "degree_institution" not in locked_fields and selected.get("degree_institution"):
        persist_resolution_candidates(
            item,
            target_type="organization",
            source_name=str(selected["degree_institution"]),
            supporting_properties={
                "organization_role": OrganizationContribution.Role.DEGREE_GRANTING,
                "organization_type": "university",
            },
        )
    if "report_institution" not in locked_fields and selected.get("report_institution"):
        persist_resolution_candidates(
            item,
            target_type="organization",
            source_name=str(selected["report_institution"]),
            supporting_properties={
                "organization_role": OrganizationContribution.Role.REPORT_ISSUER,
                "organization_type": "research_institute",
            },
        )
    people = [
        contribution.person
        for contribution in edition.contributions.filter(
            role=Contribution.Role.AUTHOR,
            approved=True,
        )
        .select_related("person")
        .order_by("order")
    ]
    author_names = [person.preferred_name for person in people]
    if not author_names:
        author_names = [
            " ".join(str(name).split()).strip()
            for name in selected.get("authors", [])
            if " ".join(str(name).split()).strip()
        ]
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
        }.get(work.document_type, "book"),
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
    edition.save()
    if not item.replacement_of_asset_id:
        suggest_relations(work, f"{work.title}\n{first_text[:20000]}")
    return edition


def _copy_asset(item: UploadItem, edition: Edition, kind: str, filename: str) -> Asset:
    existing = edition.assets.filter(kind=kind, sha256=item.sha256).first()
    if existing:
        return existing
    is_replacement = bool(item.replacement_of_asset_id)
    if is_replacement:
        if item.asset_id:
            version = item.asset.version
        else:
            latest = edition.assets.order_by("-version").values_list("version", flat=True).first()
            version = (latest or 0) + 1
    else:
        version = 1
    asset = Asset(
        edition=edition,
        kind=kind,
        sha256=item.sha256,
        byte_size=item.byte_size,
        status=Asset.Status.PROCESSING,
        processor="immutable-upload-copy",
        processor_version="1",
        is_current=not is_replacement,
        version=version,
        access_status=_batch_asset_access_status(item.batch),
        original_filename=item.source_filename,
        mime_type="application/pdf",
    )
    with item.file.open("rb") as source:
        asset.file.save(filename, File(source), save=False)
    asset.save()
    return asset


def _ensure_cloud_copy(item: UploadItem, asset: Asset) -> bool:
    if not settings.REQUIRE_CLOUD_FOR_PUBLICATION:
        return True
    ready = asset.cloud_objects.filter(status=CloudObject.Status.READY).exists()
    if ready:
        return True
    provider = CloudProvider.objects.filter(enabled=True, is_default=True).first()
    if provider is None:
        raise PublicationBlocked(["未配置可用的默认云对象存储"])
    if not cloud_budget_allows_new_publication(provider):
        raise PublicationBlocked(["云端月度预算保护已阻止新的公开同步"])
    cloud_object, _ = CloudObject.objects.get_or_create(
        asset=asset,
        provider=provider,
        object_key=(
            f"published/{asset.edition_id}/v{asset.version}/"
            f"{asset.edition.canonical_filename}"
        ),
        defaults={
            "sha256": asset.sha256,
            "byte_size": asset.byte_size,
        },
    )
    if cloud_object.status != CloudObject.Status.READY:
        set_stage(item, UploadItem.Status.SYNCING_CLOUD, 92)
        transaction.on_commit(
            lambda: sync_cloud_object.apply_async(
                args=[str(cloud_object.id)],
                ignore_result=True,
            )
        )
        return False
    return True


def _replacement_readiness(item: UploadItem, normalized: Asset) -> list[str]:
    asset_reasons = {
        "规范阅读文件未就绪",
        "逐页文本未就绪",
        "云端阅读副本未就绪",
    }
    reasons = [
        reason
        for reason in publication_readiness(
            item.edition,
            allow_low_confidence=True,
        )
        if reason not in asset_reasons
    ]
    if item.edition.state != PublicationState.PUBLISHED:
        reasons.append("仅已发布文献可以替换 PDF")
    if normalized.status != Asset.Status.READY:
        reasons.append("新规范阅读文件未就绪")
    elif normalized.page_count == 0 or not normalized.pages.exists():
        reasons.append("新文件逐页文本未就绪")
    if settings.REQUIRE_CLOUD_FOR_PUBLICATION and not normalized.cloud_objects.filter(
        status=CloudObject.Status.READY
    ).exists():
        reasons.append("新文件云端阅读副本未就绪")
    return reasons


@transaction.atomic
def _activate_replacement(item: UploadItem, normalized: Asset) -> Asset:
    from reading.models import Annotation

    item = UploadItem.objects.select_for_update(of=("self",)).select_related(
        "batch",
        "edition",
        "asset",
    ).get(pk=item.pk)
    old_asset = Asset.objects.select_for_update().get(pk=item.replacement_of_asset_id)
    normalized = Asset.objects.select_for_update().get(pk=normalized.pk)
    if old_asset.edition_id != item.edition_id or normalized.edition_id != item.edition_id:
        raise PublicationBlocked(["替换文件与目标版本不属于同一文献"])
    if not old_asset.is_current:
        if normalized.is_current:
            return old_asset
        raise PublicationBlocked(["替换目标已变化，请重新选择当前 PDF"])
    if normalized.kind != Asset.Kind.NORMALIZED or normalized.status != Asset.Status.READY:
        raise PublicationBlocked(["新规范阅读文件未就绪"])
    new_original = item.asset
    if (
        new_original is None
        or new_original.kind != Asset.Kind.ORIGINAL
        or new_original.version != normalized.version
    ):
        raise PublicationBlocked(["新原始文件未就绪"])

    current_original = (
        Asset.objects.select_for_update()
        .filter(
            edition=item.edition,
            kind=Asset.Kind.ORIGINAL,
            is_current=True,
        )
        .exclude(pk=new_original.pk)
        .first()
    )
    Asset.objects.filter(
        edition=item.edition,
        kind=Asset.Kind.NORMALIZED,
        is_current=True,
    ).exclude(pk=normalized.pk).update(is_current=False, updated_at=timezone.now())
    normalized.is_current = True
    normalized.save(update_fields=["is_current", "updated_at"])
    Asset.objects.filter(
        edition=item.edition,
        kind=Asset.Kind.ORIGINAL,
        is_current=True,
    ).exclude(pk=new_original.pk).update(is_current=False, updated_at=timezone.now())
    new_original.is_current = True
    new_original.save(update_fields=["is_current", "updated_at"])
    orphaned_count = Annotation.objects.filter(asset=old_asset).update(
        orphaned=True,
        updated_at=timezone.now(),
    )
    AuditEvent.objects.create(
        actor=item.batch.created_by,
        action="pdf_replaced",
        object_type="Edition",
        object_id=str(item.edition_id),
        before={
            "normalized_asset_id": str(old_asset.id),
            "original_asset_id": str(current_original.id) if current_original else None,
            "version": old_asset.version,
        },
        after={
            "normalized_asset_id": str(normalized.id),
            "original_asset_id": str(new_original.id),
            "version": normalized.version,
            "orphaned_annotations": orphaned_count,
        },
    )
    return old_asset


def _finalize_item_publication(item: UploadItem, normalized: Asset) -> dict:
    if item.replacement_of_asset_id:
        reasons = _replacement_readiness(item, normalized)
        if reasons:
            raise PublicationBlocked(reasons)
        public_index = index_asset(normalized, is_public=True)
        old_asset = item.replacement_of_asset
        try:
            index_asset(old_asset, is_public=False)
            old_asset = _activate_replacement(item, normalized)
        except Exception:
            index_asset(normalized, is_public=False)
            index_asset(old_asset, is_public=True)
            raise
        try:
            remove_asset_from_index(old_asset)
            remove_semantic_asset(str(old_asset.id))
        except Exception as exc:
            AuditEvent.objects.create(
                actor=item.batch.created_by,
                action="old_search_index_cleanup_failed",
                object_type="Asset",
                object_id=str(old_asset.id),
                after={"error": str(exc)[:1000]},
            )
        item.status = UploadItem.Status.PUBLISHED
        item.stage_progress = 100
        item.save(update_fields=["status", "stage_progress", "updated_at"])
        if item.edition.ocr_status in {OcrStatus.NOT_REQUIRED, OcrStatus.SUCCEEDED}:
            queue_semantic_job(normalized, force=True, actor=item.batch.created_by)
        return {"public_index": public_index, "replacement": True}

    was_manually_reviewed = item.edition.field_locks.exists()
    reasons = publication_readiness(
        item.edition,
        allow_low_confidence=was_manually_reviewed,
    )
    if reasons:
        raise PublicationBlocked(reasons)
    public_index = index_asset(normalized, is_public=True)
    try:
        publish_edition(
            item.edition,
            actor=item.batch.created_by,
            idempotency_key=f"upload-item:{item.id}:publish",
            allow_low_confidence=was_manually_reviewed,
        )
    except Exception:
        index_asset(normalized, is_public=False)
        raise
    item.status = UploadItem.Status.PUBLISHED
    item.stage_progress = 100
    item.save(update_fields=["status", "stage_progress", "updated_at"])
    if item.edition.ocr_status in {OcrStatus.NOT_REQUIRED, OcrStatus.SUCCEEDED}:
        queue_semantic_job(normalized, force=False, actor=item.batch.created_by)
    return {"public_index": public_index, "replacement": False}


def resume_reviewed_item_publication(item_id: str) -> UploadItem:
    """Continue at indexing after a human metadata review.

    Human corrections and field locks are already committed before this runs.
    A search, storage, or broker failure must therefore remain a retryable
    processing failure instead of rolling those corrections back.
    """
    item = UploadItem.objects.select_related(
        "batch",
        "edition__work",
        "replacement_of_asset",
    ).get(pk=item_id)
    if item.edition_id is None:
        item.status = UploadItem.Status.NEEDS_REVIEW
        item.error_code = "missing_edition"
        item.error_message = "文献记录尚未建立。"
        item.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        transition_upload_item(
            item,
            UploadItem.WorkflowState.NEEDS_REVIEW,
            actor=item.batch.created_by,
            reason="复核续跑缺少书目版本",
            force=True,
        )
        refresh_batch(item.batch)
        return item
    if item.status in {UploadItem.Status.PUBLISHED, UploadItem.Status.DELETED}:
        return item

    normalized = item.edition.assets.filter(
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        is_current=True,
    ).first()
    if normalized is None:
        item.status = UploadItem.Status.NEEDS_REVIEW
        item.error_code = "missing_normalized_asset"
        item.error_message = "规范阅读文件未就绪。"
        item.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        transition_upload_item(
            item,
            UploadItem.WorkflowState.NEEDS_REVIEW,
            actor=item.batch.created_by,
            reason="复核续跑缺少规范阅读文件",
            force=True,
        )
        refresh_batch(item.batch)
        return item

    try:
        set_stage(item, UploadItem.Status.INDEXING, 82)
        with processing_attempt(item, "review_reindex") as attempt:
            if attempt.should_run:
                if (
                    item.edition.state != PublicationState.PUBLISHED
                    and not normalized.cloud_objects.exists()
                    and normalized.file.storage.exists(normalized.file.name)
                ):
                    rename_normalized_asset(
                        normalized,
                        item.edition.canonical_filename,
                    )
                result = index_asset(normalized, is_public=False)
                attempt.output_summary = result
                attempt.save(update_fields=["output_summary", "updated_at"])
            item.edition.search_indexed_at = timezone.now()
            item.edition.save(update_fields=["search_indexed_at", "updated_at"])

        set_stage(item, UploadItem.Status.READY, 90)
        if not _ensure_cloud_copy(item, normalized):
            return UploadItem.objects.get(pk=item.pk)
        item.status = UploadItem.Status.READY
        item.stage_progress = 100
        item.save(update_fields=["status", "stage_progress", "updated_at"])
        if item.edition.ocr_status in {OcrStatus.NOT_REQUIRED, OcrStatus.SUCCEEDED}:
            queue_semantic_job(normalized, force=True, actor=item.batch.created_by)
        return item
    except ProcessingCancelled:
        return UploadItem.objects.get(pk=item.pk)
    except PublicationBlocked as exc:
        item.status = UploadItem.Status.NEEDS_REVIEW
        item.error_code = "PublicationBlocked"
        item.error_message = str(exc)
        item.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        transition_upload_item(
            item,
            UploadItem.WorkflowState.NEEDS_REVIEW,
            actor=item.batch.created_by,
            reason="复核续跑被发布检查阻断",
            force=True,
        )
        return item
    except Exception as exc:
        item.status = UploadItem.Status.FAILED
        item.error_code = exc.__class__.__name__
        item.error_message = str(exc)[:4000]
        item.retry_count += 1
        item.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "retry_count",
                "updated_at",
            ]
        )
        transition_upload_item(
            item,
            UploadItem.WorkflowState.FAILED,
            actor=item.batch.created_by,
            reason=f"复核续跑失败：{item.error_code}",
            force=True,
        )
        raise
    finally:
        refresh_batch(item.batch)


def run_pipeline(item_id: str) -> UploadItem:
    item = UploadItem.objects.select_related("batch").get(pk=item_id)
    if item.status in {
        UploadItem.Status.PUBLISHED,
        UploadItem.Status.DELETED,
    } or (
        item.status == UploadItem.Status.READY
        and item.edition_id
        and item.asset_id
    ):
        return item
    source_path, cleanup_source = materialize_field_file(item.file)
    try:
        set_stage(item, UploadItem.Status.VALIDATING, 5)
        with processing_attempt(
            item,
            "validate",
            reuse_completed=bool(
                item.sha256
                and item.byte_size
                and (item.preflight_summary or {}).get("mime_type") == "application/pdf"
            ),
        ) as attempt:
            if attempt.should_run:
                if not is_pdf(source_path):
                    raise ValueError("文件内容不是有效 PDF。")
                validate_pdf_structure(source_path, settings.MAX_PDF_PAGES)
                assembled_digest_available = bool(
                    item.sha256
                    and item.byte_size
                    and source_path.stat().st_size == item.byte_size
                )
                if not assembled_digest_available:
                    item.sha256, item.byte_size = sha256_file(source_path)
                item.save(update_fields=["sha256", "byte_size", "updated_at"])
                duplicate = Asset.objects.filter(
                    sha256=item.sha256,
                    kind=Asset.Kind.ORIGINAL,
                ).exclude(pk=item.asset_id).select_related("edition__work").first()
                item.preflight_summary = {
                    "filename": item.source_filename,
                    "size_bytes": item.byte_size,
                    "sha256": item.sha256,
                    "mime_type": "application/pdf",
                    "exact_duplicate": bool(duplicate),
                    "duplicate_asset_id": str(duplicate.id) if duplicate else "",
                    "duplicate_policy": item.batch.duplicate_policy,
                    "checksum_source": (
                        "streamed_chunk_assembly"
                        if assembled_digest_available
                        else "validated_source_read"
                    ),
                }
                item.save(update_fields=["preflight_summary", "updated_at"])
                if duplicate and not item.asset_id:
                    raise DuplicateDocument(duplicate)

        set_stage(item, UploadItem.Status.METADATA, 18)
        metadata_reusable = bool(
            item.edition_id
            and item.recognized_metadata
            and item.metadata_candidates.exists()
        )
        with processing_attempt(
            item,
            "metadata",
            reuse_completed=metadata_reusable,
        ) as attempt:
            if attempt.should_run:
                candidates, first_text = extract_local_candidates(source_path)
                if item.batch.external_enrichment_enabled:
                    candidates, provider_warnings = enrich_candidates_with_gateway(
                        candidates,
                        source_path,
                        upload_item=item,
                    )
                else:
                    provider_warnings = ["该批次已关闭外部元数据补充。"]
                ai_summary = {"status": "disabled"}
                if item.batch.ai_suggestions_enabled:
                    ai_candidates, ai_summary = metadata_candidates_from_ai(
                        first_text,
                        upload_item=item,
                    )
                    candidates.extend(ai_candidates)
                candidates.extend(controlled_vocabulary_candidates(first_text))
                selected = select_best(candidates)
                _persist_candidates(item, candidates, selected)
                item.recognized_metadata = selected
                item.save(update_fields=["recognized_metadata", "updated_at"])
                edition = _create_or_update_catalog(item, selected, candidates, first_text)
                attempt.output_summary = {
                    "candidate_count": len(candidates),
                    "provider_warnings": provider_warnings,
                    "ai_metadata": ai_summary,
                }
                attempt.save(update_fields=["output_summary", "updated_at"])
            else:
                candidates = _reload_candidates(item)
                _, first_text = extract_local_candidates(source_path)
                selected = dict(item.recognized_metadata or {})
                edition = Edition.objects.select_related("work").get(pk=item.edition_id)
                provider_warnings = ["已复用完成的元数据阶段。"]
                ai_summary = {"status": "reused"}

        set_stage(item, UploadItem.Status.EXTRACTING, 32)
        asset_reusable = bool(
            item.asset_id
            and edition.assets.filter(
                kind=Asset.Kind.NORMALIZED,
                sha256=item.sha256,
            ).exists()
        )
        with processing_attempt(
            item,
            "asset",
            reuse_completed=asset_reusable,
        ) as attempt:
            if attempt.should_run:
                original = _copy_asset(item, edition, Asset.Kind.ORIGINAL, item.source_filename)
                item.asset = original
                item.save(update_fields=["asset", "updated_at"])
                normalized = _copy_asset(
                    item,
                    edition,
                    Asset.Kind.NORMALIZED,
                    edition.canonical_filename,
                )
                if normalized.source_asset_id != original.id:
                    normalized.source_asset = original
                    normalized.save(update_fields=["source_asset", "updated_at"])
                edition.public_asset_prepared_at = timezone.now()
                edition.save(update_fields=["public_asset_prepared_at", "updated_at"])
            else:
                original = Asset.objects.get(pk=item.asset_id)
                normalized = edition.assets.get(
                    kind=Asset.Kind.NORMALIZED,
                    sha256=item.sha256,
                )

        with processing_attempt(item, "text_extraction", reuse_completed=False) as attempt:
            pages, detected_needs_ocr = extract_native_pages(normalized.file.path)
            detected_page_indexes = ocr_required_page_indexes(pages)
            if item.batch.ocr_strategy == UploadBatch.OcrStrategy.FORCE:
                ocr_page_indexes = [page.index for page in pages]
            elif item.batch.ocr_strategy == UploadBatch.OcrStrategy.SKIP:
                ocr_page_indexes = []
            else:
                ocr_page_indexes = detected_page_indexes
            needs_ocr = bool(ocr_page_indexes)
            text_profile = (
                "born_digital"
                if not detected_page_indexes
                else "scanned"
                if len(detected_page_indexes) == len(pages)
                else "mixed"
            )
            item.preflight_summary = {
                **(item.preflight_summary or {}),
                "page_count": len(pages),
                "text_profile": text_profile,
                "detected_ocr_pages": len(detected_page_indexes),
                "scheduled_ocr_pages": len(ocr_page_indexes),
                "ocr_strategy": item.batch.ocr_strategy,
                "language": selected.get("language", ""),
            }
            item.save(update_fields=["preflight_summary", "updated_at"])
            ocr_reason_counts: dict[str, int] = {}
            for page in pages:
                for reason in page.ocr_reasons:
                    ocr_reason_counts[reason] = ocr_reason_counts.get(reason, 0) + 1
            if needs_ocr:
                method = "pending_ocr"
            elif (
                item.batch.ocr_strategy == UploadBatch.OcrStrategy.SKIP
                and detected_needs_ocr
            ):
                method = "ocr_disabled"
            else:
                method = "embedded"
            persist_pages(normalized, pages)
            normalized.page_count = len(pages)
            normalized.extraction_method = method
            normalized.status = Asset.Status.READY
            normalized.validation_status = Asset.ValidationStatus.VALID
            normalized.validation_details = {
                "page_count": len(pages),
                "sha256": normalized.sha256,
                "validated_at": timezone.now().isoformat(),
                "ocr_required_page_indexes": ocr_page_indexes,
                "ocr_reason_counts": ocr_reason_counts,
                "ocr_detection_version": "per-page-v1",
                "ocr_strategy": item.batch.ocr_strategy,
                "ocr_detected_page_indexes": detected_page_indexes,
            }
            normalized.save(
                update_fields=[
                    "page_count",
                    "extraction_method",
                    "status",
                    "validation_status",
                    "validation_details",
                    "updated_at",
                ]
            )
            original.page_count = len(pages)
            original.status = Asset.Status.READY
            original.validation_status = Asset.ValidationStatus.VALID
            original.validation_details = {
                "page_count": len(pages),
                "sha256": original.sha256,
                "validated_at": timezone.now().isoformat(),
            }
            original.save(
                update_fields=[
                    "page_count",
                    "status",
                    "validation_status",
                    "validation_details",
                    "updated_at",
                ]
            )
            if needs_ocr:
                edition.ocr_status = OcrStatus.PENDING
            elif (
                item.batch.ocr_strategy == UploadBatch.OcrStrategy.SKIP
                and detected_needs_ocr
            ):
                edition.ocr_status = OcrStatus.DISABLED
            else:
                edition.ocr_status = OcrStatus.NOT_REQUIRED
            edition.page_label_status = (
                PageLabelStatus.READY
                if pages and all(page.label_source == Page.LabelSource.PDF_PAGE_LABELS for page in pages)
                else PageLabelStatus.NEEDS_REVIEW
            )
            edition.semantic_index_status = (
                SemanticIndexStatus.NOT_INDEXED
                if edition.ocr_status == OcrStatus.DISABLED
                else SemanticIndexStatus.PENDING
            )
            edition.save(
                update_fields=[
                    "ocr_status",
                    "page_label_status",
                    "semantic_index_status",
                    "updated_at",
                ]
            )
            attempt.output_summary = {
                "pages": len(pages),
                "method": method,
                "ocr_required": needs_ocr,
                "ocr_target_pages": len(ocr_page_indexes),
                "ocr_reason_counts": ocr_reason_counts,
                "ocr_strategy": item.batch.ocr_strategy,
                "ocr_detected": detected_needs_ocr,
            }
            attempt.save(update_fields=["output_summary", "updated_at"])

        canonical_first_text = "\n".join(page.text for page in pages[:5])
        classification_chunks = []
        classification_chars = 0
        for page in pages:
            if not page.text.strip() or classification_chars >= 250_000:
                continue
            remaining = 250_000 - classification_chars
            chunk = f"PDF 第 {page.index} 页\n{page.text[:remaining]}"
            classification_chunks.append(chunk)
            classification_chars += len(chunk)
        classification_text = "\n".join(classification_chunks)
        candidates = [
            candidate
            for candidate in candidates
            if candidate.source != "controlled_vocabulary_match_v1"
        ]
        candidates.extend(controlled_vocabulary_candidates(classification_text))
        selected = select_best(candidates)
        _persist_candidates(item, candidates, selected)
        item.recognized_metadata = selected
        item.save(update_fields=["recognized_metadata", "updated_at"])
        if canonical_first_text.strip() and (
            method != "embedded"
            or len(canonical_first_text) > len(first_text) * 1.2
        ):
            with processing_attempt(item, "metadata_refinement", reuse_completed=False) as attempt:
                refined = extract_text_candidates(
                    canonical_first_text,
                    source="ocr_first_pages" if method == "paddleocr" else "canonical_first_pages",
                )
                candidates = [*candidates, *refined]
                if item.batch.external_enrichment_enabled:
                    candidates, provider_warnings = enrich_candidates_with_gateway(
                        candidates,
                        source_path,
                        upload_item=item,
                    )
                else:
                    provider_warnings = ["该批次已关闭外部元数据补充。"]
                if item.batch.ai_suggestions_enabled:
                    existing_ai_keys = {
                        (candidate.field_name, repr(candidate.value))
                        for candidate in candidates
                        if candidate.source == "ai_metadata_candidate"
                    }
                    ai_candidates, ai_summary = metadata_candidates_from_ai(
                        canonical_first_text,
                        upload_item=item,
                    )
                    candidates.extend(
                        candidate
                        for candidate in ai_candidates
                        if (candidate.field_name, repr(candidate.value)) not in existing_ai_keys
                    )
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate.source != "controlled_vocabulary_match_v1"
                ]
                candidates.extend(controlled_vocabulary_candidates(classification_text))
                selected = select_best(candidates)
                _persist_candidates(item, candidates, selected)
                item.recognized_metadata = selected
                item.save(update_fields=["recognized_metadata", "updated_at"])
                edition = _create_or_update_catalog(
                    item,
                    selected,
                    candidates,
                    canonical_first_text,
                )
                rename_normalized_asset(normalized, edition.canonical_filename)
                attempt.output_summary = {
                    "source": method,
                    "candidate_count": len(candidates),
                    "selected_fields": sorted(selected),
                    "provider_warnings": provider_warnings,
                    "ai_metadata": ai_summary,
                }
                attempt.save(update_fields=["output_summary", "updated_at"])

        with processing_attempt(item, "publication_place_detection", reuse_completed=False) as attempt:
            place_evidence = detect_publication_places(
                normalized,
                force=True,
                allow_targeted_ocr=(
                    not needs_ocr
                    and item.batch.ocr_strategy != UploadBatch.OcrStrategy.SKIP
                ),
            )
            attempt.output_summary = {
                "candidate_count": len(place_evidence),
                "targeted_ocr_deferred": needs_ocr,
                "confirmed": sum(
                    1
                    for evidence in place_evidence
                    if evidence.verification_status in {"auto_confirmed", "manually_confirmed", "manually_corrected"}
                ),
            }
            attempt.save(update_fields=["output_summary", "updated_at"])

        if edition.work.document_type == "book":
            with processing_attempt(item, "cover_detection", reuse_completed=False) as attempt:
                candidates = generate_cover_candidates(normalized)
                attempt.output_summary = {
                    "candidate_count": len(candidates),
                    "selected_page": next(
                        (
                            candidate.page_index
                            for candidate in candidates
                            if candidate.selected
                        ),
                        None,
                    ),
                }
                attempt.save(update_fields=["output_summary", "updated_at"])
        else:
            with processing_attempt(item, "recommendation_image", reuse_completed=False) as attempt:
                image = generate_recommendation_image(normalized)
                attempt.output_summary = {
                    "generated": bool(image),
                    "document_type": edition.work.document_type,
                }
                attempt.save(update_fields=["output_summary", "updated_at"])

        # Theory suggestions depend on the persisted PDF text and page mapping.
        # Failure here must not make the document unreadable or unpublishable.
        try:
            with processing_attempt(item, "theory_suggestions", reuse_completed=False) as attempt:
                result = generate_theory_review_tasks(
                    normalized,
                    actor=item.batch.created_by,
                    force=False,
                )
                attempt.output_summary = result
                attempt.save(update_fields=["output_summary", "updated_at"])
        except Exception as exc:
            AuditEvent.objects.create(
                actor=item.batch.created_by,
                action="theory_suggestions_failed",
                object_type="Asset",
                object_id=str(normalized.id),
                after={"error": str(exc)[:1000]},
            )

        set_stage(item, UploadItem.Status.INDEXING, 78)
        with processing_attempt(item, "search_index", reuse_completed=False) as attempt:
            result = index_asset(normalized, is_public=False)
            attempt.output_summary = result
            attempt.save(update_fields=["output_summary", "updated_at"])
            edition.search_indexed_at = timezone.now()
            edition.save(update_fields=["search_indexed_at", "updated_at"])

        set_stage(item, UploadItem.Status.READY, 88)
        if not _ensure_cloud_copy(item, normalized):
            return UploadItem.objects.get(pk=item.pk)

        if needs_ocr:
            queue_ocr_job(
                normalized,
                upload_item=item,
                actor=item.batch.created_by,
            )
        else:
            # Replacement activation queues its forced semantic rebuild after
            # the new asset becomes current. Do not create a second job before
            # activation, because a failed first attempt could invalidate the
            # only active index target and make publication fail spuriously.
            if (
                not item.replacement_of_asset_id
                and edition.ocr_status != OcrStatus.DISABLED
            ):
                queue_semantic_job(normalized, force=False, actor=item.batch.created_by)
            queue_page_label_job(
                normalized,
                upload_item=item,
                actor=item.batch.created_by,
            )
        if item.replacement_of_asset_id:
            with processing_attempt(item, "replacement_activation", reuse_completed=False) as attempt:
                result = _finalize_item_publication(item, normalized)
                attempt.output_summary = result
                attempt.save(update_fields=["output_summary", "updated_at"])
        else:
            item.status = UploadItem.Status.READY
            item.stage_progress = 100
            item.save(update_fields=["status", "stage_progress", "updated_at"])
        return item
    except ProcessingCancelled:
        return UploadItem.objects.get(pk=item.pk)
    except DuplicateDocument as exc:
        item.asset = exc.asset
        item.edition = exc.asset.edition
        policy = item.batch.duplicate_policy
        if policy == UploadBatch.DuplicatePolicy.BLOCK_EXACT:
            item.status = UploadItem.Status.FAILED
            item.error_code = "duplicate_document_blocked"
            item.error_message = f"{exc}。该批次设置为阻止完全重复文件。"
            target_workflow = UploadItem.WorkflowState.FAILED
        elif policy == UploadBatch.DuplicatePolicy.ALLOW:
            item.status = UploadItem.Status.READY
            item.stage_progress = 100
            item.error_code = ""
            item.error_message = ""
            item.preflight_summary = {
                "duplicate": True,
                "policy": policy,
                "linked_asset_id": str(exc.asset.id),
                "detail": "完全相同的 PDF 已关联到现有馆藏，没有复制第二份原文件。",
            }
            target_workflow = UploadItem.WorkflowState.READY
        else:
            item.status = UploadItem.Status.NEEDS_REVIEW
            item.error_code = "duplicate_document"
            item.error_message = str(exc)
            target_workflow = UploadItem.WorkflowState.NEEDS_REVIEW
        item.save(
            update_fields=[
                "asset",
                "edition",
                "status",
                "stage_progress",
                "preflight_summary",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        transition_upload_item(
            item,
            target_workflow,
            actor=item.batch.created_by,
            reason=f"发现完全重复 PDF，批次策略为 {policy}",
            force=True,
        )
        return item
    except PublicationBlocked as exc:
        item.status = UploadItem.Status.NEEDS_REVIEW
        item.error_code = exc.__class__.__name__
        item.error_message = str(exc)
        item.save(update_fields=["status", "error_code", "error_message", "updated_at"])
        transition_upload_item(
            item,
            UploadItem.WorkflowState.NEEDS_REVIEW,
            actor=item.batch.created_by,
            reason="处理结果需要人工复核",
            force=True,
        )
        return item
    except Exception as exc:
        item.status = UploadItem.Status.FAILED
        item.error_code = exc.__class__.__name__
        item.error_message = str(exc)[:4000]
        item.retry_count += 1
        item.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "retry_count",
                "updated_at",
            ]
        )
        transition_upload_item(
            item,
            UploadItem.WorkflowState.FAILED,
            actor=item.batch.created_by,
            reason=f"处理失败：{item.error_code}",
            force=True,
        )
        raise
    finally:
        if cleanup_source:
            cleanup_source()
        refresh_batch(item.batch)


def resume_publication_for_asset(asset_id: str) -> None:
    asset = Asset.objects.select_related("edition").filter(
        pk=asset_id,
        kind=Asset.Kind.NORMALIZED,
    ).first()
    if asset is None:
        return
    item = UploadItem.objects.filter(
        edition_id=asset.edition_id,
        asset__version=asset.version,
        status=UploadItem.Status.SYNCING_CLOUD,
    ).select_related(
        "edition__work",
        "batch",
        "replacement_of_asset",
    ).first()
    if item is None:
        return
    try:
        if asset.status != Asset.Status.READY:
            raise PublicationBlocked(["规范阅读文件未就绪"])
        if item.replacement_of_asset_id:
            _finalize_item_publication(item, asset)
        else:
            item.status = UploadItem.Status.READY
            item.stage_progress = 100
            item.error_code = ""
            item.error_message = ""
            item.save(
                update_fields=[
                    "status",
                    "stage_progress",
                    "error_code",
                    "error_message",
                    "updated_at",
                ]
            )
            if item.edition.ocr_status == OcrStatus.PENDING:
                queue_ocr_job(asset, upload_item=item, actor=item.batch.created_by)
            elif item.edition.ocr_status in {OcrStatus.NOT_REQUIRED, OcrStatus.SUCCEEDED}:
                queue_semantic_job(asset, force=False, actor=item.batch.created_by)
    except PublicationBlocked as exc:
        item.status = UploadItem.Status.NEEDS_REVIEW
        item.error_code = "PublicationBlocked"
        item.error_message = str(exc)
        item.save(update_fields=["status", "error_code", "error_message", "updated_at"])
    finally:
        refresh_batch(item.batch)
