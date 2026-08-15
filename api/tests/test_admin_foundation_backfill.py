from io import StringIO
import json

from django.core.management import call_command
from django.core.management.base import CommandError
import pytest

from catalog.models import Contribution, DocumentType, Edition, Person, PublicationState, Work
from ingestion.models import (
    CandidateEvidence,
    DecisionLog,
    FieldLock,
    MetadataCandidate,
    ReviewTask,
    SourceRecord,
    UploadBatch,
    UploadItem,
)


pytestmark = pytest.mark.django_db


def make_legacy_records(admin_user):
    work = Work.objects.create(document_type=DocumentType.BOOK, title="旧入库记录")
    edition = Edition.objects.create(work=work, state=PublicationState.DRAFT)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="legacy.pdf",
        recognized_metadata={"authors": ["王明", {"literal": "新作者"}]},
    )
    first_person = Person.objects.create(preferred_name="王明", sort_name="王明")
    second_person = Person.objects.create(preferred_name="王 明", sort_name="王明")
    Contribution.objects.create(
        edition=edition,
        person=first_person,
        role=Contribution.Role.AUTHOR,
        approved=True,
        source="legacy_manual_review",
    )
    lock = FieldLock.objects.create(
        edition=edition,
        field_name="title",
        locked_by=admin_user,
        locked_value="旧入库记录",
        reason="人工复核",
    )
    locked_candidate = MetadataCandidate.objects.create(
        upload_item=item,
        field_name="title",
        value="旧入库记录",
        source="crossref",
        evidence={"doi": "10.1234/example", "page": 2, "text_quote": "旧入库记录"},
        confidence=0.96,
        selected=True,
        lifecycle=MetadataCandidate.Lifecycle.PROPOSED,
    )
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="title",
        value="旧入库纪录",
        source="ocr",
        evidence={"page": 2, "text_quote": "旧入库纪录"},
        confidence=0.55,
    )
    uncertain_candidate = MetadataCandidate.objects.create(
        upload_item=item,
        field_name="publisher",
        value="某出版社",
        source="legacy",
        confidence=0.7,
        selected=True,
        lifecycle=MetadataCandidate.Lifecycle.ACCEPTED,
    )
    return {
        "work": work,
        "edition": edition,
        "item": item,
        "people": (first_person, second_person),
        "lock": lock,
        "locked_candidate": locked_candidate,
        "uncertain_candidate": uncertain_candidate,
    }


def test_backfill_defaults_to_dry_run_and_returns_json_report(admin_user):
    records = make_legacy_records(admin_user)
    output = StringIO()

    call_command(
        "backfill_admin_foundation",
        "--format",
        "json",
        "--item-id",
        str(records["item"].id),
        stdout=output,
    )

    report = json.loads(output.getvalue())
    assert report["mode"] == "dry-run"
    assert report["action_count"] > 0
    assert report["summary"]["person_duplicate_review"] == 1
    assert report["summary"]["author_reconciliation"] == 2
    records["people"][0].refresh_from_db()
    records["locked_candidate"].refresh_from_db()
    assert records["people"][0].authority_status == Person.AuthorityStatus.DRAFT
    assert records["locked_candidate"].lifecycle == MetadataCandidate.Lifecycle.PROPOSED
    assert SourceRecord.objects.count() == 0
    assert ReviewTask.objects.count() == 0
    assert not records["item"].entity_resolution_candidates.exists()


def test_apply_backfill_is_additive_review_first_and_idempotent(admin_user):
    records = make_legacy_records(admin_user)
    output = StringIO()

    call_command(
        "backfill_admin_foundation",
        "--apply",
        "--format",
        "json",
        "--item-id",
        str(records["item"].id),
        stdout=output,
    )

    report = json.loads(output.getvalue())
    assert report["mode"] == "apply"
    assert report["applied"]["candidate_enrich"] >= 2
    first_person, second_person = records["people"]
    first_person.refresh_from_db()
    second_person.refresh_from_db()
    assert first_person.authority_status == Person.AuthorityStatus.NEEDS_REVIEW
    assert second_person.authority_status == Person.AuthorityStatus.DRAFT
    assert Person.objects.count() == 2

    candidate = records["locked_candidate"]
    candidate.refresh_from_db()
    assert candidate.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED
    assert candidate.selected is True
    assert candidate.is_locked is True
    assert candidate.accepted_by_id == admin_user.id
    assert candidate.accepted_at == records["lock"].created_at
    assert candidate.normalized_value == "旧入库记录"
    assert candidate.conflict_group
    assert candidate.score_factors["calibration_version"] == "metadata-candidate-v1"
    assert candidate.source_record.provider == "crossref"
    assert candidate.source_record.raw_response["raw_response_available"] is False
    assert candidate.source_record.raw_response["backfill_version"] == "admin-foundation-v1"
    evidence = CandidateEvidence.objects.get(metadata_candidate=candidate)
    assert evidence.page_number == 2
    assert evidence.source_record_id == candidate.source_record_id
    decision = DecisionLog.objects.get(
        metadata_candidate=candidate,
        action="backfill_accept_metadata_candidate",
    )
    assert decision.actor_id == admin_user.id
    assert decision.reason == "由既有人工字段锁补齐候选决定来源"

    assert ReviewTask.objects.filter(task_type="authority_reconciliation").count() == 1
    duplicate_task = ReviewTask.objects.get(task_type="duplicate_person_authority")
    assert duplicate_task.details["automatic_merge_allowed"] is False
    assert ReviewTask.objects.filter(task_type="legacy_candidate_provenance").count() == 1
    assert ReviewTask.objects.filter(task_type="metadata_candidate_consistency").count() == 1
    assert records["item"].entity_resolution_candidates.filter(source_name="王明").count() == 2
    assert records["item"].entity_resolution_candidates.filter(source_name="新作者").count() == 1

    records["edition"].refresh_from_db()
    assert records["edition"].state == PublicationState.DRAFT
    assert Work.objects.filter(pk=records["work"].id).exists()

    second_output = StringIO()
    call_command(
        "backfill_admin_foundation",
        "--apply",
        "--format",
        "json",
        "--item-id",
        str(records["item"].id),
        stdout=second_output,
    )
    second_report = json.loads(second_output.getvalue())
    assert second_report["action_count"] == 0
    assert second_report["applied"] == {}
    assert Person.objects.count() == 2
    assert SourceRecord.objects.count() == 1
    assert CandidateEvidence.objects.filter(metadata_candidate=candidate).count() == 1
    assert DecisionLog.objects.filter(metadata_candidate=candidate).count() == 1


def test_csv_report_can_be_written_without_applying(tmp_path, admin_user):
    records = make_legacy_records(admin_user)
    report_path = tmp_path / "admin-foundation.csv"

    call_command(
        "backfill_admin_foundation",
        "--dry-run",
        "--format",
        "csv",
        "--output",
        str(report_path),
        "--item-id",
        str(records["item"].id),
    )

    content = report_path.read_text(encoding="utf-8")
    assert content.startswith("mode,code,target_type,target_id,reason,details")
    assert "dry-run,author_reconciliation" in content
    assert SourceRecord.objects.count() == 0


def test_backfill_rejects_invalid_scope_identifier():
    with pytest.raises(CommandError, match="不是有效 UUID"):
        call_command("backfill_admin_foundation", "--item-id", "not-a-uuid")
