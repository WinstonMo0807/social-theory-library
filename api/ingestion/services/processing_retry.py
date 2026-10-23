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


def selected_ocr_remaining(stats, remaining):
    selection = stats.get("retry_selection") or {}
    if selection.get("state") != "active":
        return remaining
    selected = set(selection.get("page_indexes") or [])
    return [index for index in remaining if index in selected]
