"""Editorial source inspection over the same publication and retrieval services."""
from time import monotonic

from django.db.models import Count, Q
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from catalog import models as m
from catalog.services.knowledge_core import require_editor
from catalog.services.knowledge_sources import require_revision_access, create_anchor, locator
from catalog.services.discovery_projection import active_generation, DiscoveryIndexError, meili
from catalog.services.publication_eligibility import public_editions


def source_directory(actor, *, query="", work_id=None, revision_id=None):
    require_editor(actor)
    rows = m.DocumentRevision.objects.select_related("asset__edition__work").order_by("-created_at")
    rows = rows.filter(pk=revision_id) if revision_id else rows.filter(is_active=True)
    if work_id:
        rows = rows.filter(asset__edition__work_id=work_id)
    if query:
        rows = rows.filter(asset__edition__work__title__icontains=query)
    revisions = list(rows[:200])
    generation = active_generation()
    index_error = ""
    if generation:
        cache_key = f"knowledge:index-presence:{generation.pk}"
        present = cache.get(cache_key)
        if present is None:
            try:
                meili("GET", f"/indexes/{generation.uid}/stats", timeout=3)
                present = True
            except DiscoveryIndexError:
                present = False
            cache.set(cache_key, present, 10)
        if not present:
            index_error = "检索服务当前没有可读取的活动索引，请到搜索维护检查。"
    counts = {(str(r["document_revision_id"]), r["source_revision"]): r for r in m.DiscoveryDocument.objects.filter(
        generation=generation, document_revision_id__in=[r.pk for r in revisions], channel="passages")
        .values("document_revision_id", "source_revision").annotate(total=Count("pk"), keywords=Count("pk", filter=Q(keyword_ready=True)),
            vectors=Count("pk", filter=Q(vector_ready=True)))} if generation else {}
    published = {e.pk: e for e in public_editions().filter(pk__in=[r.asset.edition_id for r in revisions])
        .select_related("active_catalog_revision")}
    states = {str(s.source_id): s for s in m.DiscoverySourceState.objects.filter(generation=generation,
        source_type="edition", source_id__in=published).select_related("job")} if generation else {}
    runs, structures, structure_jobs, sync_jobs = {}, {}, {}, {}
    keys = [r.pk for r in revisions]
    outlines=dict(m.DocumentOutlineRevision.objects.filter(document_revision_id__in=keys,is_active=True).values_list("document_revision_id","pk"))
    for run in m.CurationRun.objects.filter(document_revision_id__in=keys).only("id", "status", "document_revision_id").order_by("-created_at"):
        runs.setdefault(run.document_revision_id, run)
    for structure in m.DocumentStructure.objects.filter(document_revision_id__in=keys).only("id", "coverage", "document_revision_id","outline_revision_id").order_by("-created_at"):
        if structure.outline_revision_id==outlines.get(structure.document_revision_id):
            structures.setdefault(structure.document_revision_id, structure)
    from ingestion.models import ProcessingJob
    for job in ProcessingJob.objects.filter(job_type="logical_structure",asset_id__in=[r.asset_id for r in revisions]).order_by("-created_at"):
        sync_jobs.setdefault(job.stats.get("revision_id"),job)
    for job in ProcessingJob.objects.filter(job_type="document_structure",asset_id__in=[r.asset_id for r in revisions]).order_by("-created_at"):
        structure_jobs.setdefault(job.stats.get("input",{}).get("revision_id"),job)
    output = []
    for revision in revisions:
        asset = revision.asset
        edition = asset.edition
        public = published.get(edition.pk)
        active = bool(public and public.active_catalog_revision.document_revision_id == revision.pk
            and public.active_catalog_revision.reader_asset_id == asset.pk)
        state = states.get(str(edition.pk))
        expected = state.expected_count if state else 0
        # Counts from a retained or partial index alone never mean a version is searchable.
        from catalog.services.discovery_sources import edition_revision
        current_hash = edition_revision(public.active_catalog_revision_id, revision.pk, revision.text_checksum, asset.access_status) if active else None
        count = counts.get((str(revision.pk), current_hash), {})
        indexed = bool(active and state and state.source_revision == current_hash and state.indexed_at and not state.error and expected > 0
            and state.completed_count == expected and count.get("keywords", 0) >= expected)
        run, structure = runs.get(revision.pk), structures.get(revision.pk)
        structure_job = structure_jobs.get(str(revision.pk))
        sync_job=sync_jobs.get(str(revision.pk))
        output.append({"revision_id": str(revision.pk), "asset_id": str(asset.pk), "edition_id": str(edition.pk),
            "work_id": str(edition.work_id), "title": edition.work.title, "edition_label": edition.version_label,
            "revision_number": revision.revision, "pages": asset.page_count,
            "readable": asset.status == "ready" and bool(asset.file), "published": active,
            "keywords": "unavailable" if index_error else "ready" if indexed else "partial" if count.get("keywords") else "pending",
            "semantic": "unavailable" if index_error else "ready" if indexed and count.get("vectors") == count.get("keywords") else "partial" if count.get("vectors") else "pending",
            "index_counts": {**count, "expected": expected}, "index_error": index_error or (state.error if state else ""),
            "index_job": {"id": str(state.job_id), "status": state.job.status} if state and state.job else None,
            "curation": {"id": str(run.pk), "status": run.status} if run else None,
            "structure_id": str(structure.pk) if structure else None,
            "structure_coverage": structure.coverage if structure else {},
            "sync_job":{"id":str(sync_job.pk),"status":sync_job.status,"error":sync_job.error_message} if sync_job else None,
            "structure_job": {"id":str(structure_job.pk),"status":structure_job.status,"error":structure_job.error_message,
                "pages":structure_job.stats.get("input",{}).get("pages")} if structure_job else None,
            "reader_url": f"/reader/{asset.pk}?revision={revision.pk}&preview=1",
            "work_url": f"/works/{public.public_slug}" if public and public.public_slug else None,
            "catalog_url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}",
            "outline_url": f"/admin/library/assets/{asset.pk}/outline",
            "ocr_url": f"/admin/library/assets/{asset.pk}/ocr"})
    return {"sources": output, "limit": 200, "index_id": str(generation.pk) if generation else None}


def inspect_retrieval(actor, query, *, revision_id=None, mode="hybrid"):
    require_editor(actor)
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 1200 or mode not in {"keyword", "hybrid"}:
        raise ValidationError("请输入2至1200字的检索问题，并选择关键词或混合检索。")
    from catalog.services.retrieval.search import retrieve_channel
    from catalog.services.discovery_sessions import _public_row
    from catalog.services.semantic_search import viewer_access_statuses
    filters = {"_keyword_only": mode == "keyword"}
    if revision_id:
        revision = get_object_or_404(m.DocumentRevision.objects.select_related("asset__edition"), pk=revision_id)
        require_revision_access(revision, actor, editorial=True)
        if not public_editions(require_fulltext=True).filter(pk=revision.asset.edition_id,
                active_catalog_revision__document_revision=revision).exists():
            return {"status": "unpublished", "results": [], "warnings": [{"code": "unpublished", "message": "此正文修订尚未发布，读者检索不会使用它。可在原文页检查正文。"}], "elapsed_ms": 0}
        filters.update(_asset_id=str(revision.asset_id), work_ids=[str(revision.asset.edition.work_id)])
    started = monotonic()
    # Inspect the signed-in reader scope, not an administrator-only wider corpus.
    result = retrieve_channel(query.strip(), "passages", filters, viewer_access_statuses(authenticated=True), limit=40)
    codes = {v["code"] for v in result["warnings"]}
    if "keyword_unavailable" in codes and (mode == "keyword" or "dense_unavailable" in codes):
        raise DiscoveryIndexError("search_unavailable", "检索服务请求失败。问题和筛选已保留，请重试或检查搜索维护。")
    status = "waiting_index" if codes & {"index_pending", "scope_index_pending", "coverage_pending"} else "ready"
    return {"status": status, "results": [_public_row(r) for r in result["rows"]], "warnings": result["warnings"],
        "elapsed_ms": round((monotonic() - started) * 1000), "mode": mode, "index_id": result["version"],
        "coverage": "returned_results_only"}


def verify_selection(actor, revision_id, segments):
    require_editor(actor)
    revision = get_object_or_404(m.DocumentRevision, pk=revision_id)
    require_revision_access(revision, actor, editorial=True)
    anchor = create_anchor(revision, segments)
    return locator(anchor, actor, editorial=True)
