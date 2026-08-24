from __future__ import annotations

from hashlib import sha256
import json
from typing import Any, Iterable
import uuid

from django.db import DatabaseError, transaction

from catalog.models import (
    ClaimEvidence,
    DerivedClaim,
    EvidenceSpan,
    ProjectionState,
)
from common.ai_runtime import AICapability
from ingestion.services.ai_client import AIClient, AIServiceError

from .attribution import infer_attribution


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


def _bounded_score(value: object, default: float = 0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return round(max(0.0, min(parsed, 1.0)), 4)


def _bounded_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _mapping(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _qualifiers(value: object) -> list[str]:
    if isinstance(value, str):
        rows: Iterable = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        rows = value
    else:
        rows = ()
    output: list[str] = []
    for row in rows:
        text = _bounded_text(row, 400)
        if text and text not in output:
            output.append(text)
        if len(output) >= 16:
            break
    return output


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


def _extraction_input_key(
    span: EvidenceSpan,
    *,
    prompt_key: str,
    prompt_version: str,
    provider: str,
    model: str,
    model_revision: str,
    prompt_content_hash: str,
    prompt_schema_hash: str,
) -> str:
    revision = span.document_revision
    payload = {
        "document_revision_id": str(revision.id),
        "document_revision": revision.revision,
        "revision_text_checksum": revision.text_checksum,
        "evidence_span_id": str(span.id),
        "evidence_content_hash": span.content_hash,
        "prompt_key": prompt_key,
        "prompt_version": prompt_version,
        "prompt_content_hash": prompt_content_hash,
        "prompt_schema_hash": prompt_schema_hash,
        "provider": provider,
        "model": model,
        "model_revision": model_revision,
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _claim_fingerprint(input_key: str, candidate: dict[str, Any]) -> str:
    identity = {
        "input_key": input_key,
        "proposition": candidate["proposition"].casefold(),
        "subject": candidate["subject"].casefold(),
        "predicate": candidate["predicate"].casefold(),
        "object": candidate["object"].casefold(),
        "polarity": candidate["polarity"],
        "modality": candidate["modality"].casefold(),
        "qualifiers": candidate["qualifiers"],
        "temporal_scope": candidate["temporal_scope"],
        "geographic_scope": candidate["geographic_scope"],
        "population_scope": candidate["population_scope"],
        "attribution": candidate["attribution"],
        "claim_type": candidate["claim_type"],
    }
    return sha256(_canonical_json(identity).encode("utf-8")).hexdigest()


def _normalize_candidate(raw: object, *, evidence_text: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    proposition = _bounded_text(raw.get("proposition"), 1600)
    claim_type = _bounded_text(raw.get("claim_type"), 24).casefold()
    if not proposition or claim_type not in DerivedClaim.ClaimType.values:
        return None
    polarity = _bounded_text(raw.get("polarity"), 20).casefold()
    if polarity not in DerivedClaim.Polarity.values:
        polarity = DerivedClaim.Polarity.UNCERTAIN
    decision = infer_attribution(
        proposition,
        explicit=raw.get("attribution"),
        claim_type=claim_type,
        context=evidence_text,
    )
    qualifiers = _qualifiers(raw.get("qualifiers"))
    return {
        "proposition": proposition,
        "subject": _bounded_text(raw.get("subject"), 600),
        "predicate": _bounded_text(raw.get("predicate"), 300),
        "object": _bounded_text(raw.get("object"), 1600),
        "polarity": polarity,
        "modality": _bounded_text(raw.get("modality"), 120),
        "qualifiers": qualifiers,
        "temporal_scope": _mapping(raw.get("temporal_scope")),
        "geographic_scope": _mapping(raw.get("geographic_scope")),
        "population_scope": _mapping(raw.get("population_scope")),
        "attribution": decision.attribution,
        "claim_type": claim_type,
        "quality_score": _bounded_score(raw.get("quality_score"), default=0.5),
        "importance_score": _bounded_score(raw.get("importance_score"), default=0.5),
        "cluster_key": _bounded_text(raw.get("cluster_key"), 160),
        "attribution_decision": decision.as_dict(),
    }


def _client_identity(client: AIClient, *, model_revision: str) -> tuple[str, str, str]:
    config = getattr(client, "config", None)
    provider = _bounded_text(getattr(config, "provider", "unknown"), 120) or "unknown"
    model = _bounded_text(
        getattr(config, "model", "") or getattr(config, "metadata_model", ""),
        240,
    ) or "unknown"
    reasoning = getattr(config, "reasoning", None)
    configured_revision = reasoning.get("model_revision") if isinstance(reasoning, dict) else ""
    revision = _bounded_text(model_revision or configured_revision or "unversioned", 160)
    return provider, model, revision


def _valid_span(span: EvidenceSpan) -> tuple[bool, str]:
    revision = span.document_revision
    if span.is_stale:
        return False, "evidence_span_stale"
    if not revision.is_active:
        return False, "document_revision_superseded"
    if span.page.asset_id != revision.asset_id:
        return False, "page_revision_asset_mismatch"
    if not span.original_text.strip():
        return False, "evidence_text_empty"
    return True, ""


def _existing_for_input(
    span: EvidenceSpan,
    *,
    input_key: str,
) -> list[DerivedClaim]:
    rows = list(
        DerivedClaim.objects.filter(
            primary_evidence=span,
            status=DerivedClaim.Status.ACTIVE,
            shadow=True,
        ).order_by("created_at")
    )
    return [
        row
        for row in rows
        if isinstance(row.quality_factors, dict)
        and row.quality_factors.get("extraction_input_key") == input_key
    ]


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
    """Persist only derived shadow rows and their locator-backed evidence."""

    valid, error_code = _valid_span(span)
    if not valid:
        return {
            "status": "skipped",
            "error_code": error_code,
            "created": 0,
            "reused": 0,
            "invalid": 0,
            "claim_ids": [],
            "publication_blocking": False,
        }
    input_key = _extraction_input_key(
        span,
        prompt_key=prompt_key,
        prompt_version=prompt_version,
        provider=provider,
        model=model,
        model_revision=model_revision,
        prompt_content_hash=prompt_content_hash,
        prompt_schema_hash=prompt_schema_hash,
    )
    revision = span.document_revision
    asset = revision.asset
    edition = asset.edition
    work = edition.work
    created = 0
    reused = 0
    invalid = 0
    claim_ids: list[str] = []
    current_claim_ids = []

    for raw in list(candidates)[:MAX_CLAIMS_PER_SPAN]:
        candidate = _normalize_candidate(raw, evidence_text=span.original_text)
        if candidate is None:
            invalid += 1
            continue
        fingerprint = _claim_fingerprint(input_key, candidate)
        quality_factors = {
            "extraction_input_key": input_key,
            "evidence_quality": span.quality,
            "qualifier_count": len(candidate["qualifiers"]),
            "attribution": candidate.pop("attribution_decision"),
            "prompt": {
                "key": prompt_key,
                "version": prompt_version,
                "registry_id": prompt_registry_id,
                "registry_version": prompt_registry_version,
                "content_hash": prompt_content_hash,
                "schema_hash": prompt_schema_hash,
                "source": prompt_source,
            },
        }
        claim, was_created = DerivedClaim.objects.get_or_create(
            document_revision=revision,
            fingerprint=fingerprint,
            defaults={
                "primary_evidence": span,
                "work": work,
                "edition": edition,
                "proposition": candidate["proposition"],
                "subject": candidate["subject"],
                "predicate": candidate["predicate"],
                "object": candidate["object"],
                "polarity": candidate["polarity"],
                "modality": candidate["modality"],
                "qualifiers": candidate["qualifiers"],
                "temporal_scope": candidate["temporal_scope"],
                "geographic_scope": candidate["geographic_scope"],
                "population_scope": candidate["population_scope"],
                "attribution": candidate["attribution"],
                "claim_type": candidate["claim_type"],
                "prompt_key": prompt_key,
                "prompt_version": prompt_version,
                "model_provider": provider,
                "model_name": model,
                "model_revision": model_revision,
                "quality_factors": quality_factors,
                "quality_score": candidate["quality_score"],
                "importance_score": candidate["importance_score"],
                "cluster_key": candidate["cluster_key"],
                "status": DerivedClaim.Status.ACTIVE,
                "shadow": True,
            },
        )
        ClaimEvidence.objects.get_or_create(
            derived_claim=claim,
            evidence_span=span,
            role=ClaimEvidence.Role.PRIMARY,
            defaults={
                "confidence": max(span.quality, claim.quality_score),
                "validation": {
                    "document_revision_active": True,
                    "evidence_span_stale": False,
                    "content_hash": span.content_hash,
                },
            },
        )
        ProjectionState.objects.get_or_create(
            object_type="derived_claim",
            object_id=claim.id,
            projection_type=ProjectionState.ProjectionType.CLAIM_INDEX,
            defaults={
                "source_revision": max(1, revision.revision),
                "projected_revision": 0,
                "status": ProjectionState.Status.STALE,
                "stale_reason": "derived claim awaiting claim index",
            },
        )
        created += int(was_created)
        reused += int(not was_created)
        claim_ids.append(str(claim.id))
        current_claim_ids.append(claim.id)

    if current_claim_ids:
        older = DerivedClaim.objects.filter(
            primary_evidence=span,
            status=DerivedClaim.Status.ACTIVE,
            shadow=True,
        ).exclude(pk__in=current_claim_ids)
        older_ids = []
        for row in older.only("id", "quality_factors"):
            factors = row.quality_factors if isinstance(row.quality_factors, dict) else {}
            if factors.get("extraction_input_key") != input_key:
                older_ids.append(row.id)
        if older_ids:
            DerivedClaim.objects.filter(pk__in=older_ids).update(
                status=DerivedClaim.Status.SUPERSEDED,
                stale_reason="superseded_by_new_extraction_revision",
            )
            ProjectionState.objects.filter(
                object_type="derived_claim",
                object_id__in=older_ids,
                projection_type=ProjectionState.ProjectionType.CLAIM_INDEX,
            ).update(
                status=ProjectionState.Status.STALE,
                stale_reason="claim superseded and must be removed from index",
            )

    return {
        "status": "completed",
        "created": created,
        "reused": reused,
        "invalid": invalid,
        "claim_ids": claim_ids,
        "extraction_input_key": input_key,
        "shadow": True,
        "publication_blocking": False,
    }


def extract_claims_shadow(
    span: EvidenceSpan,
    *,
    client: AIClient | None = None,
    prompt_key: str = CLAIM_PROMPT_KEY,
    prompt_version: str = CLAIM_PROMPT_VERSION,
    model_revision: str = "",
) -> dict[str, Any]:
    """Run optional claim extraction without participating in publication.

    Provider, configuration, timeout and invalid-output failures are returned
    as degraded state.  The original EvidenceSpan and all canonical knowledge
    remain untouched.
    """

    valid, error_code = _valid_span(span)
    if not valid:
        return {
            "status": "skipped",
            "error_code": error_code,
            "created": 0,
            "reused": 0,
            "invalid": 0,
            "claim_ids": [],
            "shadow": True,
            "publication_blocking": False,
        }
    prompt = resolve_claim_extraction_prompt(
        key=prompt_key,
        fallback_version=prompt_version,
    )
    resolved_prompt_key = prompt["key"]
    resolved_prompt_version = prompt["version"]
    try:
        active_client = client or AIClient(capability=AICapability.CLAIM_EXTRACTION)
    except AIServiceError as exc:
        return {
            "status": "degraded",
            "error_code": getattr(exc, "code", exc.__class__.__name__),
            "message": str(exc)[:500],
            "claim_ids": [],
            "shadow": True,
            "publication_blocking": False,
        }

    provider, model, resolved_model_revision = _client_identity(
        active_client,
        model_revision=model_revision,
    )
    input_key = _extraction_input_key(
        span,
        prompt_key=resolved_prompt_key,
        prompt_version=resolved_prompt_version,
        provider=provider,
        model=model,
        model_revision=resolved_model_revision,
        prompt_content_hash=prompt["content_hash"],
        prompt_schema_hash=prompt["schema_hash"],
    )
    existing = _existing_for_input(span, input_key=input_key)
    if existing:
        return {
            "status": "completed",
            "created": 0,
            "reused": len(existing),
            "invalid": 0,
            "claim_ids": [str(row.id) for row in existing],
            "extraction_input_key": input_key,
            "provider": provider,
            "model": model,
            "model_revision": resolved_model_revision,
            "prompt": {
                key: prompt[key]
                for key in (
                    "key",
                    "version",
                    "registry_version",
                    "registry_id",
                    "content_hash",
                    "schema_hash",
                    "source",
                )
            },
            "shadow": True,
            "publication_blocking": False,
            "idempotent_replay": True,
        }

    try:
        result = active_client.generate_json(
            task="claim_extraction",
            system_prompt=prompt["content"],
            document_text=span.original_text,
            schema=prompt["schema"],
            prompt_version=resolved_prompt_version,
            model=None if model == "unknown" else model,
        )
    except AIServiceError as primary_error:
        fallback_key = str(
            getattr(getattr(active_client, "config", None), "fallback_profile_key", "")
            or ""
        ).strip()
        if not fallback_key or client is not None:
            return {
                "status": "degraded",
                "error_code": getattr(primary_error, "code", primary_error.__class__.__name__),
                "message": str(primary_error)[:500],
                "claim_ids": [],
                "shadow": True,
                "publication_blocking": False,
            }
        try:
            active_client = AIClient(
                capability=AICapability.CLAIM_EXTRACTION,
                profile_key=fallback_key,
            )
            provider, model, resolved_model_revision = _client_identity(
                active_client,
                model_revision=model_revision,
            )
            result = active_client.generate_json(
                task="claim_extraction",
                system_prompt=prompt["content"],
                document_text=span.original_text,
                schema=prompt["schema"],
                prompt_version=resolved_prompt_version,
                model=None if model == "unknown" else model,
            )
        except AIServiceError as fallback_error:
            return {
                "status": "degraded",
                "error_code": getattr(fallback_error, "code", fallback_error.__class__.__name__),
                "message": str(fallback_error)[:500],
                "claim_ids": [],
                "shadow": True,
                "publication_blocking": False,
                "fallback_attempted": True,
            }

    output = persist_claim_candidates(
        span,
        (result.data.get("claims") or ()) if isinstance(result.data, dict) else (),
        prompt_key=resolved_prompt_key,
        prompt_version=resolved_prompt_version,
        provider=_bounded_text(getattr(result, "provider", provider), 120) or provider,
        model=_bounded_text(getattr(result, "model", model), 240) or model,
        model_revision=resolved_model_revision,
        prompt_content_hash=prompt["content_hash"],
        prompt_schema_hash=prompt["schema_hash"],
        prompt_registry_id=prompt["registry_id"],
        prompt_registry_version=prompt["registry_version"],
        prompt_source=prompt["source"],
    )
    output.update(
        {
            "provider": _bounded_text(getattr(result, "provider", provider), 120) or provider,
            "model": _bounded_text(getattr(result, "model", model), 240) or model,
            "model_revision": resolved_model_revision,
            "prompt_key": resolved_prompt_key,
            "prompt_version": resolved_prompt_version,
            "prompt": {
                key: prompt[key]
                for key in (
                    "registry_version",
                    "registry_id",
                    "content_hash",
                    "schema_hash",
                    "source",
                )
            },
        }
    )
    return output


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


def _claim_demand_idempotency_key(span: EvidenceSpan, prompt: dict, runtime: dict) -> str:
    payload = {
        "document_revision_id": str(span.document_revision_id),
        "document_text_checksum": span.document_revision.text_checksum,
        "evidence_span_id": str(span.id),
        "evidence_content_hash": span.content_hash,
        "prompt_key": prompt["key"],
        "prompt_version": prompt["version"],
        "prompt_content_hash": prompt["content_hash"],
        "prompt_schema_hash": prompt["schema_hash"],
        "profile_key": runtime["profile_key"],
        "provider": runtime["provider"],
        "model": runtime["model"],
        "model_revision": runtime["model_revision"],
    }
    digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"claim-extraction:{span.id}:{digest}"


def dispatch_claim_extraction_demand(demand) -> bool:
    """Reserve a demand before putting its lease on the consumed default queue."""

    from catalog.models import CapabilityExecutor
    from common.task_runtime import (
        claim_specific_demand,
        live_executors,
        release_demand,
    )

    executors = [
        executor
        for executor in live_executors("llm_small", require_capacity=True)
        if executor.kind == CapabilityExecutor.Kind.NAS
    ]
    for executor in executors:
        lease = claim_specific_demand(
            demand.id,
            executor_id=executor.executor_id,
            lease_seconds=300,
        )
        if lease is None:
            continue
        try:
            from catalog.tasks import execute_claim_extraction_demand

            execute_claim_extraction_demand.apply_async(
                args=[
                    str(lease.demand_id),
                    str(lease.lease_token),
                    lease.executor_id,
                ],
                task_id=str(uuid.uuid4()),
                queue="celery",
            )
        except Exception as exc:
            release_demand(
                lease.demand_id,
                lease.lease_token,
                executor_id=lease.executor_id,
                error_code="queue_unavailable",
                error_message=str(exc),
                retry=True,
                retry_after_seconds=30,
            )
            raise
        return True
    return False


def schedule_document_claim_extraction(
    revision,
    *,
    priority: int = 0,
    span_offset: int = 0,
    span_limit: int | None = None,
    page_indexes: Iterable[int] | None = None,
) -> dict[str, Any]:
    """Schedule one idempotent, non-blocking demand per current EvidenceSpan."""

    from catalog.models import CapabilityExecutor, DocumentRevision
    from common.task_runtime import live_executors, queue_or_wait

    if not isinstance(revision, DocumentRevision):
        revision = DocumentRevision.objects.get(pk=revision)
    if not revision.is_active:
        return {
            "status": "skipped",
            "reason": "document_revision_superseded",
            "document_revision_id": str(revision.id),
            "scheduled": 0,
            "publication_blocking": False,
        }
    prompt = resolve_claim_extraction_prompt()
    runtime = _scheduled_runtime_identity()
    nas_available = any(
        executor.kind == CapabilityExecutor.Kind.NAS
        for executor in live_executors("llm_small", require_capacity=True)
    )
    span_offset = max(0, int(span_offset))
    if span_limit is not None:
        span_limit = max(1, min(int(span_limit), 5000))
    span_query = (
        revision.evidence_spans.filter(is_stale=False)
        .select_related("document_revision", "page__asset")
        .order_by("page_number", "start_offset", "id")
    )
    normalized_pages = None
    if page_indexes is not None:
        normalized_pages = sorted({int(value) for value in page_indexes if int(value) > 0})
        span_query = span_query.filter(page__index__in=normalized_pages)
    spans = list(
        span_query[span_offset : span_offset + span_limit]
        if span_limit is not None
        else span_query[span_offset:]
    )
    states: dict[str, int] = {}
    demand_ids: list[str] = []
    dispatch_requested = 0
    for span in spans:
        result = queue_or_wait(
            owner_type="evidence_span",
            owner_key=str(span.id),
            capability="llm_small",
            idempotency_key=_claim_demand_idempotency_key(span, prompt, runtime),
            payload={
                "task_kind": "claim_extraction",
                "document_revision_id": str(revision.id),
                "evidence_span_id": str(span.id),
                "prompt_key": prompt["key"],
                "prompt_version": prompt["version"],
                "prompt_content_hash": prompt["content_hash"],
                "prompt_schema_hash": prompt["schema_hash"],
                "prompt_content": prompt["content"],
                "prompt_schema": prompt["schema"],
                "prompt_registry_id": prompt["registry_id"],
                "prompt_registry_version": prompt["registry_version"],
                "prompt_source": prompt["source"],
                "profile_key": runtime["profile_key"],
                "provider": runtime["provider"],
                "model": runtime["model"],
                "model_revision": runtime["model_revision"],
            },
            priority=priority,
            publication_blocking=False,
            preferred_queue="celery",
            dispatch=dispatch_claim_extraction_demand if nas_available else None,
        )
        state = str(result.demand.state)
        states[state] = states.get(state, 0) + 1
        demand_ids.append(str(result.demand.id))
        dispatch_requested += int(result.dispatched)
    return {
        "status": "scheduled" if spans else "no_evidence",
        "document_revision_id": str(revision.id),
        "evidence_spans": len(spans),
        "scheduled": len(demand_ids),
        "demand_ids": demand_ids,
        "states": states,
        "dispatch_requested": dispatch_requested,
        "runtime_profile_enabled": runtime["enabled"],
        "span_offset": span_offset,
        "span_limit": span_limit,
        "page_indexes": normalized_pages,
        "publication_blocking": False,
    }


def dispatch_ready_claim_extraction_demands(*, limit: int = 20) -> dict[str, int]:
    """Bounded NAS push adapter; remote GPU workers continue using pull claims."""

    from catalog.models import CapabilityDemand
    from django.db.models import Q
    from django.utils import timezone

    demands = list(
        CapabilityDemand.objects.filter(
            state=CapabilityDemand.State.READY,
            owner_type="evidence_span",
            payload__task_kind="claim_extraction",
        )
        .filter(Q(not_before__isnull=True) | Q(not_before__lte=timezone.now()))
        .order_by("-priority", "created_at")[: max(1, min(int(limit), 100))]
    )
    dispatched = 0
    for demand in demands:
        dispatched += int(dispatch_claim_extraction_demand(demand))
    return {"candidates": len(demands), "dispatched": dispatched}
