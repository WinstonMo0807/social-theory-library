from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
import json
import logging
from typing import Any
from uuid import uuid4

from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import Edition, ResearchRun
from catalog.services.field_enrichment import FieldEnrichmentRequest, FieldEnrichmentService
from catalog.services.workflow_suggestions import WorkflowSuggestionAggregator
from ingestion.models import EntityResolutionCandidate, SourceRecord, UploadItem
from ingestion.services.entity_resolution_decisions import available_resolution_actions

from .context import RESEARCH_CONTEXT_VERSION, ResearchContext, build_research_context
from .contracts import (
    RESEARCH_CONTRACT_VERSION,
    RESEARCH_CONTRACTS,
    ResearchImplementation,
    contract_payload,
    validate_contract_coverage,
)
from .diagnostics import ResearchDiagnostics, ResearchErrorCode
from .entity_discovery import EntityDiscoveryRequest, UniversalEntityDiscovery
from .planner import RESEARCH_PLANNER_VERSION, ResearchPlanner


logger = logging.getLogger(__name__)
RESEARCH_ORCHESTRATOR_VERSION = "research-orchestrator-v2"
MAX_ENTITY_QUERIES = 6
MAX_BACKGROUND_STEPS = 3

INTAKE_REVIEW_TARGETS = {
    "person": ("person", {}),
    "work": ("work", {}),
    "knowledge_node": ("knowledge_node", {"node_type": "concept"}),
    "theory": ("knowledge_node", {"node_type": "theory_tradition"}),
    "concept": ("knowledge_node", {"node_type": "concept"}),
    "debate": ("knowledge_node", {"node_type": "debate"}),
    "topic": ("knowledge_node", {"node_type": "topic"}),
    "discipline": ("knowledge_node", {"node_type": "discipline"}),
    "subdiscipline": ("knowledge_node", {"node_type": "subdiscipline"}),
    "organization": ("organization", {"organization_type": "other"}),
    "publisher": ("publisher", {}),
}

RESEARCH_ALLOWED_RESOLUTION_ACTIONS = "research_allowed_resolution_actions"


def _research_resolution_actions(contract) -> list[str]:
    """Return the intake decisions allowed by one exact field contract."""

    actions = ["link_existing"]
    if contract.allow_create_draft:
        actions.append("create_draft")
    actions.extend(["keep_unresolved", "reject"])
    return actions


def _constrain_background_discovery_payload(
    payload: dict[str, Any],
    *,
    contract,
) -> dict[str, Any]:
    """Keep background discovery actions inside the exact field contract."""

    constrained = dict(payload or {})
    results = []
    for source_row in constrained.get("results") or []:
        if not isinstance(source_row, dict):
            continue
        row = dict(source_row)
        actions = list(
            dict.fromkeys(
                str(value).strip()
                for value in row.get("available_actions") or []
                if str(value).strip()
            )
        )
        if not contract.allow_create_draft:
            actions = [value for value in actions if value != "create_draft"]
        row["available_actions"] = actions or ["inspect"]
        results.append(row)
    constrained["results"] = results
    constrained["multiple_candidates"] = len(results) > 1
    return constrained


def _resolution_actions_for_research_field(field_name: str) -> list[str]:
    try:
        step, field = str(field_name or "").split(".", 1)
        contract = RESEARCH_CONTRACTS.get(step, field)
    except (TypeError, ValueError):
        # A malformed or obsolete research field must never gain draft creation.
        return ["keep_unresolved", "reject"]
    return _research_resolution_actions(contract)


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _research_candidate_key(
    *,
    entity_type: str,
    target_type: str,
    field_name: str,
    row: dict[str, Any],
) -> str:
    stable_source = {
        "provider": row.get("provider"),
        "source_url": row.get("source_url"),
        "external_ids": row.get("external_ids") or {},
    }
    if stable_source["source_url"] or stable_source["external_ids"]:
        # Web result identifiers contain a rank suffix. The URL and provider
        # remain stable when the same result moves between search positions.
        source_identity = _stable_json(stable_source)
    else:
        source_identity = str(row.get("id") or "").strip() or _stable_json(
            {
                **stable_source,
                "label": row.get("label"),
            }
        )
    return sha256(
        f"{entity_type}:{target_type}:{field_name}:{source_identity}".encode("utf-8")
    ).hexdigest()


def _context_from_snapshot(value: dict[str, Any]) -> ResearchContext:
    allowed = {
        "work_id",
        "edition_id",
        "upload_item_id",
        "document_type",
        "active_step",
        "persisted_data",
        "draft_data",
        "confirmed_entities",
        "unresolved_entities",
        "accepted_candidates",
        "rejected_candidates",
        "field_locks",
        "pdf_ocr_signals",
        "workflow_status",
        "canonical_revision",
        "draft_session_id",
        "draft_hash",
        "trigger_input_values",
        "trigger_input_hash",
        "workflow_gaps",
        "changed_fields",
        "fingerprint",
        "version",
    }
    payload = {key: row for key, row in dict(value or {}).items() if key in allowed}
    payload["changed_fields"] = tuple(payload.get("changed_fields") or [])
    return ResearchContext(**payload)


def _candidate_payload(candidate) -> dict[str, Any]:
    evidence = list(candidate.evidence_records.filter(is_current=True).values(
        "source_record_id",
        "source_url",
        "canonical_url",
        "source_title",
        "source_class",
        "provider",
        "supporting_text",
        "locator",
        "retrieved_at",
        "content_checksum",
        "confidence",
        "extraction_method",
    )[:12])
    return {
        "id": str(candidate.id),
        "kind": "enrichment",
        "target_type": candidate.target_type,
        "target_id": str(candidate.target_id),
        "field": candidate.field_name,
        "proposed_value": candidate.proposed_value,
        "current_value": candidate.current_value,
        "status": candidate.status,
        "confidence": candidate.confidence,
        "confidence_factors": candidate.confidence_factors,
        "identity_status": candidate.identity_status,
        "identity_evidence": candidate.identity_evidence,
        "conflicts": candidate.conflicts,
        "source_class": candidate.source_class,
        "evidence": evidence,
        "evidence_count": len(evidence),
        "available_actions": ["inspect", "accept", "reject"] if candidate.status == "pending" else ["inspect"],
        "human_confirmation_required": True,
    }


class ResearchOrchestrator:
    def __init__(
        self,
        *,
        planner: ResearchPlanner | None = None,
        entity_discovery: UniversalEntityDiscovery | None = None,
        enrichment_service: FieldEnrichmentService | None = None,
    ):
        self.planner = planner or ResearchPlanner()
        self.entity_discovery = entity_discovery or UniversalEntityDiscovery()
        self.enrichment_service = enrichment_service or FieldEnrichmentService()

    @staticmethod
    def _validate_runtime_contracts() -> dict[str, Any]:
        coverage = validate_contract_coverage()
        missing: list[str] = []
        try:
            from catalog.services.field_enrichment.policies import FIELD_POLICIES

            for contract in RESEARCH_CONTRACTS.all():
                if (
                    contract.field == contract.canonical_field
                    and contract.research_enabled
                    and contract.implementation == ResearchImplementation.FIELD_ENRICHMENT
                ):
                    try:
                        FIELD_POLICIES.get(str(contract.target_type), contract.enrichment_field)
                    except ValueError:
                        missing.append(f"{contract.step}.{contract.field}")
        except Exception as exc:
            missing.append(f"field_policy_registry:{exc.__class__.__name__}")
        coverage["missing_implementations"] = missing
        coverage["healthy"] = not missing
        if missing and settings.DEBUG:
            raise RuntimeError(f"Research implementation coverage invalid missing={missing}")
        return coverage

    @staticmethod
    def _idempotency_key(
        *,
        edition_id: str,
        context_fingerprint: str,
        trigger: str,
        mode: str,
        force: bool,
    ) -> str:
        nonce = str(uuid4()) if force else "stable"
        return sha256(
            f"{RESEARCH_ORCHESTRATOR_VERSION}:{edition_id}:{context_fingerprint}:{trigger}:{mode}:{nonce}".encode()
        ).hexdigest()

    @staticmethod
    def _dispatch_research_run(run_id: str, task_id: str) -> None:
        from catalog.tasks import execute_research_run

        try:
            execute_research_run.apply_async(args=[run_id], task_id=task_id)
        except Exception as exc:
            logger.exception(
                "research run dispatch failed",
                extra={"research_run_id": run_id, "research_task_id": task_id},
            )
            now = timezone.now()
            with transaction.atomic():
                run = (
                    ResearchRun.objects.select_for_update(of=("self",))
                    .filter(
                        pk=run_id,
                        task_id=task_id,
                        status=ResearchRun.Status.QUEUED,
                    )
                    .first()
                )
                if run is None:
                    return
                diagnostics = dict(run.diagnostics or {})
                errors = list(diagnostics.get("errors") or [])
                errors.append(
                    {
                        "code": "research_dispatch_failed",
                        "detail": "研究任务未能提交到 Celery，未执行任何外部研究。",
                        "provider": "celery",
                    }
                )
                diagnostics["errors"] = errors
                run.status = ResearchRun.Status.FAILED
                run.diagnostics = diagnostics
                run.error_code = "research_dispatch_failed"
                run.error_message = f"{exc.__class__.__name__}: 研究任务派发失败。"
                run.finished_at = now
                run.save(
                    update_fields=[
                        "status",
                        "diagnostics",
                        "error_code",
                        "error_message",
                        "finished_at",
                        "updated_at",
                    ]
                )

    def prepare(
        self,
        edition: Edition,
        *,
        item: UploadItem | None = None,
        active_step: str,
        draft_data: dict[str, Any] | None = None,
        changed_fields: list[str] | tuple[str, ...] | None = None,
        trigger: str = ResearchRun.Trigger.AUTO_LOAD,
        mode: str = "full",
        actor=None,
        force: bool = False,
        dispatch: bool = True,
        include_background: bool = True,
        draft_session_id: str = "",
    ) -> tuple[ResearchRun, bool]:
        if trigger not in ResearchRun.Trigger.values:
            raise ValueError("未知 Research trigger。")
        if item is not None and item.edition_id != edition.id:
            raise ValueError("UploadItem 与 Edition 不属于同一研究上下文。")
        mode = str(mode or "full").strip().casefold()
        if mode not in {"structured", "web", "full"}:
            raise ValueError("Research mode 必须是 structured、web 或 full。")
        coverage = self._validate_runtime_contracts()
        context = build_research_context(
            edition,
            item=item,
            active_step=active_step,
            draft_data=draft_data,
            changed_fields=changed_fields,
            draft_session_id=draft_session_id,
        )
        context, tasks = self.planner.plan(context, include_background=include_background)
        plan = [row.payload() for row in tasks]
        key = self._idempotency_key(
            edition_id=str(edition.id),
            context_fingerprint=context.fingerprint,
            trigger=trigger,
            mode=mode,
            force=force,
        )

        aggregator = WorkflowSuggestionAggregator(edition, item=item)
        active_query = next((row.query for row in tasks if row.step == context.active_step and row.query), None)
        local_workflow = aggregator.aggregate(step=context.active_step, query=active_query)
        local_entities = []
        for task in tasks:
            if task.implementation != ResearchImplementation.ENTITY_DISCOVERY or not task.query:
                continue
            for entity_type in task.entity_types:
                local_entities.append(
                    self.entity_discovery.discover(
                        EntityDiscoveryRequest(
                            entity_type=entity_type,
                            field=f"{task.step}.{task.field}",
                            query=task.query,
                            context=context,
                            include_external=False,
                            include_web=False,
                            limit=12,
                        )
                    )
                )
            if len(local_entities) >= MAX_ENTITY_QUERIES:
                break
        diagnostics = ResearchDiagnostics(
            context_revision=context.fingerprint,
            active_step=context.active_step,
            changed_fields=list(context.changed_fields),
        )
        diagnostics.generated_queries = list(dict.fromkeys(row.query for row in tasks if row.query))
        diagnostics.providers_attempted = ["local", "query_lexicon", "pdf"]
        diagnostics.candidate_counts["local_workflow"] = len(local_workflow.get("suggestions") or [])
        diagnostics.candidate_counts["local_entities"] = sum(len(row.get("results") or []) for row in local_entities)
        if coverage.get("missing_implementations"):
            diagnostics.add_error(
                ResearchErrorCode.CONTRACT_MISSING,
                ", ".join(coverage["missing_implementations"]),
            )
        dispatch_task_id = str(uuid4()) if tasks and dispatch else ""
        defaults = {
            "work_id": edition.work_id,
            "edition_id": edition.id,
            "upload_item_id": item.id if item else None,
            "requested_by": actor if getattr(actor, "is_authenticated", False) else None,
            "trigger": trigger,
            "status": ResearchRun.Status.QUEUED if tasks else ResearchRun.Status.COMPLETED,
            "context_fingerprint": context.fingerprint,
            "canonical_revision": context.canonical_revision,
            "draft_session_id": context.draft_session_id,
            "draft_hash": context.draft_hash,
            "trigger_input_values": context.trigger_input_values,
            "trigger_input_hash": context.trigger_input_hash,
            "is_current": True,
            "context_version": RESEARCH_CONTEXT_VERSION,
            "contract_version": RESEARCH_CONTRACT_VERSION,
            "planner_version": RESEARCH_PLANNER_VERSION,
            "active_step": context.active_step,
            "changed_fields": list(context.changed_fields),
            "context_snapshot": context.payload(),
            "plan": plan,
            "local_results": {"workflow": local_workflow, "entities": local_entities},
            "external_results": {},
            "diagnostics": {**diagnostics.payload(), "mode": mode, "coverage": coverage},
            "task_id": dispatch_task_id,
            "finished_at": timezone.now() if not tasks else None,
        }
        should_dispatch = False
        with transaction.atomic():
            prior_same_context = ResearchRun.objects.select_for_update(of=("self",)).filter(
                idempotency_key=key
            ).first()
            if prior_same_context is not None and not prior_same_context.is_current:
                key = sha256(f"{key}:reactivated:{uuid4()}".encode()).hexdigest()
            run, created = ResearchRun.objects.get_or_create(
                idempotency_key=key,
                defaults=defaults,
            )
            if created:
                self._supersede_affected_runs(run)
                # The first aggregate happens before the new run can mark prior
                # draft-bound candidates stale. Refresh inside the same
                # transaction so the response never advertises candidates from
                # a superseded draft snapshot.
                refreshed_workflow = aggregator.aggregate(
                    step=context.active_step,
                    query=active_query,
                )
                if refreshed_workflow != local_workflow:
                    local_workflow = refreshed_workflow
                    run.local_results = {
                        "workflow": local_workflow,
                        "entities": local_entities,
                    }
                    run_diagnostics = dict(run.diagnostics or {})
                    candidate_counts = dict(run_diagnostics.get("candidate_counts") or {})
                    candidate_counts["local_workflow"] = len(
                        local_workflow.get("suggestions") or []
                    )
                    run_diagnostics["candidate_counts"] = candidate_counts
                    run.diagnostics = run_diagnostics
                    run.save(update_fields=["local_results", "diagnostics", "updated_at"])
            if tasks and dispatch:
                if created:
                    should_dispatch = True
                elif run.status == ResearchRun.Status.QUEUED and not str(run.task_id or "").strip():
                    dispatch_task_id = str(uuid4())
                    claimed = ResearchRun.objects.filter(
                        pk=run.pk,
                        status=ResearchRun.Status.QUEUED,
                        task_id="",
                    ).update(task_id=dispatch_task_id, updated_at=timezone.now())
                    if claimed:
                        run.task_id = dispatch_task_id
                        should_dispatch = True
                    else:
                        run.refresh_from_db()
                if should_dispatch:
                    transaction.on_commit(
                        lambda run_id=str(run.id), task_id=dispatch_task_id: self._dispatch_research_run(
                            run_id,
                            task_id,
                        )
                    )
        if should_dispatch:
            run.refresh_from_db()
        return run, created

    @staticmethod
    def _plan_fields(plan: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> set[str]:
        return {
            f"{row.get('step')}.{row.get('field')}"
            for row in plan or []
            if isinstance(row, dict) and row.get("step") and row.get("field")
        }

    @staticmethod
    def _plan_by_field(plan: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> dict[str, dict[str, Any]]:
        return {
            f"{row.get('step')}.{row.get('field')}": row
            for row in plan or []
            if isinstance(row, dict) and row.get("step") and row.get("field")
        }

    @classmethod
    def _overlapping_inputs_changed(cls, current: ResearchRun, previous: ResearchRun) -> bool:
        current_plan = cls._plan_by_field(list(current.plan or []))
        previous_plan = cls._plan_by_field(list(previous.plan or []))
        overlap = set(current_plan) & set(previous_plan)
        if not overlap:
            return False
        if dict(current.canonical_revision or {}) != dict(previous.canonical_revision or {}):
            return True
        for field_name in overlap:
            current_task = current_plan[field_name]
            previous_task = previous_plan[field_name]
            if (
                "trigger_input_values" in current_task
                and "trigger_input_values" in previous_task
            ):
                if _stable_json(current_task.get("trigger_input_values") or {}) != _stable_json(
                    previous_task.get("trigger_input_values") or {}
                ):
                    return True
            elif current.trigger_input_hash != previous.trigger_input_hash:
                # Compatibility for 3.0.0 plans that predate per-task trigger
                # snapshots. Their global hash is conservative but safe.
                return True
        return False

    @classmethod
    def _supersede_affected_runs(cls, current: ResearchRun) -> None:
        """Invalidate only prior runs whose planned outputs overlap this draft change."""

        affected = cls._plan_fields(list(current.plan or []))
        if not affected:
            return
        queryset = (
            ResearchRun.objects.select_for_update(of=("self",))
            .filter(edition_id=current.edition_id, is_current=True)
            .exclude(pk=current.pk)
            .order_by("created_at")
        )
        if current.draft_session_id:
            # 3.0.0 ResearchRun rows have no draft session.  Include them in
            # the first 3.0.1 comparison so old title/person candidates cannot
            # survive a new unsaved draft merely because the legacy column was
            # backfilled as an empty string.
            queryset = queryset.filter(
                Q(draft_session_id=current.draft_session_id)
                | Q(draft_session_id="")
            )
        elif current.requested_by_id:
            queryset = queryset.filter(requested_by_id=current.requested_by_id)
        stale_run_ids: list[str] = []
        now = timezone.now()
        for previous in queryset:
            if not (affected & cls._plan_fields(list(previous.plan or []))):
                continue
            if not cls._overlapping_inputs_changed(current, previous):
                continue
            previous.status = ResearchRun.Status.SUPERSEDED
            previous.is_current = False
            previous.superseded_by = current
            previous.superseded_at = now
            previous.stale_reason = "未保存草稿或触发输入已变化。"
            previous.finished_at = previous.finished_at or now
            previous.save(
                update_fields=[
                    "status",
                    "is_current",
                    "superseded_by",
                    "superseded_at",
                    "stale_reason",
                    "finished_at",
                    "updated_at",
                ]
            )
            stale_run_ids.append(str(previous.id))

        if not stale_run_ids:
            return
        # Automatically generated candidates remain auditable, but cannot be
        # adopted after their draft context has been superseded.
        from catalog.models import EnrichmentCandidate

        for candidate in EnrichmentCandidate.objects.select_for_update().filter(
            Q(target_type=EnrichmentCandidate.TargetType.WORK, target_id=current.work_id)
            | Q(target_type=EnrichmentCandidate.TargetType.EDITION, target_id=current.edition_id),
            status=EnrichmentCandidate.Status.PENDING,
        ):
            candidate_run = str((candidate.request_context or {}).get("research_run_id") or "")
            if candidate_run in stale_run_ids:
                request_context = dict(candidate.request_context or {})
                request_context["is_current_context"] = False
                request_context["stale_reason"] = "未保存草稿或触发输入已变化。"
                candidate.status = EnrichmentCandidate.Status.SUPERSEDED
                candidate.request_context = request_context
                candidate.save(update_fields=["status", "request_context", "updated_at"])
        for candidate in EntityResolutionCandidate.objects.select_for_update().filter(
            upload_item_id=current.upload_item_id,
            status=EntityResolutionCandidate.Status.PROPOSED,
        ):
            candidate_run = str((candidate.supporting_properties or {}).get("research_run_id") or "")
            if candidate_run in stale_run_ids:
                properties = dict(candidate.supporting_properties or {})
                properties["stale_reason"] = "未保存草稿或触发输入已变化。"
                properties["is_current_context"] = False
                candidate.status = EntityResolutionCandidate.Status.STALE
                candidate.supporting_properties = properties
                candidate.save(update_fields=["status", "supporting_properties", "updated_at"])

    def retry_failed(
        self,
        failed_run: ResearchRun,
        *,
        retry_key: str,
        actor=None,
        dispatch: bool = True,
    ) -> tuple[ResearchRun, bool]:
        """Create one bounded Celery-owned retry for an exact failed run.

        Recovery uses the persisted context and plan instead of executing the
        failed row inline. This keeps external work under the Research Celery
        task's soft and hard time limits.
        """

        stable_retry_key = str(retry_key or "").strip()
        if not stable_retry_key:
            raise ValueError("Research retry 缺少幂等键。")
        idempotency_key = sha256(
            f"{RESEARCH_ORCHESTRATOR_VERSION}:retry:{failed_run.id}:{stable_retry_key}".encode()
        ).hexdigest()
        plan = list(failed_run.plan or [])
        dispatch_task_id = str(uuid4()) if plan and dispatch else ""
        previous_diagnostics = dict(failed_run.diagnostics or {})
        retry_diagnostics = {
            "mode": str(previous_diagnostics.get("mode") or "full"),
            "coverage": previous_diagnostics.get("coverage") or {},
            "retry_of": str(failed_run.id),
            "retry_key": stable_retry_key,
        }
        defaults = {
            "work_id": failed_run.work_id,
            "edition_id": failed_run.edition_id,
            "upload_item_id": failed_run.upload_item_id,
            "requested_by_id": (
                actor.pk
                if getattr(actor, "is_authenticated", False)
                else failed_run.requested_by_id
            ),
            "trigger": ResearchRun.Trigger.HEALTH,
            "status": ResearchRun.Status.QUEUED if plan else ResearchRun.Status.COMPLETED,
            "context_fingerprint": failed_run.context_fingerprint,
            "canonical_revision": dict(failed_run.canonical_revision or {}),
            "draft_session_id": failed_run.draft_session_id,
            "draft_hash": failed_run.draft_hash,
            "trigger_input_values": dict(failed_run.trigger_input_values or {}),
            "trigger_input_hash": failed_run.trigger_input_hash,
            "is_current": failed_run.is_current,
            "context_version": failed_run.context_version,
            "contract_version": failed_run.contract_version,
            "planner_version": failed_run.planner_version,
            "active_step": failed_run.active_step,
            "changed_fields": list(failed_run.changed_fields or []),
            "context_snapshot": dict(failed_run.context_snapshot or {}),
            "plan": plan,
            "local_results": dict(failed_run.local_results or {}),
            "external_results": {},
            "diagnostics": retry_diagnostics,
            "task_id": dispatch_task_id,
            "finished_at": timezone.now() if not plan else None,
        }
        should_dispatch = False
        with transaction.atomic():
            source = ResearchRun.objects.select_for_update(of=("self",)).get(pk=failed_run.pk)
            if source.status != ResearchRun.Status.FAILED:
                raise ValueError("只有 failed ResearchRun 可以重试。")
            if not source.is_current:
                raise ValueError("草稿上下文已经变化，不能重试过期 ResearchRun。")
            run, created = ResearchRun.objects.get_or_create(
                idempotency_key=idempotency_key,
                defaults=defaults,
            )
            should_dispatch = created and bool(plan) and dispatch
            if should_dispatch:
                transaction.on_commit(
                    lambda run_id=str(run.id), task_id=dispatch_task_id: self._dispatch_research_run(
                        run_id,
                        task_id,
                    )
                )
        if should_dispatch:
            run.refresh_from_db()
        return run, created

    @staticmethod
    def _person_queries(context: ResearchContext, fallback: str) -> list[str]:
        output = []
        for contributor in (context.draft_data.get("contributors") or {}).get("items") or []:
            if isinstance(contributor, dict):
                value = str(contributor.get("display_name") or "").strip()
                if value:
                    output.append(value)
        if fallback:
            output.append(fallback)
        return list(dict.fromkeys(output))[:MAX_ENTITY_QUERIES]

    def _run_enrichment(
        self,
        *,
        run: ResearchRun,
        context: ResearchContext,
        tasks: list[dict[str, Any]],
        mode: str,
        actor,
        diagnostics: ResearchDiagnostics,
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for task in tasks:
            contract = RESEARCH_CONTRACTS.canonical(task["step"], task["field"])
            if contract.implementation != ResearchImplementation.FIELD_ENRICHMENT:
                continue
            target_id = context.work_id if contract.target_type == "work" else context.edition_id
            grouped[(str(contract.target_type), target_id)].append({"contract": contract, "task": task})
        output = []
        for (target_type, target_id), rows in grouped.items():
            all_fields = tuple(dict.fromkeys(row["contract"].enrichment_field for row in rows))
            for offset in range(0, len(all_fields), 12):
                fields = all_fields[offset : offset + 12]
                form_context = {
                    "research_context": context.payload(),
                    "research_queries": list(dict.fromkeys(row["task"].get("query") for row in rows if row["task"].get("query"))),
                    "active_step": context.active_step,
                    "research_run_id": str(run.id),
                    "research_context_fingerprint": context.fingerprint,
                    "research_draft_session_id": context.draft_session_id,
                    "research_draft_hash": context.draft_hash,
                    "research_trigger_input_hash": context.trigger_input_hash,
                    "is_current_context": True,
                }
                result = self.enrichment_service.enrich(
                    FieldEnrichmentRequest(
                        target_type=target_type,
                        target_id=target_id,
                        field_names=fields,
                        form_context=form_context,
                        requested_mode=mode,
                        visibility="admin",
                    ),
                    actor=actor,
                )
                diagnostics.providers_attempted.extend(["structured", "searxng", "safe_web_fetcher"])
                result_key = f"{target_type}.enrichment"
                diagnostics.query_result_counts[result_key] = (
                    diagnostics.query_result_counts.get(result_key, 0)
                    + len(result.candidates)
                )
                for error in result.errors:
                    diagnostics.add_error(error.code, error.detail, field_name=error.field_name, provider=error.provider)
                output.extend(_candidate_payload(candidate) for candidate in result.candidates)
        return output

    def _run_entity_discovery(
        self,
        *,
        context: ResearchContext,
        tasks: list[dict[str, Any]],
        diagnostics: ResearchDiagnostics,
    ) -> list[dict[str, Any]]:
        output = []
        seen: set[tuple[str, str, str]] = set()
        for task in tasks:
            contract = RESEARCH_CONTRACTS.get(task["step"], task["field"])
            if contract.implementation not in {
                ResearchImplementation.ENTITY_DISCOVERY,
                ResearchImplementation.EDITORIAL_DISCOVERY,
            }:
                continue
            base_query = str(task.get("query") or "").strip()
            queries = self._person_queries(context, base_query) if "person" in contract.entity_types else [base_query]
            for entity_type in contract.entity_types:
                for query in queries:
                    if not query:
                        continue
                    key = (entity_type, query.casefold(), f"{task['step']}.{task['field']}")
                    if key in seen:
                        continue
                    seen.add(key)
                    payload = self.entity_discovery.discover(
                        EntityDiscoveryRequest(
                            entity_type=entity_type,
                            field=f"{task['step']}.{task['field']}",
                            query=query,
                            context=context,
                            include_external=True,
                            include_web=True,
                            limit=12,
                        )
                    )
                    payload = _constrain_background_discovery_payload(
                        payload,
                        contract=contract,
                    )
                    diagnostics.providers_attempted.extend(payload.get("providers_attempted") or [])
                    diagnostics.searxng_called = diagnostics.searxng_called or "searxng" in (payload.get("providers_attempted") or [])
                    diagnostics.query_result_counts[f"{entity_type}:{query}"] = len(payload.get("results") or [])
                    for error in payload.get("warnings") or []:
                        diagnostics.add_error(
                            str(error.get("code") or "provider_unavailable"),
                            str(error.get("detail") or ""),
                            field_name=f"{task['step']}.{task['field']}",
                            provider="entity_discovery",
                        )
                    output.append(payload)
                    if len(output) >= MAX_ENTITY_QUERIES:
                        return output
        return output

    @staticmethod
    def _persist_intake_entity_candidates(
        *,
        run: ResearchRun | None = None,
        context: ResearchContext | None = None,
        item: UploadItem | None,
        groups: list[dict[str, Any]],
    ) -> None:
        if item is None:
            return
        if run is not None and context is None:
            raise ValueError("ResearchRun candidate persistence requires its exact ResearchContext.")
        with transaction.atomic():
            if run is not None:
                locked_run = ResearchRun.objects.select_for_update(of=("self",)).filter(
                    pk=run.pk,
                    is_current=True,
                    status=ResearchRun.Status.RUNNING,
                    context_fingerprint=context.fingerprint,
                    draft_hash=context.draft_hash,
                    trigger_input_hash=context.trigger_input_hash,
                ).first()
                if locked_run is None:
                    return
            locked_item = UploadItem.objects.select_for_update(of=("self",)).get(pk=item.pk)
            existing_rows = list(
                EntityResolutionCandidate.objects.select_for_update(of=("self",))
                .filter(upload_item=locked_item)
                .order_by("created_at")
            )
            by_research_key: dict[str, EntityResolutionCandidate] = {}
            for existing in existing_rows:
                existing_key = str(
                    (existing.supporting_properties or {}).get("research_candidate_key") or ""
                ).strip()
                if existing_key:
                    by_research_key.setdefault(existing_key, existing)

            for payload in groups:
                entity_type = str(payload.get("entity_type") or "").strip().casefold()
                target_config = INTAKE_REVIEW_TARGETS.get(entity_type)
                if target_config is None:
                    continue
                target_type, target_defaults = target_config
                field_name = str(payload.get("field") or "")
                for row in payload.get("results") or []:
                    if row.get("candidate_group") not in {"authority", "external_web", "unresolved"}:
                        continue
                    label = str(row.get("label") or "").strip()[:500]
                    if not label:
                        continue
                    research_key = _research_candidate_key(
                        entity_type=entity_type,
                        target_type=target_type,
                        field_name=field_name,
                        row=row,
                    )
                    if context is not None:
                        context_identity = (
                            context.fingerprint
                            if run is not None
                            else context.draft_hash
                        )
                        research_key = sha256(
                            f"{research_key}:{context_identity}".encode("utf-8")
                        ).hexdigest()
                    candidate = by_research_key.get(research_key)

                    source_record = None
                    if row.get("source_record_id"):
                        try:
                            source_record = SourceRecord.objects.filter(pk=row["source_record_id"]).first()
                        except (TypeError, ValueError):
                            source_record = None
                    context_properties = {}
                    if context is not None:
                        context_properties = {
                            "research_context_fingerprint": context.fingerprint,
                            "research_draft_session_id": context.draft_session_id,
                            "research_draft_hash": context.draft_hash,
                            "research_trigger_input_hash": context.trigger_input_hash,
                            "is_current_context": True,
                        }
                    if run is not None:
                        context_properties["research_run_id"] = str(run.id)
                    properties = {
                        **target_defaults,
                        "research_field": field_name,
                        "research_candidate_id": str(row.get("id") or ""),
                        "research_candidate_key": research_key,
                        "candidate_group": row.get("candidate_group"),
                        "provider": row.get("provider"),
                        "source_url": row.get("source_url"),
                        "evidence_status": row.get("evidence_status"),
                        **context_properties,
                        RESEARCH_ALLOWED_RESOLUTION_ACTIONS: _resolution_actions_for_research_field(
                            field_name
                        ),
                    }
                    if target_type == "organization":
                        properties["organization_role"] = (
                            "degree_granting"
                            if field_name.endswith("degree_institution")
                            else "report_issuer"
                            if field_name.endswith("report_institution")
                            else "issuing_body"
                        )
                    preview_data = {
                        "secondary_identity": row.get("secondary_identity"),
                        "source": row.get("source"),
                        "source_url": row.get("source_url"),
                        "evidence": row.get("evidence") or [],
                    }
                    if candidate is None:
                        candidate = EntityResolutionCandidate.objects.create(
                            upload_item=locked_item,
                            source_record=source_record,
                            target_type=target_type,
                            source_name=label,
                            candidate_entity_type=f"{target_type}_draft",
                            label=label,
                            aliases=list((row.get("metadata") or {}).get("aliases") or []),
                            external_ids=dict(row.get("external_ids") or {}),
                            supporting_properties=properties,
                            match_score=float(row.get("confidence") or 0),
                            match_reasons=list(row.get("match_reasons") or []),
                            conflicts=list(row.get("conflicts") or []),
                            preview_data=preview_data,
                        )
                        by_research_key[research_key] = candidate
                    elif candidate.status == EntityResolutionCandidate.Status.PROPOSED:
                        candidate.source_record = source_record or candidate.source_record
                        candidate.aliases = list(
                            (row.get("metadata") or {}).get("aliases")
                            or candidate.aliases
                            or []
                        )
                        candidate.external_ids = dict(row.get("external_ids") or candidate.external_ids or {})
                        previous_properties = dict(candidate.supporting_properties or {})
                        preserve_verified_evidence = (
                            previous_properties.get("evidence_status")
                            in {"verified_text", "web_evidence", "external_evidence"}
                            and properties.get("evidence_status")
                            in {None, "", "none", "lead_only", "searching"}
                        )
                        if preserve_verified_evidence:
                            properties["evidence_status"] = previous_properties["evidence_status"]
                            properties["candidate_group"] = previous_properties.get(
                                "candidate_group", properties.get("candidate_group")
                            )
                            for key in (
                                "source_url",
                                "evidence_provider",
                                "evidence_source_class",
                                "verified_at",
                            ):
                                if previous_properties.get(key):
                                    properties[key] = previous_properties[key]
                            # A later search pass is discovery metadata only. It
                            # must not erase previously fetched body evidence or
                            # the reason that made the candidate adoptable.
                            preview_data = {
                                **preview_data,
                                **dict(candidate.preview_data or {}),
                            }
                            match_reasons = list(
                                dict.fromkeys(
                                    [
                                        *(candidate.match_reasons or []),
                                        *(row.get("match_reasons") or []),
                                    ]
                                )
                            )
                        else:
                            match_reasons = list(
                                row.get("match_reasons") or candidate.match_reasons or []
                            )
                        candidate.supporting_properties = properties
                        candidate.match_score = max(candidate.match_score, float(row.get("confidence") or 0))
                        candidate.match_reasons = match_reasons
                        candidate.conflicts = list(row.get("conflicts") or candidate.conflicts or [])
                        candidate.preview_data = preview_data
                        candidate.save(update_fields=[
                            "source_record",
                            "aliases",
                            "external_ids",
                            "supporting_properties",
                            "match_score",
                            "match_reasons",
                            "conflicts",
                            "preview_data",
                            "updated_at",
                        ])
                    by_research_key[research_key] = candidate
                    row["review_candidate_id"] = str(candidate.id)
                    row["decision_url"] = f"/ingestion/items/{locked_item.id}/entity-resolution-candidates/{candidate.id}/decision/"
                    row["available_actions"] = ["inspect", *available_resolution_actions(candidate)]
                    row["review_status"] = candidate.status

    def _run_editorial_evidence(
        self,
        *,
        run: ResearchRun,
        edition: Edition,
        item: UploadItem | None,
        context: ResearchContext,
        tasks: list[dict[str, Any]],
        mode: str,
        actor,
        diagnostics: ResearchDiagnostics,
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for task in tasks:
            contract = RESEARCH_CONTRACTS.canonical(task["step"], task["field"])
            if contract.implementation == ResearchImplementation.EVIDENCE_ONLY:
                grouped[task["step"]].append(task)
        output = []
        aggregator = WorkflowSuggestionAggregator(edition, item=item)
        for step, rows in list(grouped.items())[:MAX_BACKGROUND_STEPS]:
            fields = list(dict.fromkeys(row["field"] for row in rows))
            query = next((str(row.get("query") or "").strip() for row in rows if row.get("query")), None)
            payload = aggregator.run_step(
                step=step,
                fields=fields,
                mode=mode,
                query=query,
                actor=actor,
                form_context={
                    **context.payload(),
                    "research_context": context.payload(),
                    "research_run_id": str(run.id),
                    "research_context_fingerprint": context.fingerprint,
                    "research_draft_session_id": context.draft_session_id,
                    "research_draft_hash": context.draft_hash,
                    "research_trigger_input_hash": context.trigger_input_hash,
                    "is_current_context": True,
                },
            )
            diagnostics.providers_attempted.extend(["searxng", "safe_web_fetcher"])
            diagnostics.searxng_called = diagnostics.searxng_called or bool((payload.get("run") or {}).get("web_queries"))
            for error in payload.get("errors") or []:
                diagnostics.add_error(
                    str(error.get("code") or "provider_unavailable"),
                    str(error.get("detail") or ""),
                    field_name=step,
                    provider="workflow_research",
                )
            output.append(payload)
        return output

    @staticmethod
    def _execution_queryset():
        return (
            ResearchRun.objects.select_for_update(of=("self",))
            .select_related("edition__work")
        )

    @staticmethod
    def _run_is_current(run: ResearchRun, context: ResearchContext) -> bool:
        return ResearchRun.objects.filter(
            pk=run.pk,
            is_current=True,
            status=ResearchRun.Status.RUNNING,
            context_fingerprint=context.fingerprint,
            draft_hash=context.draft_hash,
            trigger_input_hash=context.trigger_input_hash,
        ).exists()

    @staticmethod
    def _field_outcomes(tasks: list[dict[str, Any]], external: dict[str, Any]) -> list[dict[str, Any]]:
        found: set[str] = set()
        for candidate in external.get("enrichment") or []:
            field_name = str(candidate.get("field") or "")
            target_type = str(candidate.get("target_type") or "")
            step = "work" if target_type == "work" else "bibliography" if target_type == "edition" else ""
            if step and field_name:
                found.add(f"{step}.{field_name}")
        for payload in external.get("entities") or []:
            if payload.get("results"):
                found.add(str(payload.get("field") or ""))
        for payload in external.get("editorial_evidence") or []:
            for candidate in payload.get("suggestions") or []:
                step = str(candidate.get("step") or "")
                field_name = str(candidate.get("field_name") or candidate.get("field") or "")
                if step and field_name:
                    found.add(f"{step}.{field_name}")
        outcomes = []
        for task in tasks:
            field_key = f"{task.get('step')}.{task.get('field')}"
            outcomes.append(
                {
                    "field": field_key,
                    "status": "candidates_available" if field_key in found else "no_reliable_candidate",
                    "reason": "" if field_key in found else str(
                        task.get("no_reliable_candidate_reason")
                        or "证据数量或质量未达到当前字段要求。"
                    ),
                    "context_fingerprint": task.get("context_fingerprint"),
                }
            )
        return outcomes

    def execute(self, run_id: str, *, task_id: str = "") -> ResearchRun:
        expected_task_id = str(task_id or "").strip()
        with transaction.atomic():
            run = self._execution_queryset().get(pk=run_id)
            if run.status in {
                ResearchRun.Status.COMPLETED,
                ResearchRun.Status.DEGRADED,
                ResearchRun.Status.FAILED,
                ResearchRun.Status.CANCELED,
                ResearchRun.Status.SUPERSEDED,
            }:
                return run
            if not run.is_current:
                return run
            if expected_task_id and str(run.task_id or "").strip() != expected_task_id:
                return run
            if run.status != ResearchRun.Status.QUEUED:
                return run
            run.status = ResearchRun.Status.RUNNING
            run.started_at = run.started_at or timezone.now()
            run.error_code = ""
            run.error_message = ""
            run.save(update_fields=["status", "started_at", "error_code", "error_message", "updated_at"])

        context = _context_from_snapshot(run.context_snapshot)
        tasks = list(run.plan or [])
        diagnostics = ResearchDiagnostics(
            context_revision=context.fingerprint,
            active_step=context.active_step,
            changed_fields=list(context.changed_fields),
        )
        diagnostics.generated_queries = list(dict.fromkeys(str(row.get("query") or "") for row in tasks if row.get("query")))
        diagnostics.providers_attempted = ["local", "query_lexicon", "pdf"]
        mode = str((run.diagnostics or {}).get("mode") or "full")
        item = UploadItem.objects.filter(pk=run.upload_item_id).first() if run.upload_item_id else None
        external: dict[str, Any] = {"enrichment": [], "entities": [], "editorial_evidence": []}
        try:
            external["enrichment"] = self._run_enrichment(
                run=run,
                context=context,
                tasks=tasks,
                mode=mode,
                actor=run.requested_by,
                diagnostics=diagnostics,
            )
            if not self._run_is_current(run, context):
                return ResearchRun.objects.get(pk=run.pk)
            external["entities"] = self._run_entity_discovery(
                context=context,
                tasks=tasks,
                diagnostics=diagnostics,
            )
            if not self._run_is_current(run, context):
                return ResearchRun.objects.get(pk=run.pk)
            self._persist_intake_entity_candidates(
                run=run,
                context=context,
                item=item,
                groups=external["entities"],
            )
            external["editorial_evidence"] = self._run_editorial_evidence(
                run=run,
                edition=run.edition,
                item=item,
                context=context,
                tasks=tasks,
                mode=mode,
                actor=run.requested_by,
                diagnostics=diagnostics,
            )
            if not self._run_is_current(run, context):
                return ResearchRun.objects.get(pk=run.pk)
            refreshed = WorkflowSuggestionAggregator(run.edition, item=item).aggregate(step=context.active_step)
            external["active_step_candidates"] = refreshed
            external["field_outcomes"] = self._field_outcomes(tasks, external)
            diagnostics.candidate_counts = {
                "enrichment": len(external["enrichment"]),
                "entity_groups": len(external["entities"]),
                "entities": sum(len(row.get("results") or []) for row in external["entities"]),
                "active_step": len(refreshed.get("suggestions") or []),
            }
            diagnostics.providers_attempted = list(dict.fromkeys(diagnostics.providers_attempted))
            diagnostics.extracted_count = sum(diagnostics.candidate_counts.values())
            status_value = ResearchRun.Status.DEGRADED if diagnostics.errors else ResearchRun.Status.COMPLETED
            terminal_queryset = ResearchRun.objects.filter(
                pk=run.pk,
                status=ResearchRun.Status.RUNNING,
                is_current=True,
            )
            if expected_task_id:
                terminal_queryset = terminal_queryset.filter(task_id=expected_task_id)
            terminal_queryset.update(
                status=status_value,
                external_results=external,
                diagnostics={**diagnostics.payload(), "mode": mode},
                finished_at=timezone.now(),
                error_code="",
                error_message="",
                updated_at=timezone.now(),
            )
        except SoftTimeLimitExceeded:
            # The Celery task owns timeout semantics. It records a degraded
            # terminal state while preserving candidates already written.
            raise
        except Exception as exc:
            logger.exception("research run failed", extra={"research_run_id": str(run.id)})
            diagnostics.add_error("research_run_failed", str(exc)[:500])
            terminal_queryset = ResearchRun.objects.filter(
                pk=run.pk,
                status=ResearchRun.Status.RUNNING,
                is_current=True,
            )
            if expected_task_id:
                terminal_queryset = terminal_queryset.filter(task_id=expected_task_id)
            terminal_queryset.update(
                status=ResearchRun.Status.FAILED,
                external_results=external,
                diagnostics={**diagnostics.payload(), "mode": mode},
                error_code="research_run_failed",
                error_message=str(exc)[:2000],
                finished_at=timezone.now(),
                updated_at=timezone.now(),
            )
        return ResearchRun.objects.get(pk=run.pk)


def research_run_payload(run: ResearchRun, *, include_context: bool = False) -> dict[str, Any]:
    value = {
        "id": str(run.id),
        "version": RESEARCH_ORCHESTRATOR_VERSION,
        "status": run.status,
        "trigger": run.trigger,
        "work_id": str(run.work_id),
        "edition_id": str(run.edition_id),
        "upload_item_id": str(run.upload_item_id) if run.upload_item_id else None,
        "active_step": run.active_step,
        "changed_fields": run.changed_fields,
        "context_fingerprint": run.context_fingerprint,
        "canonical_revision": run.canonical_revision,
        "draft_session_id": run.draft_session_id,
        "draft_hash": run.draft_hash,
        "trigger_input_values": run.trigger_input_values,
        "trigger_input_hash": run.trigger_input_hash,
        "is_current": run.is_current,
        "superseded_by": str(run.superseded_by_id) if run.superseded_by_id else None,
        "superseded_at": run.superseded_at,
        "stale_reason": run.stale_reason,
        "context_version": run.context_version,
        "contract_version": run.contract_version,
        "planner_version": run.planner_version,
        "plan": run.plan,
        "local_results": run.local_results,
        "external_results": run.external_results,
        "diagnostics": run.diagnostics,
        "error": {"code": run.error_code, "message": run.error_message} if run.error_code else None,
        "task_id": run.task_id,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "human_confirmation_required": True,
        "contracts": [contract_payload(row) for row in RESEARCH_CONTRACTS.for_step(run.active_step)],
    }
    if include_context:
        value["context"] = run.context_snapshot
    return value
