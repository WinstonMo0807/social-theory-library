from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from catalog.services.field_enrichment.web import SafeWebFetcher, WebFetchError
from ingestion.models import EntityResolutionCandidate


@dataclass(frozen=True)
class CandidateVerificationResult:
    candidate: EntityResolutionCandidate
    status: str
    code: str
    detail: str
    idempotent: bool = False


class CandidateVerificationError(ValueError):
    def __init__(self, code: str, detail: str, *, http_status: int = 422):
        super().__init__(detail)
        self.code = code
        self.http_status = http_status


def _candidate_terms(candidate: EntityResolutionCandidate) -> list[str]:
    values = [candidate.source_name, candidate.label, *(candidate.aliases or [])]
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        compact = " ".join(str(value or "").split()).strip()
        key = compact.casefold()
        if len(compact) < 2 or key in seen or compact.startswith(("http://", "https://")):
            continue
        seen.add(key)
        output.append(compact)
    return output[:12]


def _evidence_excerpt(text: str, terms: list[str], *, limit: int = 1600) -> tuple[str, int, int, str]:
    compact = " ".join(str(text or "").split())
    folded = compact.casefold()
    matches = [
        (folded.find(term.casefold()), term)
        for term in terms
        if folded.find(term.casefold()) >= 0
    ]
    if not matches:
        return "", 0, 0, ""
    position, matched_term = min(matches, key=lambda row: row[0])
    start = max(0, position - 360)
    end = min(len(compact), start + limit)
    return compact[start:end], start, end, matched_term


def _existing_evidence(candidate: EntityResolutionCandidate) -> list[dict[str, Any]]:
    evidence = (candidate.preview_data or {}).get("evidence") or []
    return [row for row in evidence if isinstance(row, dict) and str(row.get("text") or "").strip()]


def verify_research_candidate(
    candidate: EntityResolutionCandidate,
    *,
    fetcher: SafeWebFetcher | None = None,
) -> CandidateVerificationResult:
    """Turn one persisted search lead into an evidenced, still-human-reviewed candidate."""

    candidate = EntityResolutionCandidate.objects.select_related(
        "upload_item__edition__work"
    ).get(pk=candidate.pk)
    if candidate.status != EntityResolutionCandidate.Status.PROPOSED:
        raise CandidateVerificationError(
            "candidate_finalized",
            "该候选已经有最终决定，不能再次核实。",
            http_status=409,
        )

    properties = dict(candidate.supporting_properties or {})
    group = str(properties.get("candidate_group") or "").strip().casefold()
    evidence_status = str(properties.get("evidence_status") or "").strip().casefold()
    existing_evidence = _existing_evidence(candidate)
    if group in {"external_evidence", "verified_web"} and evidence_status in {
        "verified_text",
        "web_evidence",
    } and existing_evidence:
        return CandidateVerificationResult(
            candidate=candidate,
            status="verified",
            code="candidate_already_verified",
            detail="该结果已取得正文证据，可以进行人工决定。",
            idempotent=True,
        )

    provider = str(properties.get("provider") or "").strip().casefold()
    if group not in {"external_web", "research_lead"} and provider not in {
        "searxng",
        "web_search",
        "searching",
    }:
        raise CandidateVerificationError(
            "not_a_web_lead",
            "该候选不是需要正文核实的 Web 搜索线索。",
            http_status=409,
        )
    source_url = str(
        properties.get("source_url")
        or (candidate.preview_data or {}).get("source_url")
        or ""
    ).strip()
    if not source_url:
        raise CandidateVerificationError(
            "missing_source_url",
            "该搜索线索没有可核实的来源地址。",
            http_status=422,
        )

    try:
        document = (fetcher or SafeWebFetcher()).fetch(source_url)
    except WebFetchError as exc:
        raise CandidateVerificationError(exc.code, str(exc), http_status=502) from exc

    excerpt, start, end, matched_term = _evidence_excerpt(
        document.text,
        _candidate_terms(candidate),
    )
    if not excerpt:
        raise CandidateVerificationError(
            "no_reliable_candidate",
            "已取得来源正文，但正文未明确出现候选名称，不能形成可靠候选。",
            http_status=422,
        )

    retrieved_at = document.retrieved_at or timezone.now()
    evidence = {
        "kind": "external_page",
        "source": {
            "title": document.title,
            "url": document.canonical_url,
            "domain": document.domain,
            "source_class": document.source_class,
        },
        "text": excerpt,
        "locator": {
            "url": document.canonical_url,
            "start_offset": start,
            "end_offset": end,
            "matched_term": matched_term,
        },
        "quality": {
            "body_fetched": True,
            "identity_term_present": True,
            "http_status": document.http_status,
            "content_type": document.content_type,
        },
        "provenance": {
            "provider": "safe_web_fetch",
            "discovery_provider": properties.get("provider") or "web_search",
            "source_record_id": str(document.source_record_id or ""),
            "content_checksum": document.content_checksum,
            "retrieved_at": retrieved_at.isoformat(),
        },
        "reader_url": document.canonical_url,
    }

    with transaction.atomic():
        locked = EntityResolutionCandidate.objects.select_for_update().get(pk=candidate.pk)
        if locked.status != EntityResolutionCandidate.Status.PROPOSED:
            raise CandidateVerificationError(
                "candidate_finalized",
                "核实期间候选已被处理，请刷新后查看。",
                http_status=409,
            )
        locked_properties = dict(locked.supporting_properties or {})
        locked_properties.update(
            {
                "candidate_group": "external_evidence",
                "evidence_status": "verified_text",
                "source_url": document.canonical_url,
                "evidence_provider": "safe_web_fetch",
                "evidence_source_class": document.source_class,
                "verified_at": retrieved_at.isoformat(),
            }
        )
        preview = dict(locked.preview_data or {})
        preview.update(
            {
                "source_url": document.canonical_url,
                "source_title": document.title,
                "evidence": [evidence],
            }
        )
        reasons = list(locked.match_reasons or [])
        verified_reason = "SafeWebFetcher 已取得原页正文，候选名称在正文中可定位"
        if verified_reason not in reasons:
            reasons.append(verified_reason)
        locked.source_record_id = document.source_record_id
        locked.supporting_properties = locked_properties
        locked.preview_data = preview
        locked.match_reasons = reasons
        locked.save(
            update_fields=[
                "source_record",
                "supporting_properties",
                "preview_data",
                "match_reasons",
                "updated_at",
            ]
        )

    return CandidateVerificationResult(
        candidate=locked,
        status="verified",
        code="candidate_verified",
        detail="已取得并定位来源正文，候选现在可以进行人工决定。",
    )
