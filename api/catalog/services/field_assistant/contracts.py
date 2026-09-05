from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID


FIELD_ASSISTANT_VERSION = "catalog-field-assistant-v1"


@dataclass(frozen=True, slots=True)
class FieldAssistantRequest:
    """One explicit cataloguing-field lookup.

    ``confirmed_context`` may contain unsaved form values.  They are lookup
    context only and are never persisted by the assistant.
    """

    object_type: str
    object_id: UUID
    field_name: str
    query: str = ""
    confirmed_context: dict[str, Any] = field(default_factory=dict)
    upload_item_id: UUID | None = None
    allow_external: bool = True
    visibility: str = "admin"
    default_limit: int = 3


@dataclass(frozen=True, slots=True)
class FieldAssistantResult:
    field: dict[str, Any]
    context_fingerprint: str
    results: tuple[dict[str, Any], ...]
    more_results: tuple[dict[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    version: str = FIELD_ASSISTANT_VERSION

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["has_more"] = bool(self.more_results)
        payload["more_count"] = len(self.more_results)
        return payload
