"""Server-side protocol helpers for opportunistic pull workers.

The remote worker only leases derived work. PostgreSQL remains authoritative
for demand state, evidence provenance and persisted claim candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import CapabilityDemand, CapabilityExecutor, EvidencePack, EvidenceSpan
from catalog.services.claims.pipeline import (
    MAX_CLAIMS_PER_SPAN,
    persist_claim_candidates,
    resolve_claim_extraction_prompt,
)
from catalog.services.research.library_synthesis import (
    LIBRARY_SYNTHESIS_FIELDS,
    persist_library_synthesis_candidate,
    resolve_library_synthesis_prompt,
)
from common.task_runtime import DemandLease, complete_demand
from ingestion.models import UploadItem


REMOTE_TASK_KINDS = frozenset({"claim_extraction", "library_synthesis"})
AI_CAPABILITIES = frozenset({"embedding", "rerank", "llm_small", "llm_large"})
COMPLETION_MARKER_KEY = "_remote_completion"
LEASE_CONTEXT_KEY = "_remote_lease_context"


class RemoteWorkerProtocolError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = str(code)[:120]
        self.status_code = status_code


@dataclass(frozen=True)
class RemoteCompletion:
    demand_id: str
    status: str
    created: int
    reused: int
    invalid: int
    claim_ids: list[str]
    candidate_ids: list[str]
    idempotent_replay: bool
    publication_blocking: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "demand_id": self.demand_id,
            "status": self.status,
            "created": self.created,
            "reused": self.reused,
            "invalid": self.invalid,
            "claim_ids": self.claim_ids,
            "candidate_ids": self.candidate_ids,
            "idempotent_replay": self.idempotent_replay,
            "publication_blocking": self.publication_blocking,
        }


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def result_fingerprint(result: dict[str, Any]) -> str:
    return sha256(canonical_json(result).encode("utf-8")).hexdigest()


def sanitize_model_revisions(raw: object, *, capabilities: list[str]) -> dict[str, dict[str, str]]:
    if not isinstance(raw, dict):
        raise RemoteWorkerProtocolError(
            "invalid_model_revisions",
            "model_revisions must be an object keyed by capability.",
        )
    output: dict[str, dict[str, str]] = {}
    for capability in capabilities:
        if capability not in AI_CAPABILITIES:
            continue
        value = raw.get(capability)
        if not isinstance(value, dict):
            raise RemoteWorkerProtocolError(
                "missing_model_revision",
                f"{capability} must declare provider, model and revision.",
            )
        provider = str(value.get("provider") or "").strip()[:120]
        model = str(value.get("model") or "").strip()[:240]
        revision = str(value.get("revision") or "").strip()[:160]
        if not provider or not model or not revision:
            raise RemoteWorkerProtocolError(
                "missing_model_revision",
                f"{capability} must declare provider, model and revision.",
            )
        output[capability] = {
            "provider": provider,
            "model": model,
            "revision": revision,
        }
    return output


def sanitize_metadata(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    fields = {
        "worker_version": 80,
        "runtime": 120,
        "gpu_name": 160,
        "host_label": 160,
    }
    output = {
        field: str(raw.get(field) or "").strip()[:limit]
        for field, limit in fields.items()
        if str(raw.get(field) or "").strip()
    }
    try:
        memory = int(raw.get("gpu_memory_mb"))
    except (TypeError, ValueError):
        memory = 0
    if memory > 0:
        output["gpu_memory_mb"] = min(memory, 1024 * 1024)
    task_kinds = [
        str(value or "").strip()
        for value in raw.get("task_kinds") or []
        if str(value or "").strip() in REMOTE_TASK_KINDS
    ]
    if task_kinds:
        output["task_kinds"] = sorted(set(task_kinds))
    raw_profiles = raw.get("task_profiles")
    if isinstance(raw_profiles, dict):
        profiles: dict[str, list[str]] = {}
        for task_kind, values in raw_profiles.items():
            normalized_kind = str(task_kind or "").strip()
            if normalized_kind not in REMOTE_TASK_KINDS or not isinstance(values, (list, tuple, set)):
                continue
            profiles[normalized_kind] = sorted(
                {
                    str(value or "").strip()[:120]
                    for value in values
                    if str(value or "").strip()
                }
            )[:20]
        if profiles:
            output["task_profiles"] = profiles
    return output


def _immutable_prompt(payload: dict[str, Any]) -> dict[str, Any]:
    content = str(payload.get("prompt_content") or "").strip()
    schema = payload.get("prompt_schema")
    if content and isinstance(schema, dict) and schema:
        return {
            "key": str(payload.get("prompt_key") or "claim_extraction")[:160],
            "version": str(payload.get("prompt_version") or "")[:120],
            "content": content,
            "schema": schema,
            "content_hash": str(payload.get("prompt_content_hash") or "")[:64],
            "schema_hash": str(payload.get("prompt_schema_hash") or "")[:64],
            "registry_id": str(payload.get("prompt_registry_id") or "")[:64],
            "registry_version": payload.get("prompt_registry_version"),
            "source": str(payload.get("prompt_source") or "code_baseline")[:40],
        }

    task_kind = str(payload.get("task_kind") or "claim_extraction")
    current = (
        resolve_library_synthesis_prompt()
        if task_kind == "library_synthesis"
        else resolve_claim_extraction_prompt(
            key=str(payload.get("prompt_key") or "claim_extraction")
        )
    )
    expected_hashes = (
        str(payload.get("prompt_content_hash") or ""),
        str(payload.get("prompt_schema_hash") or ""),
    )
    current_hashes = (str(current["content_hash"]), str(current["schema_hash"]))
    if any(expected_hashes) and expected_hashes != current_hashes:
        raise RemoteWorkerProtocolError(
            "prompt_revision_stale",
            "The scheduled prompt revision is no longer available. Reschedule the demand.",
            status_code=409,
        )
    return current


def _claim_span(demand: CapabilityDemand) -> EvidenceSpan:
    payload = dict(demand.payload or {})
    if payload.get("task_kind") != "claim_extraction":
        raise RemoteWorkerProtocolError(
            "unsupported_task_kind",
            "The remote worker cannot process this demand type.",
            status_code=409,
        )
    span_id = str(payload.get("evidence_span_id") or "")
    if demand.owner_type != "evidence_span" or demand.owner_key != span_id:
        raise RemoteWorkerProtocolError(
            "demand_owner_mismatch",
            "The demand owner does not match its evidence payload.",
            status_code=409,
        )
    try:
        span = EvidenceSpan.objects.select_related(
            "document_revision__asset__edition__work",
            "page__asset",
        ).get(pk=span_id)
    except (EvidenceSpan.DoesNotExist, ValueError) as exc:
        raise RemoteWorkerProtocolError(
            "evidence_span_missing",
            "The source evidence span is unavailable.",
            status_code=409,
        ) from exc
    if str(span.document_revision_id) != str(payload.get("document_revision_id") or ""):
        raise RemoteWorkerProtocolError(
            "document_revision_mismatch",
            "The source revision does not match the demand payload.",
            status_code=409,
        )
    if span.is_stale or not span.document_revision.is_active:
        raise RemoteWorkerProtocolError(
            "source_revision_stale",
            "The source evidence has been superseded.",
            status_code=409,
        )
    return span


def _library_synthesis_pack(demand: CapabilityDemand) -> EvidencePack:
    payload = dict(demand.payload or {})
    if payload.get("task_kind") != "library_synthesis":
        raise RemoteWorkerProtocolError(
            "unsupported_task_kind",
            "The remote worker cannot process this demand type.",
            status_code=409,
        )
    pack_id = str(payload.get("evidence_pack_id") or "")
    if demand.owner_type != "evidence_pack" or demand.owner_key != pack_id:
        raise RemoteWorkerProtocolError(
            "demand_owner_mismatch",
            "The demand owner does not match its EvidencePack payload.",
            status_code=409,
        )
    try:
        pack = EvidencePack.objects.get(pk=pack_id)
    except (EvidencePack.DoesNotExist, ValueError) as exc:
        raise RemoteWorkerProtocolError(
            "evidence_pack_missing",
            "The scheduled EvidencePack is unavailable.",
            status_code=409,
        ) from exc
    if pack.task_profile_key != "library_synthesis":
        raise RemoteWorkerProtocolError(
            "evidence_pack_profile_mismatch",
            "The EvidencePack was not created for Library Synthesis.",
            status_code=409,
        )
    if pack.subject_type != "work" or str(pack.subject_id) != str(payload.get("work_id") or ""):
        raise RemoteWorkerProtocolError(
            "evidence_pack_subject_mismatch",
            "The EvidencePack Work does not match the scheduled target.",
            status_code=409,
        )
    field_name = str(payload.get("field_name") or "")
    retrieval_field = str((pack.retrieval_snapshot or {}).get("field_name") or "")
    if field_name not in LIBRARY_SYNTHESIS_FIELDS or retrieval_field != field_name:
        raise RemoteWorkerProtocolError(
            "evidence_pack_field_mismatch",
            "The EvidencePack field does not match the scheduled synthesis target.",
            status_code=409,
        )
    try:
        item = UploadItem.objects.select_related("edition__work").get(
            pk=payload.get("upload_item_id")
        )
    except (UploadItem.DoesNotExist, ValueError) as exc:
        raise RemoteWorkerProtocolError(
            "upload_item_missing",
            "The Library Synthesis intake item is unavailable.",
            status_code=409,
        ) from exc
    if item.edition_id is None or str(item.edition.work_id) != str(pack.subject_id):
        raise RemoteWorkerProtocolError(
            "evidence_pack_subject_mismatch",
            "The intake item no longer belongs to the EvidencePack Work.",
            status_code=409,
        )
    envelopes = pack.envelope_snapshot
    if not isinstance(envelopes, list) or len(envelopes) < 2 or len(envelopes) > 12:
        raise RemoteWorkerProtocolError(
            "evidence_pack_invalid",
            "Library Synthesis requires two to twelve immutable evidence envelopes.",
            status_code=409,
        )
    span_ids = {
        str(row.get("id") or "")
        for row in envelopes
        if isinstance(row, dict) and str(row.get("id") or "")
    }
    if len(span_ids) != len(envelopes):
        raise RemoteWorkerProtocolError(
            "evidence_pack_invalid",
            "Every Library Synthesis envelope must identify one EvidenceSpan.",
            status_code=409,
        )
    current_ids = {
        str(value)
        for value in EvidenceSpan.objects.filter(
            pk__in=span_ids,
            is_stale=False,
            document_revision__is_active=True,
        ).values_list("id", flat=True)
    }
    if current_ids != span_ids:
        raise RemoteWorkerProtocolError(
            "source_revision_stale",
            "One or more EvidencePack spans have been superseded.",
            status_code=409,
        )
    text_chars = sum(len(str(row.get("text") or "")) for row in envelopes)
    if text_chars > settings.CAPABILITY_REMOTE_WORKER_MAX_JOB_TEXT_CHARS:
        raise RemoteWorkerProtocolError(
            "job_text_too_large",
            "The EvidencePack exceeds the configured remote worker text limit.",
            status_code=409,
        )
    return pack


def build_remote_job(lease: DemandLease) -> dict[str, Any]:
    demand = CapabilityDemand.objects.get(pk=lease.demand_id)
    payload = dict(demand.payload or {})
    prompt = _immutable_prompt(payload)
    runtime = payload.get(LEASE_CONTEXT_KEY)
    if not isinstance(runtime, dict):
        raise RemoteWorkerProtocolError(
            "lease_context_missing",
            "The remote lease model context is unavailable.",
            status_code=409,
        )
    common = {
        "prompt": {
            "key": prompt["key"],
            "version": prompt["version"],
            "content": prompt["content"],
            "content_hash": prompt["content_hash"],
            "schema_hash": prompt["schema_hash"],
        },
        "output_schema": prompt["schema"],
        "runtime": {
            "provider": runtime.get("provider"),
            "model": runtime.get("model"),
            "model_revision": runtime.get("model_revision"),
        },
    }
    task_kind = str(payload.get("task_kind") or "")
    if task_kind == "claim_extraction":
        span = _claim_span(demand)
        if len(span.original_text) > settings.CAPABILITY_REMOTE_WORKER_MAX_JOB_TEXT_CHARS:
            raise RemoteWorkerProtocolError(
                "job_text_too_large",
                "The evidence span exceeds the configured remote worker text limit.",
                status_code=409,
            )
        return {
            "task_kind": task_kind,
            "input": {
                "document_revision_id": str(span.document_revision_id),
                "document_revision": span.document_revision.revision,
                "document_text_checksum": span.document_revision.text_checksum,
                "evidence_span_id": str(span.id),
                "evidence_content_hash": span.content_hash,
                "text": span.original_text,
                "language": span.language,
                "page_number": span.page_number,
                "printed_page_label": span.printed_page_label,
                "section": span.section,
            },
            **common,
            "limits": {"max_claims": MAX_CLAIMS_PER_SPAN},
        }
    if task_kind == "library_synthesis":
        pack = _library_synthesis_pack(demand)
        return {
            "task_kind": task_kind,
            "task_profile_key": "library_synthesis",
            "input": {
                "evidence_pack_id": str(pack.id),
                "evidence_pack_fingerprint": pack.fingerprint,
                "subject_type": pack.subject_type,
                "subject_id": pack.subject_id,
                "requested_field": str(payload.get("field_name") or ""),
                "evidence": pack.envelope_snapshot,
            },
            **common,
            "limits": {"max_evidence": 12, "max_output_chars": 12_000},
        }
    raise RemoteWorkerProtocolError(
        "unsupported_task_kind",
        "The remote worker cannot process this demand type.",
        status_code=409,
    )


@transaction.atomic
def bind_remote_lease_context(lease: DemandLease) -> dict[str, str]:
    """Snapshot model provenance for this lease without storing its token."""

    demand = (
        CapabilityDemand.objects.select_for_update(of=("self",))
        .select_related("claimed_by")
        .get(pk=lease.demand_id)
    )
    if (
        demand.state != CapabilityDemand.State.CLAIMED
        or demand.claimed_by is None
        or demand.claimed_by.executor_id != lease.executor_id
        or str(demand.lease_token) != str(lease.lease_token)
        or demand.claimed_by.kind != CapabilityExecutor.Kind.REMOTE_GPU
    ):
        raise RemoteWorkerProtocolError(
            "lease_not_active",
            "The remote demand lease is no longer active.",
            status_code=409,
        )
    declared = (demand.claimed_by.model_revisions or {}).get(demand.capability)
    if not isinstance(declared, dict):
        raise RemoteWorkerProtocolError(
            "model_revision_not_declared",
            "The executor heartbeat did not declare this model revision.",
            status_code=409,
        )
    context = {
        "executor_id": lease.executor_id,
        "provider": str(declared.get("provider") or "").strip()[:120],
        "model": str(declared.get("model") or "").strip()[:240],
        "model_revision": str(declared.get("revision") or "").strip()[:160],
        "claimed_at": timezone.now().isoformat(),
    }
    if not context["provider"] or not context["model"] or not context["model_revision"]:
        raise RemoteWorkerProtocolError(
            "model_revision_not_declared",
            "Provider, model and revision are required for claim provenance.",
            status_code=409,
        )
    payload = dict(demand.payload or {})
    payload[LEASE_CONTEXT_KEY] = context
    demand.payload = payload
    demand.save(update_fields=["payload", "updated_at"])
    return context


def _model_identity(
    executor: CapabilityExecutor,
    demand: CapabilityDemand,
    result: dict[str, Any],
) -> tuple[str, str, str]:
    declared = (demand.payload or {}).get(LEASE_CONTEXT_KEY)
    if not isinstance(declared, dict):
        raise RemoteWorkerProtocolError(
            "model_revision_not_declared",
            "The executor heartbeat did not declare this model revision.",
            status_code=409,
        )
    identity = {
        "provider": str(declared.get("provider") or "").strip()[:120],
        "model": str(declared.get("model") or "").strip()[:240],
        "model_revision": str(declared.get("model_revision") or "").strip()[:160],
    }
    if str(declared.get("executor_id") or "") != executor.executor_id:
        raise RemoteWorkerProtocolError(
            "model_identity_mismatch",
            "The completion executor differs from the leased model context.",
            status_code=409,
        )
    for supplied_key, canonical_key in (
        ("provider", "provider"),
        ("model", "model"),
        ("model_revision", "model_revision"),
    ):
        supplied = str(result.get(supplied_key) or "").strip()
        if supplied and supplied != identity[canonical_key]:
            raise RemoteWorkerProtocolError(
                "model_identity_mismatch",
                "The completion model identity differs from the latest heartbeat.",
                status_code=409,
            )
    if not all(identity.values()):
        raise RemoteWorkerProtocolError(
            "model_revision_not_declared",
            "Provider, model and revision are required for claim provenance.",
            status_code=409,
        )
    return identity["provider"], identity["model"], identity["model_revision"]


def _completion_from_marker(demand: CapabilityDemand, marker: dict[str, Any]) -> RemoteCompletion:
    summary = marker.get("summary") if isinstance(marker.get("summary"), dict) else {}
    return RemoteCompletion(
        demand_id=str(demand.id),
        status="completed",
        created=int(summary.get("created") or 0),
        reused=int(summary.get("reused") or 0),
        invalid=int(summary.get("invalid") or 0),
        claim_ids=[str(value) for value in (summary.get("claim_ids") or [])][:MAX_CLAIMS_PER_SPAN],
        candidate_ids=[str(value) for value in (summary.get("candidate_ids") or [])][:12],
        idempotent_replay=True,
    )


@transaction.atomic
def complete_remote_demand(
    demand_id,
    *,
    executor_id: str,
    lease_token,
    completion_id: str,
    result: dict[str, Any],
) -> RemoteCompletion:
    demand = (
        CapabilityDemand.objects.select_for_update(of=("self",))
        .select_related("claimed_by")
        .get(pk=demand_id)
    )
    payload = dict(demand.payload or {})
    fingerprint = result_fingerprint(result)
    marker = payload.get(COMPLETION_MARKER_KEY)
    if demand.state == CapabilityDemand.State.COMPLETED and isinstance(marker, dict):
        if marker.get("completion_id") == completion_id and marker.get("result_hash") == fingerprint:
            return _completion_from_marker(demand, marker)
        raise RemoteWorkerProtocolError(
            "completion_conflict",
            "This demand was already completed with a different result.",
            status_code=409,
        )
    if (
        demand.state != CapabilityDemand.State.CLAIMED
        or demand.claimed_by is None
        or demand.claimed_by.executor_id != executor_id
        or str(demand.lease_token) != str(lease_token)
    ):
        raise RemoteWorkerProtocolError(
            "lease_not_active",
            "The demand lease is no longer active.",
            status_code=409,
        )
    if demand.lease_expires_at is None or demand.lease_expires_at <= timezone.now():
        raise RemoteWorkerProtocolError(
            "lease_expired",
            "The demand lease has expired.",
            status_code=409,
        )
    prompt = _immutable_prompt(payload)
    provider, model, model_revision = _model_identity(demand.claimed_by, demand, result)
    task_kind = str(payload.get("task_kind") or "")
    if task_kind == "claim_extraction":
        span = _claim_span(demand)
        claims = result.get("claims")
        if not isinstance(claims, list) or len(claims) > MAX_CLAIMS_PER_SPAN:
            raise RemoteWorkerProtocolError(
                "invalid_claim_result",
                f"claims must be an array with at most {MAX_CLAIMS_PER_SPAN} items.",
            )
        persisted = persist_claim_candidates(
            span,
            claims,
            prompt_key=prompt["key"],
            prompt_version=prompt["version"],
            provider=provider,
            model=model,
            model_revision=model_revision,
            prompt_content_hash=prompt["content_hash"],
            prompt_schema_hash=prompt["schema_hash"],
            prompt_registry_id=prompt.get("registry_id") or "",
            prompt_registry_version=prompt.get("registry_version"),
            prompt_source=prompt.get("source") or "code_baseline",
        )
        if persisted.get("status") != "completed":
            raise RemoteWorkerProtocolError(
                str(persisted.get("error_code") or "claim_persistence_failed"),
                "The claim result could not be attached to current evidence.",
                status_code=409,
            )
        claim_ids = [str(value) for value in (persisted.get("claim_ids") or [])]
        candidate_ids: list[str] = []
    elif task_kind == "library_synthesis":
        _library_synthesis_pack(demand)
        try:
            persisted = persist_library_synthesis_candidate(
                demand,
                result,
                provider=provider,
                model=model,
                model_revision=model_revision,
            )
        except ValueError as exc:
            raise RemoteWorkerProtocolError(
                "invalid_library_synthesis_result",
                str(exc),
                status_code=409,
            ) from exc
        claim_ids = []
        candidate_ids = [str(persisted["candidate_id"])]
    else:
        raise RemoteWorkerProtocolError(
            "unsupported_task_kind",
            "The remote worker cannot complete this demand type.",
            status_code=409,
        )
    completed = complete_demand(
        demand.id,
        lease_token,
        executor_id=executor_id,
    )
    summary = {
        "created": int(persisted.get("created") or 0),
        "reused": int(persisted.get("reused") or 0),
        "invalid": int(persisted.get("invalid") or 0),
        "claim_ids": claim_ids,
        "candidate_ids": candidate_ids,
    }
    completed_payload = dict(completed.payload or {})
    completed_payload[COMPLETION_MARKER_KEY] = {
        "completion_id": completion_id,
        "result_hash": fingerprint,
        "executor_id": executor_id,
        "completed_at": timezone.now().isoformat(),
        "summary": summary,
    }
    completed.payload = completed_payload
    completed.save(update_fields=["payload", "updated_at"])
    return RemoteCompletion(
        demand_id=str(completed.id),
        status="completed",
        created=summary["created"],
        reused=summary["reused"],
        invalid=summary["invalid"],
        claim_ids=summary["claim_ids"],
        candidate_ids=summary["candidate_ids"],
        idempotent_replay=False,
    )
