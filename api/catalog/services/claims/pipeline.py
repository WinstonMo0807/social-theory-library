"""Read-only legacy prompt metadata and explicit retired-producer responses."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable

from django.db import DatabaseError, transaction

from catalog.models import (
    EvidenceSpan,
)
from common.ai_runtime import AICapability
from ingestion.services.ai_client import AIClient



CLAIM_PROMPT_KEY = "claim_extraction"
CLAIM_PROMPT_VERSION = "claim-extraction-v1"
MAX_CLAIMS_PER_SPAN = 24

CLAIM_EXTRACTION_SCHEMA = {
    "type": "object",
    "required": ["claims"],
    "properties": {
        "claims": {
            "type": "array",
            "maxItems": MAX_CLAIMS_PER_SPAN,
            "items": {
                "type": "object",
                "required": ["proposition", "claim_type"],
                "properties": {
                    "proposition": {"type": "string", "maxLength": 1600},
                    "subject": {"type": "string", "maxLength": 600},
                    "predicate": {"type": "string", "maxLength": 300},
                    "object": {"type": "string", "maxLength": 1600},
                    "polarity": {"type": "string"},
                    "modality": {"type": "string", "maxLength": 120},
                    "qualifiers": {
                        "type": "array",
                        "maxItems": 16,
                        "items": {"type": "string", "maxLength": 400},
                    },
                    "temporal_scope": {"type": "object"},
                    "geographic_scope": {"type": "object"},
                    "population_scope": {"type": "object"},
                    "attribution": {"type": "string"},
                    "claim_type": {"type": "string"},
                    "quality_score": {"type": "number"},
                    "importance_score": {"type": "number"},
                    "cluster_key": {"type": "string", "maxLength": 160},
                },
            },
        },
    },
}

CLAIM_EXTRACTION_SYSTEM_PROMPT = """
从给定的单一馆藏原文证据中提取相对原子化的社会科学命题候选。
每个候选只表达一个可判断的命题，不要输出章节摘要。保留否定、情态、时间、地理、人群和其他限定条件。
必须区分作者主张、引用主张、转述主张、被批评主张、历史描述和归因不确定。
不得引入原文之外的知识。返回值仅是机器派生候选，不代表已发布的正式知识。
""".strip()




def _bounded_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]






def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def resolve_claim_extraction_prompt(
    *,
    key: str = CLAIM_PROMPT_KEY,
    fallback_version: str = CLAIM_PROMPT_VERSION,
) -> dict[str, Any]:
    """Resolve the existing Prompt Registry before using the code baseline."""

    normalized_key = _bounded_text(key, 160) or CLAIM_PROMPT_KEY
    try:
        from catalog.services.research.prompt_registry import resolve_prompt

        prompt = resolve_prompt(key=normalized_key)
    except (DatabaseError, RuntimeError):
        prompt = None
    if (
        prompt is not None
        and prompt.capability == AICapability.CLAIM_EXTRACTION
        and str(prompt.content or "").strip()
        and isinstance(prompt.output_schema, dict)
        and prompt.output_schema
    ):
        return {
            "key": prompt.key,
            "version": f"registry-{prompt.version}",
            "registry_version": prompt.version,
            "registry_id": str(prompt.id),
            "content": prompt.content,
            "schema": dict(prompt.output_schema),
            "content_hash": prompt.content_hash,
            "schema_hash": prompt.schema_hash,
            "source": "prompt_registry",
        }
    baseline_schema = dict(CLAIM_EXTRACTION_SCHEMA)
    return {
        "key": normalized_key,
        "version": _bounded_text(fallback_version, 120) or CLAIM_PROMPT_VERSION,
        "registry_version": None,
        "registry_id": "",
        "content": CLAIM_EXTRACTION_SYSTEM_PROMPT,
        "schema": baseline_schema,
        "content_hash": sha256(CLAIM_EXTRACTION_SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "schema_hash": sha256(_canonical_json(baseline_schema).encode("utf-8")).hexdigest(),
        "source": "code_baseline",
    }














@transaction.atomic
def persist_claim_candidates(
    span: EvidenceSpan,
    candidates: Iterable[object],
    *,
    prompt_key: str,
    prompt_version: str,
    provider: str,
    model: str,
    model_revision: str,
    prompt_content_hash: str = "",
    prompt_schema_hash: str = "",
    prompt_registry_id: str = "",
    prompt_registry_version: int | None = None,
    prompt_source: str = "code_baseline",
) -> dict[str, Any]:
    from catalog.services.knowledge_retirement import MESSAGE
    raise ValueError(MESSAGE)



def extract_claims_shadow(
    span: EvidenceSpan,
    *,
    client: AIClient | None = None,
    prompt_key: str = CLAIM_PROMPT_KEY,
    prompt_version: str = CLAIM_PROMPT_VERSION,
    model_revision: str = "",
) -> dict[str, Any]:
    from catalog.services.knowledge_retirement import retired_result
    return retired_result()



run_claim_extraction_shadow = extract_claims_shadow


def _scheduled_runtime_identity() -> dict[str, Any]:
    try:
        from common.ai_runtime import runtime_profile

        profile = runtime_profile(AICapability.CLAIM_EXTRACTION)
    except (DatabaseError, RuntimeError, ValueError):
        return {
            "profile_key": "",
            "provider": "none",
            "model": "",
            "model_revision": "unversioned",
            "enabled": False,
        }
    reasoning = profile.reasoning if isinstance(profile.reasoning, dict) else {}
    return {
        "profile_key": profile.key,
        "provider": profile.provider,
        "model": profile.model,
        "model_revision": str(reasoning.get("model_revision") or "unversioned")[:160],
        "enabled": bool(profile.enabled),
    }




def dispatch_claim_extraction_demand(demand) -> bool:
    return False



def schedule_document_claim_extraction(
    revision,
    *,
    priority: int = 0,
    span_offset: int = 0,
    span_limit: int | None = None,
    page_indexes: Iterable[int] | None = None,
) -> dict[str, Any]:
    from catalog.services.knowledge_retirement import retired_result
    return retired_result()



def dispatch_ready_claim_extraction_demands(*, limit: int = 20) -> dict[str, int]:
    return {"candidates": 0, "dispatched": 0, "retired": True}
