from __future__ import annotations

from django.db.models import Count

from catalog.models import IntelligenceFeedback


def record_intelligence_feedback(
    *,
    reviewer,
    task_profile_key: str,
    candidate_type: str,
    candidate_id: str,
    decision: str,
    task_profile_version: int = 1,
    provider: str = "",
    model: str = "",
    prompt_key: str = "",
    prompt_version: str = "",
    original_payload: dict | None = None,
    edited_payload: dict | None = None,
    field_key: str = "",
    expertise: list | None = None,
) -> IntelligenceFeedback:
    if not reviewer or not getattr(reviewer, "is_authenticated", False):
        raise PermissionError("人工反馈必须记录真实 Editor。")
    if decision not in IntelligenceFeedback.Decision.values:
        raise ValueError("未知的人工反馈决定。")
    feedback, _ = IntelligenceFeedback.objects.update_or_create(
        candidate_type=candidate_type,
        candidate_id=str(candidate_id),
        reviewed_by=reviewer,
        defaults={
            "task_profile_key": task_profile_key,
            "task_profile_version": task_profile_version,
            "provider": provider,
            "model": model,
            "prompt_key": prompt_key,
            "prompt_version": prompt_version,
            "decision": decision,
            "original_payload": dict(original_payload or {}),
            "edited_payload": dict(edited_payload or {}),
            "field_key": field_key,
            "expertise": list(expertise or []),
        },
    )
    return feedback


def feedback_calibration_snapshot() -> list[dict]:
    rows = (
        IntelligenceFeedback.objects.values("task_profile_key", "provider", "prompt_key", "decision")
        .annotate(total=Count("id"))
        .order_by("task_profile_key", "provider", "prompt_key", "decision")
    )
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row["task_profile_key"], row["provider"], row["prompt_key"])
        bucket = grouped.setdefault(
            key,
            {
                "task_profile_key": key[0],
                "provider": key[1],
                "prompt_key": key[2],
                "decisions": {},
                "total": 0,
            },
        )
        count = int(row["total"])
        bucket["decisions"][row["decision"]] = count
        bucket["total"] += count
    output = []
    for bucket in grouped.values():
        accepted = bucket["decisions"].get(IntelligenceFeedback.Decision.ACCEPT, 0)
        accepted += bucket["decisions"].get(IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT, 0)
        bucket["acceptance_rate"] = accepted / bucket["total"] if bucket["total"] else None
        output.append(bucket)
    return output

