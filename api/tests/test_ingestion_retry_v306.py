"""Exercise the recovery contract locally as well as on the PostgreSQL suite."""

import pytest

from ingestion.models import MetadataCandidate, UploadBatch, UploadItem
from ingestion.services.metadata import Candidate
from ingestion.services.taxonomy import persist_controlled_vocabulary_candidates

from .test_ingestion_postgres_integration import (
    test_postgres_historical_metadata_failure_retry_is_idempotent_and_reuses_catalog as run_recovery,
)


@pytest.mark.django_db(transaction=True)
def test_metadata_retry_keeps_catalog_candidates_and_manual_lock(api_client, admin_user, tmp_path, settings):
    run_recovery(api_client, admin_user, tmp_path, settings)


@pytest.mark.django_db
@pytest.mark.parametrize("lifecycle,locked", [("accepted", True), ("rejected", False)])
def test_classifier_retry_reuses_actual_source_and_preserves_human_decision(admin_user, lifecycle, locked):
    item = UploadItem.objects.create(batch=UploadBatch.objects.create(created_by=admin_user), source_filename="local-fixture.pdf")
    suggestion = Candidate("topics", "社会认同", "keyword_classifier_v3_candidate", 0.8, {"quote": "原文线索"})
    first = persist_controlled_vocabulary_candidates(item, [suggestion, suggestion])
    assert first["created"] == 1
    row = item.metadata_candidates.get()
    row.lifecycle, row.is_locked, row.selected = lifecycle, locked, lifecycle == "accepted"
    row.save()
    evidence_ids = set(row.evidence_records.values_list("pk", flat=True))
    repeated = persist_controlled_vocabulary_candidates(item, [suggestion])
    row.refresh_from_db()
    assert repeated["created"] == 0 and item.metadata_candidates.count() == 1
    assert row.lifecycle == lifecycle and row.is_locked == locked
    assert row.selected == (lifecycle == MetadataCandidate.Lifecycle.ACCEPTED)
    assert set(row.evidence_records.values_list("pk", flat=True)) == evidence_ids
