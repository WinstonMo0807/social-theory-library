"""Presentation facts only; processing remains in its existing task services."""
from .processing_commands import task_actions, task_version
from .processing_identity import processing_edition
from .processing_recovery import recovery_state


def workspace_task(job, row, actor):
    row = dict(row)
    stats = row.pop("stats", {}) or {}
    edition = processing_edition(job)
    asset = job.asset if job.asset_id else None
    upload = getattr(job, "upload_item", None)
    file_asset = asset or (upload.asset if upload and upload.asset_id else None)
    heartbeat = getattr(job, "heartbeat_at", None)
    actions = task_actions(job, actor)
    recovery = recovery_state(job)
    recovery["can_recover"] = "recover" in actions
    ocr = row.get("ocr_progress")
    if ocr:
        if not ocr["can_resume"]: actions = [action for action in actions if action not in {"resume", "retry"}]
        if not ocr["can_cancel"] and row["status"] == "failed": actions = [action for action in actions if action != "cancel"]
    cover_id = edition.work.cover_rendition_id if edition else None
    counts = {key: value for key in ("target_pages", "processed_pages", "completed_pages", "total_pages", "failed_pages", "indexed_chunks", "failed_chunks", "completed_chunks", "total_chunks", "completed_units", "documents") if isinstance(value := stats.get(key), int) and not isinstance(value, bool) and value >= 0}
    failed_pages = sorted({page for page in (stats.get("active_page_indexes") or []) if type(page) is int and page > 0}) if ocr and job.status == "failed" else []
    unit = stats.get("active_unit") if row["job_type"] == "discovery_index" and job.status == "failed" else None
    failure_location = {key: unit.get(key) if type(unit.get(key)) is int and unit[key] >= (1 if key == "pdf_page" else 0) else None
                        for key in ("pdf_page", "start_offset", "end_offset")} if isinstance(unit, dict) else None
    return {**row, "version": task_version(job), "actions": actions, "pause_requested": bool(job.pause_requested_at),
            "file_id": str(file_asset.source_asset_id or file_asset.pk) if file_asset else None,
            "retry_url": f"/admin/processing?task_id={stats['retry_replacement_id']}&task_source={row['source']}" if stats.get("retry_replacement_id") else "",
            "partial": job.status == "partial" or bool(stats.get("partial")), "heartbeat_at": heartbeat,
            "failure_pages": failed_pages[:200], "failure_page_count": len(failed_pages), "failure_location": failure_location,
            "heartbeat_stale": job.status == "running" and recovery["state"] in {"recoverable", "delayed"},
            "recovery": recovery,
            "operation": "outline_rebuild" if stats.get("operation") == "outline_rebuild" else "",
            "can_export_results": row["source"] == "processing_job" and (row["job_type"] == "ocr" or stats.get("operation") == "outline_rebuild"
                or row["job_type"] == "discovery_index" and stats.get("action") == "source" and stats.get("source_type") == "edition"),
            "file": {"filename": row.get("source_filename", ""), "pages": asset.page_count if asset else None,
                     "bytes": asset.byte_size if asset else None, "is_current": asset.is_current if asset else None},
            "cover_url": f"/api/catalog/admin/media/renditions/{cover_id}/file/" if cover_id else "",
            "counts": counts, "permission_reason": "" if actions else ocr.get("resume_reason", "") if ocr else "当前状态没有可执行操作，请查看原处理入口。",
            "result_urls": {"ocr": f"/admin/library/assets/{ocr['source_asset_id'] if ocr and row['status'] == 'failed' and ocr.get('source_asset_id') else asset.pk}/ocr" if asset else "",
                            "outline": f"/admin/library/assets/{asset.pk}/outline" if asset else "",
                            "files": f"/admin/library/works/{edition.work_id}/files?edition={edition.pk}" if edition else "",
                            "index": "/admin/processing/semantic-index" if row["job_type"] in {"discovery_index", "semantic_index"} else ""}}
