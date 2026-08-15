from importlib import import_module
from unittest.mock import Mock

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from ingestion.models import (
    CandidateEvidence,
    DecisionLog,
    EntityResolutionCandidate,
    MetadataCandidate,
    ProcessingAttempt,
    ProcessingJob,
    ReviewTask,
    SourceRecord,
    UploadBatch,
    UploadItem,
)
from ingestion.serializers import MetadataCandidateSerializer, UploadBatchSerializer, UploadItemSerializer


@pytest.mark.django_db
def test_ingestion_foundation_defaults_are_compatible_with_existing_uploads(admin_user):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="foundation.pdf")

    assert batch.label == ""
    assert batch.access_policy == UploadBatch.AccessPolicy.PUBLIC
    assert batch.ocr_strategy == UploadBatch.OcrStrategy.AUTO
    assert batch.duplicate_policy == UploadBatch.DuplicatePolicy.REVIEW
    assert batch.external_enrichment_enabled is True
    assert batch.ai_suggestions_enabled is False
    assert item.workflow_state == UploadItem.WorkflowState.UPLOADED
    assert item.priority == 0
    assert item.preflight_summary == {}
    assert item.workflow_updated_at is not None

    batch_payload = UploadBatchSerializer(batch).data
    item_payload = UploadItemSerializer(item).data
    assert batch_payload["ocr_strategy"] == "auto"
    assert batch_payload["duplicate_policy"] == "review"
    assert item_payload["workflow_state"] == "uploaded"
    assert item_payload["preflight_summary"] == {}


@pytest.mark.django_db
def test_source_candidates_evidence_and_decisions_keep_provenance(admin_user):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="provenance.pdf")
    source = SourceRecord.objects.create(
        upload_item=item,
        provider="open_library",
        operation="lookup_book_by_isbn",
        query={"isbn": "9780000000000"},
        request_fingerprint="sha256:request",
        external_id="OL1M",
        raw_response={"title": "候选书名"},
        provider_version="v1",
        status=SourceRecord.Status.SUCCEEDED,
    )
    candidate = MetadataCandidate.objects.create(
        upload_item=item,
        field_name="title",
        value="候选书名",
        normalized_value="候选书名",
        source="open_library",
        source_record=source,
        conflict_group="title-primary",
        confidence=0.82,
        score_factors={"identifier_match": 1.0},
    )
    evidence = CandidateEvidence.objects.create(
        metadata_candidate=candidate,
        source_record=source,
        page_number=4,
        bbox=[10, 20, 100, 60],
        text_quote="候选书名",
        source_kind="external_record",
    )
    resolution = EntityResolutionCandidate.objects.create(
        upload_item=item,
        source_record=source,
        target_type="agent",
        source_name="王明",
        candidate_entity_type="person",
        candidate_entity_id="authority-1",
        label="王明（社会学者）",
        match_score=0.74,
        match_reasons=["名称一致"],
        conflicts=["同名人物"],
    )
    review_task = ReviewTask.objects.create(
        upload_item=item,
        task_type="entity_resolution",
        target_type="upload_item",
        target_id=str(item.id),
        title="确认同名人物",
        created_by=admin_user,
    )
    decision = DecisionLog.objects.create(
        upload_item=item,
        review_task=review_task,
        metadata_candidate=candidate,
        resolution_candidate=resolution,
        actor=admin_user,
        action="defer",
        target_type="entity_resolution_candidate",
        target_id=str(resolution.id),
        reason="需要更多身份属性",
    )

    payload = MetadataCandidateSerializer(candidate).data
    assert payload["source_record"] == source.id
    assert payload["lifecycle"] == MetadataCandidate.Lifecycle.PROPOSED
    assert payload["evidence_records"][0]["id"] == str(evidence.id)
    assert decision.review_task_id == review_task.id
    with pytest.raises(ProtectedError):
        source.delete()


@pytest.mark.django_db
def test_processing_idempotency_keys_are_unique_only_when_present(admin_user):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="idempotency.pdf")

    ProcessingAttempt.objects.create(upload_item=item, stage="preflight")
    ProcessingAttempt.objects.create(upload_item=item, stage="preflight")
    ProcessingAttempt.objects.create(
        upload_item=item,
        stage="preflight",
        idempotency_key="attempt:preflight:one",
        correlation_id="ingestion:one",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ProcessingAttempt.objects.create(
                upload_item=item,
                stage="preflight",
                idempotency_key="attempt:preflight:one",
            )

    ProcessingJob.objects.create(job_type=ProcessingJob.JobType.OCR)
    ProcessingJob.objects.create(job_type=ProcessingJob.JobType.OCR)
    ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.OCR,
        idempotency_key="job:ocr:one",
        correlation_id="ingestion:one",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ProcessingJob.objects.create(
                job_type=ProcessingJob.JobType.OCR,
                idempotency_key="job:ocr:one",
            )


@pytest.mark.django_db
def test_admin_redesign_data_migration_maps_legacy_state_without_accepting_new_candidates(
    admin_user,
):
    migration = import_module("ingestion.migrations.0008_admin_redesign_foundation")
    connection = Mock()
    connection.vendor = "postgresql"
    schema_editor = Mock()
    schema_editor.connection = connection
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=4)
    mappings = {
        UploadItem.Status.VALIDATING: UploadItem.WorkflowState.PREFLIGHT,
        UploadItem.Status.OCR: UploadItem.WorkflowState.PARSING,
        UploadItem.Status.NEEDS_REVIEW: UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.Status.WITHDRAWN: UploadItem.WorkflowState.ARCHIVED,
    }
    items = []
    for index, legacy_status in enumerate(mappings):
        items.append(
            UploadItem.objects.create(
                batch=batch,
                source_filename=f"legacy-{index}.pdf",
                status=legacy_status,
            )
        )
    selected = MetadataCandidate.objects.create(
        upload_item=items[0],
        field_name="title",
        value="旧系统已选值",
        source="legacy",
        selected=True,
    )
    proposed = MetadataCandidate.objects.create(
        upload_item=items[0],
        field_name="publisher",
        value="仍待审核",
        source="legacy",
        selected=False,
    )

    migration.backfill_admin_redesign_state(apps, schema_editor)
    connection.check_constraints.assert_called_once_with()

    for item in items:
        item.refresh_from_db()
        assert item.workflow_state == mappings[item.status]
        assert item.workflow_updated_at == item.updated_at
    selected.refresh_from_db()
    proposed.refresh_from_db()
    assert selected.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED
    assert selected.accepted_by_id is None
    assert proposed.lifecycle == MetadataCandidate.Lifecycle.PROPOSED
