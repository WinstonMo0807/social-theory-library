"""Live catalogue labels for task displays; never persist a second book title."""
from catalog.models import EditorialRevision


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
    return edition_titles([edition for job in jobs if (edition := processing_edition(job)) is not None])


def draft_title_work_ids(query):
    return EditorialRevision.objects.filter(
        target_type="work", status="draft", materialized_preview__title__icontains=query,
    ).order_by().values_list("target_id", flat=True)


def processing_identity(job, titles=None):
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
