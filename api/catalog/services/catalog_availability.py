"""Request-scoped capability availability from existing revision/task records.

No file is opened, no service is probed, no task is dispatched and no private
reader record is inspected. Readiness and the age/scope of its evidence remain
separate. Publication commands and their immutable revisions remain authority.
"""
from collections import defaultdict
from uuid import UUID

from django.conf import settings
from django.db.models import Q, prefetch_related_objects
from django.utils import timezone

from catalog.models import (
    Asset, CatalogPublicationRevision, DocumentRevision, HealthCheckRun,
    KnowledgePublicationEvent, ProjectionState, SemanticIndexJob, SiteSetting,
)
from catalog.services.publication_commands import catalog_publication_state


INDEX_SOURCES = {"fulltext": "fulltext_index_revision_id", "semantic": "semantic_index_revision_id", "viewpoint": "claim_index_revision_id"}
LABELS = {"pdf": "PDF阅读", "text": "正文文本", "fulltext": "全文检索", "semantic": "语义检索", "viewpoint": "观点检索", "qa": "馆藏原文问答"}
JOB_TYPES = {"pdf": {"text_extraction"}, "text": {"text_extraction", "ocr"}, "fulltext": {"projection_refresh"}, "semantic": {"semantic_index"}, "viewpoint": {"projection_refresh"}, "qa": {"projection_refresh"}}


def _uuid(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def batch_catalog_availability(editions):
    """One batch per request; edition_summary consumes the result without SQL."""
    editions = list(editions)
    if not editions:
        return {}
    prefetch_related_objects(editions, "assets", "processing_jobs", "catalog_revisions", "active_catalog_revision__reader_asset", "active_catalog_revision__document_revision")
    assets = [asset for edition in editions for asset in edition.assets.all()]
    active = [edition.active_catalog_revision for edition in editions if catalog_publication_state(edition)["catalog_revision_active"]]
    revision_ids = {row.pk for row in active}
    revision_ids.update(identifier for row in active for key in INDEX_SOURCES.values() if (identifier := _uuid((row.provenance or {}).get(key))))
    revisions = {row.pk: row for row in CatalogPublicationRevision.objects.filter(pk__in=revision_ids)} if revision_ids else {}
    events = {}
    if revision_ids:
        for event in KnowledgePublicationEvent.objects.filter(catalog_revision_id__in=revision_ids).select_related("domain_event").prefetch_related("deliveries").order_by("-created_at", "-pk"):
            events.setdefault(event.catalog_revision_id, event)
    projection_scope = Q(pk__in=[])
    for kind in {event.object_type for event in events.values()}:
        projection_scope |= Q(object_type=kind, object_id__in={event.object_id for event in events.values() if event.object_type == kind})
    projections = {(row.object_type, row.object_id, row.projection_type): row for row in ProjectionState.objects.filter(projection_scope)} if events else {}
    documents, document_by_id, semantic_jobs = defaultdict(list), {}, defaultdict(list)
    if assets:
        document_ids = {row.document_revision_id for row in active if row.document_revision_id}
        for row in DocumentRevision.objects.filter(Q(asset_id__in=[asset.pk for asset in assets], is_active=True) | Q(pk__in=document_ids)).prefetch_related("quality_assessments"):
            documents[row.asset_id].append(row)
            document_by_id[row.pk] = row
        for row in SemanticIndexJob.objects.filter(asset_id__in=[asset.pk for asset in assets]).order_by("-updated_at", "-pk"):
            semantic_jobs[row.asset_id].append(row)
    now = timezone.now()
    # Skip unrelated runtime/config reads for entirely bibliographic batches.
    qa_runtime, observations, ocr_paused = {}, {}, False
    if assets:
        from catalog.services.system_health import HEALTH_CHECKS
        from reading.runtime_profiles import active_library_runtime_summary
        qa_runtime = active_library_runtime_summary()
        ocr_paused = SiteSetting.objects.filter(key="ocr_processing_paused", value=True).exists()
        for row in HealthCheckRun.objects.filter(probe_key__in=["storage_reader", "semantic", "ocr"]).order_by("probe_key", "-started_at", "-pk"):
            if row.probe_key not in observations:
                fresh = 0 <= (now - row.started_at).total_seconds() <= 2 * HEALTH_CHECKS.get(row.probe_key).interval_seconds
                observations[row.probe_key] = {"id": str(row.pk), "checked_at": row.started_at, "fresh": fresh,
                                               "status": row.status if fresh else "unknown",
                                               "functional": row.functional if fresh else None,
                                               "reachable": row.reachable if fresh else None}
    context = {"revisions": revisions, "events": events, "projections": projections, "documents": documents,
               "semantic_jobs": semantic_jobs, "now": now, "qa_runtime": qa_runtime, "observations": observations,
               "ocr_paused": ocr_paused, "document_by_id": document_by_id}
    return {edition.pk: _edition_availability(edition, context) for edition in editions}


def catalog_availability(edition):
    return batch_catalog_availability([edition])[edition.pk]


def _projection_result(key, active, document, context):
    """Honor legitimate carried index revisions; never borrow another Edition."""
    source_id = _uuid((active.provenance or {}).get(INDEX_SOURCES.get(key, ""))) or active.pk
    source = context["revisions"].get(source_id)
    if not source or source.edition_id != active.edition_id or source.document_revision_id != document.pk or source.reader_asset_id != document.asset_id or source.status not in {"active", "superseded"} or not source.metadata_ready:
        return "stale", "索引来源与当前公开正文不一致，旧任务不能证明本修订就绪。", None, []
    event = context["events"].get(source.pk)
    if event is None:
        return "unknown", "没有可追溯到该来源修订的投递记录，不能由索引时间戳推断完成。", None, []
    consumer = "viewpoint" if key == "viewpoint" else "rag" if key == "qa" else key
    delivery = next((row for row in event.deliveries.all() if row.consumer == consumer), None)
    if delivery is None or event.domain_event is None or delivery.source_revision != event.domain_event.canonical_revision:
        return "unknown", "缺少匹配来源版本的投递依据。", event, []
    requirements = list((delivery.result or {}).get("required_projections") or [])
    states = [context["projections"].get((event.object_type, event.object_id, name)) for name in requirements]
    trace = [{"type": row.projection_type, "source_revision": row.source_revision, "projected_revision": row.projected_revision,
              "status": row.status, "updated_at": row.updated_at} for row in states if row is not None]
    if delivery.status == "skipped":
        return "pending", "原投递明确未执行此能力；书目和获准PDF可以独立可用。", event, trace
    if any(row is None or row.projected_revision < delivery.source_revision for row in states):
        if any(row is not None and row.status == "failed" for row in states):
            return "failed", "本来源修订的必要投影失败，可从原任务恢复。", event, trace
        return "stale", "必要投影尚未追上本来源修订；旧成功记录不计为当前完成。", event, trace
    if delivery.status == "failed":
        return "failed", "原投递记录失败，尚未确认恢复。", event, trace
    if delivery.status != "completed":
        return "pending", "原投递仍在处理，命令接受不等于公开结果生效。", event, trace
    return "ready", "本来源修订的投递及必要投影已完成。", event, trace


def _edition_availability(edition, context):
    publication = catalog_publication_state(edition)
    active = edition.active_catalog_revision if publication["catalog_revision_active"] else None
    assets = sorted(edition.assets.all(), key=lambda row: (row.version, row.created_at, str(row.pk)), reverse=True)
    serving_reader = active.reader_asset if active and active.reader_asset_id and active.reader_asset.edition_id == edition.pk else None
    reader = serving_reader or next((row for row in assets if row.kind == "normalized" and row.is_current), None)
    document = context["document_by_id"].get(active.document_revision_id) if active and active.document_revision_id else next(iter(context["documents"].get(reader.pk, [])), None) if reader else None
    document_matches = bool(document and reader and document.asset_id == reader.pk and document.source_checksum == reader.sha256)
    assessment = max(document.quality_assessments.all(), key=lambda row: row.created_at, default=None) if document else None
    # The active revision may reference a superseded interpretation on purpose.
    # Evidence/Reader use its exact ID; is_active alone cannot replace that ID.
    quality = dict(assessment.details or {}) if assessment else {}
    populated, page_count = int(quality.get("populated_pages") or 0), int(quality.get("page_count") or 0)
    text_ready = document_matches and populated > 0
    applicable = not (edition.publication_mode == "bibliographic" and not assets)
    file_ready = bool(reader and reader.kind == "normalized" and reader.status == "ready" and reader.validation_status == "valid")
    rows = []
    jobs = sorted(edition.processing_jobs.all(), key=lambda row: (row.updated_at, str(row.pk)), reverse=True)
    for key, label in LABELS.items():
        task_rows = []
        for job in jobs:
            if job.job_type not in JOB_TYPES[key] or (job.asset_id and (not reader or job.asset_id != reader.pk)):
                continue
            source_document = (job.stats or {}).get("document_revision_id")
            current_source = not source_document or (document and str(document.pk) == str(source_document))
            task_rows.append({"id": str(job.pk), "status": job.status, "label": job.get_job_type_display(),
                              "current_source": bool(current_source), "updated_at": job.updated_at,
                              "url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#file"})
        if key == "semantic" and reader:
            task_rows.extend({"id": str(job.pk), "status": job.status, "label": "语义索引", "current_source": not (job.stats or {}).get("document_revision_id") or str((job.stats or {}).get("document_revision_id")) == str(document.pk if document else ""),
                              "updated_at": job.updated_at, "url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#reader"}
                             for job in context["semantic_jobs"].get(reader.pk, [])[:10])
        task_rows.sort(key=lambda row: (row["updated_at"], row["id"]), reverse=True)
        matching = [row for row in task_rows if row["current_source"]]
        task = matching[0] if matching else None
        state, detail, event, trace = "unknown", "尚无足够的当前来源记录。", None, []
        if not applicable:
            state, detail = "not_applicable", "纯书目没有文档文件，本项原文能力不适用，也不阻断书目公开。"
        elif key == "pdf":
            if reader is None:
                state, detail = "pending", "尚无当前版本的阅读文件。"
            elif reader.validation_status == "invalid" or reader.status == "failed":
                state, detail = "failed", "阅读文件验证失败；保留原件，处理后重新验证。"
            elif not file_ready:
                state, detail = "pending", "阅读文件尚未处理完成或仍等待验证；只有valid可算通过。"
            else:
                state, detail = "ready", "阅读文件记录已通过验证。" + ("当前公开修订引用此文件。" if serving_reader else "此文件尚未被有效公开修订引用，仅可使用受控预览。") + "本次未访问NAS验证字节。"
        elif key == "text":
            if text_ready:
                state = "ready" if page_count and populated >= page_count else "partial"
                detail = f"当前文档解释记录有{populated}/{page_count}页文本；正文质量和检索能力另外核对。"
            elif document and not document_matches:
                state, detail = "stale", "文档解释的文件校验和或归属不匹配，不能采用旧任务结果。"
            elif task and task["status"] in {"paused", "failed"}:
                state, detail = task["status"], "当前正文处理已暂停。" if task["status"] == "paused" else "当前正文处理失败，可从原任务恢复。"
            elif context["ocr_paused"]:
                state, detail = "paused", "OCR全局暂停且本文件暂无可核验正文；PDF与书目不因此失效。"
            else:
                state, detail = "pending" if task else "unknown", "尚无带来源版本及文本覆盖记录的文档解释；未执行不等于失败。"
        elif key == "semantic" and not settings.SEMANTIC_SEARCH_ENABLED:
            state, detail = "disabled", "语义检索未启用，全文和PDF能力分别判断。"
        elif key == "qa" and context["qa_runtime"].get("enabled") is False:
            state, detail = "disabled", "馆藏问答运行配置未启用；不读取读者私有模型或对话。"
        elif not active or not active.fulltext_ready or not document_matches or not serving_reader or not file_ready:
            state = "paused" if task and task["status"] == "paused" else "failed" if task and task["status"] == "failed" else "pending"
            detail = "当前没有可用于本项能力的有效公开正文修订；不阻断合法书目和PDF。"
        else:
            state, detail, event, trace = _projection_result(key, active, document, context)
            if state == "ready" and key == "qa":
                state, detail = "unknown", "本修订的问答材料已投递；运行配置不等于模型调用成功，实时问答能力待核验。"
            elif state == "ready":
                observation = context["observations"].get("semantic", {})
                if not observation.get("fresh") or observation.get("functional") is not True:
                    state = "failed" if observation.get("fresh") and observation.get("reachable") is False else "unknown"
                    detail += "检索服务的最近功能检查失败。" if state == "failed" else "缺少新鲜服务功能检查，实时检索待核验。"
        observation = context["observations"].get("storage_reader" if key == "pdf" else "ocr" if key == "text" else "semantic", {})
        rows.append({"key": key, "label": label, "applicable": applicable, "status": state, "detail": detail,
                     "public_ready": bool(active and state == "ready" and (serving_reader and reader.access_status == "public" if key == "pdf" else active.fulltext_ready and document_matches)),
                     "runtime_verified": False if key == "qa" else bool(observation.get("fresh") and observation.get("functional") is True),
                     "source": {"catalog_revision_id": str(event.catalog_revision_id) if event else str(active.pk) if active else None,
                                "document_revision_id": str(document.pk) if document else None, "asset_id": str(reader.pk) if reader else None,
                                "canonical_revision": event.domain_event.canonical_revision if event and event.domain_event else None,
                                "evaluated_at": context["now"], "record_updated_at": event.updated_at if event else document.updated_at if document else reader.updated_at if reader else edition.updated_at,
                                "runtime_observation": observation}, "projections": trace, "tasks": task_rows[:10]})
    return {"scope": "saved_revision_and_task_records", "generated_at": context["now"], "edition_id": str(edition.pk),
            "active_catalog_revision_id": str(active.pk) if active else None, "capabilities": rows,
            "live_probes_performed": False, "private_reader_data": "not_read"}
