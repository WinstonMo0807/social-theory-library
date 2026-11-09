"""Offline experiments only: canonical quote validation and read-only coverage.

No model call, index mutation, extraction dispatch or publication is performed.
Model offsets use Python Unicode code points in EvidenceSpan.original_text,
never stored page offsets or JavaScript UTF-16 offsets. Hash checks compare
captured and database metadata; they do not reread or validate physical PDFs.
"""
from collections import Counter, defaultdict
from hashlib import sha256
from math import isfinite
from uuid import UUID

from django.db.models import F, Q

from catalog.models import CapabilityDemand, ClaimEvidence, DerivedClaim, EvidenceSpan, ProjectionState
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.publication_eligibility import active_asset_q, active_document_revision_q
from catalog.services.semantic_search import viewer_access_statuses


MATERIAL_REASONS = frozenset({
    "no_explicit_claim", "historical_description", "table_of_contents", "references",
    "table", "ocr_quality_insufficient", "filtered", "other",
})


def raw_text_hash(text: str) -> str:
    """Different from EvidenceSpan.content_hash, which hashes normalized text."""
    return sha256(text.encode("utf-8")).hexdigest()


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _checksum(value):
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def resolve_exact_evidence(
    evidence_span_id, proposal, *, expected_source_checksum: str,
    expected_raw_text_hash: str, access_statuses=None,
) -> dict:
    """Validate a model's three-field proposal against a trusted source identity.

    Invalid model output falls back to the full *authorized* span. Missing,
    withdrawn, stale or changed sources return source_invalid without text.
    The existing Reader can focus the span, not the selected sentence's box.
    """
    identifier = _uuid(evidence_span_id)
    invalid = {"status": "source_invalid", "reason": "source_not_current_or_accessible"}
    if identifier is None:
        return invalid
    access_statuses = viewer_access_statuses() if access_statuses is None else access_statuses
    span = (EvidenceSpan.objects.filter(
        pk=identifier, is_stale=False, document_revision__is_active=True,
        document_revision__asset__kind="normalized", document_revision__asset__status="ready",
        document_revision__asset__validation_status="valid",
        document_revision__asset__access_status__in=access_statuses,
        page__asset_id=F("document_revision__asset_id"), page_number=F("page__index"),
    ).filter(
        active_document_revision_q(revision_prefix="document_revision"),
        active_asset_q(asset_prefix="document_revision__asset", require_fulltext=True),
    ).select_related("page", "document_revision__asset__edition__work",
                     "document_revision__asset__edition__active_catalog_revision").first())
    if span is None:
        return invalid
    revision = span.document_revision
    source_checksum = revision.source_checksum
    current_hash = raw_text_hash(span.original_text)
    if (not span.original_text.strip() or span.page_number < 1
            or not _checksum(source_checksum) or not _checksum(expected_source_checksum)
            or source_checksum != revision.asset.sha256 or source_checksum != expected_source_checksum
            or not _checksum(expected_raw_text_hash) or current_hash != expected_raw_text_hash):
        return {"status": "source_invalid", "reason": "source_fingerprint_or_text_invalid"}

    valid = (isinstance(proposal, dict)
             and set(proposal) == {"evidence_span_id", "start_offset", "end_offset"}
             and _uuid(proposal["evidence_span_id"]) == identifier
             and type(proposal["start_offset"]) is int and type(proposal["end_offset"]) is int
             and 0 <= proposal["start_offset"] < proposal["end_offset"] <= len(span.original_text))
    start, end = (proposal["start_offset"], proposal["end_offset"]) if valid else (0, len(span.original_text))
    # An empty/whitespace selection cannot constitute a useful quote.
    if not span.original_text[start:end].strip():
        valid, start, end = False, 0, len(span.original_text)
    envelope = evidence_span_envelope(span)
    bbox = span.bbox
    has_box = (isinstance(bbox, list) and len(bbox) == 4
               and all(type(value) in (int, float) and isfinite(value) for value in bbox)
               and bbox[2] > bbox[0] and bbox[3] > bbox[1])
    # Current PassageFocusView is primary-edition-only; other public editions
    # remain readable by PDF page, so never promise an unavailable focus link.
    has_focus = revision.asset.edition.is_primary
    reader_url = envelope.reader_url if has_focus else f"/reader/{revision.asset_id}?page={span.page_number}"
    return {
        "status": "exact" if valid else "full_span",
        "reason": "validated_offsets" if valid else "invalid_model_locator",
        "evidence_span_id": identifier, "document_revision_id": str(revision.id),
        "start_offset": start, "end_offset": end,
        "text_offset_basis": "evidence_span.original_text:python_codepoints",
        "quote": span.original_text[start:end], "raw_text_hash": current_hash,
        "source_checksum": source_checksum, "source_validation": "captured_and_database_metadata",
        "locator": envelope.locator, "pdf_locator_precision": "span" if has_box and has_focus else "page",
        "reader_url": reader_url, "pdf_url": envelope.pdf_url,
    }


def audit_evidence_claim_coverage(span_ids, *, classifications=None) -> dict:
    """Inventory a caller-selected batch without inferring absence of viewpoints.

    Active means a current model row, not human-verified semantic correctness.
    Demand history is scoped to span + revision, across all recorded extraction
    configurations; its latest row supplies the task state. Current scheduling
    does not persist a captured content hash, so that limitation is explicit.
    Optional sidecar reasons are caller-supplied reviews, verified only for
    identity/hash consistency, never inferred from zero claims or model scores.
    """
    identifiers = list(dict.fromkeys(_uuid(value) for value in span_ids))
    if None in identifiers:
        raise ValueError("coverage requires valid EvidenceSpan identifiers")
    classifications = classifications or {}
    spans = {str(row.id): row for row in EvidenceSpan.objects.filter(pk__in=identifiers)
             .select_related("document_revision")}
    claims = DerivedClaim.objects.filter(
        Q(primary_evidence_id__in=identifiers) | Q(evidence_links__evidence_span_id__in=identifiers),
        status="active", document_revision__is_active=True, primary_evidence__is_stale=False,
        primary_evidence__document_revision_id=F("document_revision_id"),
    ).distinct()
    claim_map, claim_revisions = defaultdict(set), {}
    for claim_id, span_id, revision_id in claims.values_list("id", "primary_evidence_id", "document_revision_id"):
        claim_revisions[claim_id] = revision_id
        claim_map[str(span_id)].add(claim_id)
    for span_id, claim_id in ClaimEvidence.objects.filter(
        evidence_span_id__in=identifiers, derived_claim_id__in=claim_revisions,
    ).values_list("evidence_span_id", "derived_claim_id"):
        span = spans.get(str(span_id))
        if span and span.document_revision_id == claim_revisions[claim_id]:
            claim_map[str(span_id)].add(claim_id)
    projections = {row.object_id: row.status for row in ProjectionState.objects.filter(
        object_type="derived_claim", object_id__in=claim_revisions, projection_type="claim_index")}
    demands = defaultdict(list)
    for row in CapabilityDemand.objects.filter(
        owner_type="evidence_span", owner_key__in=identifiers,
        payload__task_kind="claim_extraction",
    ).order_by("created_at", "id"):
        span = spans.get(row.owner_key)
        payload = row.payload
        if (span and str(payload.get("document_revision_id")) == str(span.document_revision_id)
                and str(payload.get("evidence_span_id")) == row.owner_key
                and ("evidence_content_hash" not in payload
                     or payload["evidence_content_hash"] == span.content_hash)):
            demands[row.owner_key].append(row)

    rows = []
    for identifier in identifiers:
        span = spans.get(identifier)
        if span is None:
            rows.append({"evidence_span_id": identifier, "state": "source_missing"})
            continue
        active_ids = claim_map[identifier]
        history = demands[identifier]
        state, reason = "unknown", "no_claim_or_current_demand_record"
        if span.is_stale or not span.document_revision.is_active:
            state, reason = "source_stale", "evidence_or_revision_not_current"
            active_ids = set()
        elif active_ids:
            state, reason = "active_claim_present", "current_claim_relation_exists"
        elif history:
            state, reason = history[-1].state, "latest_matching_demand_state"
            if state == "completed":
                state, reason = "completed_without_claim", "extraction_outcome_not_recorded"
        material_reason, classification_status = "unknown", "absent"
        review = classifications.get(identifier)
        if review is not None:
            valid_review = (isinstance(review, dict) and state != "source_stale"
                and review.get("reason") in MATERIAL_REASONS
                and isinstance(review.get("reviewer"), str) and bool(review["reviewer"].strip())
                and str(review.get("document_revision_id")) == str(span.document_revision_id)
                and review.get("raw_text_hash") == raw_text_hash(span.original_text)
                and (review.get("reason") != "other" or bool(str(review.get("notes") or "").strip())))
            classification_status = "provided_review" if valid_review else "invalid"
            if valid_review:
                material_reason = review["reason"]
        rows.append({
            "evidence_span_id": identifier, "document_revision_id": str(span.document_revision_id),
            "state": state, "reason": reason, "active_claim_count": len(active_ids),
            "semantic_validity": "not_evaluated",
            "claim_projection_states": dict(Counter(projections.get(key, "unknown") for key in active_ids)),
            "demand_states": dict(Counter(row.state for row in history)),
            "demand_content_hash_recorded": bool(history) and all(
                "evidence_content_hash" in row.payload for row in history),
            "error_codes": sorted({row.last_error_code for row in history if row.last_error_code}),
            "material_reason": material_reason, "classification_status": classification_status,
        })
    return {"rows": rows, "counts": dict(Counter(row["state"] for row in rows)),
            "read_only": True, "configuration_scope": "all_recorded_extraction_configs",
            "coverage_scope": "requested_evidence_spans_only"}
