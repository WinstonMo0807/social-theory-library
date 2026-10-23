"""Deferred acceptance: an OCR follow-up setting must survive checkpoints and preserve human review."""
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import EvidenceSnippet, KnowledgeNode, Page, Passage, TheoryReviewTask, WorkNodeRelation
from catalog.services.theory_suggestions import generate_theory_review_tasks
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.processing import OCRClaimSuperseded, _publish_ocr_result, _write_ocr_checkpoint
from ingestion.services.processing_commands import task_version
from ingestion.services.processing_followup import followup_state, run_concept_followup
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-workspace/"


def pending_followup(settings, tmp_path, actor):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    return ProcessingJob.objects.create(job_type="ocr", status="running", edition=edition, asset=asset,
        created_by=actor, task_id=str(uuid4()), stats={"source_sha256": asset.sha256,
            "requested_asset_id": str(asset.pk), "requested_mode": "all_pages", "completed_page_indexes": [1]})


def command(job, enabled):
    return {"source": "processing_job", "job_id": str(job.pk), "request_id": str(uuid4()),
            "action": "configure_followup", "expected_version": task_version(job), "align_concepts": enabled}


def test_toggle_replay_survives_worker_checkpoint_and_publication(api_client, admin_user, settings, tmp_path):
    job = pending_followup(settings, tmp_path, admin_user)
    stale_stats = dict(job.stats)
    body = command(job, False)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    first = api_client.post(URL, body, format="json", **headers)
    assert first.status_code == 200, first.data
    assert api_client.post(URL, body, format="json", **headers).data == first.data
    assert AuditEvent.objects.filter(action="processing.configure_followup", object_id=str(job.pk)).count() == 1
    _write_ocr_checkpoint(job, stats={**stale_stats, "processed_pages": 1})
    assert _publish_ocr_result(job, dict(stale_stats), job.task_id)
    job.refresh_from_db()
    assert job.stats["after_processing"]["align_concepts"] is False
    with patch("ingestion.services.processing.generate_theory_review_tasks") as generate:
        assert run_concept_followup(job) == {"enabled": False}
    generate.assert_not_called()
    job.refresh_from_db()
    assert followup_state(job)["state"] == "skipped"
    assert job.stats["completed_page_indexes"] == [1]


def test_phase_receipt_and_source_guards(api_client, admin_user, settings, tmp_path):
    job = pending_followup(settings, tmp_path, admin_user)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    stopped = command(job, False)
    assert api_client.post(f"{URL}commands/{stopped['request_id']}/", {"action": "cancel_pending"}, format="json", **headers).status_code == 200
    assert api_client.post(URL, stopped, format="json", **headers).data["state"] == "cancelled"
    assert api_client.post(URL, command(job, False), format="json", HTTP_X_EDITOR_OWNER=str(uuid4())).status_code == 403
    job.asset.sha256 = "f" * 64
    job.asset.save(update_fields=["sha256", "updated_at"])
    assert api_client.post(URL, command(job, False), format="json", **headers).status_code == 409
    job.stats = {**job.stats, "concept_alignment": {"state": "running"}}
    job.save(update_fields=["stats", "updated_at"])
    assert api_client.post(URL, command(job, False), format="json", **headers).status_code == 409
    assert not AuditEvent.objects.filter(action="processing.configure_followup", object_id=str(job.pk)).exists()


def test_followup_uses_existing_service_once_and_fences_replaced_worker(admin_user, settings, tmp_path):
    job = pending_followup(settings, tmp_path, admin_user)
    result = {"enabled": True, "created": 2, "updated": 1, "new_node_tasks": 0}
    with patch("ingestion.services.processing.generate_theory_review_tasks", return_value=result) as generate:
        assert run_concept_followup(job) == result
        assert run_concept_followup(job) == result
    generate.assert_called_once_with(job.asset, actor=admin_user, force=False)
    job.refresh_from_db()
    assert followup_state(job)["counts"]["created"] == 2
    ProcessingJob.objects.filter(pk=job.pk).update(task_id=str(uuid4()))
    with patch("ingestion.services.processing.generate_theory_review_tasks") as late:
        with pytest.raises(OCRClaimSuperseded):
            run_concept_followup(job)
    late.assert_not_called()


def test_new_task_saves_followup_choice_before_dispatch(api_client, admin_user, settings, tmp_path):
    _, _, _, asset = create_item_with_files(settings, tmp_path)
    api_client.force_authenticate(admin_user)
    body = {"action": "create", "task_type": "ocr", "request_id": str(uuid4()), "asset_id": str(asset.pk),
            "source_version": asset.updated_at.isoformat(), "confirmed": True, "align_concepts": False}
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    with patch("ingestion.services.processing.dispatch_ocr_job"):
        created = api_client.post(URL, body, format="json", **headers)
    assert created.status_code == 200, created.data
    job = ProcessingJob.objects.get(pk=created.data["job_id"])
    assert job.stats["after_processing"] == {"align_concepts": False}
    assert api_client.post(URL, {**body, "align_concepts": True}, format="json", **headers).status_code == 409
    assert api_client.post(URL, body, format="json", **headers).data == created.data


@pytest.mark.parametrize("decision", ["confirmed", "rejected", "deferred", "needs_changes", "insufficient_evidence"])
def test_regeneration_keeps_human_decisions_and_quotes(admin_user, settings, tmp_path, decision):
    settings.THEORY_SYSTEM_ENABLED = True
    work, _, _, asset = create_item_with_files(settings, tmp_path, title="象征互动论的经验研究")
    asset.page_count = 3
    asset.save(update_fields=["page_count", "updated_at"])
    node = KnowledgeNode.objects.create(node_type="theory_tradition", canonical_name_zh="象征互动论", slug="interaction", status="published")
    for index in (1, 2, 3):
        text = "本文依据象征互动论分析日常互动，象征互动论强调行动者对情境意义的解释。"
        page = Page.objects.create(asset=asset, index=index, text=text, normalized_text=text, text_source="embedded")
        Passage.objects.create(page=page, order=0, text=text, normalized_text=text)
    generate_theory_review_tasks(asset, actor=admin_user)
    task = TheoryReviewTask.objects.get(work=work, candidate_node=node)
    relation = WorkNodeRelation.objects.get(work=work, node=node)
    snippet = EvidenceSnippet.objects.filter(work=work, node=node).first()
    snippet.quote, snippet.reviewed_by, snippet.reviewed_at = "人工核对后保留的原句", admin_user, timezone.now()
    snippet.save()
    # Even a pending relation with an editor attribution is protected.
    relation.reviewed_by, relation.reviewed_at, relation.confidence = admin_user, timezone.now(), .42
    relation.save()
    generate_theory_review_tasks(asset, actor=admin_user, force=True)
    relation.refresh_from_db()
    assert relation.confidence == .42
    relation.reviewed_by, relation.reviewed_at = None, None
    relation.save()
    generate_theory_review_tasks(asset, actor=admin_user, force=True)
    snippet.refresh_from_db()
    assert snippet.quote == "人工核对后保留的原句"
    task.status, task.evidence_text = decision, "人工决定与原证据"
    task.save()
    result = generate_theory_review_tasks(asset, actor=admin_user, force=True)
    task.refresh_from_db()
    assert (task.status, task.evidence_text) == (decision, "人工决定与原证据")
    assert result["protected_nodes"] == 1
