from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


RESEARCH_DIAGNOSTICS_VERSION = "research-diagnostics-v1"


class ResearchErrorCode:
    QUERY_PLAN_EMPTY = "query_plan_empty"
    WEB_SEARCH_NOT_CONFIGURED = "web_search_not_configured"
    WEB_SEARCH_FAILED = "web_search_failed"
    WEB_SEARCH_ZERO_RESULTS = "web_search_zero_results"
    FETCH_BLOCKED = "fetch_blocked"
    FETCH_FAILED = "fetch_failed"
    FETCH_NO_CANDIDATE = "fetch_succeeded_but_no_candidate"
    AUTHORITY_UNAVAILABLE = "authority_unavailable"
    IDENTITY_AMBIGUOUS = "identity_ambiguous"
    CONTRACT_MISSING = "contract_missing"
    EXTRACTOR_FAILED = "extractor_failed"


@dataclass
class ResearchDiagnostics:
    context_revision: str
    active_step: str
    changed_fields: list[str]
    generated_queries: list[str] = field(default_factory=list)
    providers_attempted: list[str] = field(default_factory=list)
    searxng_called: bool = False
    query_result_counts: dict[str, int] = field(default_factory=dict)
    fetch_count: int = 0
    fetch_failure_count: int = 0
    blocked_count: int = 0
    structured_provider_results: dict[str, int] = field(default_factory=dict)
    candidate_counts: dict[str, int] = field(default_factory=dict)
    extracted_count: int = 0
    rejected_count: int = 0
    accepted_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    version: str = RESEARCH_DIAGNOSTICS_VERSION

    def add_error(self, code: str, detail: str, *, field_name: str = "", provider: str = "") -> None:
        self.errors.append({
            "code": code,
            "detail": str(detail)[:500],
            "field": field_name,
            "provider": provider,
        })

    def payload(self) -> dict[str, Any]:
        return asdict(self)
