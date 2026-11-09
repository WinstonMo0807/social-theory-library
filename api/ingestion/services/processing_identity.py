"""Live catalogue labels for task displays; never persist a second book title."""
from uuid import UUID

from catalog.models import EditorialRevision, RecommendationIssue


def _issue_id(job):
    stats = job.stats if isinstance(job.stats, dict) else {}
    try:
        return str(UUID(str(stats.get("issue_id", ""))))
    except ValueError:
        return ""


def processing_edition(job):
    asset = job.asset if job.asset_id else None
    edition = asset.edition if asset else getattr(job, "edition", None)
    upload = getattr(job, "upload_item", None)
    if edition is None and upload is not None and upload.edition_id:
        edition = upload.edition
    return edition


def edition_titles(editions):
    titles = {str(edition.work_id): {"title": edition.work.title, "title_has_unpublished_changes": False} for edition in editions}
    seen = set()
    for revision in EditorialRevision.objects.filter(target_type="work", status="draft", target_id__in=list(titles)).order_by("target_id", "-revision"):
        work_id = str(revision.target_id)
        if work_id in seen:
            continue
        seen.add(work_id)
        title = (revision.materialized_preview or {}).get("title")
        if isinstance(title, str) and title.strip():
            titles[work_id] = {"title": title, "title_has_unpublished_changes": title != titles[work_id]["title"]}
    return titles


def task_titles(jobs):
    titles = edition_titles([edition for job in jobs if (edition := processing_edition(job)) is not None])
    issue_ids = {_issue_id(job) for job in jobs if getattr(job, "job_type", "") == "editorial_assistance"} - {""}
    titles.update({f"issue:{issue.pk}": {"title": issue.title} for issue in RecommendationIssue.objects.filter(pk__in=issue_ids)})
    return titles


def draft_title_work_ids(query):
    return EditorialRevision.objects.filter(
        target_type="work", status="draft", materialized_preview__title__icontains=query,
    ).order_by().values_list("target_id", flat=True)


def concept_review_url(job):
    if not job.asset_id:
        return ""
    return f"/admin/intelligence?work_id={job.asset.edition.work_id}"


def processing_identity(job, titles=None):
    if getattr(job, "job_type", "") == "editorial_assistance":
        issue_id = _issue_id(job)
        title = (titles if titles is not None else task_titles([job])).get(f"issue:{issue_id}", {}).get("title", "已移除的特别策划" if issue_id else "特别策划来源待核对")
        return {"title": title, "title_has_unpublished_changes": False, "edition_label": "特别策划候选",
                "edition_id": None, "work_id": None, "source_filename": "",
                "workbench_url": f"/admin/recommendations/issues/{issue_id}?assistant={job.pk}" if issue_id else ""}
    edition = processing_edition(job)
    upload = getattr(job, "upload_item", None)
    filename = upload.source_filename if upload else job.asset.original_filename if job.asset_id else ""
    version = " · ".join(str(part) for part in (
        edition.version_label, edition.publication_year, edition.publisher,
    ) if part) if edition else ""
    return {
        "title": edition.work.title if edition else filename or "未关联馆藏的处理记录",
        "title_has_unpublished_changes": False,
        **((titles or {}).get(str(edition.work_id), {}) if edition else {}),
        "edition_label": version or ("出版信息尚未填写" if edition else "尚未建立出版版本"),
        "edition_id": str(edition.pk) if edition else None,
        "work_id": str(edition.work_id) if edition else None,
        "source_filename": filename,
        "workbench_url": (
            f"/admin/library/works/{edition.work_id}?edition={edition.pk}#file" if edition
            else f"/admin/intake/{upload.pk}#file" if upload else ""
        ),
    }
