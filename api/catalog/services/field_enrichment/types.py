from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class FieldEnrichmentRequest:
    target_type: str
    target_id: UUID
    field_names: tuple[str, ...]
    current_value: Any = None
    form_context: dict[str, Any] = field(default_factory=dict)
    requested_mode: str = "structured"
    visibility: str = "admin"


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    provider: str = ""
    source_class: str = "unknown"


@dataclass(frozen=True)
class FetchedDocument:
    source_url: str
    canonical_url: str
    title: str
    domain: str
    text: str
    retrieved_at: datetime
    content_checksum: str
    http_status: int
    content_type: str
    source_record_id: UUID | None = None
    source_class: str = "unknown"


@dataclass(frozen=True)
class FieldObservation:
    field_name: str
    value: Any
    provider: str
    source_class: str
    source_url: str
    canonical_url: str
    source_title: str
    supporting_text: str
    content_checksum: str
    retrieved_at: datetime
    locator: dict[str, Any] = field(default_factory=dict)
    source_record_id: UUID | None = None
    external_identifier: str = ""
    identity_claims: dict[str, Any] = field(default_factory=dict)
    confidence_factors: dict[str, Any] = field(default_factory=dict)
    http_status: int | None = None
    content_type: str = ""
    extraction_method: str = "structured"


@dataclass(frozen=True)
class EnrichmentError:
    code: str
    detail: str
    provider: str = ""
    field_name: str = ""


@dataclass
class EnrichmentResult:
    request_id: UUID
    candidates: list[Any] = field(default_factory=list)
    errors: list[EnrichmentError] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
