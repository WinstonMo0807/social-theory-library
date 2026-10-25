"""Bounded failed-page selection, without changing a task's original targets."""


def failed_ocr_pages(job):
    if job.job_type != "ocr" or job.status != "failed":
        return []
    stats = job.stats or {}
    completed = {index for index in (stats.get("completed_page_indexes") or []) if type(index) is int}
    targets = stats.get("requested_page_indexes")
    targets = {index for index in targets if type(index) is int} if isinstance(targets, list) else None
    count = stats.get("total_pages") or (job.asset.page_count if job.asset_id else 0)
    return sorted({index for index in (stats.get("active_page_indexes") or [])
                   if type(index) is int and type(count) is int and 1 <= index <= count
                   and index not in completed and (targets is None or index in targets)})


def failed_page_listing(job, expected_version, page):
    from rest_framework.exceptions import ValidationError
    from catalog.services.editorial_issues import EditConflict
    from .processing_commands import task_version
    version = task_version(job)
    if version != expected_version:
        raise EditConflict("任务记录已变化，请重新读取任务并核对中断页。")
    indexes = failed_ocr_pages(job)
    page_size = 200
    pages = max(1, (len(indexes) + page_size - 1) // page_size)
    if type(page) is not int or not 1 <= page <= pages:
        raise ValidationError({"page": "页码超出当前中断页列表，请重新读取。"})
    return {"job_id": str(job.pk), "version": version, "count": len(indexes),
            "page": page, "pages": pages, "page_size": page_size,
            "results": indexes[(page - 1) * page_size:page * page_size]}


def selected_ocr_remaining(stats, remaining):
    selection = stats.get("retry_selection") or {}
    if selection.get("state") != "active":
        return remaining
    selected = set(selection.get("page_indexes") or [])
    return [index for index in remaining if index in selected]
