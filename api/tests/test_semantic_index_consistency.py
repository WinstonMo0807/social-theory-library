from unittest.mock import patch

import pytest

from catalog.models import SemanticChunk, SemanticIndexJob, SemanticIndexVersion
from catalog.services.semantic_chunks import CHUNK_VERSION, PARSER_VERSION, build_semantic_chunks
from catalog.services.semantic_index_consistency import (
    audit_semantic_index_consistency,
    repair_semantic_index_version_metadata,
)
from catalog.services.semantic_indexing import (
    SemanticModelUnavailable,
    SemanticIndexVersionRequired,
    active_semantic_index_version,
    create_semantic_job,
    queue_semantic_job,
    run_semantic_index_job,
)

from .test_semantic_stability_and_evaluation import _create_asset


def _version_and_ready_chunk(status=SemanticIndexVersion.Status.READY):
    asset, _pages = _create_asset(f"consistency-{status}")
    with patch("catalog.services.semantic_chunks._current_model_name", return_value="test-model"):
        chunk = build_semantic_chunks(asset)[0]
    chunk.index_status = chunk.IndexStatus.READY
    chunk.save(update_fields=["index_status", "updated_at"])
    version = SemanticIndexVersion.objects.create(
        uid=f"semantic_consistency_{status}",
        provider="huggingFace",
        model_repo_id="test-model",
        config_snapshot={
            "model": "test-model",
            "model_repo_id": "test-model",
            "parser_version": PARSER_VERSION,
            "chunk_version": CHUNK_VERSION,
        },
        document_count=0,
        expected_document_count=1,
        status=status,
    )
    return version, chunk


@pytest.mark.django_db
def test_consistency_audit_distinguishes_metadata_drift_from_corpus_drift():
    version, chunk = _version_and_ready_chunk(SemanticIndexVersion.Status.ACTIVE)
    remote_identity = {str(chunk.id): chunk.document_id}
    with patch(
        "catalog.services.semantic_index_consistency._remote_document_identity",
        return_value=(remote_identity, 1),
    ), patch(
        "catalog.services.semantic_index_consistency.semantic_index_document_count",
        return_value=1,
    ):
        report = audit_semantic_index_consistency(version)

    assert report["status"] == "drift"
    assert report["metadata_drift"] is True
    assert report["corpus_drift"] is False
    assert report["counts"]["missing_in_index"] == 0
    assert report["counts"]["extra_in_index"] == 0


@pytest.mark.django_db
def test_consistency_audit_reports_missing_and_extra_documents():
    version, chunk = _version_and_ready_chunk()
    version.document_count = 1
    version.save(update_fields=["document_count", "updated_at"])
    with patch(
        "catalog.services.semantic_index_consistency._remote_document_identity",
        return_value=({"remote-extra": "extra-document"}, 1),
    ), patch(
        "catalog.services.semantic_index_consistency.semantic_index_document_count",
        return_value=1,
    ):
        report = audit_semantic_index_consistency(version)

    assert report["status"] == "drift"
    assert report["corpus_drift"] is True
    assert report["counts"]["missing_in_index"] == 1
    assert report["counts"]["extra_in_index"] == 1
    assert str(chunk.id) in report["missing_in_index_sample"]


@pytest.mark.django_db
def test_consistency_audit_reports_legacy_missing_document_id_as_schema_drift():
    version, chunk = _version_and_ready_chunk()
    version.document_count = 1
    version.save(update_fields=["document_count", "updated_at"])
    with patch(
        "catalog.services.semantic_index_consistency._remote_document_identity",
        return_value=({str(chunk.id): ""}, 1),
    ), patch(
        "catalog.services.semantic_index_consistency.semantic_index_document_count",
        return_value=1,
    ):
        report = audit_semantic_index_consistency(version)

    assert report["status"] == "drift"
    assert report["corpus_drift"] is False
    assert report["schema_drift"] is True
    assert report["counts"]["mismatched_document_id"] == 0
    assert report["counts"]["meilisearch_missing_document_id"] == 1


@pytest.mark.django_db
def test_non_active_metadata_repair_requires_exact_corpus_match():
    version, chunk = _version_and_ready_chunk()
    remote_identity = {str(chunk.id): chunk.document_id}
    with patch(
        "catalog.services.semantic_index_consistency._remote_document_identity",
        return_value=(remote_identity, 1),
    ), patch(
        "catalog.services.semantic_index_consistency.semantic_index_document_count",
        return_value=1,
    ):
        report = repair_semantic_index_version_metadata(version)

    version.refresh_from_db()
    assert report["status"] == "consistent"
    assert version.document_count == 1
    assert version.validation_details["metadata_reconciled_document_count"] == 1


@pytest.mark.django_db
def test_active_metadata_repair_is_refused():
    version, _chunk = _version_and_ready_chunk(SemanticIndexVersion.Status.ACTIVE)
    with pytest.raises(ValueError, match="活动索引只允许只读审计"):
        repair_semantic_index_version_metadata(version)


@pytest.mark.django_db
def test_incremental_job_requires_one_active_index_version():
    asset, _pages = _create_asset("version-guard")
    with pytest.raises(SemanticIndexVersionRequired):
        create_semantic_job(asset)

    version = SemanticIndexVersion.objects.create(
        uid="semantic-version-guard",
        provider="huggingFace",
        model_repo_id="test-model",
        status=SemanticIndexVersion.Status.ACTIVE,
    )
    job = create_semantic_job(asset)
    assert job.index_version_id == version.id
    assert active_semantic_index_version().id == version.id


@pytest.mark.django_db
def test_legacy_null_version_job_fails_closed_without_active_version():
    asset, _pages = _create_asset("legacy-null-version")
    job = SemanticIndexJob.objects.create(
        asset=asset,
        operation=SemanticIndexJob.Operation.BUILD,
        status=SemanticIndexJob.Status.QUEUED,
    )
    completed = run_semantic_index_job(str(job.id))
    completed.refresh_from_db()
    assert completed.status == SemanticIndexJob.Status.FAILED
    assert completed.error_code == "INDEX_VERSION_REQUIRED"


@pytest.mark.django_db
def test_model_unavailable_fails_job_and_restores_chunks_to_ready():
    version, chunk = _version_and_ready_chunk(SemanticIndexVersion.Status.ACTIVE)
    chunk.index_status = SemanticChunk.IndexStatus.INDEXING
    chunk.save(update_fields=["index_status", "updated_at"])
    token = "model-unavailable-task"
    job = SemanticIndexJob.objects.create(
        asset=chunk.asset,
        operation=SemanticIndexJob.Operation.BUILD,
        status=SemanticIndexJob.Status.QUEUED,
        task_id=token,
        index_version=version,
    )

    with patch(
        "catalog.services.semantic_indexing.build_semantic_chunks",
        return_value=[chunk],
    ), patch(
        "ingestion.services.processing.queue_query_lexicon_candidate_job",
        side_effect=RuntimeError("candidate enrichment is independent"),
    ), patch(
        "catalog.services.semantic_indexing.ensure_semantic_index",
        side_effect=SemanticModelUnavailable("offline model files are missing"),
    ):
        with pytest.raises(SemanticModelUnavailable):
            run_semantic_index_job(str(job.id), task_id=token)

    job.refresh_from_db()
    chunk.refresh_from_db()
    assert job.status == SemanticIndexJob.Status.FAILED
    assert job.error_code == "MODEL_UNAVAILABLE"
    assert chunk.index_status == SemanticChunk.IndexStatus.READY
    assert chunk.index_error == ""


@pytest.mark.django_db
def test_queue_version_guard_is_recorded_without_failing_source_pipeline():
    asset, _pages = _create_asset("queue-version-guard")
    edition_state = asset.edition.state

    first = queue_semantic_job(asset)
    second = queue_semantic_job(asset)

    assert first.status == SemanticIndexJob.Status.FAILED
    assert first.error_code == "INDEX_VERSION_REQUIRED"
    assert second.id == first.id
    asset.edition.refresh_from_db()
    assert asset.edition.state == edition_state
    assert asset.edition.semantic_index_status == "failed"
