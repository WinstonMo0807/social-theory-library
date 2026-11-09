"""Server-side protocol helpers for opportunistic pull workers.

The remote worker only leases derived work. PostgreSQL remains authoritative
for demand state, evidence provenance and curation artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import CapabilityDemand, CapabilityExecutor
from common.task_runtime import DemandLease, complete_demand


REMOTE_TASK_KINDS = frozenset({"document_structure", "curation_stage"})
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
    artifact_ids: list[str] = field(default_factory=list)

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
            "artifact_ids":self.artifact_ids,
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


def build_remote_job(lease: DemandLease) -> dict[str, Any]:
    demand = CapabilityDemand.objects.get(pk=lease.demand_id)
    payload = dict(demand.payload or {})
    if payload.get("task_kind") == "curation_stage":
        from catalog.services.intelligence_remote import remote_job
        from rest_framework.exceptions import APIException
        try: return remote_job(demand)
        except APIException as exc: raise RemoteWorkerProtocolError("curation_source_changed",str(exc),status_code=409) from exc
    if payload.get("task_kind") == "document_structure":
        from catalog.services.document_structure import structure_job,DOCLING_VERSION
        from rest_framework.exceptions import APIException
        try: job,revision=structure_job(demand)
        except APIException as exc: raise RemoteWorkerProtocolError("structure_source_changed",str(exc),status_code=409) from exc
        job.status="running";job.started_at=timezone.now();job.save(update_fields=["status","started_at","updated_at"])
        return {"task_kind":"document_structure","input":{"source_checksum":revision.source_checksum,
            "pages":job.stats["input"]["pages"],"revision_id":str(revision.pk)},
            "parser_version":DOCLING_VERSION,"source_path":f"demands/{demand.pk}/source/"}
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
    if demand.payload.get("task_kind") == "curation_stage":
        from catalog.services.intelligence_remote import remote_job
        from rest_framework.exceptions import APIException
        try: runtime=remote_job(demand)["runtime"]
        except APIException as exc: raise RemoteWorkerProtocolError("curation_source_changed",str(exc),status_code=409) from exc
        declared={**runtime,"revision":runtime["model_revision"]}
    elif demand.payload.get("task_kind") == "document_structure":
        from catalog.services.document_structure import DOCLING_VERSION
        declared={"provider":"docling","model":"layout","revision":DOCLING_VERSION}
    else:
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
            "Provider, model and revision are required for artifact provenance.",
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
            "Provider, model and revision are required for artifact provenance.",
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
        claim_ids=[str(value) for value in (summary.get("claim_ids") or [])][:24],
        candidate_ids=[str(value) for value in (summary.get("candidate_ids") or [])][:12],
        idempotent_replay=True,
        artifact_ids=[str(value) for value in summary.get("artifact_ids",[])],
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
    task_kind = str(payload.get("task_kind") or "")
    if task_kind not in REMOTE_TASK_KINDS:
        raise RemoteWorkerProtocolError("knowledge_producer_retired","旧知识生成协议已停止写回，请使用策展阶段任务。",status_code=409)
    provider, model, model_revision = _model_identity(demand.claimed_by, demand, result)
    artifact_ids=[]
    if task_kind == "curation_stage":
        from catalog.services.intelligence_remote import complete_stage
        from rest_framework.exceptions import APIException
        try: artifact=complete_stage(demand,result)
        except APIException as exc: raise RemoteWorkerProtocolError("invalid_curation_result",str(exc),status_code=409) from exc
        persisted={"created":1};claim_ids=[];candidate_ids=[];artifact_ids=[str(artifact.pk)]
    elif task_kind == "document_structure":
        from catalog.services.document_structure import complete_structure
        from rest_framework.exceptions import APIException
        try:
            parsed=result.get("parsed")
            if not isinstance(parsed,dict):
                raise RemoteWorkerProtocolError("invalid_structure_result","Missing parsed structure.")
            elapsed=result.get("elapsed_ms",0)
            if type(elapsed) is not int or elapsed < 0:
                raise RemoteWorkerProtocolError("invalid_structure_result","Invalid execution duration.")
            structure=complete_structure(demand,parsed,elapsed_ms=elapsed,executor_id=executor_id)
        except APIException as exc:
            raise RemoteWorkerProtocolError("invalid_structure_result",str(exc),status_code=409) from exc
        persisted={"created":1};claim_ids=[];candidate_ids=[];artifact_ids=[str(structure.pk)]
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
        "artifact_ids":artifact_ids,
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
        artifact_ids=artifact_ids,
    )
