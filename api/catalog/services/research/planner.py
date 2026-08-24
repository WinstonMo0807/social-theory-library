from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any

from .context import ResearchContext
from .contracts import RESEARCH_CONTRACTS, ResearchFieldContract
from .task_profiles import profile_key_for_contract, resolve_task_profile


RESEARCH_PLANNER_VERSION = "research-planner-v2"
MAX_RESEARCH_TASKS = 64


@dataclass(frozen=True)
class WorkflowGap:
    step: str
    field: str
    priority: int
    reason: str
    candidate_count: int
    blocking_state: str


@dataclass(frozen=True)
class ResearchTask:
    step: str
    field: str
    canonical_field: str
    priority: int
    query: str
    implementation: str
    entity_types: tuple[str, ...]
    providers: tuple[str, ...]
    reason: str
    changed_fields: tuple[str, ...]
    context_fingerprint: str
    contract_version: str
    task_profile_key: str
    task_profile_version: int
    retrieval_profile: str
    minimum_evidence_policy: dict[str, Any]
    prompt_key: str
    required_capability: str
    canonical_revision: dict[str, Any]
    draft_session_id: str
    draft_hash: str
    trigger_input_values: dict[str, Any]
    trigger_input_hash: str
    no_reliable_candidate_reason: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["entity_types"] = list(self.entity_types)
        value["providers"] = list(self.providers)
        value["changed_fields"] = list(self.changed_fields)
        return value


class WorkflowGapAnalyzer:
    def analyze(self, context: ResearchContext, *, candidate_counts: dict[str, int] | None = None) -> list[WorkflowGap]:
        counts = candidate_counts or {}
        steps = {
            str(row.get("key")): row
            for row in context.workflow_status.get("steps") or []
            if isinstance(row, dict)
        }
        gaps: list[WorkflowGap] = []
        for contract in RESEARCH_CONTRACTS.all():
            if contract.field != contract.canonical_field or not contract.research_enabled:
                continue
            step_state = steps.get(contract.step) or {}
            status = str(step_state.get("status") or "pending")
            issues = [row for row in step_state.get("issues") or [] if isinstance(row, dict)]
            field_issues = [row for row in issues if not row.get("field") or row.get("field") == contract.field]
            value = context.draft_value(contract.step, contract.field, None)
            empty = value in (None, "", [], {})
            if status in {"complete", "skipped"} and not field_issues and not empty:
                continue
            blocking = "blocker" if any(row.get("severity") == "blocker" for row in field_issues) else status
            priority = 100 if contract.step == context.active_step else 65
            if blocking == "blocker":
                priority += 20
            if field_issues:
                reason = str(field_issues[0].get("message") or "该字段仍有工作流问题。")
            elif empty:
                reason = "当前字段尚未确认，建议先补充可核对候选。"
            else:
                reason = "当前步骤尚未完成，建议核对已有值与候选。"
            gaps.append(
                WorkflowGap(
                    step=contract.step,
                    field=contract.field,
                    priority=min(priority, 120),
                    reason=reason,
                    candidate_count=int(counts.get(f"{contract.step}.{contract.field}", 0)),
                    blocking_state=blocking,
                )
            )

        for row in context.unresolved_entities:
            if row.get("entity_type") != "person" or not row.get("label"):
                continue
            gaps.append(
                WorkflowGap(
                    step="contributors",
                    field="contributors",
                    priority=120,
                    reason=f"责任者“{row['label']}”尚未关联正式 Person，建议优先确认身份。",
                    candidate_count=int(counts.get("contributors.contributors", 0)),
                    blocking_state="needs_identity",
                )
            )
        unique: dict[tuple[str, str, str], WorkflowGap] = {}
        for gap in gaps:
            key = (gap.step, gap.field, gap.reason)
            previous = unique.get(key)
            if previous is None or gap.priority > previous.priority:
                unique[key] = gap
        return sorted(unique.values(), key=lambda row: (-row.priority, row.step, row.field))[:40]


class ResearchPlanner:
    def __init__(self, *, gap_analyzer: WorkflowGapAnalyzer | None = None):
        self.gap_analyzer = gap_analyzer or WorkflowGapAnalyzer()

    @staticmethod
    def _text_values(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, dict):
            output = []
            for row in value.values():
                output.extend(ResearchPlanner._text_values(row))
            return output
        if isinstance(value, list):
            output = []
            for row in value:
                output.extend(ResearchPlanner._text_values(row))
            return output
        return []

    def _query(self, context: ResearchContext, contract: ResearchFieldContract) -> str:
        if contract.step == "contributors":
            contributors = (context.draft_data.get("contributors") or {}).get("items") or []
            names = [
                str(row.get("display_name") or "").strip()
                for row in contributors
                if isinstance(row, dict) and str(row.get("display_name") or "").strip()
            ]
            if names:
                return names[0]
        for changed in context.changed_fields:
            if changed not in contract.effective_trigger_inputs and changed != f"{contract.step}.{contract.field}":
                continue
            values = self._text_values(context.trigger_input_values.get(changed))
            if values:
                return values[0][:500]
        value = context.draft_value(contract.step, contract.field, None)
        values = self._text_values(value)
        if values:
            return values[0][:500]
        for path in contract.effective_trigger_inputs:
            values = self._text_values(context.trigger_input_values.get(path))
            if values:
                return values[0][:500]
        for step, field in (
            ("work", "title"),
            ("work", "original_title"),
            ("bibliography", "doi"),
            ("bibliography", "isbn13"),
            ("bibliography", "isbn"),
        ):
            candidate = context.draft_value(step, field, "")
            if str(candidate or "").strip():
                return str(candidate).strip()[:500]
        return ""

    @staticmethod
    def _paths_overlap(left: str, right: str) -> bool:
        return (
            left == right
            or left.startswith(f"{right}.")
            or right.startswith(f"{left}.")
        )

    @classmethod
    def _affected(cls, contract: ResearchFieldContract, changed_fields: tuple[str, ...]) -> bool:
        if not changed_fields:
            return True
        keys = {f"{contract.step}.{contract.field}", *contract.effective_trigger_inputs}
        return any(
            cls._paths_overlap(changed, key)
            for changed in changed_fields
            for key in keys
        )

    @staticmethod
    def _canonical_dependency_path(path: str) -> str:
        normalized = str(path or "").strip()
        if "." not in normalized:
            return normalized
        step, field = normalized.split(".", 1)
        if "." in field:
            return normalized
        try:
            contract = RESEARCH_CONTRACTS.get(step, field)
        except ValueError:
            return normalized
        return f"{contract.step}.{contract.canonical_field}"

    @classmethod
    def _expanded_dependency_paths(cls, changed_fields: tuple[str, ...]) -> tuple[str, ...]:
        """Resolve declared downstream fields without scheduling unrelated work."""

        expanded = {
            cls._canonical_dependency_path(value)
            for value in changed_fields
            if str(value or "").strip()
        }
        if not expanded:
            return ()
        while True:
            before = len(expanded)
            for contract in RESEARCH_CONTRACTS.all():
                keys = {f"{contract.step}.{contract.field}", *contract.effective_trigger_inputs}
                if not any(
                    cls._paths_overlap(path, key)
                    for path in expanded
                    for key in keys
                ):
                    continue
                expanded.update(
                    cls._canonical_dependency_path(path)
                    for path in contract.dependent_fields
                    if str(path or "").strip()
                )
            if len(expanded) == before:
                break
        return tuple(sorted(expanded))

    def plan(
        self,
        context: ResearchContext,
        *,
        candidate_counts: dict[str, int] | None = None,
        include_background: bool = True,
    ) -> tuple[ResearchContext, list[ResearchTask]]:
        gaps = self.gap_analyzer.analyze(context, candidate_counts=candidate_counts)
        gap_priority = {(row.step, row.field): row.priority for row in gaps}
        context = replace(context, workflow_gaps=[asdict(row) for row in gaps])
        affected_paths = self._expanded_dependency_paths(context.changed_fields)
        tasks = []
        for contract in RESEARCH_CONTRACTS.all():
            if contract.field != contract.canonical_field or not contract.research_enabled:
                continue
            if not self._affected(contract, affected_paths):
                continue
            if contract.step != context.active_step and not include_background and not context.changed_fields:
                continue
            query = self._query(context, contract)
            priority = 100 if contract.step == context.active_step else 45
            priority = max(priority, gap_priority.get((contract.step, contract.field), 0))
            contract_path = f"{contract.step}.{contract.field}"
            if any(
                self._paths_overlap(contract_path, path)
                for path in affected_paths
                if path not in context.changed_fields
            ):
                priority = max(priority, 110)
            providers = [
                *contract.local_catalog_sources,
                *contract.document_sources,
                *contract.authority_providers,
                *contract.external_providers,
            ]
            task_profile_key = contract.research_task_profile or profile_key_for_contract(
                step=contract.step,
                field=contract.field,
                implementation=contract.implementation,
            )
            task_profile = resolve_task_profile(task_profile_key)
            trigger_values = {
                path: context.trigger_input_values.get(path)
                for path in contract.effective_trigger_inputs
            }
            tasks.append(
                ResearchTask(
                    step=contract.step,
                    field=contract.field,
                    canonical_field=contract.canonical_field,
                    priority=priority,
                    query=query,
                    implementation=contract.implementation,
                    entity_types=contract.entity_types,
                    providers=tuple(dict.fromkeys(providers)),
                    reason=next(
                        (row.reason for row in gaps if row.step == contract.step and row.field == contract.field),
                        "当前步骤自动研究。" if contract.step == context.active_step else "后台预研究未完成步骤。",
                    ),
                    changed_fields=context.changed_fields,
                    context_fingerprint=context.fingerprint,
                    contract_version=contract.version,
                    task_profile_key=task_profile_key,
                    task_profile_version=int(task_profile.get("version") or 1),
                    retrieval_profile=str(task_profile.get("retrieval_profile") or "research_evidence"),
                    minimum_evidence_policy=dict(task_profile.get("minimum_evidence_policy") or {}),
                    prompt_key=str(task_profile.get("prompt_key") or ""),
                    required_capability=str(task_profile.get("required_capability") or ""),
                    canonical_revision=context.canonical_revision,
                    draft_session_id=context.draft_session_id,
                    draft_hash=context.draft_hash,
                    trigger_input_values=trigger_values,
                    trigger_input_hash=context.trigger_input_hash,
                    no_reliable_candidate_reason=contract.no_reliable_candidate_reason,
                )
            )
        tasks.sort(key=lambda row: (-row.priority, row.step, row.field, row.query))
        return context, tasks[:MAX_RESEARCH_TASKS]
