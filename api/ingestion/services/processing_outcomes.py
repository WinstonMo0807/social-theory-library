"""Visible partial results without changing the original worker lifecycle."""
from django.db.models import Case, CharField, F, Q, Value, When


# Only known stage warnings become user-facing issues; no raw provider errors,
# prompts or traces leave stats through this workspace projection.
STAGES = (
    ("theory_suggestion_warning", "概念对齐", "已有识别文字保留；请核对已生成的关系候选及原文证据。", "relations"),
    ("page_label_warning", "页码处理", "页码任务尚未成功登记，请从文件页核对页码及相关任务。", "files"),
    ("ocr_pdf_warning", "可搜索下载副本", "副本生成或部分文字定位未完整完成，请核对当前下载副本；独立识别文字保留。", "files"),
    ("front_matter_warning", "前附页候选", "封面及前附页候选未完整生成，请在材料工作台核对。", "workbench"),
    ("publication_place_warning", "出版地候选", "出版地候选提取未完成，请核对版本资料。", "workbench"),
    ("taxonomy_candidate_warning", "分类候选", "分类候选未完整保存，请核对材料分类。", "workbench"),
)


def workspace_status():
    """Shared by task counts and file-stage SQL, never changes stored status."""
    warnings = Q(stats__concept_alignment__state="failed")
    for key, *_ in STAGES:
        field = f"stats__{key}"
        present = Q(**{field + "__isnull": False}) & ~Q(**{field: ""}) & ~Q(**{field: None})
        if key == "theory_suggestion_warning":
            # A separately recorded successful follow-up supersedes an old warning.
            present &= Q(stats__concept_alignment__state__isnull=True) | ~Q(stats__concept_alignment__state__in=["completed", "skipped", "disabled"])
        warnings |= present
    return Case(When(Q(job_type="ocr", status="succeeded") & warnings, then=Value("failed")), default=F("status"), output_field=CharField())


def outcome_issues(job, *, files_url, workbench_url):
    if getattr(job, "job_type", "") != "ocr":
        return []
    stats = job.stats or {}
    alignment = (stats.get("concept_alignment") or {}).get("state")
    links = {"relations": "/admin/theories/relations", "files": files_url, "workbench": workbench_url}
    issues = []
    for key, label, message, destination in STAGES:
        present = isinstance(stats.get(key), str) and bool(stats[key])
        if key == "theory_suggestion_warning":
            present = alignment == "failed" or present and alignment not in {"completed", "skipped", "disabled"}
        if present:
            issues.append({"code": key, "label": label, "message": message, "url": links[destination]})
    return issues
