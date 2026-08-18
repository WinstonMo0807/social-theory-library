from __future__ import annotations

import time
import uuid
from datetime import timedelta
from urllib.parse import urlsplit, urlunsplit

import httpx
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import OperationalError as KombuOperationalError

from catalog.models import (
    Asset,
    Edition,
    OcrStatus,
    PublicationState,
    SemanticChunk,
    SemanticIndexJob,
    SemanticIndexStatus,
    SemanticIndexVersion,
    SiteSetting,
)
from catalog.services.semantic_chunks import (
    CHUNK_VERSION,
    PARSER_VERSION,
    build_semantic_chunks,
)
from catalog.services.passage_language import language_detector_config
from ingestion.services.indexing import _headers, _wait_task


SEMANTIC_INDEX_UID = "semantic_passages"
SEMANTIC_PAUSE_KEY = "semantic_index_paused"
MANUAL_ACTIVATION_MODE = "manual"
SEMANTIC_INDEX_PROTOCOL_VERSION = "v2"
DEFAULT_SEMANTIC_DOCUMENT_BATCH_SIZE = 128
MAX_SEMANTIC_DOCUMENT_BATCH_SIZE = 1000
DEFAULT_DOCUMENT_TEMPLATE = (
    "{{doc.title}}\n{{doc.authors}}\n{{doc.chapter_title}}\n"
    "{{doc.section_title}}\n{{doc.original_text}}"
)
SNAPSHOT_RUNTIME_FIELDS = (
    "enabled",
    "engine",
    "provider",
    "embedder_name",
    "model",
    "model_repo_id",
    "model_local_path",
    "model_revision",
    "dimensions",
    "pooling",
    "offline_mode",
    "semantic_ratio",
    "reranker",
    "query_rewrite_enabled",
    "max_results_per_work",
    "api_key_configured",
    "external_text_warning",
    "saved_configuration_version",
)
SNAPSHOT_VIEWPOINT_V2_FIELDS = (
    "enabled",
    "profile",
    "dense_top_k",
    "sparse_top_k",
    "fusion_top_k",
    "rerank_top_k",
    "final_top_k",
    "query_expansion_enabled",
    "query_expansion_max",
    "rerank_provider",
    "rerank_model",
    "rerank_service_configured",
)
EFFECTIVE_RUNTIME_FIELDS = (
    "engine",
    "provider",
    "embedder_name",
    "model",
    "model_repo_id",
    "model_local_path",
    "model_revision",
    "dimensions",
    "pooling",
    "offline_mode",
    "endpoint",
    "service_url",
    "semantic_ratio",
    "reranker",
    "query_rewrite_enabled",
    "max_results_per_work",
)


class SemanticIndexVersionRequired(RuntimeError):
    """Raised when an index write cannot be bound to one unambiguous version."""

    error_code = "INDEX_VERSION_REQUIRED"


class SemanticModelUnavailable(RuntimeError):
    """Raised when the configured offline embedding model is not on disk."""

    error_code = "MODEL_UNAVAILABLE"


def active_semantic_index_version() -> SemanticIndexVersion:
    """Return the only active version allowed to receive incremental writes.

    The historical UID fallback remains available to read-only search code, but
    writes must never guess a target when the database has zero or multiple
    active version rows.
    """

    active = list(
        SemanticIndexVersion.objects.filter(
            status=SemanticIndexVersion.Status.ACTIVE,
        ).order_by("-activated_at", "-created_at")[:2]
    )
    if len(active) != 1:
        raise SemanticIndexVersionRequired(
            "语义索引写入需要且只能有一个 active SemanticIndexVersion。"
        )
    return active[0]


def _write_index_version(
    index_version: SemanticIndexVersion | None,
) -> SemanticIndexVersion:
    if index_version is not None:
        return index_version
    return active_semantic_index_version()


def active_semantic_index_uid() -> str:
    active = SemanticIndexVersion.objects.filter(
        status=SemanticIndexVersion.Status.ACTIVE,
    ).order_by("-activated_at", "-created_at").first()
    return active.uid if active else SEMANTIC_INDEX_UID


def semantic_index_paused() -> bool:
    stored = SiteSetting.objects.filter(key=SEMANTIC_PAUSE_KEY).first()
    return bool(stored and stored.value is True)


def _secret_free_service_url(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname or ""
        if not parsed.scheme or not host:
            return ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        netloc = host
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except (TypeError, ValueError):
        return ""


def semantic_index_config_snapshot(config: dict) -> dict:
    """Return the immutable, secret-free inputs needed to rebuild one index."""

    snapshot = {
        key: config.get(key)
        for key in SNAPSHOT_RUNTIME_FIELDS
        if key in config
    }
    viewpoint_v2 = config.get("viewpoint_v2")
    if isinstance(viewpoint_v2, dict):
        snapshot["viewpoint_v2"] = {
            key: viewpoint_v2.get(key)
            for key in SNAPSHOT_VIEWPOINT_V2_FIELDS
            if key in viewpoint_v2
        }
    service_url = _secret_free_service_url(
        config.get("service_url") or config.get("endpoint")
    )
    snapshot.update(
        {
            "protocol_version": SEMANTIC_INDEX_PROTOCOL_VERSION,
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
            "language_detector": language_detector_config(),
            "document_template": str(
                config.get("document_template") or DEFAULT_DOCUMENT_TEMPLATE
            ),
            "service_url": service_url,
            "endpoint": service_url,
        }
    )
    return snapshot


def semantic_index_version_runtime(
    version: SemanticIndexVersion | None,
) -> dict | None:
    if version is None or not isinstance(version.config_snapshot, dict):
        return None
    return dict(version.config_snapshot) if version.config_snapshot else None


def semantic_document_batch_size(value: int | None = None) -> int:
    configured = (
        value
        if value is not None
        else getattr(
            settings,
            "SEMANTIC_INDEX_DOCUMENT_BATCH_SIZE",
            DEFAULT_SEMANTIC_DOCUMENT_BATCH_SIZE,
        )
    )
    return min(MAX_SEMANTIC_DOCUMENT_BATCH_SIZE, max(1, int(configured)))


def index_semantic_documents_in_batches(
    index_uid: str,
    documents: list[dict],
    *,
    document_batch_size: int | None = None,
) -> dict:
    """Idempotently upsert a bounded document batch sequence into Meilisearch."""

    batch_size = semantic_document_batch_size(document_batch_size)
    tasks: list[dict] = []
    for offset in range(0, len(documents), batch_size):
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/documents",
            headers=_headers(),
            json=documents[offset : offset + batch_size],
            timeout=max(30, settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS),
        )
        response.raise_for_status()
        tasks.append(
            _wait_task(
                response.json(),
                timeout=settings.SEMANTIC_INDEX_TASK_TIMEOUT_SECONDS,
            )
        )
    return {
        "documents": len(documents),
        "batches": len(tasks),
        "document_batch_size": batch_size,
        "task": tasks[-1] if tasks else None,
    }


def semantic_runtime_setting_value(config: dict) -> dict:
    """Return only fields consumed by ``current_semantic_runtime``.

    Version snapshots also contain protocol, parser and diagnostic metadata.
    Those values remain on the version and are never copied into the mutable
    effective setting.
    """

    return {
        key: config.get(key)
        for key in EFFECTIVE_RUNTIME_FIELDS
        if key in config
    }


def set_semantic_index_paused(paused: bool, *, actor=None) -> dict[str, int]:
    SiteSetting.objects.update_or_create(
        key=SEMANTIC_PAUSE_KEY,
        defaults={"value": bool(paused), "public": False, "updated_by": actor},
    )
    if not paused:
        return {"jobs_paused": 0, "jobs_pause_requested": 0}

    now = timezone.now()
    queued = SemanticIndexJob.objects.filter(
        status=SemanticIndexJob.Status.QUEUED,
    ).update(
        status=SemanticIndexJob.Status.PAUSED,
        task_id="",
        pause_requested_at=now,
        updated_at=now,
    )
    running = SemanticIndexJob.objects.filter(
        status=SemanticIndexJob.Status.RUNNING,
        pause_requested_at__isnull=True,
    ).update(pause_requested_at=now, updated_at=now)
    return {"jobs_paused": queued, "jobs_pause_requested": running}


def _semantic_pause_requested(job: SemanticIndexJob) -> bool:
    job.refresh_from_db(
        fields=["status", "task_id", "pause_requested_at", "updated_at"]
    )
    return bool(
        job.status == SemanticIndexJob.Status.PAUSED
        or job.pause_requested_at
        or semantic_index_paused()
    )


def _mark_semantic_job_paused(
    job: SemanticIndexJob,
    *,
    stage: str,
) -> SemanticIndexJob:
    job.status = SemanticIndexJob.Status.PAUSED
    job.task_id = ""
    job.pause_requested_at = job.pause_requested_at or timezone.now()
    job.finished_at = None
    job.stats = {**(job.stats or {}), "paused_at_stage": stage}
    job.save(
        update_fields=[
            "status",
            "task_id",
            "pause_requested_at",
            "finished_at",
            "stats",
            "updated_at",
        ]
    )
    if job.asset_id:
        job.asset.semantic_chunks.filter(
            index_status=SemanticChunk.IndexStatus.INDEXING,
        ).update(
            index_status=SemanticChunk.IndexStatus.PENDING,
            updated_at=timezone.now(),
        )
        Edition.objects.filter(pk=job.asset.edition_id).update(
            semantic_index_status=SemanticIndexStatus.PENDING,
            updated_at=timezone.now(),
        )
    return job


def request_semantic_job_pause(job: SemanticIndexJob) -> SemanticIndexJob:
    if job.status == SemanticIndexJob.Status.PAUSED:
        return job
    if job.status not in {
        SemanticIndexJob.Status.QUEUED,
        SemanticIndexJob.Status.RUNNING,
    }:
        raise ValueError("该语义任务当前不能暂停。")
    job.pause_requested_at = timezone.now()
    if job.status == SemanticIndexJob.Status.QUEUED:
        job.status = SemanticIndexJob.Status.PAUSED
        job.task_id = ""
    job.save(
        update_fields=["pause_requested_at", "status", "task_id", "updated_at"]
    )
    return job


def resume_semantic_job(job: SemanticIndexJob, *, actor=None) -> SemanticIndexJob:
    if semantic_index_paused():
        raise ValueError("语义索引仍处于全局暂停状态。")
    if job.status == SemanticIndexJob.Status.RUNNING and job.pause_requested_at:
        job.pause_requested_at = None
        job.save(update_fields=["pause_requested_at", "updated_at"])
        return job
    if job.status != SemanticIndexJob.Status.PAUSED:
        raise ValueError("只有已暂停的语义任务可以恢复。")
    if job.asset_id is None:
        raise ValueError("语义任务目标 PDF 已不存在。")
    if not _bind_legacy_job_version(job):
        raise SemanticIndexVersionRequired(job.error_message)

    task_id = str(uuid.uuid4())
    job.status = SemanticIndexJob.Status.QUEUED
    job.task_id = task_id
    job.pause_requested_at = None
    job.error_code = ""
    job.error_message = ""
    job.finished_at = None
    if actor is not None and job.requested_by_id is None:
        job.requested_by = actor
    job.save(
        update_fields=[
            "status",
            "task_id",
            "pause_requested_at",
            "error_code",
            "error_message",
            "finished_at",
            "requested_by",
            "updated_at",
        ]
    )
    Edition.objects.filter(pk=job.asset.edition_id).update(
        semantic_index_status=SemanticIndexStatus.PENDING,
        updated_at=timezone.now(),
    )
    transaction.on_commit(lambda: dispatch_semantic_job(str(job.id), task_id))
    return job


def ensure_semantic_index(config: dict | None = None, *, index_uid: str | None = None) -> None:
    from catalog.services.semantic_search import current_semantic_runtime, semantic_model_health

    config = config or current_semantic_runtime()
    index_uid = index_uid or active_semantic_index_version().uid
    if (
        config.get("engine") == "meilisearch_hybrid"
        and config.get("provider") == "huggingFace"
        and config.get("offline_mode")
    ):
        model_health = semantic_model_health(config)
        if not model_health["available"]:
            raise SemanticModelUnavailable(
                model_health.get("reason") or "本地语义模型不可用。"
            )
    base_url = settings.MEILISEARCH_URL.rstrip("/")
    response = httpx.get(f"{base_url}/indexes/{index_uid}", headers=_headers(), timeout=5)
    if response.status_code == 404:
        created = httpx.post(
            f"{base_url}/indexes",
            headers=_headers(),
            json={"uid": index_uid, "primaryKey": "id"},
            timeout=5,
        )
        created.raise_for_status()
        _wait_task(created.json())
    else:
        response.raise_for_status()

    desired = {
        "searchableAttributes": [
            "title",
            "authors",
            "chapter_title",
            "section_title",
            "original_text",
            "normalized_text",
        ],
        "filterableAttributes": [
            "asset_id",
            "edition_id",
            "work_id",
            "document_id",
            "document_type",
            "language",
            "access_status",
            "publication_year",
            "author_ids",
            "theory_slugs",
            "topic_slugs",
            "concept_slugs",
            "is_public",
        ],
        "displayedAttributes": [
            "id",
            "document_id",
            "asset_id",
            "edition_id",
            "edition_slug",
            "work_id",
            "title",
            "authors",
            "document_type",
            "language",
            "access_status",
            "publication_year",
            "page_start",
            "page_end",
            "chapter_title",
            "section_title",
            "original_text",
            "context_before",
            "context_after",
            "locators",
            "quality_flags",
            "theory_slugs",
            "topic_slugs",
            "concept_slugs",
            "is_public",
        ],
        "searchCutoffMs": 1600,
    }
    updated = httpx.patch(
        f"{base_url}/indexes/{index_uid}/settings",
        headers=_headers(),
        json=desired,
        timeout=10,
    )
    updated.raise_for_status()
    _wait_task(updated.json())

    if config.get("engine") == "meilisearch_hybrid":
        embedder = {
            "source": config["provider"],
            "model": config.get("model_repo_id") or config["model"],
            "documentTemplate": config.get("document_template")
            or DEFAULT_DOCUMENT_TEMPLATE,
        }
        if config["provider"] == "huggingFace":
            if config.get("model_revision"):
                embedder["revision"] = config["model_revision"]
            if config.get("pooling"):
                embedder["pooling"] = config["pooling"]
        if config["provider"] == "openAi":
            if not settings.SEMANTIC_EMBEDDING_API_KEY:
                raise ValueError("启用外部 Embedding 前必须配置密钥。")
            embedder["apiKey"] = settings.SEMANTIC_EMBEDDING_API_KEY
            if config.get("dimensions"):
                embedder["dimensions"] = config["dimensions"]
        if config["provider"] == "ollama" and config.get("service_url"):
            embedder["url"] = config["service_url"].rstrip("/")
        response = httpx.patch(
            f"{base_url}/indexes/{index_uid}/settings/embedders",
            headers=_headers(),
            json={config["embedder_name"]: embedder},
            timeout=settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        _wait_task(response.json(), timeout=120)


def _relations(work):
    relations = work.knowledge_relations.filter(approved=True).select_related(
        "theory_school", "topic", "concept"
    )
    return {
        "theories": [item.theory_school for item in relations if item.theory_school_id],
        "topics": [item.topic for item in relations if item.topic_id],
        "concepts": [item.concept for item in relations if item.concept_id],
    }


def semantic_documents(
    asset: Asset,
    *,
    runtime_config: dict | None = None,
) -> list[dict]:
    from catalog.services.semantic_search import current_semantic_runtime

    edition = asset.edition
    work = edition.work
    runtime = runtime_config if runtime_config is not None else current_semantic_runtime()
    model_name = str(runtime.get("model_repo_id") or runtime.get("model") or "")
    authors = list(
        edition.contributions.filter(approved=True)
        .order_by("order")
        .values_list("person__preferred_name", flat=True)
    )
    author_ids = list(
        edition.contributions.filter(approved=True).values_list("person_id", flat=True)
    )
    relations = _relations(work)
    is_public = (
        edition.state == PublicationState.PUBLISHED
        and asset.is_current
        and asset.status == Asset.Status.READY
    )
    return [
        {
            "id": str(chunk.id),
            "document_id": chunk.document_id,
            "asset_id": str(asset.id),
            "edition_id": str(edition.id),
            "edition_slug": edition.public_slug,
            "work_id": str(work.id),
            "title": work.title,
            "authors": authors,
            "author_ids": [str(value) for value in author_ids],
            "document_type": work.document_type,
            "language": chunk.language or "unknown",
            "access_status": asset.access_status,
            "publication_year": edition.publication_year,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "chapter_title": chunk.chapter_title,
            "section_title": chunk.section_title,
            "original_text": chunk.original_text,
            "normalized_text": chunk.normalized_text,
            "context_before": chunk.context_before,
            "context_after": chunk.context_after,
            "locators": chunk.locators,
            "quality_flags": chunk.quality_flags,
            "theory_slugs": [item.slug for item in relations["theories"]],
            "topic_slugs": [item.slug for item in relations["topics"]],
            "concept_slugs": [item.slug for item in relations["concepts"]],
            "is_public": is_public,
        }
        for chunk in asset.semantic_chunks.filter(
            parser_version=PARSER_VERSION,
            chunk_version=CHUNK_VERSION,
            embedding_model=model_name,
        ).order_by("order")
    ]


def _indexed_semantic_asset_document_ids(index_uid: str, asset_id: str) -> set[str]:
    base_url = settings.MEILISEARCH_URL.rstrip("/")
    document_ids: set[str] = set()
    offset = 0
    limit = 1000
    while True:
        response = httpx.post(
            f"{base_url}/indexes/{index_uid}/documents/fetch",
            headers=_headers(),
            json={
                "filter": f'asset_id = "{asset_id}"',
                "offset": offset,
                "limit": limit,
                "fields": ["id"],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        document_ids.update(str(item["id"]) for item in results if item.get("id"))
        total = int(payload.get("total") or len(document_ids))
        if offset + len(results) >= total:
            return document_ids
        if not results:
            raise RuntimeError("Meilisearch 语义文档分页提前结束。")
        offset += len(results)


def _remove_stale_semantic_asset_documents(
    index_uid: str,
    asset_id: str,
    current_ids: set[str],
) -> int:
    stale_ids = sorted(
        _indexed_semantic_asset_document_ids(index_uid, asset_id) - current_ids
    )
    for offset in range(0, len(stale_ids), 1000):
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/documents/delete-batch",
            headers=_headers(),
            json=stale_ids[offset : offset + 1000],
            timeout=30,
        )
        response.raise_for_status()
        _wait_task(response.json(), timeout=60)
    return len(stale_ids)


def _bind_legacy_job_version(job: SemanticIndexJob) -> bool:
    """Safely repair a historical null-version job before it can write."""

    if job.index_version_id:
        return True
    try:
        version = active_semantic_index_version()
    except SemanticIndexVersionRequired as exc:
        job.status = SemanticIndexJob.Status.FAILED
        job.error_code = exc.error_code
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "finished_at",
                "updated_at",
            ]
        )
        return False
    with transaction.atomic():
        updated = SemanticIndexJob.objects.filter(
            pk=job.pk,
            index_version__isnull=True,
        ).update(index_version=version, updated_at=timezone.now())
    if updated:
        job.index_version = version
        job.index_version_id = version.pk
    else:
        job.refresh_from_db(fields=["index_version"])
    return bool(job.index_version_id)


def index_semantic_asset(
    asset: Asset,
    *,
    index_version: SemanticIndexVersion | None = None,
    runtime_config: dict | None = None,
) -> dict:
    index_version = _write_index_version(index_version)
    runtime = (
        runtime_config
        if runtime_config is not None
        else semantic_index_version_runtime(index_version)
    )
    documents = semantic_documents(asset, runtime_config=runtime)
    try:
        index_uid = index_version.uid
        ensure_semantic_index(runtime, index_uid=index_uid)
        if not documents:
            removed = _remove_stale_semantic_asset_documents(
                index_uid,
                str(asset.id),
                set(),
            )
            synchronize_active_semantic_index_document_count(index_uid)
            return {
                "backend": "no-chunks",
                "index_uid": index_uid,
                "documents": 0,
                "removed_stale_documents": removed,
            }
        write_result = index_semantic_documents_in_batches(
            index_uid,
            documents,
        )
        asset.semantic_chunks.update(
            index_status=SemanticChunk.IndexStatus.READY,
            index_error="",
            indexed_at=timezone.now(),
            updated_at=timezone.now(),
        )
        removed = _remove_stale_semantic_asset_documents(
            index_uid,
            str(asset.id),
            {document["id"] for document in documents},
        )
        synchronize_active_semantic_index_document_count(index_uid)
        return {
            "backend": "meilisearch",
            "index_uid": index_uid,
            "documents": len(documents),
            "batches": write_result["batches"],
            "document_batch_size": write_result["document_batch_size"],
            "removed_stale_documents": removed,
            "task": write_result["task"],
        }
    except SemanticModelUnavailable:
        asset.semantic_chunks.filter(
            index_status=SemanticChunk.IndexStatus.INDEXING,
        ).update(
            index_status=SemanticChunk.IndexStatus.READY,
            index_error="",
            updated_at=timezone.now(),
        )
        raise
    except (httpx.HTTPError, RuntimeError, TimeoutError, ValueError) as exc:
        asset.semantic_chunks.update(
            index_status=SemanticChunk.IndexStatus.FAILED,
            index_error=str(exc)[:2000],
            updated_at=timezone.now(),
        )
        if settings.SEMANTIC_SEARCH_REQUIRED:
            raise
        return {"backend": "database-fallback", "documents": len(documents), "warning": str(exc)}


def remove_semantic_asset(asset_id: str) -> None:
    try:
        index_uid = active_semantic_index_version().uid
    except SemanticIndexVersionRequired:
        # A missing or ambiguous active version must never turn into a write
        # against the historical fallback UID. Callers can record the warning
        # and continue their source-of-truth operation independently.
        return
    try:
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/documents/delete",
            headers=_headers(),
            json={"filter": f'asset_id = "{asset_id}"'},
            timeout=15,
        )
        if response.status_code == 404:
            return
        response.raise_for_status()
        _wait_task(response.json(), timeout=30)
        synchronize_active_semantic_index_document_count(index_uid)
    except (httpx.HTTPError, RuntimeError, TimeoutError):
        if settings.SEMANTIC_SEARCH_REQUIRED:
            raise


def run_semantic_index_job(job_id: str, *, task_id: str = "") -> SemanticIndexJob:
    job = SemanticIndexJob.objects.select_related(
        "asset__edition__work",
        "index_version",
    ).get(pk=job_id)
    if task_id and job.task_id != task_id:
        return job
    if job.status == SemanticIndexJob.Status.CANCELED:
        return job
    if job.asset is None:
        job.status = SemanticIndexJob.Status.CANCELED
        job.error_message = "目标 PDF 已不存在。"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        return job
    if not _bind_legacy_job_version(job):
        return job
    if _semantic_pause_requested(job):
        return _mark_semantic_job_paused(job, stage="before_chunk_build")

    started = time.monotonic()
    runtime_config = semantic_index_version_runtime(job.index_version)
    job.status = SemanticIndexJob.Status.RUNNING
    job.started_at = timezone.now()
    job.attempts += 1
    job.progress = 5
    job.save(update_fields=["status", "started_at", "attempts", "progress", "updated_at"])
    job.asset.edition.semantic_index_status = SemanticIndexStatus.RUNNING
    job.asset.edition.save(update_fields=["semantic_index_status", "updated_at"])
    candidate_extraction_stats = {}
    try:
        job.asset.semantic_chunks.update(index_status=SemanticChunk.IndexStatus.INDEXING)
        chunks = build_semantic_chunks(
            job.asset,
            force=job.operation == SemanticIndexJob.Operation.REBUILD,
            runtime_config=runtime_config,
        )
        job.progress = 55
        job.save(update_fields=["progress", "updated_at"])
        try:
            from ingestion.services.processing import (
                queue_query_lexicon_candidate_job,
            )

            candidate_job = queue_query_lexicon_candidate_job(
                job.asset,
                actor=job.requested_by,
            )
            candidate_extraction_stats = {
                "query_lexicon_candidate_job_id": str(candidate_job.id),
                "query_lexicon_candidate_job_status": candidate_job.status,
            }
        except Exception as exc:
            # Candidate discovery is enrichment. Its durable job can be
            # repaired independently and must never fail semantic indexing.
            candidate_extraction_stats = {
                "query_lexicon_candidate_warning": str(exc)[:2000],
            }
        if _semantic_pause_requested(job):
            job.model_name = chunks[0].embedding_model if chunks else ""
            job.chunk_version = CHUNK_VERSION
            job.stats = {
                **(job.stats or {}),
                "chunks": len(chunks),
                "runtime_protocol": (
                    runtime_config or {}
                ).get("protocol_version", "legacy"),
                **candidate_extraction_stats,
            }
            job.save(
                update_fields=[
                    "model_name",
                    "chunk_version",
                    "stats",
                    "updated_at",
                ]
            )
            return _mark_semantic_job_paused(job, stage="chunks_persisted")
        result = index_semantic_asset(
            job.asset,
            index_version=job.index_version,
            runtime_config=runtime_config,
        ) if settings.SEMANTIC_SEARCH_ENABLED else {
            "backend": "disabled",
            "documents": len(chunks),
        }
        elapsed = round(time.monotonic() - started, 3)
        if _semantic_pause_requested(job):
            job.progress = 90
            job.model_name = chunks[0].embedding_model if chunks else ""
            job.chunk_version = CHUNK_VERSION
            job.stats = {
                **result,
                "chunks": len(chunks),
                "elapsed_seconds": elapsed,
                "runtime_protocol": (
                    runtime_config or {}
                ).get("protocol_version", "legacy"),
                **candidate_extraction_stats,
            }
            job.save(
                update_fields=[
                    "progress",
                    "model_name",
                    "chunk_version",
                    "stats",
                    "updated_at",
                ]
            )
            return _mark_semantic_job_paused(job, stage="remote_index_completed")
        job.status = (
            SemanticIndexJob.Status.PARTIAL
            if result.get("backend") == "database-fallback"
            else SemanticIndexJob.Status.COMPLETED
        )
        job.progress = 100
        job.stats = {
            **result,
            "chunks": len(chunks),
            "elapsed_seconds": elapsed,
            **candidate_extraction_stats,
        }
        job.model_name = chunks[0].embedding_model if chunks else ""
        job.chunk_version = CHUNK_VERSION
        job.error_code = ""
        job.error_message = result.get("warning", "")[:2000]
        job.finished_at = timezone.now()
        job.save()
        job.asset.edition.semantic_index_status = (
            SemanticIndexStatus.READY
            if result.get("backend") == "meilisearch"
            else SemanticIndexStatus.FAILED
        )
        job.asset.edition.save(update_fields=["semantic_index_status", "updated_at"])
        if job.index_version_id:
            if job.status == SemanticIndexJob.Status.COMPLETED:
                activated = maybe_activate_semantic_index_version(job.index_version)
                if not activated:
                    dispatch_semantic_version_batch(
                        job.index_version_id,
                        batch_size=settings.SEMANTIC_INDEX_STAGE_BATCH_SIZE,
                    )
            else:
                SemanticIndexVersion.objects.filter(pk=job.index_version_id).update(
                    status=SemanticIndexVersion.Status.FAILED,
                    error_message="候选索引任务降级为数据库检索，生产索引未切换。",
                    updated_at=timezone.now(),
                )
    except Exception as exc:
        job.status = SemanticIndexJob.Status.FAILED
        job.error_code = getattr(exc, "error_code", exc.__class__.__name__)
        job.error_message = str(exc)[:4000]
        job.finished_at = timezone.now()
        job.save()
        if isinstance(exc, SemanticModelUnavailable):
            job.asset.semantic_chunks.filter(
                index_status=SemanticChunk.IndexStatus.INDEXING,
            ).update(
                index_status=SemanticChunk.IndexStatus.READY,
                index_error="",
                updated_at=timezone.now(),
            )
        job.asset.edition.semantic_index_status = SemanticIndexStatus.FAILED
        job.asset.edition.save(update_fields=["semantic_index_status", "updated_at"])
        if job.index_version_id:
            SemanticIndexVersion.objects.filter(pk=job.index_version_id).update(
                status=SemanticIndexVersion.Status.FAILED,
                error_message=str(exc)[:4000],
                updated_at=timezone.now(),
            )
        raise
    return job


def create_semantic_job(
    asset: Asset,
    *,
    force: bool = False,
    actor=None,
    index_version: SemanticIndexVersion | None = None,
    deferred: bool = False,
) -> SemanticIndexJob | None:
    # Reuse an already queued/running job before resolving the active version.
    # A temporary version-management outage must not turn an idempotent enqueue
    # into a second failure when the existing job already has its own target.
    if not force:
        pending = asset.semantic_index_jobs.filter(
            status__in=[SemanticIndexJob.Status.QUEUED, SemanticIndexJob.Status.RUNNING],
        ).first()
        if pending:
            return pending

    index_version = _write_index_version(index_version)
    if deferred:
        return SemanticIndexJob.objects.create(
            operation=SemanticIndexJob.Operation.REBUILD if force else SemanticIndexJob.Operation.BUILD,
            status=SemanticIndexJob.Status.PAUSED,
            asset=asset,
            requested_by=actor,
            chunk_version=CHUNK_VERSION,
            index_version=index_version,
        )
    if semantic_index_paused():
        return SemanticIndexJob.objects.create(
            operation=SemanticIndexJob.Operation.REBUILD if force else SemanticIndexJob.Operation.BUILD,
            status=SemanticIndexJob.Status.PAUSED,
            asset=asset,
            requested_by=actor,
            chunk_version=CHUNK_VERSION,
            index_version=index_version,
            pause_requested_at=timezone.now(),
        )
    return SemanticIndexJob.objects.create(
        operation=SemanticIndexJob.Operation.REBUILD if force else SemanticIndexJob.Operation.BUILD,
        asset=asset,
        requested_by=actor,
        chunk_version=CHUNK_VERSION,
        index_version=index_version,
    )


def queue_semantic_job(
    asset: Asset,
    *,
    force: bool = False,
    actor=None,
    index_version: SemanticIndexVersion | None = None,
) -> SemanticIndexJob | None:
    try:
        job = create_semantic_job(
            asset,
            force=force,
            actor=actor,
            index_version=index_version,
        )
    except SemanticIndexVersionRequired as exc:
        # Semantic indexing is derived enrichment. Record a durable, explicit
        # failure while allowing upload/publication and stored page text to
        # complete. A later retry with one active version can create a fresh
        # queued job; repeated failed enqueues remain idempotent for this asset.
        if not force:
            existing_failure = asset.semantic_index_jobs.filter(
                status=SemanticIndexJob.Status.FAILED,
                error_code=exc.error_code,
            ).order_by("-created_at").first()
            if existing_failure:
                return existing_failure
        job = SemanticIndexJob.objects.create(
            operation=(
                SemanticIndexJob.Operation.REBUILD
                if force
                else SemanticIndexJob.Operation.BUILD
            ),
            status=SemanticIndexJob.Status.FAILED,
            asset=asset,
            requested_by=actor,
            chunk_version=CHUNK_VERSION,
            error_code=exc.error_code,
            error_message=str(exc)[:4000],
            finished_at=timezone.now(),
        )
        Edition.objects.filter(pk=asset.edition_id).update(
            semantic_index_status=SemanticIndexStatus.FAILED,
            updated_at=timezone.now(),
        )
        return job
    if job is None or job.status == SemanticIndexJob.Status.PAUSED:
        return job
    if job.task_id:
        return job
    task_id = str(uuid.uuid4())
    SemanticIndexJob.objects.filter(pk=job.pk).update(
        task_id=task_id,
        status=SemanticIndexJob.Status.QUEUED,
        error_code="",
        error_message="",
        finished_at=None,
    )
    if job.asset_id:
        Edition.objects.filter(pk=job.asset.edition_id).update(
            semantic_index_status=SemanticIndexStatus.PENDING,
            updated_at=timezone.now(),
        )
    job.task_id = task_id
    transaction.on_commit(lambda: dispatch_semantic_job(str(job.id), task_id))
    return job


@transaction.atomic
def dispatch_semantic_version_batch(
    version_or_id: SemanticIndexVersion | str,
    *,
    batch_size: int | None = None,
    retry_failed: bool = False,
) -> dict[str, int | str]:
    """Queue one bounded batch for a candidate semantic index."""

    version_id = getattr(version_or_id, "pk", version_or_id)
    version = SemanticIndexVersion.objects.select_for_update().get(pk=version_id)
    batch_size = max(
        1,
        min(int(batch_size or settings.SEMANTIC_INDEX_STAGE_BATCH_SIZE), 20),
    )
    if version.status in {
        SemanticIndexVersion.Status.ACTIVE,
        SemanticIndexVersion.Status.RETIRED,
    }:
        return {"queued": 0, "remaining": 0, "status": version.status}
    if semantic_index_paused():
        return {
            "queued": 0,
            "remaining": version.jobs.filter(
                status=SemanticIndexJob.Status.PAUSED
            ).count(),
            "status": version.status,
            "paused": 1,
        }
    if version.status == SemanticIndexVersion.Status.FAILED:
        if not retry_failed:
            return {
                "queued": 0,
                "remaining": version.jobs.filter(
                    status=SemanticIndexJob.Status.PAUSED
                ).count(),
                "status": version.status,
            }
        version.status = SemanticIndexVersion.Status.BUILDING
        version.error_message = ""
        version.save(update_fields=["status", "error_message", "updated_at"])
        version.jobs.filter(
            status__in=[
                SemanticIndexJob.Status.FAILED,
                SemanticIndexJob.Status.PARTIAL,
            ]
        ).update(
            status=SemanticIndexJob.Status.PAUSED,
            task_id="",
            pause_requested_at=None,
            progress=0,
            error_code="",
            error_message="",
            started_at=None,
            finished_at=None,
            updated_at=timezone.now(),
        )

    active = version.jobs.filter(
        status__in=[SemanticIndexJob.Status.QUEUED, SemanticIndexJob.Status.RUNNING]
    ).count()
    if active:
        return {
            "queued": 0,
            "active": active,
            "remaining": version.jobs.filter(
                status=SemanticIndexJob.Status.PAUSED
            ).count(),
            "status": version.status,
        }

    jobs = list(
        version.jobs.select_related("asset__edition")
        .filter(status=SemanticIndexJob.Status.PAUSED, asset__isnull=False)
        .order_by("created_at", "id")[:batch_size]
    )
    dispatches: list[tuple[str, str]] = []
    now = timezone.now()
    for job in jobs:
        task_id = str(uuid.uuid4())
        job.status = SemanticIndexJob.Status.QUEUED
        job.task_id = task_id
        job.pause_requested_at = None
        job.progress = 0
        job.error_code = ""
        job.error_message = ""
        job.started_at = None
        job.finished_at = None
        job.save(
            update_fields=[
                "status",
                "task_id",
                "pause_requested_at",
                "progress",
                "error_code",
                "error_message",
                "started_at",
                "finished_at",
                "updated_at",
            ]
        )
        Edition.objects.filter(pk=job.asset.edition_id).update(
            semantic_index_status=SemanticIndexStatus.PENDING,
            updated_at=now,
        )
        dispatches.append((str(job.id), task_id))
    for job_id, task_id in dispatches:
        transaction.on_commit(
            lambda job_id=job_id, task_id=task_id: dispatch_semantic_job(job_id, task_id)
        )
    return {
        "queued": len(dispatches),
        "active": len(dispatches),
        "remaining": version.jobs.filter(
            status=SemanticIndexJob.Status.PAUSED
        ).count(),
        "status": version.status,
    }


@transaction.atomic
def maybe_activate_semantic_index_version(version: SemanticIndexVersion) -> bool:
    version = SemanticIndexVersion.objects.select_for_update().get(pk=version.pk)
    if version.status in {SemanticIndexVersion.Status.ACTIVE, SemanticIndexVersion.Status.FAILED}:
        return version.status == SemanticIndexVersion.Status.ACTIVE
    jobs = version.jobs.all()
    if not jobs.exists() or jobs.exclude(
        status__in=[SemanticIndexJob.Status.COMPLETED, SemanticIndexJob.Status.PARTIAL]
    ).exists():
        return False
    if jobs.filter(status=SemanticIndexJob.Status.PARTIAL).exists():
        version.status = SemanticIndexVersion.Status.FAILED
        version.error_message = "新索引存在降级任务，未切换生产查询。"
        version.save(update_fields=["status", "error_message", "updated_at"])
        return False
    document_count = sum(int(job.stats.get("documents", 0)) for job in jobs)
    if version.expected_document_count and document_count != version.expected_document_count:
        version.status = SemanticIndexVersion.Status.FAILED
        version.document_count = document_count
        version.error_message = (
            f"候选索引文档数为 {document_count}，"
            f"与快照预期 {version.expected_document_count} 不一致。"
        )
        version.save(
            update_fields=[
                "status",
                "document_count",
                "error_message",
                "updated_at",
            ]
        )
        return False
    if version.validation_details.get("activation_mode") == MANUAL_ACTIVATION_MODE:
        version.status = SemanticIndexVersion.Status.READY
        version.document_count = document_count
        version.error_message = ""
        version.validation_details = {
            **version.validation_details,
            "build_completed_at": timezone.now().isoformat(),
            "actual_document_count": document_count,
        }
        version.save(
            update_fields=[
                "status",
                "document_count",
                "error_message",
                "validation_details",
                "updated_at",
            ]
        )
        return False
    now = timezone.now()
    SemanticIndexVersion.objects.filter(status=SemanticIndexVersion.Status.ACTIVE).exclude(
        pk=version.pk
    ).update(status=SemanticIndexVersion.Status.RETIRED, updated_at=now)
    version.status = SemanticIndexVersion.Status.ACTIVE
    version.document_count = document_count
    version.activated_at = now
    version.error_message = ""
    version.save()
    return True


def stage_semantic_index_version(
    config: dict,
    *,
    actor=None,
    batch_size: int | None = None,
    auto_dispatch: bool = True,
    asset_queryset=None,
    force_rebuild: bool = True,
    expected_document_count: int = 0,
    validation_details: dict | None = None,
) -> SemanticIndexVersion:
    config_snapshot = semantic_index_config_snapshot(config)
    stamp = timezone.now().strftime("%Y%m%d%H%M%S")
    suffix = uuid.uuid5(
        uuid.NAMESPACE_URL,
        ":".join(
            [
                str(config_snapshot.get("provider")),
                str(
                    config_snapshot.get("model_repo_id")
                    or config_snapshot.get("model")
                ),
                str(config_snapshot.get("model_revision")),
                str(config_snapshot.get("dimensions")),
                str(config_snapshot.get("pooling")),
            ]
        ),
    ).hex[:8]
    version = SemanticIndexVersion.objects.create(
        uid=f"semantic_passages_{stamp}_{suffix}",
        provider=str(config_snapshot.get("provider") or ""),
        model_repo_id=str(
            config_snapshot.get("model_repo_id")
            or config_snapshot.get("model")
            or ""
        ),
        model_local_path=str(config_snapshot.get("model_local_path") or ""),
        model_revision=str(config_snapshot.get("model_revision") or ""),
        dimensions=config_snapshot.get("dimensions"),
        pooling=str(config_snapshot.get("pooling") or ""),
        document_template=str(config_snapshot["document_template"]),
        config_snapshot=config_snapshot,
        expected_document_count=max(0, int(expected_document_count)),
        validation_details=validation_details or {},
    )
    try:
        ensure_semantic_index(config_snapshot, index_uid=version.uid)
    except Exception as exc:
        version.status = SemanticIndexVersion.Status.FAILED
        version.error_message = str(exc)[:4000]
        version.save(update_fields=["status", "error_message", "updated_at"])
        return version

    assets = asset_queryset
    if assets is None:
        assets = Asset.objects.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
            edition__ocr_status__in=[OcrStatus.NOT_REQUIRED, OcrStatus.SUCCEEDED],
        )
    assets = assets.select_related("edition").order_by("created_at", "id")
    queued = 0
    for asset in assets:
        create_semantic_job(
            asset,
            force=force_rebuild,
            actor=actor,
            index_version=version,
            deferred=True,
        )
        queued += 1
    if queued == 0:
        now = timezone.now()
        if version.validation_details.get("activation_mode") == MANUAL_ACTIVATION_MODE:
            version.status = SemanticIndexVersion.Status.FAILED
            version.error_message = "候选快照没有可复用的语义分块。"
            version.save(update_fields=["status", "error_message", "updated_at"])
        else:
            SemanticIndexVersion.objects.filter(status=SemanticIndexVersion.Status.ACTIVE).update(
                status=SemanticIndexVersion.Status.RETIRED,
                updated_at=now,
            )
            version.status = SemanticIndexVersion.Status.ACTIVE
            version.activated_at = now
            version.save(update_fields=["status", "activated_at", "updated_at"])
    elif auto_dispatch:
        dispatch_semantic_version_batch(version, batch_size=batch_size)
    return version


def stage_semantic_snapshot_version(
    config: dict,
    *,
    actor=None,
    batch_size: int | None = None,
    auto_dispatch: bool = True,
) -> SemanticIndexVersion:
    """Copy the currently validated chunk set into a clean candidate index."""

    existing_candidate = SemanticIndexVersion.objects.filter(
        status__in=[
            SemanticIndexVersion.Status.BUILDING,
            SemanticIndexVersion.Status.READY,
        ]
    ).first()
    if existing_candidate:
        raise ValueError(f"已有候选索引 {existing_candidate.uid}，请先处理该版本。")

    config_snapshot = semantic_index_config_snapshot(config)
    model_name = str(
        config_snapshot.get("model_repo_id")
        or config_snapshot.get("model")
        or ""
    )
    chunk_filter = {
        "semantic_chunks__parser_version": PARSER_VERSION,
        "semantic_chunks__chunk_version": CHUNK_VERSION,
        "semantic_chunks__embedding_model": model_name,
        "semantic_chunks__index_status": SemanticChunk.IndexStatus.READY,
    }
    assets = Asset.objects.filter(
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        is_current=True,
        **chunk_filter,
    ).distinct()
    reusable_chunks = SemanticChunk.objects.filter(
        asset__in=assets,
        parser_version=PARSER_VERSION,
        chunk_version=CHUNK_VERSION,
        embedding_model=model_name,
        index_status=SemanticChunk.IndexStatus.READY,
    ).count()
    if reusable_chunks < 1:
        raise ValueError("当前没有通过验证、可安全复制的语义分块。")
    current_assets = Asset.objects.filter(
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        is_current=True,
    )
    reusable_asset_count = assets.count()
    deferred_asset_count = current_assets.exclude(pk__in=assets.values("pk")).count()
    return stage_semantic_index_version(
        config_snapshot,
        actor=actor,
        batch_size=batch_size,
        auto_dispatch=auto_dispatch,
        asset_queryset=assets,
        force_rebuild=False,
        expected_document_count=reusable_chunks,
        validation_details={
            "activation_mode": MANUAL_ACTIVATION_MODE,
            "build_mode": "validated_snapshot",
            "expected_asset_count": reusable_asset_count,
            "deferred_asset_count": deferred_asset_count,
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
        },
    )


def semantic_index_document_count(index_uid: str) -> int:
    response = httpx.get(
        f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/stats",
        headers=_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return int(response.json().get("numberOfDocuments") or 0)


def synchronize_active_semantic_index_document_count(index_uid: str) -> int | None:
    """Persist the current remote count after one active-index mutation.

    Candidate versions remain frozen and are finalized by their existing build
    validation. Active indexes accept later asset upserts and deletions, so the
    corresponding version row must track the current UID rather than retain the
    original build count forever.
    """

    with transaction.atomic():
        version = (
            SemanticIndexVersion.objects.select_for_update()
            .filter(uid=index_uid, status=SemanticIndexVersion.Status.ACTIVE)
            .first()
        )
        if version is None:
            return None
        actual = semantic_index_document_count(index_uid)
        version.document_count = actual
        version.validation_details = {
            **(version.validation_details or {}),
            "document_count_semantics": "current_remote_document_count",
            "current_document_count": actual,
            "document_count_synced_at": timezone.now().isoformat(),
        }
        version.save(
            update_fields=[
                "document_count",
                "validation_details",
                "updated_at",
            ]
        )
        return actual


def validate_semantic_index_version(
    version_or_id: SemanticIndexVersion | str,
) -> dict:
    from catalog.services.semantic_search import current_semantic_runtime, semantic_model_health

    version_id = getattr(version_or_id, "pk", version_or_id)
    version = SemanticIndexVersion.objects.get(pk=version_id)
    if version.status != SemanticIndexVersion.Status.READY:
        raise ValueError("只有已完成建立并等待切换的候选索引可以验证。")
    jobs = version.jobs.all()
    if not jobs.exists() or jobs.exclude(status=SemanticIndexJob.Status.COMPLETED).exists():
        raise ValueError("候选索引仍有未成功完成的任务。")

    runtime = semantic_index_version_runtime(version) or current_semantic_runtime()
    runtime_model = str(runtime.get("model_repo_id") or runtime.get("model") or "")
    expected_configuration = {
        "provider": str(runtime.get("provider") or ""),
        "model_repo_id": runtime_model,
        "model_revision": str(runtime.get("model_revision") or ""),
        "dimensions": runtime.get("dimensions"),
        "pooling": str(runtime.get("pooling") or ""),
    }
    version_configuration = {
        "provider": version.provider,
        "model_repo_id": version.model_repo_id,
        "model_revision": version.model_revision,
        "dimensions": version.dimensions,
        "pooling": version.pooling,
    }
    if version_configuration != expected_configuration:
        raise ValueError("候选索引模型配置与当前有效设置不一致，不能切换。")
    model_health = semantic_model_health(runtime)
    if model_health.get("available") is not True:
        raise ValueError(model_health.get("reason") or "本地语义模型不可用。")

    job_document_count = sum(int(job.stats.get("documents", 0)) for job in jobs)
    actual_document_count = semantic_index_document_count(version.uid)
    expected_document_count = version.expected_document_count or job_document_count
    if actual_document_count != expected_document_count:
        raise ValueError(
            f"Meilisearch 实际文档数为 {actual_document_count}，"
            f"候选快照预期为 {expected_document_count}。"
        )
    if job_document_count != expected_document_count:
        raise ValueError(
            f"任务写入文档数为 {job_document_count}，"
            f"候选快照预期为 {expected_document_count}。"
        )

    details = {
        **version.validation_details,
        "validated_at": timezone.now().isoformat(),
        "actual_document_count": actual_document_count,
        "job_document_count": job_document_count,
        "completed_job_count": jobs.count(),
        "model_available": True,
    }
    SemanticIndexVersion.objects.filter(pk=version.pk).update(
        document_count=actual_document_count,
        validation_details=details,
        error_message="",
        updated_at=timezone.now(),
    )
    return details


def activate_semantic_index_version(
    version_or_id: SemanticIndexVersion | str,
    *,
    actor=None,
) -> SemanticIndexVersion:
    """Validate a ready candidate, then atomically move the production pointer."""

    version_id = getattr(version_or_id, "pk", version_or_id)
    details = validate_semantic_index_version(version_id)
    with transaction.atomic():
        version = SemanticIndexVersion.objects.select_for_update().get(pk=version_id)
        if version.status != SemanticIndexVersion.Status.READY:
            raise ValueError("候选索引状态已经变化，请刷新后重试。")
        now = timezone.now()
        SemanticIndexVersion.objects.select_for_update().filter(
            status=SemanticIndexVersion.Status.ACTIVE,
        ).exclude(pk=version.pk).update(
            status=SemanticIndexVersion.Status.RETIRED,
            updated_at=now,
        )
        version.status = SemanticIndexVersion.Status.ACTIVE
        version.activated_at = now
        version.validation_details = {
            **details,
            "activated_at": now.isoformat(),
        }
        version.error_message = ""
        version.save(
            update_fields=[
                "status",
                "activated_at",
                "validation_details",
                "error_message",
                "updated_at",
            ]
        )
        runtime_value = semantic_runtime_setting_value(version.config_snapshot or {})
        if runtime_value:
            SiteSetting.objects.update_or_create(
                key="semantic_search_runtime",
                defaults={
                    "value": runtime_value,
                    "public": False,
                    "updated_by": actor,
                },
            )
        return version


def dispatch_semantic_job(job_id: str, task_id: str) -> bool:
    """Send a durable semantic job without relying on Celery's result backend."""

    job = SemanticIndexJob.objects.filter(pk=job_id).only("status", "task_id").first()
    if (
        job is None
        or job.status != SemanticIndexJob.Status.QUEUED
        or job.task_id != task_id
    ):
        return False

    from catalog.tasks import build_semantic_index

    try:
        build_semantic_index.apply_async(
            args=[job_id],
            task_id=task_id,
            ignore_result=True,
        )
    except (KombuOperationalError, OSError, ConnectionError, TimeoutError) as exc:
        SemanticIndexJob.objects.filter(
            pk=job_id,
            status=SemanticIndexJob.Status.QUEUED,
            task_id=task_id,
        ).update(
            status=SemanticIndexJob.Status.FAILED,
            error_code="queue_unavailable",
            error_message=f"语义索引任务未进入队列：{exc}"[:4000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        edition_id = Asset.objects.filter(
            semantic_index_jobs__pk=job_id,
        ).values_list("edition_id", flat=True).first()
        if edition_id:
            Edition.objects.filter(pk=edition_id).update(
                semantic_index_status=SemanticIndexStatus.FAILED,
                updated_at=timezone.now(),
            )
        version_id = SemanticIndexJob.objects.filter(pk=job_id).values_list(
            "index_version_id", flat=True
        ).first()
        if version_id:
            SemanticIndexVersion.objects.filter(pk=version_id).update(
                status=SemanticIndexVersion.Status.FAILED,
                error_message=f"候选索引任务未进入队列：{exc}"[:4000],
                updated_at=timezone.now(),
            )
        return False
    return True


def recover_semantic_index_jobs(*, now=None) -> dict[str, int]:
    """Requeue jobs lost during broker restarts or interrupted worker runs."""

    if semantic_index_paused():
        return {"requeued": 0, "paused": 1}

    now = now or timezone.now()
    queued_before = now - timedelta(seconds=settings.SEMANTIC_INDEX_QUEUE_STALLED_SECONDS)
    running_before = now - timedelta(seconds=settings.SEMANTIC_INDEX_RUNNING_STALLED_SECONDS)
    candidates = SemanticIndexJob.objects.filter(
        Q(
            status=SemanticIndexJob.Status.FAILED,
            error_code="queue_unavailable",
        )
        | Q(
            status=SemanticIndexJob.Status.QUEUED,
            updated_at__lt=queued_before,
        )
        | Q(
            status=SemanticIndexJob.Status.RUNNING,
            updated_at__lt=running_before,
        )
    ).order_by("created_at")[: settings.SEMANTIC_INDEX_RECOVERY_BATCH_SIZE]

    dispatches: list[tuple[str, str]] = []
    with transaction.atomic():
        for job in SemanticIndexJob.objects.select_for_update().filter(
            pk__in=[candidate.pk for candidate in candidates]
        ):
            task_id = str(uuid.uuid4())
            job.status = SemanticIndexJob.Status.QUEUED
            job.task_id = task_id
            job.pause_requested_at = None
            job.progress = 0
            job.error_code = ""
            job.error_message = ""
            job.started_at = None
            job.finished_at = None
            job.save(
                update_fields=[
                    "status",
                    "task_id",
                    "pause_requested_at",
                    "progress",
                    "error_code",
                    "error_message",
                    "started_at",
                    "finished_at",
                    "updated_at",
                ]
            )
            dispatches.append((str(job.id), task_id))

        def dispatch_all():
            for job_id, task_id in dispatches:
                dispatch_semantic_job(job_id, task_id)

        transaction.on_commit(dispatch_all)
    return {"requeued": len(dispatches), "paused": 0}
