from __future__ import annotations

from hashlib import sha256
from importlib import metadata
import json
import logging
from typing import Iterable

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from catalog.models import (
    Asset,
    ClaimEvidence,
    DerivedClaim,
    DocumentQualityAssessment,
    DocumentRevision,
    EvidenceSpan,
    Page,
    Passage,
)


logger = logging.getLogger(__name__)

NATIVE_EXTRACTION_VERSION = "native-page-blocks-v1"
OCR_EXTRACTION_VERSION = "selective-page-ocr-v1"
QUALITY_ASSESSOR = "document-intelligence"
QUALITY_ASSESSOR_VERSION = "quality-v1"


def _pymupdf_version() -> str:
    try:
        return metadata.version("PyMuPDF")
    except metadata.PackageNotFoundError:
        return "unknown"


def _hash_value(hasher, value) -> None:
    if isinstance(value, (dict, list, tuple)):
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    else:
        rendered = str(value or "")
    encoded = rendered.encode("utf-8", errors="replace")
    hasher.update(len(encoded).to_bytes(8, "big"))
    hasher.update(encoded)


def document_text_checksum(asset: Asset) -> str:
    """Hash the current page text and passage locators without loading a PDF."""

    digest = sha256()
    page_rows = (
        Page.objects.filter(asset=asset)
        .order_by("index")
        .values_list(
            "index",
            "printed_label",
            "chapter_title",
            "normalized_text",
            "text_source",
            "confidence",
        )
    )
    for row in page_rows.iterator(chunk_size=200):
        for value in row:
            _hash_value(digest, value)
    passage_rows = (
        Passage.objects.filter(page__asset=asset)
        .order_by("page__index", "order")
        .values_list(
            "page__index",
            "order",
            "normalized_text",
            "start_offset",
            "end_offset",
            "bbox_union",
        )
    )
    for row in passage_rows.iterator(chunk_size=500):
        for value in row:
            _hash_value(digest, value)
    return digest.hexdigest()


def _source_checksum(asset: Asset) -> str:
    value = str(asset.sha256 or "").strip().casefold()
    if len(value) == 64:
        return value
    # Real ingestion always persists the validated SHA-256.  This fallback
    # keeps legacy/test assets deterministic without reading the source file.
    return sha256(value.encode("utf-8") or str(asset.pk).encode("ascii")).hexdigest()


def _bounded_score(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 4)


def _mean(values: Iterable[float], *, fallback: float = 0.0) -> float:
    values = [float(value) for value in values]
    if not values:
        return fallback
    return sum(values) / len(values)


def _quality_values(
    asset: Asset,
    *,
    pending_ocr_pages: Iterable[int] = (),
) -> dict:
    page_rows = list(
        Page.objects.filter(asset=asset)
        .order_by("index")
        .values(
            "index",
            "normalized_text",
            "text_source",
            "confidence",
            "chapter_title",
            "printed_label",
        )
    )
    page_count = len(page_rows)
    denominator = max(page_count, 1)
    populated = [row for row in page_rows if str(row["normalized_text"] or "").strip()]
    claim_ready = [
        row
        for row in page_rows
        if len(str(row["normalized_text"] or "").strip()) >= 80
    ]
    passage_pages = Passage.objects.filter(page__asset=asset).values("page_id").distinct().count()
    average_confidence = _mean(
        [float(row["confidence"] or 0) for row in populated],
        fallback=0.0,
    )
    text_coverage = len(populated) / denominator
    validated = (
        asset.status == Asset.Status.READY
        and asset.validation_status == Asset.ValidationStatus.VALID
    )
    reader_quality = (0.75 if validated else 0.35) + 0.25 * text_coverage
    fulltext_quality = text_coverage * (0.5 + 0.5 * average_confidence)
    semantic_quality = (passage_pages / denominator) * (0.4 + 0.6 * fulltext_quality)
    claim_quality = (len(claim_ready) / denominator) * (0.4 + 0.6 * average_confidence)
    structure_quality = (
        0.6
        * sum(bool(str(row["chapter_title"] or "").strip()) for row in page_rows)
        / denominator
        + 0.4
        * sum(bool(str(row["printed_label"] or "").strip()) for row in page_rows)
        / denominator
    )
    ocr_rows = [
        row
        for row in page_rows
        if row["text_source"] in {Page.TextSource.OCR, Page.TextSource.HYBRID}
    ]
    ocr_quality = _mean(
        [float(row["confidence"] or 0) for row in ocr_rows],
        fallback=1.0,
    )
    critical_pages = {
        int(row["index"])
        for row in page_rows
        if not str(row["normalized_text"] or "").strip()
        or float(row["confidence"] or 0) < 0.5
    }
    critical_pages.update(int(index) for index in pending_ocr_pages if int(index) > 0)
    return {
        "reader_quality": _bounded_score(reader_quality),
        "fulltext_quality": _bounded_score(fulltext_quality),
        "semantic_quality": _bounded_score(semantic_quality),
        "claim_quality": _bounded_score(claim_quality),
        "structure_quality": _bounded_score(structure_quality),
        "ocr_quality": _bounded_score(ocr_quality),
        "critical_pages": sorted(critical_pages),
        "details": {
            "page_count": page_count,
            "populated_pages": len(populated),
            "passage_pages": passage_pages,
            "claim_ready_pages": len(claim_ready),
            "average_text_confidence": _bounded_score(average_confidence),
        },
    }


def _ensure_quality_assessment(
    revision: DocumentRevision,
    *,
    pending_ocr_pages: Iterable[int] = (),
) -> DocumentQualityAssessment:
    values = _quality_values(
        revision.asset,
        pending_ocr_pages=pending_ocr_pages,
    )
    assessment, _ = DocumentQualityAssessment.objects.update_or_create(
        document_revision=revision,
        assessor=QUALITY_ASSESSOR,
        assessor_version=QUALITY_ASSESSOR_VERSION,
        defaults=values,
    )
    summary = {
        key: values[key]
        for key in (
            "reader_quality",
            "fulltext_quality",
            "semantic_quality",
            "claim_quality",
            "structure_quality",
            "ocr_quality",
            "critical_pages",
        )
    }
    summary.update(values["details"])
    if revision.quality_summary != summary:
        revision.quality_summary = summary
        revision.save(update_fields=["quality_summary", "updated_at"])
    return assessment


def _evidence_content_hash(passage: Passage) -> str:
    text = str(passage.normalized_text or passage.text or "")
    return sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _sync_evidence_spans(revision: DocumentRevision) -> int:
    existing = {
        (
            span.page_id,
            span.content_hash,
            span.start_offset,
            span.end_offset,
        ): span
        for span in EvidenceSpan.objects.filter(document_revision=revision)
    }
    seen_ids = set()
    creates = []
    updates = []
    language = str(
        revision.asset.language_guess
        or revision.asset.edition.work.language
        or ""
    )[:32]
    passages = (
        Passage.objects.filter(page__asset=revision.asset)
        .select_related("page")
        .order_by("page__index", "order")
    )
    now = timezone.now()
    for passage in passages.iterator(chunk_size=500):
        page = passage.page
        content_hash = _evidence_content_hash(passage)
        key = (
            page.pk,
            content_hash,
            int(passage.start_offset or 0),
            int(passage.end_offset or 0),
        )
        ocr_provenance = {}
        if page.text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}:
            ocr_provenance = {
                "provider": revision.ocr_provider,
                "model": revision.ocr_model,
                "version": revision.ocr_version,
            }
        defaults = {
            "passage": passage,
            "page_number": page.index,
            "printed_page_label": page.printed_label,
            "start_offset": int(passage.start_offset or 0),
            "end_offset": int(passage.end_offset or 0),
            "bbox": passage.bbox_union or [],
            "original_text": passage.text,
            "normalized_text": passage.normalized_text,
            "language": language,
            "section": page.chapter_title,
            "quality": _bounded_score(page.confidence),
            "extraction_method": page.text_source,
            "ocr_provenance": ocr_provenance,
            "is_stale": False,
            "stale_reason": "",
            "invalidated_at": None,
        }
        span = existing.get(key)
        if span is None:
            creates.append(
                EvidenceSpan(
                    document_revision=revision,
                    page=page,
                    content_hash=content_hash,
                    **defaults,
                )
            )
            continue
        for field, value in defaults.items():
            setattr(span, field, value)
        span.updated_at = now
        updates.append(span)
        seen_ids.add(span.pk)
    if creates:
        EvidenceSpan.objects.bulk_create(creates, batch_size=500)
        seen_ids.update(span.pk for span in creates)
    if updates:
        EvidenceSpan.objects.bulk_update(
            updates,
            fields=[
                "passage",
                "page_number",
                "printed_page_label",
                "start_offset",
                "end_offset",
                "bbox",
                "original_text",
                "normalized_text",
                "language",
                "section",
                "quality",
                "extraction_method",
                "ocr_provenance",
                "is_stale",
                "stale_reason",
                "invalidated_at",
                "updated_at",
            ],
            batch_size=500,
        )
    obsolete = EvidenceSpan.objects.filter(document_revision=revision, is_stale=False)
    if seen_ids:
        obsolete = obsolete.exclude(pk__in=seen_ids)
    obsolete.update(
        is_stale=True,
        stale_reason="passage_removed",
        invalidated_at=now,
        updated_at=now,
    )
    return EvidenceSpan.objects.filter(document_revision=revision, is_stale=False).count()


def _invalidate_old_evidence(
    revision: DocumentRevision,
    *,
    page_indexes: Iterable[int] | None,
    reason: str,
) -> tuple[int, int]:
    spans = EvidenceSpan.objects.filter(document_revision=revision, is_stale=False)
    if page_indexes is not None:
        indexes = sorted({int(index) for index in page_indexes if int(index) > 0})
        if not indexes:
            return 0, 0
        spans = spans.filter(page__index__in=indexes)
    span_ids = list(spans.values_list("pk", flat=True))
    if not span_ids:
        return 0, 0
    claim_ids = list(
        DerivedClaim.objects.filter(
            Q(primary_evidence_id__in=span_ids)
            | Q(evidence_links__evidence_span_id__in=span_ids)
        )
        .values_list("pk", flat=True)
        .distinct()
    )
    now = timezone.now()
    span_count = EvidenceSpan.objects.filter(pk__in=span_ids).update(
        is_stale=True,
        stale_reason=reason,
        invalidated_at=now,
        updated_at=now,
    )
    claim_count = DerivedClaim.objects.filter(pk__in=claim_ids).exclude(
        status__in=[DerivedClaim.Status.REJECTED, DerivedClaim.Status.SUPERSEDED]
    ).update(
        status=DerivedClaim.Status.STALE,
        stale_reason=reason,
        updated_at=now,
    )
    return span_count, claim_count


def _same_interpretation(
    revision: DocumentRevision,
    *,
    source_checksum: str,
    text_checksum: str,
    parser_name: str,
    parser_version: str,
    extraction_method: str,
    extraction_version: str,
    ocr_provider: str,
    ocr_model: str,
    ocr_version: str,
) -> bool:
    return all(
        (
            revision.source_checksum == source_checksum,
            revision.text_checksum == text_checksum,
            revision.parser_name == parser_name,
            revision.parser_version == parser_version,
            revision.extraction_method == extraction_method,
            revision.extraction_version == extraction_version,
            revision.ocr_provider == ocr_provider,
            revision.ocr_model == ocr_model,
            revision.ocr_version == ocr_version,
        )
    )


def _span_identity(span: EvidenceSpan) -> tuple:
    return (
        span.page_id,
        span.content_hash,
        int(span.start_offset or 0),
        int(span.end_offset or 0),
    )


def _carry_forward_unchanged_claims(
    previous: DocumentRevision,
    current: DocumentRevision,
    *,
    changed_page_indexes: Iterable[int],
) -> tuple[int, int]:
    """Reuse derived interpretation for pages untouched by selective OCR.

    A new DocumentRevision is still the active provenance record, so claims
    and curated evidence must point at its EvidenceSpan rows.  Copying only
    claims whose complete evidence set is unchanged avoids an all-document LLM
    rerun while keeping active-revision visibility rules intact.
    """

    changed = {int(value) for value in changed_page_indexes if int(value) > 0}
    current_spans = {
        _span_identity(span): span
        for span in current.evidence_spans.filter(is_stale=False).select_related("page")
    }
    carried_claims = 0
    carried_curated_links = 0
    copied_source_ids = []
    source_claims = (
        previous.derived_claims.filter(status=DerivedClaim.Status.ACTIVE)
        .select_related("primary_evidence")
        .prefetch_related("evidence_links__evidence_span")
    )
    for source in source_claims:
        source_spans = [source.primary_evidence]
        source_spans.extend(link.evidence_span for link in source.evidence_links.all())
        if any(
            span.is_stale
            or span.page_number in changed
            or _span_identity(span) not in current_spans
            for span in source_spans
        ):
            continue
        primary = current_spans[_span_identity(source.primary_evidence)]
        clone, created = DerivedClaim.objects.get_or_create(
            document_revision=current,
            fingerprint=source.fingerprint,
            defaults={
                "primary_evidence": primary,
                "work": source.work,
                "edition": source.edition,
                "proposition": source.proposition,
                "subject": source.subject,
                "predicate": source.predicate,
                "object": source.object,
                "polarity": source.polarity,
                "modality": source.modality,
                "qualifiers": source.qualifiers,
                "temporal_scope": source.temporal_scope,
                "geographic_scope": source.geographic_scope,
                "population_scope": source.population_scope,
                "attribution": source.attribution,
                "claim_type": source.claim_type,
                "prompt_key": source.prompt_key,
                "prompt_version": source.prompt_version,
                "model_provider": source.model_provider,
                "model_name": source.model_name,
                "model_revision": source.model_revision,
                "quality_factors": source.quality_factors,
                "quality_score": source.quality_score,
                "importance_score": source.importance_score,
                "cluster_key": source.cluster_key,
                "status": DerivedClaim.Status.ACTIVE,
                "shadow": source.shadow,
                "stale_reason": "",
            },
        )
        if created:
            carried_claims += 1
        for link in source.evidence_links.all():
            ClaimEvidence.objects.get_or_create(
                derived_claim=clone,
                evidence_span=current_spans[_span_identity(link.evidence_span)],
                role=link.role,
                defaults={
                    "confidence": link.confidence,
                    "sort_order": link.sort_order,
                    "validation": link.validation,
                },
            )
        copied_source_ids.append(source.pk)

    curated_links = (
        ClaimEvidence.objects.filter(
            curated_claim__isnull=False,
            evidence_span__document_revision=previous,
            evidence_span__is_stale=False,
        )
        .select_related("evidence_span")
        .order_by("created_at")
    )
    for link in curated_links:
        span = link.evidence_span
        replacement = current_spans.get(_span_identity(span))
        if span.page_number in changed or replacement is None:
            continue
        _, created = ClaimEvidence.objects.get_or_create(
            curated_claim=link.curated_claim,
            evidence_span=replacement,
            role=link.role,
            defaults={
                "confidence": link.confidence,
                "sort_order": link.sort_order,
                "validation": link.validation,
            },
        )
        carried_curated_links += int(created)

    if copied_source_ids:
        DerivedClaim.objects.filter(pk__in=copied_source_ids).update(
            status=DerivedClaim.Status.SUPERSEDED,
            stale_reason=f"carried_forward_to_revision_{current.revision}",
            updated_at=timezone.now(),
        )
    return carried_claims, carried_curated_links


def _schedule_claim_shadow(
    revision_id: str,
    *,
    page_indexes: tuple[int, ...] | None = None,
) -> None:
    """Start optional Claim work only after revision evidence is committed."""

    try:
        from catalog.models import DocumentRevision
        from catalog.services.claims.indexing import index_document_revision_claims

        revision = DocumentRevision.objects.get(pk=revision_id)
        # This immediately publishes carried-forward machine claims and
        # tombstones superseded revision documents even if no LLM is online.
        index_document_revision_claims(revision)
    except Exception:
        logger.exception(
            "Initial Claim Index synchronization failed for DocumentRevision %s",
            revision_id,
        )
    try:
        from catalog.services.claims.pipeline import schedule_document_claim_extraction

        schedule_document_claim_extraction(revision_id, page_indexes=page_indexes)
    except Exception:
        # Claim extraction is intentionally non-blocking for ingestion and
        # publication.  The capability runtime/Processing Center can recover
        # the demand once an executor or provider is available.
        logger.exception(
            "Claim shadow scheduling failed for DocumentRevision %s",
            revision_id,
        )


@transaction.atomic
def synchronize_document_revision(
    asset: Asset,
    *,
    parser_name: str,
    parser_version: str,
    extraction_method: str,
    extraction_version: str,
    ocr_provider: str = "",
    ocr_model: str = "",
    ocr_version: str = "",
    changed_page_indexes: Iterable[int] | None = None,
    pending_ocr_pages: Iterable[int] = (),
    schedule_claims: bool = True,
    actor=None,
) -> dict:
    """Activate one interpretation revision and rebuild its evidence spans.

    ``changed_page_indexes`` limits invalidation of the previous revision.  A
    native parser change passes ``None`` because any page can have changed;
    selective OCR passes only the pages it replaced.
    """

    locked_asset = (
        Asset.objects.select_for_update()
        .select_related("edition__work")
        .get(pk=asset.pk)
    )
    source_checksum = _source_checksum(locked_asset)
    text_checksum = document_text_checksum(locked_asset)
    active = (
        DocumentRevision.objects.select_for_update()
        .filter(asset=locked_asset, is_active=True)
        .first()
    )
    created = not (
        active
        and _same_interpretation(
            active,
            source_checksum=source_checksum,
            text_checksum=text_checksum,
            parser_name=parser_name,
            parser_version=parser_version,
            extraction_method=extraction_method,
            extraction_version=extraction_version,
            ocr_provider=ocr_provider,
            ocr_model=ocr_model,
            ocr_version=ocr_version,
        )
    )
    stale_spans = 0
    stale_claims = 0
    carried_claims = 0
    carried_curated_links = 0
    previous = None
    if created:
        previous = active
        if previous is not None:
            previous.is_active = False
            previous.superseded_at = timezone.now()
            previous.save(update_fields=["is_active", "superseded_at", "updated_at"])
        next_revision = (
            DocumentRevision.objects.filter(asset=locked_asset).aggregate(
                maximum=Max("revision")
            )["maximum"]
            or 0
        ) + 1
        active = DocumentRevision.objects.create(
            asset=locked_asset,
            revision=next_revision,
            parser_name=parser_name,
            parser_version=parser_version,
            extraction_method=extraction_method,
            extraction_version=extraction_version,
            ocr_provider=ocr_provider,
            ocr_model=ocr_model,
            ocr_version=ocr_version,
            source_checksum=source_checksum,
            text_checksum=text_checksum,
            created_by=actor,
        )
        if previous is not None:
            stale_spans, stale_claims = _invalidate_old_evidence(
                previous,
                page_indexes=changed_page_indexes,
                reason=(
                    "selective_ocr_superseded"
                    if changed_page_indexes is not None
                    else "document_revision_superseded"
                ),
            )
    evidence_spans = _sync_evidence_spans(active)
    if created and previous is not None and changed_page_indexes is not None:
        carried_claims, carried_curated_links = _carry_forward_unchanged_claims(
            previous,
            active,
            changed_page_indexes=changed_page_indexes,
        )
    assessment = _ensure_quality_assessment(
        active,
        pending_ocr_pages=pending_ocr_pages,
    )
    if schedule_claims:
        scheduled_pages = (
            tuple(sorted({int(value) for value in changed_page_indexes if int(value) > 0}))
            if changed_page_indexes is not None
            else None
        )
        transaction.on_commit(
            lambda revision_id=str(active.pk), page_indexes=scheduled_pages: _schedule_claim_shadow(
                revision_id,
                page_indexes=page_indexes,
            )
        )
    return {
        "status": "ready",
        "revision_id": str(active.pk),
        "revision": active.revision,
        "created": created,
        "evidence_spans": evidence_spans,
        "stale_evidence_spans": stale_spans,
        "stale_derived_claims": stale_claims,
        "carried_forward_claims": carried_claims,
        "carried_forward_curated_evidence": carried_curated_links,
        "critical_pages": list(assessment.critical_pages or []),
    }


def synchronize_native_extraction(
    asset: Asset,
    *,
    actor=None,
    schedule_claims: bool = True,
) -> dict:
    pending_ocr_pages = (
        (asset.validation_details or {}).get("ocr_required_page_indexes") or []
    )
    return synchronize_document_revision(
        asset,
        parser_name="pymupdf",
        parser_version=_pymupdf_version(),
        extraction_method="native",
        extraction_version=NATIVE_EXTRACTION_VERSION,
        changed_page_indexes=None,
        pending_ocr_pages=pending_ocr_pages,
        schedule_claims=schedule_claims,
        actor=actor,
    )


def synchronize_ocr_completion(
    asset: Asset,
    *,
    page_indexes: Iterable[int],
    provider: str,
    model: str = "",
    provider_version: str = "",
    schedule_claims: bool = True,
    actor=None,
) -> dict:
    return synchronize_document_revision(
        asset,
        parser_name="pymupdf+ocr",
        parser_version=_pymupdf_version(),
        extraction_method="selective_ocr",
        extraction_version=OCR_EXTRACTION_VERSION,
        ocr_provider=str(provider or ""),
        ocr_model=str(model or ""),
        ocr_version=str(provider_version or "runtime-default"),
        changed_page_indexes=page_indexes,
        schedule_claims=schedule_claims,
        actor=actor,
    )


def _best_effort(operation, *args, **kwargs) -> dict:
    try:
        return operation(*args, **kwargs)
    except Exception as exc:
        logger.exception("Document Intelligence synchronization failed")
        return {
            "status": "degraded",
            "error_code": exc.__class__.__name__,
            "message": str(exc)[:1000],
        }


def best_effort_native_extraction(
    asset: Asset,
    *,
    actor=None,
    schedule_claims: bool = True,
) -> dict:
    return _best_effort(
        synchronize_native_extraction,
        asset,
        actor=actor,
        schedule_claims=schedule_claims,
    )


def best_effort_ocr_completion(
    asset: Asset,
    *,
    page_indexes: Iterable[int],
    provider: str,
    model: str = "",
    provider_version: str = "",
    schedule_claims: bool = True,
    actor=None,
) -> dict:
    return _best_effort(
        synchronize_ocr_completion,
        asset,
        page_indexes=page_indexes,
        provider=provider,
        model=model,
        provider_version=provider_version,
        schedule_claims=schedule_claims,
        actor=actor,
    )
