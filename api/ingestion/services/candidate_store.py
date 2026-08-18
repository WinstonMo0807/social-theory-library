from __future__ import annotations

from hashlib import sha256
import json
import unicodedata
import uuid

from django.db import transaction

from ingestion.models import CandidateEvidence, MetadataCandidate, SourceRecord, UploadItem

from .metadata import Candidate
from .metadata_scoring import AI_SOURCE_RE, calibrate_candidate, normalized_candidate_value


REVIEW_ONLY_FIELDS = {
    "disciplines",
    "subdisciplines",
    "theory_schools",
    "topics",
}


def _stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def normalized_value(value):
    if isinstance(value, str):
        return unicodedata.normalize("NFKC", " ".join(value.split())).strip()
    if isinstance(value, list):
        return [normalized_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalized_value(item) for key, item in sorted(value.items())}
    return value


def _candidate_key(field_name: str, source: str, value) -> tuple[str, str, str]:
    return field_name, source, normalized_candidate_value(value)


def _source_record(candidate: Candidate) -> SourceRecord | None:
    value = str((candidate.evidence or {}).get("source_record_id") or "").strip()
    if not value:
        return None
    try:
        source_id = uuid.UUID(value)
    except (TypeError, ValueError):
        return None
    return SourceRecord.objects.filter(pk=source_id).first()


def _conflict_group(item: UploadItem, field_name: str) -> str:
    payload = f"{item.pk}:{field_name}".encode("utf-8")
    return sha256(payload).hexdigest()[:32]


def _evidence_signature(values: dict) -> str:
    return sha256(_stable_json(values).encode("utf-8")).hexdigest()


def _persist_evidence(
    stored: MetadataCandidate,
    candidate: Candidate,
    source_record: SourceRecord | None,
) -> None:
    evidence = dict(candidate.evidence or {})
    page_number = evidence.get("page")
    if page_number is None and isinstance(evidence.get("page_range"), list) and evidence["page_range"]:
        page_number = evidence["page_range"][0]
    try:
        page_number = int(page_number) if page_number is not None else None
    except (TypeError, ValueError):
        page_number = None
    values = {
        "source_record_id": str(source_record.id) if source_record else "",
        "page_number": page_number,
        "bbox": evidence.get("bbox") if isinstance(evidence.get("bbox"), list) else [],
        "text_quote": str(evidence.get("text_quote") or evidence.get("quote") or "")[:4000],
        "source_kind": candidate.source[:40],
        "external_identifier": str(
            evidence.get("record_url")
            or evidence.get("doi")
            or evidence.get("isbn")
            or ""
        )[:400],
        "extraction_method": str(evidence.get("extraction_method") or candidate.source)[:80],
        "model_name": str(evidence.get("model_name") or "")[:160],
        "model_revision": str(evidence.get("model_revision") or "")[:160],
    }
    existing_signatures = {
        _evidence_signature(
            {
                "source_record_id": str(row.source_record_id or ""),
                "page_number": row.page_number,
                "bbox": row.bbox,
                "text_quote": row.text_quote,
                "source_kind": row.source_kind,
                "external_identifier": row.external_identifier,
                "extraction_method": row.extraction_method,
                "model_name": row.model_name,
                "model_revision": row.model_revision,
            }
        ): row
        for row in stored.evidence_records.all()
    }
    existing = existing_signatures.get(_evidence_signature(values))
    if existing:
        if existing.asset_id is None and stored.upload_item.asset_id:
            existing.asset_id = stored.upload_item.asset_id
            existing.save(update_fields=["asset", "updated_at"])
        return
    CandidateEvidence.objects.create(
        metadata_candidate=stored,
        asset=stored.upload_item.asset,
        source_record=source_record,
        page_number=values["page_number"],
        bbox=values["bbox"],
        text_quote=values["text_quote"],
        source_kind=values["source_kind"],
        external_identifier=values["external_identifier"],
        extraction_method=values["extraction_method"],
        model_name=values["model_name"],
        model_revision=values["model_revision"],
    )


@transaction.atomic
def persist_metadata_candidates(
    item: UploadItem,
    candidates: list[Candidate],
    selected: dict | None = None,
    *,
    supersede_sources: set[str] | None = None,
) -> dict[str, int]:
    """Upsert candidates while preserving every human decision and field lock."""

    # The parent row is the serialization point even when this item has no
    # candidates yet. Row-locking only the current candidate queryset would
    # not protect the empty-set case from concurrent duplicate inserts.
    item = UploadItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
    selected = selected or {}
    existing = list(
        item.metadata_candidates.select_for_update(of=("self",))
        .select_related("source_record")
        .prefetch_related("evidence_records")
    )
    by_key = {
        _candidate_key(row.field_name, row.source, row.value): row
        for row in existing
    }
    seen: set[tuple[str, str, str]] = set()
    added = 0
    updated = 0
    preserved = 0

    for candidate in candidates:
        key = _candidate_key(candidate.field_name, candidate.source, candidate.value)
        if key in seen:
            continue
        seen.add(key)
        score = calibrate_candidate(candidate, candidates)
        source_record = _source_record(candidate)
        row = by_key.get(key)
        selected_value = (
            candidate.field_name not in REVIEW_ONLY_FIELDS
            and AI_SOURCE_RE.search(candidate.source) is None
            and selected.get(candidate.field_name) == candidate.value
        )
        if row is None:
            row = MetadataCandidate.objects.create(
                upload_item=item,
                field_name=candidate.field_name,
                value=candidate.value,
                normalized_value=normalized_value(candidate.value),
                source=candidate.source,
                evidence=candidate.evidence,
                confidence=score.score,
                selected=selected_value,
                lifecycle=MetadataCandidate.Lifecycle.PROPOSED,
                source_record=source_record,
                conflict_group=_conflict_group(item, candidate.field_name),
                score_factors=score.factors,
                is_locked=False,
            )
            by_key[key] = row
            added += 1
        elif row.lifecycle in {
            MetadataCandidate.Lifecycle.ACCEPTED,
            MetadataCandidate.Lifecycle.REJECTED,
        } or row.is_locked:
            preserved += 1
        else:
            row.value = candidate.value
            row.normalized_value = normalized_value(candidate.value)
            row.evidence = candidate.evidence
            row.confidence = score.score
            row.selected = selected_value
            row.lifecycle = MetadataCandidate.Lifecycle.PROPOSED
            row.source_record = source_record
            row.conflict_group = _conflict_group(item, candidate.field_name)
            row.score_factors = score.factors
            row.save(
                update_fields=[
                    "value",
                    "normalized_value",
                    "evidence",
                    "confidence",
                    "selected",
                    "lifecycle",
                    "source_record",
                    "conflict_group",
                    "score_factors",
                    "updated_at",
                ]
            )
            updated += 1
        _persist_evidence(row, candidate, source_record)

    sources = supersede_sources if supersede_sources is not None else {candidate.source for candidate in candidates}
    superseded = 0
    for row in existing:
        key = _candidate_key(row.field_name, row.source, row.value)
        if (
            row.source in sources
            and key not in seen
            and row.lifecycle == MetadataCandidate.Lifecycle.PROPOSED
            and not row.is_locked
        ):
            row.lifecycle = MetadataCandidate.Lifecycle.SUPERSEDED
            row.selected = False
            row.save(update_fields=["lifecycle", "selected", "updated_at"])
            superseded += 1

    return {
        "added": added,
        "updated": updated,
        "preserved": preserved,
        "superseded": superseded,
    }
