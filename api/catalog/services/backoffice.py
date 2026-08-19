"""Read-oriented orchestration for the 2.7 back office.

The service deliberately reports source, workflow and projection state without
mutating any authority or derived index.  Mutations stay behind the existing
review, publication and QueryLexicon services.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count, Q
from django.utils import timezone

from catalog.models import (
    Asset,
    Edition,
    EnrichmentCandidate,
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgeNodeAlias,
    NewAuthorityCandidate,
    Person,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
    SemanticChunk,
    SemanticIndexVersion,
    SiteSetting,
    Topic,
    UnknownEntityObservation,
    Work,
)
from catalog.services.query_lexicon.operations import query_lexicon_workspace
from catalog.services.semantic_indexing import active_semantic_index_version, active_semantic_index_uid
from catalog.services.semantic_search import current_semantic_runtime, semantic_model_health
from common.ai_runtime import AICapability, profile_environment_status, runtime_profile
from distribution.models import BackupJob
from ingestion.models import ProcessingJob, UploadItem
from ingestion.services.health import (
    celery_broker_health,
    celery_worker_control_status,
    worker_heartbeat_status,
)


def _safe_count(queryset) -> int:
    try:
        return int(queryset.count())
    except Exception:
        return 0


def _migration_heads() -> list[str]:
    try:
        loader = MigrationExecutor(connection).loader
        applied = set(loader.applied_migrations)
        heads = []
        for key in sorted(applied):
            node = loader.graph.node_map.get(key)
            if node is None:
                continue
            if not any(child.key[0] == key[0] and child.key in applied for child in node.children):
                heads.append(f"{key[0]}.{key[1]}")
        return heads
    except Exception:
        return []


def _database_status() -> dict[str, Any]:
    payload: dict[str, Any] = {"vendor": connection.vendor, "status": "unknown", "version": ""}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
            if connection.vendor == "postgresql":
                cursor.execute("SELECT current_setting('server_version')")
                payload["version"] = str(cursor.fetchone()[0])
            elif connection.vendor == "sqlite":
                cursor.execute("SELECT sqlite_version()")
                payload["version"] = str(cursor.fetchone()[0])
        payload["status"] = "healthy"
    except Exception as exc:
        payload["status"] = "unavailable"
        payload["error_category"] = exc.__class__.__name__
    payload["migration_heads"] = _migration_heads()
    return payload


def _redis_status() -> dict[str, Any]:
    try:
        if not getattr(settings, "CACHE_URL", ""):
            return {"status": "local_cache", "configured": False}
        cache.set("__backoffice_health__", "ok", timeout=5)
        return {"status": "healthy", "configured": True}
    except Exception as exc:
        return {"status": "unavailable", "configured": True, "error_category": exc.__class__.__name__}


def _nas_status() -> dict[str, Any]:
    root = Path(getattr(settings, "MEDIA_ROOT", ""))
    try:
        return {"status": "healthy" if root.exists() else "missing", "configured": True, "path": str(root)}
    except Exception as exc:
        return {"status": "unavailable", "configured": True, "error_category": exc.__class__.__name__}


def _query_lexicon_status() -> dict[str, Any]:
    try:
        return query_lexicon_workspace(limit=1)
    except Exception as exc:
        return {"initialized": False, "status": "unavailable", "error_category": exc.__class__.__name__}


def _semantic_status() -> dict[str, Any]:
    try:
        active = active_semantic_index_version()
    except Exception:
        active = None
    if active is None:
        return {"status": "unavailable", "active_version": None, "uid": active_semantic_index_uid()}
    return {
        "status": "current" if active.status == SemanticIndexVersion.Status.ACTIVE else str(active.status),
        "active_version": str(active.id),
        "uid": active.uid,
        "db_ready_chunks": _safe_count(
            SemanticChunk.objects.filter(index_status=SemanticChunk.IndexStatus.READY)
        ),
        "meilisearch_document_count": active.document_count,
        "meilisearch_count_source": "SemanticIndexVersion recorded remote count",
        "expected_document_count": active.expected_document_count,
        "schema": (active.config_snapshot or {}).get("protocol_version", ""),
        "model": active.model_repo_id or active.model_local_path,
        "model_revision": active.model_revision,
    }


def _celery_status() -> dict[str, Any]:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        broker = {"reachable": True, "detail": "Celery eager mode"}
    else:
        broker = celery_broker_health()
    control = celery_worker_control_status(timeout_seconds=2)
    heartbeat = worker_heartbeat_status()
    names = [str(value).casefold() for value in control.get("workers") or []]
    default_seen = any(value.startswith("worker@") for value in names)
    ingestion_seen = any(value.startswith("ingestion@") for value in names)
    aggregate_only = bool(control.get("online") and not (default_seen or ingestion_seen))
    return {
        "status": (
            "healthy"
            if broker.get("reachable") and control.get("online")
            else "unavailable"
        ),
        "broker": broker,
        "default_worker": {
            "status": "healthy" if default_seen else ("unknown" if aggregate_only else "unavailable"),
            "control_confirmed": default_seen,
        },
        "ingestion_worker": {
            "status": (
                "healthy"
                if ingestion_seen or heartbeat.get("online")
                else ("unknown" if aggregate_only else "unavailable")
            ),
            "control_confirmed": ingestion_seen,
            "heartbeat_at": heartbeat.get("heartbeat_at"),
        },
        "beat": {
            "status": "healthy" if heartbeat.get("online") else "unknown",
            "inference": "recent scheduled ingestion heartbeat",
            "heartbeat_at": heartbeat.get("heartbeat_at"),
        },
        "control": control,
    }


def _ai_status() -> dict[str, Any]:
    profiles = []
    for capability in AICapability.VALUES:
        try:
            profile = runtime_profile(capability)
            environment = profile_environment_status(profile)
            configured = bool(
                profile.enabled
                and environment["endpoint_configured"]
                and environment["credential_configured"]
            )
            profiles.append({
                "capability": capability,
                "profile": profile.key,
                "provider": profile.provider,
                "model": profile.model,
                "enabled": profile.enabled,
                "status": "configured" if configured else "not_configured",
                "health": "unknown" if configured else "not_configured",
                "endpoint_configured": environment["endpoint_configured"],
                "credential_configured": environment["credential_configured"],
            })
        except Exception as exc:
            profiles.append({"capability": capability, "status": "invalid", "error_category": exc.__class__.__name__})
    return {"profiles": profiles, "secret_values_exposed": False}


def _web_status() -> dict[str, Any]:
    configured = bool(str(getattr(settings, "FIELD_ENRICHMENT_SEARXNG_URL", "") or "").strip())
    enabled_authority = {
        item.strip().casefold()
        for item in str(
            getattr(
                settings,
                "AUTHORITY_PROVIDER_ENABLED",
                "wikidata,viaf,loc,openalex",
            )
            or "",
        ).split(",")
        if item.strip()
    }
    enabled_metadata = {
        item.strip().casefold()
        for item in str(
            getattr(
                settings,
                "METADATA_PROVIDER_ENABLED",
                "crossref,openlibrary,google_books",
            )
            or "",
        ).split(",")
        if item.strip()
    }
    # "configured" describes an enabled adapter, not a live network probe.
    # A live probe belongs to an explicit enrichment request and must not make
    # the status page perform external calls.
    structured = {
        provider: {
            "status": "configured" if provider in enabled_authority else "not_configured",
            "health": "unknown",
        }
        for provider in ("wikidata", "viaf", "loc", "openalex")
    }
    bibliographic = {
        provider: {
            "status": (
                "configured"
                if (
                    provider in enabled_metadata
                    or (provider == "grobid" and bool(str(getattr(settings, "GROBID_SERVICE_URL", "") or "").strip()))
                )
                else "not_configured"
            ),
            "health": "unknown",
        }
        for provider in ("crossref", "openlibrary", "google_books", "grobid")
    }
    return {
        "general_web": {
            "status": "configured" if configured else "not_configured",
            "health": "unknown" if configured else "not_configured",
            "provider": "searxng",
        },
        "structured": structured,
        "bibliographic": bibliographic,
        "secret_values_exposed": False,
    }


def _backup_status() -> dict[str, Any]:
    row = BackupJob.objects.filter(status=BackupJob.Status.COMPLETED).order_by("-completed_at").first()
    if row is None:
        return {"status": "not_available", "last_success": None}
    return {
        "status": "current",
        "last_success": {
            "id": str(row.id),
            "completed_at": row.completed_at,
            "checksum": row.checksum,
            "size": (row.manifest or {}).get("byte_size"),
        },
    }


def system_status_snapshot() -> dict[str, Any]:
    from ingestion.services.r2_staging import r2_staging_status

    semantic_runtime = current_semantic_runtime()
    embedding_health = semantic_model_health(semantic_runtime)
    return {
        "generated_at": timezone.now(),
        "database": _database_status(),
        "redis": _redis_status(),
        "celery": _celery_status(),
        "storage": {"nas": _nas_status(), "r2_upload_staging": r2_staging_status()},
        "query_lexicon": _query_lexicon_status(),
        "semantic": _semantic_status(),
        "embedding": {
            "status": (
                "available"
                if embedding_health.get("available") is True
                else "unknown"
                if embedding_health.get("available") is None
                else "unavailable"
            ),
            "model": semantic_runtime.get("model_repo_id") or semantic_runtime.get("model"),
            "revision": semantic_runtime.get("model_revision"),
            "local_path": semantic_runtime.get("model_local_path"),
            "offline_mode": semantic_runtime.get("offline_mode"),
            "local_required": True,
            "health": embedding_health,
        },
        "ai": _ai_status(),
        "web_enrichment": _web_status(),
        "backup": _backup_status(),
    }


def _entity_label(entity_type: str, entity_id: str) -> str:
    models = {
        QueryLexiconEntry.EntityType.PERSON: (Person, "preferred_name"),
        QueryLexiconEntry.EntityType.KNOWLEDGE_NODE: (KnowledgeNode, "canonical_name_zh"),
        QueryLexiconEntry.EntityType.TOPIC: (Topic, "name"),
    }
    model_field = models.get(entity_type)
    if model_field is None:
        return f"{entity_type}:{entity_id}"
    model, field_name = model_field
    row = model.objects.filter(pk=entity_id).values(field_name).first()
    return str((row or {}).get(field_name) or f"{entity_type}:{entity_id}")


def query_lexicon_term_inspector(*, query: str = "", entity_type: str = "", limit: int = 60) -> dict[str, Any]:
    state = QueryLexiconState.objects.select_related("active_generation").first()
    if state is None:
        return {"initialized": False, "terms": [], "revision": None, "generation": None}
    rows = QueryLexiconEntry.objects.filter(generation=state.active_generation)
    if entity_type:
        rows = rows.filter(entity_type=entity_type)
    query = str(query or "").strip()
    if query:
        rows = rows.filter(Q(term__icontains=query) | Q(normalized_term__icontains=query))
    terms = []
    for row in rows.order_by("normalized_term", "entity_type")[: max(1, min(int(limit), 200))]:
        terms.append({
            "id": str(row.id),
            "term": row.term,
            "normalized_term": row.normalized_term,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id),
            "entity_label": _entity_label(row.entity_type, str(row.entity_id)),
            "language": row.language,
            "term_type": row.term_type,
            "trust_level": row.trust_level,
            "source_kind": row.source_kind,
            "source_ref": row.source_ref,
            "public_active": row.public_active,
            "admin_resolvable": row.admin_resolvable,
            "generation": str(state.active_generation_id),
            "revision": state.revision,
            "provenance": row.provenance,
        })
    return {
        "initialized": True,
        "revision": state.revision,
        "generation": {"id": str(state.active_generation_id), "status": state.active_generation.status},
        "terms": terms,
    }


def _projection_base(target_type: str, target_id: str) -> tuple[Any, dict[str, Any]]:
    if target_type == "work":
        target = Work.objects.filter(pk=target_id).first()
    elif target_type == "edition":
        target = Edition.objects.select_related("work").filter(pk=target_id).first()
    elif target_type == "asset":
        target = Asset.objects.select_related("edition__work").filter(pk=target_id).first()
    elif target_type == "person":
        target = Person.objects.filter(pk=target_id).first()
    elif target_type == "knowledge_node":
        target = KnowledgeNode.objects.filter(pk=target_id).first()
    elif target_type == "topic":
        target = Topic.objects.filter(pk=target_id).first()
    else:
        target = None
    return target, {"target_type": target_type, "target_id": str(target_id), "exists": target is not None}


def projection_status(*, target_type: str, target_id: str) -> dict[str, Any]:
    target, payload = _projection_base(target_type, target_id)
    if target is None:
        return payload
    if target_type == "work":
        editions = Edition.objects.filter(work_id=target.id)
        assets = Asset.objects.filter(edition__work_id=target.id, is_current=True)
        chunks = SemanticChunk.objects.filter(work_id=target.id)
        pending = EnrichmentCandidate.objects.filter(target_id=target.id, status=EnrichmentCandidate.Status.PENDING)
        payload.update({
            "label": target.title,
            "publication": "published" if editions.filter(state="published").exists() else "draft",
            "editions": editions.count(),
            "assets": assets.count(),
            "pages": sum(_safe_count(asset.pages.all()) for asset in assets[:50]),
            "semantic_chunks": chunks.count(),
            "semantic_chunks_ready": chunks.filter(index_status=SemanticChunk.IndexStatus.READY).count(),
            "semantic_index": "current" if chunks.exists() and not chunks.exclude(index_status=SemanticChunk.IndexStatus.READY).exists() else "pending",
            "pdf_knowledge_scan": "complete" if not UnknownEntityObservation.objects.filter(work_id=target.id, is_current=True).exists() else "pending_review",
            "pending_candidates": pending.count(),
            "rag": "available" if chunks.filter(index_status=SemanticChunk.IndexStatus.READY).exists() else "insufficient_corpus",
        })
    elif target_type == "edition":
        assets = target.assets.filter(is_current=True)
        chunks = SemanticChunk.objects.filter(asset__edition_id=target.id)
        payload.update({
            "label": target.work.title,
            "publication": target.state,
            "ocr": target.ocr_status,
            "semantic_index": target.semantic_index_status,
            "assets": assets.count(),
            "pages": sum(_safe_count(asset.pages.all()) for asset in assets[:50]),
            "semantic_chunks": chunks.count(),
            "semantic_chunks_ready": chunks.filter(index_status=SemanticChunk.IndexStatus.READY).count(),
        })
    elif target_type == "asset":
        chunks = target.semantic_chunks.all()
        payload.update({
            "label": target.edition.work.title,
            "publication": target.edition.state,
            "status": target.status,
            "validation": target.validation_status,
            "ocr": target.edition.ocr_status,
            "pages": target.pages.count(),
            "semantic_chunks": chunks.count(),
            "semantic_chunks_ready": chunks.filter(index_status=SemanticChunk.IndexStatus.READY).count(),
            "semantic_index": target.edition.semantic_index_status,
            "pending_candidates": QueryLexiconEntry.objects.none().count(),
        })
    elif target_type == "person":
        state = QueryLexiconState.objects.select_related("active_generation").first()
        entries = QueryLexiconEntry.objects.filter(generation=state.active_generation, entity_type="person", entity_id=target.id) if state else QueryLexiconEntry.objects.none()
        payload.update({
            "label": target.preferred_name,
            "authority": target.authority_status,
            "publication": "published" if target.authority_status == Person.AuthorityStatus.VERIFIED else target.authority_status,
            "query_lexicon": {"revision": state.revision if state else None, "entries": entries.count(), "public_active": entries.filter(public_active=True).count(), "admin_resolvable": entries.filter(admin_resolvable=True).count()},
            "evidence": {"works": target.contributions.filter(approved=True).values("edition__work_id").distinct().count(), "passages": EvidenceSnippet.objects.filter(work__editions__contributions__person_id=target.id).count()},
            "rag": "available" if EvidenceSnippet.objects.filter(work__editions__contributions__person_id=target.id).exists() else "insufficient_corpus",
            "pending_enrichment": EnrichmentCandidate.objects.filter(target_type="person", target_id=target.id, status="pending").count(),
        })
    elif target_type == "knowledge_node":
        state = QueryLexiconState.objects.select_related("active_generation").first()
        entries = QueryLexiconEntry.objects.filter(generation=state.active_generation, entity_type="knowledge_node", entity_id=target.id) if state else QueryLexiconEntry.objects.none()
        passages = EvidenceSnippet.objects.filter(node_id=target.id)
        payload.update({
            "label": target.canonical_name_zh,
            "authority": target.status,
            "publication": target.status,
            "query_lexicon": {"revision": state.revision if state else None, "entries": entries.count(), "public_active": entries.filter(public_active=True).count(), "admin_resolvable": entries.filter(admin_resolvable=True).count()},
            "evidence": {"works": passages.values("work_id").distinct().count(), "passages": passages.count(), "relations": target.outgoing_relations.count() + target.incoming_relations.count()},
            "rag": "available" if passages.exists() else "insufficient_corpus",
            "pending_enrichment": EnrichmentCandidate.objects.filter(target_type="knowledge_node", target_id=target.id, status="pending").count(),
        })
    elif target_type == "topic":
        passages = EvidenceSnippet.objects.filter(work__knowledge_relations__topic_id=target.id)
        payload.update({
            "label": target.name,
            "authority": target.editorial_status,
            "publication": target.editorial_status,
            "evidence": {"works": passages.values("work_id").distinct().count(), "passages": passages.count()},
            "rag": "available" if passages.exists() else "insufficient_corpus",
            "pending_enrichment": EnrichmentCandidate.objects.filter(target_type="topic", target_id=target.id, status="pending").count(),
        })
    return payload


def knowledge_workspace(*, status: str = "pending", entity_type: str = "", work_id: str = "") -> dict[str, Any]:
    authority = NewAuthorityCandidate.objects.prefetch_related("observations__work")
    if status and status != "all":
        authority = authority.filter(status=status)
    if entity_type:
        authority = authority.filter(entity_type=entity_type)
    if work_id:
        authority = authority.filter(observations__work_id=work_id).distinct()
    authority_rows = []
    for row in authority.order_by("-confidence", "created_at")[:200]:
        authority_rows.append({
            "id": str(row.id),
            "kind": "new_authority",
            "entity_type": row.entity_type,
            "term": row.primary_term,
            "status": row.status,
            "confidence": row.confidence,
            "evidence_count": row.observations.filter(is_current=True).count(),
            "works": list(row.observations.filter(is_current=True).values("work_id", "work__title").distinct()[:20]),
            "possible_matches": row.possible_matches,
        })
    aliases = list(KnowledgeNodeAlias.objects.select_related("node").order_by("-created_at")[:100].values(
        "id", "alias", "language", "alias_type", "source_kind", "is_verified", "node_id", "node__canonical_name_zh"
    ))
    return {
        "new_authority": authority_rows,
        "aliases": aliases,
        "relations": {"pending": _safe_count(KnowledgeNode.objects.filter(outgoing_relations__status="pending"))},
        "timelines": {"pending": _safe_count(KnowledgeNode.objects.filter(timeline_links__event__review_status="suggested"))},
        "classification": {"pending_enrichment": _safe_count(EnrichmentCandidate.objects.filter(candidate_kind="classification", status="pending"))},
        "unknown_observations": _safe_count(UnknownEntityObservation.objects.filter(is_current=True)),
    }


def intake_workspace(*, item_id: str) -> dict[str, Any]:
    item = UploadItem.objects.select_related("edition__work", "asset").prefetch_related("metadata_candidates", "entity_resolution_candidates").filter(pk=item_id).first()
    if item is None:
        return {"exists": False}
    asset = item.asset or (item.edition.assets.filter(kind=Asset.Kind.NORMALIZED, is_current=True).first() if item.edition_id else None)
    work = item.edition.work if item.edition_id else None
    edition = item.edition if item.edition_id else None
    return {
        "exists": True,
        "item": {"id": str(item.id), "filename": item.source_filename, "status": item.status, "workflow_state": item.workflow_state, "error_code": item.error_code, "error_message": item.error_message},
        "asset": {"id": str(asset.id), "status": asset.status, "validation": asset.validation_status, "page_count": asset.page_count, "mime_type": asset.mime_type, "sha256": asset.sha256} if asset else None,
        "catalog": {"work_id": str(work.id), "edition_id": str(edition.id), "title": work.title, "subtitle": work.subtitle, "original_title": work.original_title, "document_type": work.document_type, "language": work.language, "publication_state": edition.state, "publication_year": edition.publication_year, "publisher": edition.publisher, "isbn": edition.isbn, "metadata_confidence": edition.metadata_confidence} if work and edition else None,
        "metadata_candidates": list(item.metadata_candidates.values("id", "field_name", "value", "source", "confidence", "lifecycle", "is_locked")),
        "entity_candidates": list(item.entity_resolution_candidates.values("id", "target_type", "source_name", "candidate_entity_type", "candidate_entity_id", "label", "match_score", "status")),
        "knowledge_discovery": {"new_authority": list(NewAuthorityCandidate.objects.filter(observations__asset_id=asset.id, observations__is_current=True).values("id", "entity_type", "primary_term", "status", "confidence").distinct()[:100]) if asset else [], "unknown_observations": _safe_count(UnknownEntityObservation.objects.filter(asset_id=asset.id, is_current=True)) if asset else 0},
    }
