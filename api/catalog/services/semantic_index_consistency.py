from __future__ import annotations

from dataclasses import dataclass

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import Asset, SemanticChunk, SemanticIndexVersion
from catalog.services.semantic_chunks import CHUNK_VERSION, PARSER_VERSION
from catalog.services.semantic_indexing import (
    semantic_index_document_count,
    semantic_index_version_runtime,
)
from ingestion.services.indexing import _headers


MAX_ID_SAMPLE = 50


@dataclass(frozen=True)
class ExpectedChunkSet:
    queryset: object
    scope: str


def _expected_chunks(version: SemanticIndexVersion) -> ExpectedChunkSet:
    runtime = semantic_index_version_runtime(version) or {}
    parser_version = str(runtime.get("parser_version") or PARSER_VERSION)
    chunk_version = str(runtime.get("chunk_version") or CHUNK_VERSION)
    model_name = str(
        version.model_repo_id
        or runtime.get("model_repo_id")
        or runtime.get("model")
        or ""
    )
    queryset = SemanticChunk.objects.filter(
        asset__kind=Asset.Kind.NORMALIZED,
        asset__status=Asset.Status.READY,
        asset__is_current=True,
        parser_version=parser_version,
        chunk_version=chunk_version,
        embedding_model=model_name,
        index_status=SemanticChunk.IndexStatus.READY,
    )
    if version.status == SemanticIndexVersion.Status.ACTIVE:
        return ExpectedChunkSet(queryset=queryset, scope="active_current_ready_chunks")

    job_asset_ids = version.jobs.filter(asset_id__isnull=False).values_list(
        "asset_id", flat=True
    )
    if job_asset_ids.exists():
        return ExpectedChunkSet(
            queryset=queryset.filter(asset_id__in=job_asset_ids),
            scope="version_job_assets_ready_chunks",
        )
    return ExpectedChunkSet(queryset=queryset, scope="version_runtime_ready_chunks")


def _remote_document_identity(index_uid: str) -> tuple[dict[str, str], int]:
    identities: dict[str, str] = {}
    offset = 0
    limit = 1000
    total = 0
    while True:
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/documents/fetch",
            headers=_headers(),
            json={
                "offset": offset,
                "limit": limit,
                "fields": ["id", "document_id"],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        for item in results:
            record_id = str(item.get("id") or "")
            if record_id:
                identities[record_id] = str(item.get("document_id") or "")
        total = int(payload.get("total") or len(identities))
        if offset + len(results) >= total:
            return identities, total
        if not results:
            raise RuntimeError("Meilisearch 语义文档分页提前结束。")
        offset += len(results)


def audit_semantic_index_consistency(
    version: SemanticIndexVersion,
    *,
    include_ids: bool = False,
) -> dict:
    expected = _expected_chunks(version)
    db_rows = list(expected.queryset.values_list("id", "document_id"))
    db_identity = {str(row_id): str(document_id or "") for row_id, document_id in db_rows}
    remote_identity, remote_reported_total = _remote_document_identity(version.uid)
    remote_count = semantic_index_document_count(version.uid)

    db_ids = set(db_identity)
    remote_ids = set(remote_identity)
    missing_ids = sorted(db_ids - remote_ids)
    extra_ids = sorted(remote_ids - db_ids)
    mismatched_document_ids = sorted(
        record_id
        for record_id in db_ids & remote_ids
        if remote_identity[record_id]
        and db_identity[record_id] != remote_identity[record_id]
    )
    remote_missing_document_ids = sorted(
        record_id for record_id in remote_ids if not remote_identity[record_id]
    )
    db_document_ids = [value for value in db_identity.values() if value]
    remote_document_ids = [value for value in remote_identity.values() if value]
    consistent = bool(
        version.document_count == remote_count
        and remote_count == len(db_rows)
        and remote_reported_total == remote_count
        and not missing_ids
        and not extra_ids
        and not mismatched_document_ids
        and not remote_missing_document_ids
        and len(set(db_document_ids)) == len(db_rows)
        and len(set(remote_document_ids)) == remote_count
    )
    report = {
        "status": "consistent" if consistent else "drift",
        "version": {
            "id": str(version.id),
            "uid": version.uid,
            "status": version.status,
            "recorded_document_count": version.document_count,
            "expected_document_count": version.expected_document_count,
        },
        "document_count_semantics": (
            "current UID document count while active; frozen actual count for ready or retired"
        ),
        "expected_scope": expected.scope,
        "counts": {
            "db_ready_chunk_count": len(db_rows),
            "db_unique_record_id_count": len(db_ids),
            "db_unique_document_id_count": len(set(db_document_ids)),
            "meilisearch_document_count": remote_count,
            "meilisearch_reported_fetch_total": remote_reported_total,
            "meilisearch_unique_record_id_count": len(remote_ids),
            "meilisearch_unique_document_id_count": len(set(remote_document_ids)),
            "missing_in_index": len(missing_ids),
            "extra_in_index": len(extra_ids),
            "mismatched_document_id": len(mismatched_document_ids),
            "meilisearch_missing_document_id": len(remote_missing_document_ids),
        },
        "metadata_drift": version.document_count != remote_count,
        "corpus_drift": bool(missing_ids or extra_ids or mismatched_document_ids),
        "schema_drift": bool(remote_missing_document_ids),
        "missing_in_index_sample": missing_ids[:MAX_ID_SAMPLE],
        "extra_in_index_sample": extra_ids[:MAX_ID_SAMPLE],
        "mismatched_document_id_sample": mismatched_document_ids[:MAX_ID_SAMPLE],
        "meilisearch_missing_document_id_sample": remote_missing_document_ids[
            :MAX_ID_SAMPLE
        ],
    }
    if include_ids:
        report.update(
            {
                "missing_in_index_ids": missing_ids,
                "extra_in_index_ids": extra_ids,
                "mismatched_document_id_ids": mismatched_document_ids,
                "meilisearch_missing_document_id_ids": remote_missing_document_ids,
            }
        )
    return report


def repair_semantic_index_version_metadata(version: SemanticIndexVersion) -> dict:
    if version.status == SemanticIndexVersion.Status.ACTIVE:
        raise ValueError("活动索引只允许只读审计，不能由该命令自动修正元数据。")
    report = audit_semantic_index_consistency(version)
    counts = report["counts"]
    if report["corpus_drift"] or report["schema_drift"] or (
        counts["db_ready_chunk_count"] != counts["meilisearch_document_count"]
    ):
        raise ValueError("远端文档与数据库 chunk 不一致，不能只修正版本元数据。")

    with transaction.atomic():
        locked = SemanticIndexVersion.objects.select_for_update().get(pk=version.pk)
        locked.document_count = counts["meilisearch_document_count"]
        locked.validation_details = {
            **(locked.validation_details or {}),
            "document_count_semantics": (
                "current UID document count while active; frozen actual count for ready or retired"
            ),
            "metadata_reconciled_at": timezone.now().isoformat(),
            "metadata_reconciled_document_count": counts["meilisearch_document_count"],
        }
        locked.save(
            update_fields=["document_count", "validation_details", "updated_at"]
        )
    return audit_semantic_index_consistency(locked)
