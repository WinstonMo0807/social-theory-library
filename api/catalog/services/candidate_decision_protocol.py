from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


CANDIDATE_DECISION_PROTOCOL_VERSION = "candidate-decision-protocol-v1"


@dataclass(frozen=True, slots=True)
class CandidateActionSpec:
    key: str
    label: str
    method: str
    evidence_mode: str = "none"
    minimum_evidence_count: int = 0


ACTION_SPECS: dict[str, CandidateActionSpec] = {
    "inspect": CandidateActionSpec("inspect", "查看依据", "CLIENT"),
    "apply_to_draft": CandidateActionSpec("apply_to_draft", "采用到草稿", "CLIENT"),
    # Temporary alias for 3.0/3.0.1 clients.  Remove after every shipped
    # Workbench bundle consumes ``apply_to_draft``.
    "apply_draft": CandidateActionSpec("apply_draft", "采用到草稿", "CLIENT"),
    "use_value": CandidateActionSpec("use_value", "采用规范文本", "CLIENT"),
    "verify": CandidateActionSpec("verify", "核实此结果", "POST", "source_document"),
    "accept": CandidateActionSpec("accept", "采用", "POST", "verified_evidence", 1),
    "accept_with_edit": CandidateActionSpec(
        "accept_with_edit", "修改后采用", "POST", "verified_evidence", 1
    ),
    "reject": CandidateActionSpec("reject", "拒绝 / 不采用", "POST"),
    "defer": CandidateActionSpec("defer", "稍后处理", "POST"),
    "reopen": CandidateActionSpec("reopen", "重新纳入", "POST"),
    "link_existing": CandidateActionSpec("link_existing", "关联已有实体", "POST"),
    "create_draft": CandidateActionSpec(
        "create_draft", "创建实体草稿", "POST", "verified_evidence", 1
    ),
    "keep_unresolved": CandidateActionSpec(
        "keep_unresolved", "仅保留为责任者", "POST"
    ),
    "match_existing": CandidateActionSpec(
        "match_existing", "匹配已有实体", "POST", "verified_evidence", 1
    ),
}


def _endpoint_for_action(
    action: str,
    *,
    decision_url: str,
    verify_url: str,
) -> str | None:
    if action == "inspect":
        return None
    if action == "verify":
        return verify_url or None
    return decision_url or None


def describe_candidate_actions(
    available_actions: Iterable[str],
    *,
    decision_url: str | None = None,
    verify_url: str | None = None,
    evidence_count: int = 0,
    evidence_status: str = "",
    action_payloads: dict[str, dict[str, Any]] | None = None,
    action_options: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Describe existing candidate actions without changing decision semantics.

    The domain services remain authoritative for validation and mutation.  This
    function only makes their current UI contract explicit and keeps the legacy
    ``available_actions`` and ``decision_url`` fields usable during migration.
    """

    normalized_actions = list(
        dict.fromkeys(str(value or "").strip() for value in available_actions if str(value or "").strip())
    )
    count = max(0, int(evidence_count or 0))
    status = str(evidence_status or "").strip().casefold()
    output: list[dict[str, Any]] = []
    for action in normalized_actions:
        spec = ACTION_SPECS.get(action) or CandidateActionSpec(
            action,
            action.replace("_", " "),
            "POST",
        )
        endpoint = _endpoint_for_action(
            action,
            decision_url=str(decision_url or ""),
            verify_url=str(verify_url or ""),
        )
        endpoint_available = spec.method == "CLIENT" or bool(endpoint)
        requirement_satisfied = (
            spec.minimum_evidence_count <= count
            and not (
                spec.evidence_mode == "verified_evidence"
                and status in {"lead_only", "research_lead", "search_snippet"}
            )
        )
        available = endpoint_available and requirement_satisfied
        unavailable_reason = ""
        if not endpoint_available:
            unavailable_reason = "当前聚合响应没有为该操作提供端点。"
        elif not requirement_satisfied:
            unavailable_reason = "当前证据要求尚未满足。"
        descriptor = {
                "key": spec.key,
                "label": spec.label,
                "endpoint": endpoint,
                "method": spec.method,
                "payload": dict((action_payloads or {}).get(action) or {}),
                "availability": {
                    "available": available,
                    "reason": unavailable_reason,
                },
                "evidence_requirement": {
                    "mode": spec.evidence_mode,
                    "minimum_count": spec.minimum_evidence_count,
                    "satisfied": requirement_satisfied,
                },
            }
        options = dict((action_options or {}).get(action) or {})
        for key in ("label", "editable", "value_field", "tone"):
            if key in options:
                descriptor[key] = options[key]
        output.append(descriptor)
    return output


def attach_candidate_action_descriptors(payload: dict[str, Any]) -> dict[str, Any]:
    payload["action_protocol_version"] = CANDIDATE_DECISION_PROTOCOL_VERSION
    payload["action_descriptors"] = describe_candidate_actions(
        payload.get("available_actions") or ["inspect"],
        decision_url=payload.get("decision_url"),
        verify_url=payload.get("verify_url"),
        evidence_count=int(payload.get("evidence_count") or 0),
        evidence_status=str(payload.get("evidence_status") or ""),
        action_payloads=payload.get("action_payloads") or {},
        action_options=payload.get("action_options") or {},
    )
    return payload


def action_spec_payload() -> list[dict[str, Any]]:
    return [asdict(spec) for spec in ACTION_SPECS.values()]
