"""Resumable, revision-guarded projection jobs using the existing job ledger."""
from __future__ import annotations

from datetime import timedelta
from contextlib import contextmanager
import logging
import math
import json
import threading
import time
from uuid import UUID, uuid4, uuid5

from django.conf import settings
from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from catalog.discovery_index_models import DiscoveryDocument, DiscoverySourceState
from catalog.models import SemanticIndexVersion
from catalog.services.discovery_inference import chunk_text, embed_texts, inference_health, DiscoveryInferenceError
from catalog.services.discovery_projection import meili, active_generation, DiscoveryIndexError
from catalog.services.discovery_sources import SOURCE_TYPES, edition_revision, fingerprint, get_source, iter_source_headers, source_queryset, source_units
from catalog.services.contribution_projection import contribution_projection
from ingestion.models import AuditEvent, ProcessingJob

logger = logging.getLogger(__name__)
JOB_TYPE = "discovery_index"
OPEN = ("pending", "running")
RUNNING_STALLED_SECONDS = 15 * 60
QUEUED_STALLED_SECONDS = 60 * 60
_LOCAL_LOCK = threading.RLock()


@contextmanager
def index_writer():
    """One writer across workers, redelivery and reconciliation.

    PostgreSQL releases the session advisory lock if a worker dies. Do not hold
    a database transaction across model or Meilisearch calls. The local lock is
    only for non-PostgreSQL development environments.
    """
    acquired = False
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [308, 1701])
            acquired = bool(cursor.fetchone()[0])
    else:
        acquired = _LOCAL_LOCK.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [308, 1701])
            else:
                _LOCAL_LOCK.release()


def _guard_job(job, **updates):
    """Every delayed completion/checkpoint uses the claimed task identity."""
    updates["updated_at"] = timezone.now()
    changed = ProcessingJob.objects.filter(pk=job.pk, task_id=job.task_id, status="running").update(**updates)
    if not changed:
        raise DiscoveryIndexError("superseded", "任务已被更新，旧任务不再写回。")
    for key, value in updates.items():
        setattr(job, key, value)


def enabled():
    return bool(getattr(settings, "DISCOVERY_ENABLED", False))


def wait_index_task(payload, timeout=120):
    task_id = payload.get("taskUid")
    if task_id is None:
        raise DiscoveryIndexError("missing_task", "索引服务未返回可核对的写入任务。")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = meili("GET", f"/tasks/{task_id}", timeout=10)
        if result.get("status") == "succeeded":
            return result
        if result.get("status") in {"failed", "canceled"}:
            raise DiscoveryIndexError("write_failed", "索引写入失败，原有效版本仍保留。")
        time.sleep(.3)
    raise DiscoveryIndexError("write_timeout", "索引写入尚未完成，请在处理中心重试。")


def ensure_index(generation, *, extra_filterable=()):
    # Index creation is idempotent. The unique name never addresses an old index.
    try:
        meili("GET", f"/indexes/{generation.uid}")
    except DiscoveryIndexError as exc:
        if exc.code != "index_missing":
            raise
        wait_index_task(meili("POST", "/indexes", {"uid": generation.uid, "primaryKey": "id"}))
    scope_fields = ["body_text", "notes_text", "topics_text"] if generation.config_snapshot.get("scope_fields_version") == 1 else []
    desired = {"searchableAttributes": ["title", "aliases", "authors", "normalized_text", *scope_fields],
        "displayedAttributes": ["*"],
        "filterableAttributes": ["id", "channel", "source_type", "source_id", "source_revision", "scope_token", "access_status", "input_hash", "language", *extra_filterable],
        "pagination": {"maxTotalHits": 10000},
        "embedders": {"discovery": {"source": "userProvided", "dimensions": int(generation.dimensions or 384)}}}
    wait_index_task(meili("PATCH", f"/indexes/{generation.uid}/settings", desired))


def _dispatch(job_id, task_id, *, countdown=0):
    from catalog.discovery_index_tasks import process_discovery_index_job
    try:
        process_discovery_index_job.apply_async(args=[str(job_id)], task_id=task_id,
            countdown=countdown,
            queue=getattr(settings, "DISCOVERY_INDEX_TASK_QUEUE", "discovery_index"))
    except Exception as exc:
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id, status="pending").update(status="failed",
            error_code="queue_unavailable", error_kind="retryable", error_message="任务未能进入索引队列，请重试。",
            attempt=F("attempt") + 1, updated_at=timezone.now(), finished_at=timezone.now())
        logger.warning("Discovery index dispatch failed: %s", type(exc).__name__)


def _enqueue_job(job):
    task_id = str(uuid4())
    job.task_id, job.status = task_id, "pending"
    job.error_message, job.error_code, job.error_kind = "", "", ""
    job.started_at, job.finished_at = None, None
    job.save(update_fields=["task_id", "status", "error_message", "error_code", "error_kind", "started_at", "finished_at", "updated_at"])
    transaction.on_commit(lambda: _dispatch(job.pk, task_id))


@transaction.atomic
def request_rebuild(actor=None, *, activate=True):
    if not enabled():
        raise DiscoveryIndexError("disabled", "本地检索服务尚未启用。")
    # A database row lock serializes admin double-clicks across API processes.
    from catalog.models import SiteSetting
    lock, _ = SiteSetting.objects.get_or_create(key="discovery_build_lock", defaults={"value": {}})
    SiteSetting.objects.select_for_update().get(pk=lock.pk)
    existing = ProcessingJob.objects.filter(job_type=JOB_TYPE, status__in=(*OPEN, "paused"), stats__action="build").first()
    if existing:
        return existing
    job = ProcessingJob.objects.create(job_type=JOB_TYPE, created_by=actor, engine="discovery-3.0.8",
                                       stats={"action": "build", "activate": activate})
    _enqueue_job(job)
    return job


@transaction.atomic
def retry_job(job_id, *, actor=None):
    job = ProcessingJob.objects.select_for_update().filter(pk=job_id, job_type=JOB_TYPE).first()
    if not job or job.status not in {"failed", "paused"}:
        raise DiscoveryIndexError("not_retryable", "该任务当前不能重试。")
    if job.stats.get("action") == "restore_projection":
        raise DiscoveryIndexError("maintenance_restore", "此任务是丢失索引的维护恢复，请使用相同 restore_missing_discovery_index 命令继续保留的批次游标。")
    before = {"status": job.status, "error_code": job.error_code, "error_message": job.error_message,
              "attempt": job.attempt, "active_unit": job.stats.get("active_unit"), "completed_units": job.stats.get("completed_units", 0)}
    # Retrying retains the same source/generation identity and successful chunks.
    job.attempt = 0
    if job.stats.get("action") == "source":
        generation = SemanticIndexVersion.discovery_objects.filter(pk=job.stats.get("generation_id"),
            status__in=["building", "ready", "active"]).first()
        header = get_source(job.stats["source_type"], job.stats["source_id"])[1]
        if not generation or not header or header["source_revision"] != job.stats["source_revision"]:
            raise DiscoveryIndexError("superseded", "该任务对应的资料已更新或版本已停用，请等待最新资料重新排队。")
    job.save(update_fields=["attempt"])
    _enqueue_job(job)
    AuditEvent.objects.create(actor=actor, action="discovery.retry_from_checkpoint", object_type="processing_job", object_id=str(job.pk),
        before=before, after={"status": job.status, "task_id": job.task_id})
    return job


def _prepare_generation(job):
    existing_id = job.stats.get("generation_id")
    if existing_id:
        return SemanticIndexVersion.discovery_objects.get(pk=existing_id)
    try:
        health = inference_health()
    except DiscoveryInferenceError:
        health = {}
    models = health.get("models", {})
    embedding, reranker = models.get("embedding", {}), models.get("reranker", {})
    with transaction.atomic():
        current = ProcessingJob.objects.select_for_update().filter(pk=job.pk, task_id=job.task_id, status="running").first()
        if not current:
            raise DiscoveryIndexError("superseded", "建立任务已更新。")
        embedding_dimensions = int(embedding.get("dimensions") or getattr(settings, "DISCOVERY_EMBEDDING_DIMENSIONS", 384))
        if not 1 <= embedding_dimensions <= 4096:
            raise DiscoveryInferenceError("invalid_response", "向量模型维度不在允许范围内。")
        generation = SemanticIndexVersion.discovery_objects.create(index_family="discovery",
            uid="discovery_v308_" + uuid4().hex, provider="local_onnx_user_provided",
            model_repo_id=embedding.get("model", "keyword-only"), model_revision=embedding.get("revision", "unconfigured"), dimensions=embedding_dimensions,
            pooling="masked_mean_l2", document_template="passage: {title}\n{normalized_text}",
            config_snapshot={"embedding_artifact": embedding.get("artifact_id", ""), "reranker_artifact": reranker.get("artifact_id", ""),
                "pipeline": health.get("pipeline"), "normalization": health.get("normalization"), "index_configured": False,
                "chunk_tokens": 320, "overlap_tokens": 40, "dimensions": embedding_dimensions, "scope_fields_version": 1,
                "activate": job.stats.get("activate", True)})
        _guard_job(job, stats={**job.stats, "generation_id": str(generation.pk)})
    return generation


def schedule_sources(generation, *, max_queued=8):
    """Scan fingerprints only; heavy per-source work stays bounded in its queue."""
    if not SemanticIndexVersion.discovery_objects.filter(pk=generation.pk, status__in=["building", "ready", "active"]).exists():
        return 0
    current = set()
    slots = max(0, max_queued - ProcessingJob.objects.filter(job_type=JOB_TYPE, status__in=OPEN,
                    stats__action="source").count())
    pending = 0
    states = {(row.source_type, str(row.source_id)): row for row in
              DiscoverySourceState.objects.filter(generation=generation).iterator(chunk_size=200)}
    # Small published knowledge records become ready without a corpus re-encode.
    for kind in (*SOURCE_TYPES[1:], "edition"):
        for source, header in iter_source_headers(kind):
            current.add((kind, str(source.pk)))
            state = states.get((kind, str(source.pk)))
            if state is None:
                state, _ = DiscoverySourceState.objects.get_or_create(generation=generation, source_type=kind, source_id=source.pk)
                states[(kind, str(source.pk))] = state
            if (state.source_revision == header["source_revision"] and state.indexed_at and not state.error
                    and state.completed_count == state.expected_count):
                continue
            pending += 1
            key = fingerprint([str(generation.pk), kind, str(source.pk), header["source_revision"]])
            job = ProcessingJob.objects.filter(idempotency_key="discovery:" + key).first()
            if job and job.status in OPEN:
                continue
            if (job and job.status == "failed" and job.finished_at and
                    job.finished_at + timedelta(seconds=min(1800, 60 * (2 ** job.attempt))) > timezone.now()):
                continue
            restored = bool(job and job.status == "canceled" and job.error_code == "superseded"
                            and job.stats.get("action") == "source")
            if not slots or (job and not restored and (job.attempt >= job.max_attempts or job.status == "canceled")):
                continue
            with transaction.atomic():
                if not SemanticIndexVersion.discovery_objects.select_for_update().filter(
                        pk=generation.pk, status__in=["building", "ready", "active"]).exists():
                    return pending
                if job is None:
                    job, _ = ProcessingJob.objects.get_or_create(idempotency_key="discovery:" + key,
                        defaults={"job_type": JOB_TYPE, "edition_id": source.pk if kind == "edition" else None,
                            "asset_id": header.get("asset_id"), "engine": "discovery-3.0.8",
                            "stats": {"action": "source", "generation_id": str(generation.pk), "source_type": kind,
                                      "source_id": str(source.pk), "source_revision": header["source_revision"]}})
                job = ProcessingJob.objects.select_for_update().get(pk=job.pk)
                if job.status in OPEN and job.task_id:
                    continue
                restored = (job.status == "canceled" and job.error_code == "superseded"
                            and job.stats.get("action") == "source")
                if job.status == "canceled" and not restored:
                    continue
                if job.status == "succeeded" or restored:
                    fresh = get_source(kind, source.pk)[1]
                    if (not fresh or fresh["source_revision"] != header["source_revision"]
                            or job.stats.get("generation_id") != str(generation.pk)
                            or job.stats.get("source_type") != kind
                            or job.stats.get("source_id") != str(source.pk)
                            or job.stats.get("source_revision") != header["source_revision"]):
                        continue
                    # Withdrawal can delete derived rows while their old unit
                    # checkpoint survives. Replay units, retaining existing ready
                    # chunks via _write_chunk's idempotent completion check.
                    job.attempt = 0
                    job.stats = {**job.stats, "completed_units": 0}
                    job.stats.pop("semantic_waiting", None)
                    job.save(update_fields=["attempt", "stats"])
                _enqueue_job(job)
                state.job = job
                state.save(update_fields=["job", "updated_at"])
            slots -= 1
    # Withdrawals disappear at the read boundary immediately. Remove only this
    # generation's derived documents after Meilisearch confirms deletion.
    for state in states.values():
        if (state.source_type, str(state.source_id)) in current:
            continue
        remove_source(generation, state.source_type, state.source_id)
        state.delete()
    return pending


def remove_source(generation, kind, source_id, *, keep_revision=None):
    docs = DiscoveryDocument.objects.filter(generation=generation, source_type=kind, source_id=source_id)
    if keep_revision:
        docs = docs.exclude(source_revision=keep_revision)
    filters = [f"source_type = {json.dumps(kind)}", f"source_id = {json.dumps(str(source_id))}"]
    if keep_revision:
        filters.append(f"source_revision != {json.dumps(keep_revision)}")
    if getattr(settings, "STL_DEEP_RETRIEVAL_ENABLED", False):
        from catalog.services.retrieval.deep_index import remove_source as remove_deep_source
        remove_deep_source([*filters, f"baseline_generation = {json.dumps(str(generation.pk))}"])
    while True:
        # The canonical row may already have cascaded its SQL projections.
        # Enumerate the external source too, so orphaned Meili IDs cannot block
        # count verification or survive a deletion indefinitely.
        result = meili("POST", f"/indexes/{generation.uid}/search", {"q": "", "filter": filters,
            "limit": 200, "attributesToRetrieve": ["id"]})
        ids = [str(row["id"]) for row in result.get("hits", [])]
        if not ids:
            docs.delete()
            break
        wait_index_task(meili("POST", f"/indexes/{generation.uid}/documents/delete-batch", ids))
        DiscoveryDocument.objects.filter(pk__in=ids).delete()


def _is_current(job, generation, header):
    if not ProcessingJob.objects.filter(pk=job.pk, task_id=job.task_id, status="running").exists():
        return False
    if not SemanticIndexVersion.discovery_objects.filter(pk=generation.pk, status__in=["building", "ready", "active"]).exists():
        return False
    if job.stats["source_type"] == "edition":
        row = source_queryset("edition").filter(pk=job.stats["source_id"]).values_list(
            "active_catalog_revision_id", "active_catalog_revision__document_revision_id",
            "active_catalog_revision__document_revision__text_checksum", "active_catalog_revision__reader_asset__access_status").first()
        return bool(row and edition_revision(*row) == header["source_revision"])
    fresh = get_source(job.stats["source_type"], job.stats["source_id"])[1]
    return bool(fresh and fresh["source_revision"] == header["source_revision"])


def raw_keyword_slices(text, title=""):
    """Raw code-point windows, independent of model/tokenizer availability."""
    for start in range(0, len(text), 200):
        end = min(len(text), start + 240)
        raw = text[start:end]
        if raw.strip():
            yield {"start": start, "end": end, "text": raw, "normalized_text": raw,
                "embedding_text": f"passage: {title}\n{raw}", "token_count": 0,
                "quality_flags": ["raw_codepoint_window", "token_count_unknown"]}
        if end == len(text):
            break


def _write_chunk(job, generation, header, unit, child, *, contributions=None):
    if not _is_current(job, generation, header):
        raise DiscoveryIndexError("superseded", "资料或任务已更新，旧任务已停止。")
    identifier = uuid5(generation.pk, f"{header['source_type']}:{header['source_id']}:{header['source_revision']}:{unit['unit_id']}:{child['start']}:{child['end']}")
    existing = DiscoveryDocument.objects.filter(pk=identifier, vector_ready=True, keyword_ready=True).first()
    if existing and (header["channel"] != "passages" or existing.payload.get("responsibility_projection") == 1):
        _write_deep_projection(job, existing)
        return
    _guard_job(job, stats={**job.stats, "active_unit": {"unit_id": unit["unit_id"], "pdf_page": unit["metadata"].get("pdf_page"),
        "start_offset": child["start"], "end_offset": child["end"]}})
    input_hash = fingerprint([generation.config_snapshot["embedding_artifact"], child["embedding_text"]])
    if not _is_current(job, generation, header):
        raise DiscoveryIndexError("superseded", "资料已更新，旧任务已停止；新版本会重新排队。")
    payload = {**{key: value for key, value in header.items() if key != "text"}, **unit["metadata"], "unit_id": unit["unit_id"],
               "quality_flags": list(dict.fromkeys([*unit["metadata"].get("quality_flags", []), *child.get("quality_flags", [])]))}
    if contributions is not None:
        payload.update(contributions.for_range(header["asset_id"], header["document_revision_id"], unit["metadata"].get("pdf_page")), responsibility_projection=1)
    defaults = {"generation": generation, "channel": header["channel"], "source_type": header["source_type"],
        "source_id": header["source_id"], "source_revision": header["source_revision"], "scope_token": header["scope_token"],
        "edition_id": header.get("edition_id"), "document_revision_id": header.get("document_revision_id"),
        "access_status": header["access_status"], "input_hash": input_hash, "text": child["text"],
        "normalized_text": child["normalized_text"], "token_count": child["token_count"],
        "start_offset": child["start"], "end_offset": child["end"], "payload": payload}
    document, _ = DiscoveryDocument.objects.update_or_create(pk=identifier, defaults=defaults)
    if document.channel == "passages":
        from catalog.services.retrieval.locators import index_anchor
        index_anchor(document)
    search_doc = {"id": str(identifier), "channel": header["channel"], "source_type": header["source_type"],
        "source_id": header["source_id"], "source_revision": header["source_revision"], "scope_token": header["scope_token"],
        "access_status": header["access_status"], "input_hash": input_hash, "title": header["title"],
        "aliases": header.get("aliases", []), "authors": payload.get("authors", []),
        "normalized_text": child["normalized_text"], "language": payload.get("language") or header.get("language", "unknown"),
        "_vectors": {"discovery": []}}
    if generation.config_snapshot.get("scope_fields_version") == 1:
        from catalog.services.discovery_scope import chunk_fields
        search_doc.update(chunk_fields(header, unit, child))
    wait_index_task(meili("POST", f"/indexes/{generation.uid}/documents", [search_doc]))
    # Ready is evidence of a successful external task, never merely a dispatched write.
    with transaction.atomic():
        ProcessingJob.objects.select_for_update().get(pk=job.pk)
        if not _is_current(job, generation, header):
            raise DiscoveryIndexError("superseded", "资料或任务已更新，旧写入不会标记为完成。")
        DiscoveryDocument.objects.filter(pk=document.pk).update(keyword_ready=True, indexed_at=timezone.now())
    document.keyword_ready = True
    # Keyword commit precedes every model call. Model outages do not undo it.
    if not generation.config_snapshot.get("embedding_artifact") or job.stats.get("semantic_waiting"):
        return
    try:
        vector = None
        previous = DiscoveryDocument.objects.filter(generation=generation, input_hash=input_hash, vector_ready=True).first()
        if previous:
            stored = meili("POST", f"/indexes/{generation.uid}/documents/fetch", {"ids": [str(previous.pk)], "retrieveVectors": True})
            results = stored.get("results", [])
            raw = results[0].get("_vectors", {}).get("discovery") if results else None
            if isinstance(raw, dict):
                raw = (raw.get("embeddings") or [None])[0]
            dimensions = int(generation.dimensions or generation.config_snapshot.get("dimensions") or 384)
            if (isinstance(raw, list) and len(raw) == dimensions and all(isinstance(v, (int, float)) and math.isfinite(v) for v in raw)
                    and .995 < sum(v * v for v in raw) < 1.005):
                vector = raw
        if vector is None:
            vector = embed_texts(
                [child["embedding_text"]],
                expected_artifact=generation.config_snapshot["embedding_artifact"],
                expected_dimensions=int(generation.dimensions or generation.config_snapshot.get("dimensions") or 384),
            )["vectors"][0]
        if not _is_current(job, generation, header):
            raise DiscoveryIndexError("superseded", "来源已变化，旧向量不再写入。")
        wait_index_task(meili("PUT", f"/indexes/{generation.uid}/documents", [{"id": str(identifier), "_vectors": {"discovery": vector}}]))
        with transaction.atomic():
            ProcessingJob.objects.select_for_update().get(pk=job.pk)
            if not _is_current(job, generation, header):
                raise DiscoveryIndexError("superseded", "来源已变化，旧向量不再标记就绪。")
            DiscoveryDocument.objects.filter(pk=document.pk).update(vector_ready=True)
        _write_deep_projection(job, document)
    except DiscoveryInferenceError as exc:
        _guard_job(job, stats={**job.stats, "semantic_waiting": {"code": exc.code,
            "message": "关键词已可用，语义索引等待模型。"}})


def _write_deep_projection(job, document):
    if not getattr(settings, "STL_DEEP_RETRIEVAL_ENABLED", False):
        return
    from catalog.services.retrieval.deep_index import project_document
    try:
        project_document(document)
    except (DiscoveryIndexError, DiscoveryInferenceError) as exc:
        # Optional deep model failure cannot discard a completed E5 write.
        # Keep an actionable receipt; discovery_deep_index resumes by input hash.
        logger.warning("Deep projection pending for document %s: %s", document.pk, exc.code)
        _guard_job(job, stats={**job.stats, "deep_index_pending": {
            "document_id": str(document.pk), "code": exc.code,
            "message": "基础索引已保留，深度投影待补写。"}})


def request_source_reindex(revision, *, keyword_only=False):
    """Target one published source; existing projections remain until completion."""
    from catalog.services.knowledge_sources import current_structure
    generation=active_generation()
    source,header=get_source("edition",revision.asset.edition_id)
    if not generation or not header or header.get("document_revision_id") != str(revision.pk):
        raise DiscoveryIndexError("source_not_published","请先发布此正文修订并准备活动索引，再更新关键词。")
    structure=current_structure(revision,prepare=True)
    key=fingerprint([str(generation.pk),header["source_revision"],str(structure.pk),"keyword" if keyword_only else "hybrid"])
    with transaction.atomic():
        job,created=ProcessingJob.objects.get_or_create(idempotency_key="logical-index:"+key,defaults={
            "job_type":JOB_TYPE,"edition":source,"asset":revision.asset,"engine":"logical-node-v1",
            "stats":{"action":"source","generation_id":str(generation.pk),"source_type":"edition",
                "source_id":str(source.pk),"source_revision":header["source_revision"],"structure_id":str(structure.pk)}})
        job=ProcessingJob.objects.select_for_update().get(pk=job.pk)
        if created or job.status in {"failed","canceled"}:
            if keyword_only: job.stats={**job.stats,"semantic_waiting":{"code":"keyword_only","message":"本次仅更新关键词，语义状态独立保留。"}}
            job.attempt=0;job.save()
            _enqueue_job(job)
        DiscoverySourceState.objects.update_or_create(generation=generation,source_type="edition",source_id=source.pk,defaults={"job":job})
    return job


def process_source(job, generation):
    kind, source_id = job.stats["source_type"], job.stats["source_id"]
    source, header = get_source(kind, source_id)
    if not header or header["source_revision"] != job.stats["source_revision"]:
        raise DiscoveryIndexError("superseded", "资料已更新或撤下，旧任务已停止。")
    contributions = contribution_projection(source, access_statuses=[header["access_status"]]) if kind == "edition" else None
    state, _ = DiscoverySourceState.objects.get_or_create(generation=generation, source_type=kind, source_id=source_id)
    deadline = time.monotonic() + 240
    structure_id = job.stats.get("structure_id")
    if kind == "edition" and not structure_id:
        from catalog.services.knowledge_sources import current_structure
        structure = current_structure(source.active_catalog_revision.document_revision,prepare=True)
        structure_id = str(structure.pk)
        _guard_job(job,stats={**job.stats,"structure_id":structure_id,"completed_units":0})
    completed_units = int(job.stats.get("completed_units", 0))
    for unit_index, unit in enumerate(source_units(kind, source, header,structure_id=structure_id)):
        if unit_index < completed_units:
            continue
        location = {"unit_id": unit["unit_id"], "pdf_page": unit["metadata"].get("pdf_page"), "start_offset": None, "end_offset": None}
        _guard_job(job, stats={**job.stats, "active_unit": location})
        # Canonical spans/pages remain intact; a pathological page is partitioned
        # into exact original windows before tokenizer requests, with offsets kept.
        for base in range(0, len(unit["text"]), 60000):
            original = unit["text"][base:base + 60000]
            children = {"chunks": raw_keyword_slices(original, header["title"])}
            for child in children["chunks"]:
                child = {**child, "start": child["start"] + base, "end": child["end"] + base}
                _write_chunk(job, generation, header, unit, child, contributions=contributions)
                if time.monotonic() > deadline:
                    # Completed children are durable; replay only the current unit.
                    _guard_job(job, stats={**job.stats, "completed_units": unit_index})
                    return False
        _guard_job(job, stats={**job.stats, "completed_units": unit_index + 1, "active_unit": None})
    if not _is_current(job, generation, header):
        raise DiscoveryIndexError("superseded", "资料已更新，旧任务不再回写完成状态。")
    docs = DiscoveryDocument.objects.filter(generation=generation, source_type=kind, source_id=source_id, source_revision=header["source_revision"])
    if structure_id:
        docs = docs.filter(payload__structure_id=structure_id)
    expected, completed = docs.count(), docs.filter(keyword_ready=True).count()
    if kind == "edition" and not expected:
        raise DiscoveryIndexError("text_missing", "该文件尚无可用原文文字，请检查文字处理结果后重试。")
    if expected != completed:
        raise DiscoveryIndexError("incomplete", "部分文字尚未完成索引，可重试继续。")
    if structure_id:
        # Retire only after the replacement is complete. Keep SQL identities for
        # historical feedback and source mappings instead of deleting references.
        old = DiscoveryDocument.objects.filter(generation=generation,source_type=kind,source_id=source_id,
            source_revision=header["source_revision"],keyword_ready=True).filter(
                Q(payload__structure_id__isnull=True) | ~Q(payload__structure_id=structure_id))
        while ids := list(old.values_list("pk",flat=True)[:200]):
            if not _is_current(job,generation,header):
                raise DiscoveryIndexError("superseded","来源已更新，停止旧投影清理。")
            wait_index_task(meili("POST",f"/indexes/{generation.uid}/documents/delete-batch",list(map(str,ids))))
            old.filter(pk__in=ids).update(keyword_ready=False,vector_ready=False)
    remove_source(generation, kind, source_id, keep_revision=header["source_revision"])
    with transaction.atomic():
        ProcessingJob.objects.select_for_update().get(pk=job.pk)
        if not _is_current(job, generation, header):
            raise DiscoveryIndexError("superseded", "资料已更新，旧任务不再回写完成状态。")
        _guard_job(job, stats={**job.stats, "documents": completed})
        DiscoverySourceState.objects.filter(pk=state.pk, job_id=job.pk).update(
            source_revision=header["source_revision"], expected_count=expected, completed_count=completed,
            indexed_at=timezone.now(), error="", updated_at=timezone.now())
    return True


def activate_generation(generation):
    with index_writer() as acquired:
        if not acquired:
            raise DiscoveryIndexError("writer_busy", "索引任务正在写入，请稍后再切换。")
        return _activate_generation(generation)


def deactivate_generation(generation):
    """Keep derived rows while making a 3.0.7 application rollback readable."""
    with index_writer() as acquired:
        if not acquired:
            raise DiscoveryIndexError("writer_busy", "索引任务正在写入，请先停止新增索引任务再回退。")
        with transaction.atomic():
            from catalog.models import SiteSetting
            lock, _ = SiteSetting.objects.get_or_create(key="discovery_build_lock", defaults={"value": {}})
            SiteSetting.objects.select_for_update().get(pk=lock.pk)
            generation = SemanticIndexVersion.discovery_objects.select_for_update().get(pk=generation.pk)
            if generation.status in {"building", "ready", "active"}:
                generation.status = "retired"
                generation.save(update_fields=["status", "updated_at"])
            ProcessingJob.objects.filter(job_type=JOB_TYPE, stats__generation_id=str(generation.pk),
                status__in=[*OPEN, "paused"]).update(status="canceled", error_code="application_rollback",
                    error_message="应用已回退；派生索引和已完成资料保留。", finished_at=timezone.now(), updated_at=timezone.now())
            return generation


def verify_current_sources(generation):
    states = {(row.source_type, str(row.source_id)): row for row in
              DiscoverySourceState.objects.filter(generation=generation)}
    current = set()
    for kind in SOURCE_TYPES:
        for source, header in iter_source_headers(kind):
            key = (kind, str(source.pk))
            current.add(key)
            state = states.get(key)
            if (state is None or state.source_revision != header["source_revision"] or not state.indexed_at
                    or state.error or state.completed_count != state.expected_count):
                raise DiscoveryIndexError("source_changed", "来源已更新或尚未处理完成，请等待协调任务更新后再切换。")
    if set(states) != current:
        raise DiscoveryIndexError("source_changed", "部分来源已撤下，请等待协调任务清理派生索引后再切换。")


@transaction.atomic
def _activate_generation(generation):
    # Lock one stable row so concurrent builds cannot create two active versions.
    from catalog.models import SiteSetting
    lock, _ = SiteSetting.objects.get_or_create(key="discovery_build_lock", defaults={"value": {}})
    SiteSetting.objects.select_for_update().get(pk=lock.pk)
    generation = SemanticIndexVersion.discovery_objects.select_for_update().get(pk=generation.pk)
    if generation.status not in {"ready", "retired"}:
        raise DiscoveryIndexError("not_ready", "该索引版本尚未准备好。")
    verify_current_sources(generation)
    stats = meili("GET", f"/indexes/{generation.uid}/stats")
    actual_count = DiscoveryDocument.objects.filter(generation=generation, keyword_ready=True).count()
    if stats.get("isIndexing") or stats.get("numberOfDocuments") != actual_count:
        raise DiscoveryIndexError("count_mismatch", "索引写入数量未核对完成，保留当前版本。")
    SemanticIndexVersion.discovery_objects.filter(status="active").exclude(pk=generation.pk).update(status="retired")
    generation.status, generation.activated_at = "active", timezone.now()
    generation.document_count = generation.expected_document_count = actual_count
    generation.save(update_fields=["status", "activated_at", "document_count", "expected_document_count", "updated_at"])
    return generation


def finish_builds():
    for generation in SemanticIndexVersion.discovery_objects.filter(status__in=["building", "ready"], config_snapshot__index_configured=True):
        pending = schedule_sources(generation)
        if pending:
            if generation.status == "ready":
                generation.status = "building"
                generation.save(update_fields=["status", "updated_at"])
                ProcessingJob.objects.filter(job_type=JOB_TYPE, stats__action="build",
                    stats__generation_id=str(generation.pk), status="succeeded").update(
                        status="running", progress=5, finished_at=None, updated_at=timezone.now())
            sources = DiscoverySourceState.objects.filter(generation=generation)
            total = sources.count()
            failed = sources.filter(job__status="failed", job__attempt__gte=F("job__max_attempts")).count()
            coordinators = ProcessingJob.objects.filter(job_type=JOB_TYPE, stats__action="build",
                stats__generation_id=str(generation.pk), status__in=["running", "paused"])
            for coordinator in coordinators:
                ProcessingJob.objects.filter(pk=coordinator.pk, task_id=coordinator.task_id, status__in=["running", "paused"]).update(
                    status="paused" if failed else "running", progress=min(95, max(5, int((total - pending) * 90 / max(total, 1)))),
                    stats={**coordinator.stats, "pending_sources": pending, "blocked_sources": failed},
                    error_message="部分来源多次失败，请重试对应任务后继续。" if failed else "", updated_at=timezone.now())
            continue
        count = DiscoveryDocument.objects.filter(generation=generation, keyword_ready=True).count()
        stats = meili("GET", f"/indexes/{generation.uid}/stats")
        if stats.get("isIndexing") or stats.get("numberOfDocuments") != count:
            continue
        generation.document_count = generation.expected_document_count = count
        generation.status, generation.error_message = "ready", ""
        generation.validation_details = {"all_current_sources_complete": True, "meili_document_count": count,
                                         "verified_at": timezone.now().isoformat()}
        generation.save()
        if generation.config_snapshot.get("activate"):
            activate_generation(generation)
        ProcessingJob.objects.filter(job_type=JOB_TYPE, stats__action="build", stats__generation_id=str(generation.pk)).update(
            status="succeeded", progress=100, finished_at=timezone.now(), error_message="")


def run_job(job_id, task_id):
    with index_writer() as acquired:
        if not acquired:
            if ProcessingJob.objects.filter(pk=job_id, task_id=task_id, status="pending").exists():
                _dispatch(job_id, task_id, countdown=15)
            return
        return _run_job(job_id, task_id)


def _run_job(job_id, task_id):
    with transaction.atomic():
        job = ProcessingJob.objects.select_for_update().filter(pk=job_id, task_id=task_id, status="pending", job_type=JOB_TYPE).first()
        if not job:
            return
        job.status, job.started_at = "running", timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])
    try:
        if job.stats["action"] == "build":
            generation = _prepare_generation(job)
            ensure_index(generation)
            if not ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").exists():
                raise DiscoveryIndexError("superseded", "建立任务已更新，旧任务已停止。")
            generation.config_snapshot = {**generation.config_snapshot, "index_configured": True}
            generation.save(update_fields=["config_snapshot", "updated_at"])
            schedule_sources(generation)
            # Coordinator is settled by finish_builds; no long-running poll task.
            _guard_job(job, progress=5)
        else:
            generation = SemanticIndexVersion.discovery_objects.get(pk=job.stats["generation_id"])
            completed = process_source(job, generation)
            if not completed:
                with transaction.atomic():
                    current = ProcessingJob.objects.select_for_update().filter(pk=job.pk, task_id=task_id, status="running").first()
                    if current:
                        _enqueue_job(current)
                return
            ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(
                status="succeeded", progress=100, finished_at=timezone.now(), error_message="")
        finish_builds()
    except Exception as exc:
        code = getattr(exc, "code", "index_job_failed")
        if code == "inference_busy":
            # Reader reranking shares one bounded CPU model process. Admission
            # pressure is a queued wait, not three rapid permanent failures.
            with transaction.atomic():
                current = ProcessingJob.objects.select_for_update().filter(pk=job.pk, task_id=task_id, status="running").first()
                if current:
                    next_id = str(uuid4())
                    _guard_job(current, status="pending", task_id=next_id,
                        error_code="waiting_model", error_message="本地模型正在处理其他请求，索引将自动继续。")
                    transaction.on_commit(lambda: _dispatch(job.pk, next_id, countdown=20))
            return
        superseded = code == "superseded"
        message = str(exc) if isinstance(exc, (DiscoveryIndexError, DiscoveryInferenceError)) else "索引任务失败，已完成文字保留，请重试或查看服务日志。"
        changed = ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(
            status="canceled" if superseded else "failed", error_code=code, error_message=message[:500],
            error_kind="retryable", attempt=job.attempt + 1, finished_at=timezone.now())
        if changed and job.stats.get("action") == "source":
            DiscoverySourceState.objects.filter(generation_id=job.stats["generation_id"], source_type=job.stats["source_type"],
                source_id=job.stats["source_id"], job_id=job.pk).update(error=message[:500])
        logger.warning("Discovery job %s failed: %s", job.pk, type(exc).__name__)


def reconcile():
    if not enabled():
        return {"enabled": False}
    with index_writer() as acquired:
        if not acquired:
            return {"busy": True}
        return _reconcile()


def discovery_recovery_window(job):
    if job.stats.get("action") == "build" and job.stats.get("generation_id") and job.progress >= 5:
        return job.updated_at, None
    return job.updated_at, RUNNING_STALLED_SECONDS if job.status == "running" else QUEUED_STALLED_SECONDS


def recover_interrupted_job(job_id):
    # Never replace a live writer, even if its model call has taken unusually long.
    with index_writer() as acquired:
        if not acquired:
            raise DiscoveryIndexError("writer_busy", "索引处理服务仍持有写入锁，请继续等待并核对服务状态。")
        with transaction.atomic():
            job = ProcessingJob.objects.select_for_update().get(pk=job_id, job_type=JOB_TYPE)
            last, seconds = discovery_recovery_window(job)
            if job.status not in OPEN or seconds is None or last + timedelta(seconds=seconds) > timezone.now():
                raise DiscoveryIndexError("active", "任务已恢复活动或正在正常等待来源，请重新读取。")
            if job.attempt >= job.max_attempts or job.status == "running" and job.attempt + 1 >= job.max_attempts:
                raise DiscoveryIndexError("exhausted", "已到恢复次数边界，请等待原恢复结果后明确重试。")
            if job.stats.get("action") == "source":
                try:
                    generation_id = UUID(str(job.stats.get("generation_id")))
                    source_id = UUID(str(job.stats.get("source_id")))
                except ValueError as exc:
                    raise DiscoveryIndexError("invalid_source", "原任务的来源标识不完整，请从索引维护入口核对。") from exc
                source_type = job.stats.get("source_type")
                if source_type not in SOURCE_TYPES or not job.stats.get("source_revision"):
                    raise DiscoveryIndexError("invalid_source", "原任务的来源类型或修订缺失，请从索引维护入口核对。")
                generation = SemanticIndexVersion.discovery_objects.filter(pk=generation_id, status__in=["building", "ready", "active"]).first()
                header = get_source(source_type, source_id)[1]
                state = DiscoverySourceState.objects.filter(generation=generation, source_type=source_type, source_id=source_id, job=job).first()
                if not generation or not state or not header or header["source_revision"] != job.stats["source_revision"]:
                    raise DiscoveryIndexError("superseded", "原索引来源、修订或任务归属已变化，请查看当前材料的处理任务。")
            elif job.stats.get("action") != "build":
                raise DiscoveryIndexError("unknown_action", "无法核对原索引任务用途，请从索引维护入口检查。")
            elif job.stats.get("generation_id"):
                try:
                    generation_id = UUID(str(job.stats["generation_id"]))
                except ValueError as exc:
                    raise DiscoveryIndexError("invalid_source", "原任务的索引代际标识不完整，请核对原任务。") from exc
                if not SemanticIndexVersion.discovery_objects.filter(pk=generation_id, status="building").exists():
                    raise DiscoveryIndexError("superseded", "原索引代际已不在构建中，请查看当前索引状态。")
            if job.status == "pending" and job.task_id:
                # Preserve a queued delivery's identity; an occupied queue is not a dead worker.
                job.save(update_fields=["updated_at"])
                transaction.on_commit(lambda jid=str(job.pk), tid=job.task_id: _dispatch(jid, tid))
            else:
                interrupted = job.status == "running"
                job.stats = {**job.stats, "recovery": {"reason": "worker_interrupted" if interrupted else "broker_notification_lost", "previous_task_id": job.task_id, "requeued_at": timezone.now().isoformat()}}
                if interrupted:
                    job.attempt += 1
                job.save(update_fields=["stats", "attempt"])
                _enqueue_job(job)
            return job


def _reconcile():
    stale = timezone.now() - timedelta(seconds=RUNNING_STALLED_SECONDS)
    # Eight queued sources can each use a four-minute CPU slice. Waiting behind
    # those tasks is not a lost worker lease; only running work uses 15 minutes.
    queued_stale = timezone.now() - timedelta(seconds=QUEUED_STALLED_SECONDS)
    interrupted = Q(status="running", updated_at__lt=stale) | Q(status="pending", updated_at__lt=queued_stale)
    for job in ProcessingJob.objects.filter(interrupted, job_type=JOB_TYPE)[:20]:
        if discovery_recovery_window(job)[1] is None:
            # This coordinator intentionally sleeps between source tasks.
            continue
        ProcessingJob.objects.filter(interrupted, pk=job.pk, task_id=job.task_id).update(
            status="failed", error_code="worker_interrupted", error_kind="retryable",
            error_message="索引任务中断，已完成部分保留。", attempt=F("attempt") + 1,
            finished_at=timezone.now(), updated_at=timezone.now())
    generation = active_generation()
    pending = schedule_sources(generation) if generation else 0
    finish_builds()
    return {"pending_sources": pending}
