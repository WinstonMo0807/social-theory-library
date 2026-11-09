"""Read-only history of retired concept suggestions; analysis starts in Intelligence."""
from catalog.services.editorial_issues import EditConflict
from .processing_identity import concept_review_url


def followup_state(job):
    if getattr(job, "job_type", "") != "ocr":
        return None
    stats = job.stats or {}
    counts = stats.get("theory_suggestions") or {}
    return {"enabled": False, "state": "disabled", "can_configure": False,
        "result_url": concept_review_url(job), "retry_url": "",
        "counts": {key: value for key, value in counts.items()
            if key in {"created", "updated", "new_node_tasks", "protected_nodes"} and type(value) is int and value >= 0}}


def configure_followup(job, *, enabled, actor):
    raise EditConflict("旧概念生成已退役。请从 Intelligence 选择原文版本与分析范围；已保存的识别结果保持。")


def run_concept_followup(job):
    # Old in-flight deliveries may still call this symbol. It never writes.
    return {"enabled": False, "retired": True, "created": 0, "next_url": concept_review_url(job)}
