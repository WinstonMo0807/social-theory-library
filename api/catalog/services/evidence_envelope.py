from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from django.db.models import Prefetch

from catalog.models import (
    Asset,
    ClaimEvidence,
    CuratedClaim,
    EvidenceSpan,
)
from catalog.services.semantic_search import viewer_access_statuses
from catalog.services.publication_eligibility import (
    active_catalog_snapshot,
    active_document_revision_q,
    public_editions,
)


@dataclass(frozen=True, slots=True)
class EvidenceEnvelope:
    id: str
    kind: str
    source: dict[str, Any]
    text: str
    locator: dict[str, Any]
    quality: dict[str, Any]
    provenance: dict[str, Any]
    reader_url: str
    pdf_url: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_span_envelope(
    span: EvidenceSpan,
    *,
    public_metadata: bool = True,
) -> EvidenceEnvelope:
    revision = span.document_revision
    asset = revision.asset
    edition = asset.edition
    work = edition.work
    page = span.page_number or span.page.index
    snapshot = (
        active_catalog_snapshot(edition, require_fulltext=True)
        if public_metadata
        else {}
    )
    if snapshot:
        authors = [
            str((row.get("person") or {}).get("preferred_name") or row.get("name") or "")
            for row in snapshot.get("contributions") or []
            if isinstance(row, dict)
            and row.get("role") == "author"
            and ((row.get("person") or {}).get("preferred_name") or row.get("name"))
        ]
        work_title = str((snapshot.get("work") or {}).get("title") or "未题名")
    else:
        authors = [
            contribution.person.preferred_name
            for contribution in edition.contributions.all()
            if contribution.approved
            and contribution.role == "author"
            and contribution.person_id
        ]
        work_title = work.title
    focus_id = span.passage_id or span.id
    return EvidenceEnvelope(
        id=str(span.id),
        kind="collection_text",
        source={
            "work_id": str(work.id),
            "work_title": work_title,
            "edition_id": str(edition.id),
            "asset_id": str(asset.id),
            "authors": authors,
            "document_revision_id": str(revision.id),
            "document_revision": revision.revision,
        },
        text=span.original_text,
        locator={
            "page": page,
            "page_id": str(span.page_id),
            "passage_id": str(span.passage_id) if span.passage_id else None,
            "evidence_span_id": str(span.id),
            "printed_page_label": span.printed_page_label,
            "start_offset": span.start_offset,
            "end_offset": span.end_offset,
            "bbox": span.bbox,
            "section": span.section,
        },
        quality={
            "score": span.quality,
            "stale": span.is_stale,
            "stale_reason": span.stale_reason,
        },
        provenance={
            "source_checksum": revision.source_checksum,
            "text_checksum": revision.text_checksum,
            "parser": revision.parser_name,
            "parser_version": revision.parser_version,
            "extraction_method": span.extraction_method or revision.extraction_method,
            "extraction_version": revision.extraction_version,
            "ocr_provider": revision.ocr_provider,
            "ocr_model": revision.ocr_model,
            "ocr_version": revision.ocr_version,
            "ocr": span.ocr_provenance,
        },
        # Reader's passage focus endpoint also accepts EvidenceSpan ids as a
        # locator fallback. This keeps Viewpoint Search and Ask Library on the
        # same verifiable highlight path as full-text search.
        reader_url=f"/reader/{asset.id}?page={page}&passage={focus_id}",
        pdf_url=f"/api/catalog/assets/{asset.id}/manifest/",
    )


def _serialize_curated_claim_groups(
    claims,
    *,
    evidence_attribute: str,
    allowed_kinds: tuple[str, ...],
    public_metadata: bool = True,
) -> dict[str, list[dict[str, Any]]]:
    groups = {kind: [] for kind in allowed_kinds}
    position_map = {
        ClaimEvidence.Role.SUPPORTS: "support",
        ClaimEvidence.Role.OPPOSES: "oppose",
        ClaimEvidence.Role.QUALIFIES: "qualify",
    }
    for claim in claims:
        evidence = []
        positions: list[str] = []
        for link in getattr(claim, evidence_attribute):
            envelope = evidence_span_envelope(
                link.evidence_span,
                public_metadata=public_metadata,
            ).as_dict()
            envelope.update(
                {
                    "claim_role": link.role,
                    "claim_role_label": link.get_role_display(),
                    "claim_confidence": link.confidence,
                }
            )
            evidence.append(envelope)
            position = position_map.get(link.role)
            if position and position not in positions:
                positions.append(position)
        if not evidence:
            continue
        groups[claim.kind].append(
            {
                "id": str(claim.id),
                "kind": claim.kind,
                "kind_label": claim.get_kind_display(),
                "title": claim.title,
                "proposition": claim.proposition,
                "editorial_note": claim.editorial_note,
                "qualifiers": claim.qualifiers,
                "position": positions[0] if len(positions) == 1 else "direct",
                "evidence": evidence,
            }
        )
    return groups


def public_curated_claim_groups(
    *,
    target_field: str,
    target_id,
    allowed_kinds: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    """Serialize only published curation backed by current public PDF evidence."""

    if target_field not in {"work", "node", "scholar", "topic"}:
        raise ValueError("unsupported CuratedClaim target")
    public_links = (
        ClaimEvidence.objects.filter(
            evidence_span__is_stale=False,
            evidence_span__document_revision__asset__kind=Asset.Kind.NORMALIZED,
            evidence_span__document_revision__asset__status=Asset.Status.READY,
            evidence_span__document_revision__asset__access_status__in=viewer_access_statuses(),
        )
        .filter(
            active_document_revision_q(
                revision_prefix="evidence_span__document_revision"
            )
        )
        .select_related(
            "evidence_span__page",
            "evidence_span__document_revision__asset__edition__work",
        )
        .prefetch_related(
            "evidence_span__document_revision__asset__edition__contributions__person",
        )
        .order_by("sort_order", "created_at")
    )
    claims = (
        CuratedClaim.objects.filter(
            **{
                target_field: target_id,
                "status": CuratedClaim.Status.PUBLISHED,
                "kind__in": allowed_kinds,
                "evidence_links__in": public_links,
            }
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "evidence_links",
                queryset=public_links,
                to_attr="public_evidence_links",
            )
        )
        .order_by("kind", "sort_order", "created_at")
    )
    if target_field == "work":
        # A newly confirmed claim may already have a canonical published row
        # while the new catalog revision is preparing. Readers keep the
        # previously activated selection until all required consumers finish.
        active_ids = {
            str(identifier)
            for edition in public_editions(require_fulltext=True).filter(work_id=target_id)
            for identifier in (edition.active_catalog_revision.snapshot or {}).get("curated_claim_ids", [])
        }
        claims = claims.filter(pk__in=active_ids)
    return _serialize_curated_claim_groups(
        claims,
        evidence_attribute="public_evidence_links",
        allowed_kinds=allowed_kinds,
    )


def admin_preview_curated_claim_groups(
    *,
    work_id,
    edition_id,
    allowed_kinds: tuple[str, ...],
) -> dict[str, list[dict[str, Any]]]:
    """Include current draft curation for an authenticated page preview."""

    preview_links = (
        ClaimEvidence.objects.filter(
            evidence_span__is_stale=False,
            evidence_span__document_revision__is_active=True,
            evidence_span__document_revision__asset__edition_id=edition_id,
            evidence_span__document_revision__asset__kind=Asset.Kind.NORMALIZED,
            evidence_span__document_revision__asset__status=Asset.Status.READY,
            evidence_span__document_revision__asset__is_current=True,
            evidence_span__document_revision__asset__access_status__in=viewer_access_statuses(
                authenticated=True,
                staff=True,
            ),
        )
        .select_related(
            "evidence_span__page",
            "evidence_span__document_revision__asset__edition__work",
        )
        .prefetch_related(
            "evidence_span__document_revision__asset__edition__contributions__person",
        )
        .order_by("sort_order", "created_at")
    )
    claims = (
        CuratedClaim.objects.filter(
            work_id=work_id,
            status__in=(CuratedClaim.Status.DRAFT, CuratedClaim.Status.PUBLISHED),
            kind__in=allowed_kinds,
            evidence_links__in=preview_links,
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "evidence_links",
                queryset=preview_links,
                to_attr="preview_evidence_links",
            )
        )
        .order_by("kind", "sort_order", "created_at")
    )
    return _serialize_curated_claim_groups(
        claims,
        evidence_attribute="preview_evidence_links",
        allowed_kinds=allowed_kinds,
        public_metadata=False,
    )
