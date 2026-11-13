"""Read-only operational receipts for the existing compilation, not a scheduler."""
from collections import Counter


def run_metrics(run):
    stages = {}
    for row in run.artifacts.values("stage", "status", "unit", "usage", "elapsed_ms"):
        stage = stages.setdefault(row["stage"], {"artifacts":0, "statuses":Counter(),
            "known_model_calls":0, "unknown_model_call_units":0, "agent_responses":0,
            "reused_units":0, "recorded_elapsed_ms":0, "unmeasured_units":0})
        stage["artifacts"] += 1
        stage["statuses"][row["status"]] += 1
        usage = row["usage"] or {}
        calls = usage.get("model_calls")
        if type(calls) is int:
            stage["known_model_calls"] += calls
        else:
            stage["unknown_model_call_units"] += 1
        stage["agent_responses"] += usage.get("agent_responses", 0) or 0
        stage["reused_units"] += bool(usage.get("reused_from_artifact_id"))
        if row["elapsed_ms"]:
            stage["recorded_elapsed_ms"] += row["elapsed_ms"]
        elif usage.get("agent_responses") or calls is None or calls:
            stage["unmeasured_units"] += 1
    return {"scope":"current_artifact_receipts", "plan_version":run.plan_version,
        "stages":[{"stage":key, **value, "statuses":dict(value["statuses"])} for key,value in sorted(stages.items())],
        "timing_note":"产物回执的已记录耗时之和，不是整书总时长或纯模型速度；代理阅读与未记录尝试不能计为零。"}
