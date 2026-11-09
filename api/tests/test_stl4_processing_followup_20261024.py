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


def test_retired_toggle_preserves_worker_checkpoint_and_publication(api_client, admin_user, settings, tmp_path):
    job = pending_followup(settings, tmp_path, admin_user)
    job.stats["after_processing"] = {"align_concepts": False}
    job.save(update_fields=["stats"])
    stale_stats = dict(job.stats)
    api_client.force_authenticate(admin_user)
    response = api_client.post(URL, command(job, True), format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 409
    _write_ocr_checkpoint(job, stats={**stale_stats, "processed_pages": 1})
    assert _publish_ocr_result(job, dict(stale_stats), job.task_id)
    job.refresh_from_db()
    with patch("catalog.services.theory_suggestions.generate_theory_review_tasks") as generate:
        assert run_concept_followup(job)["retired"]
    generate.assert_not_called()
    assert followup_state(job)["state"] == "disabled" and not followup_state(job)["can_configure"]
    assert job.stats["completed_page_indexes"] == [1] and job.stats["after_processing"]["align_concepts"] is False
    assert not AuditEvent.objects.filter(action="processing.configure_followup", object_id=str(job.pk)).exists()


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


def test_old_and_replaced_worker_cannot_generate_new_candidates(admin_user, settings, tmp_path):
    job = pending_followup(settings, tmp_path, admin_user)
    before = dict(job.stats)
    with patch("catalog.services.theory_suggestions.generate_theory_review_tasks") as generate:
        assert run_concept_followup(job)["retired"]
        ProcessingJob.objects.filter(pk=job.pk).update(task_id=str(uuid4()))
        assert run_concept_followup(job)["retired"]
    generate.assert_not_called()
    job.refresh_from_db()
    assert job.stats == before and not TheoryReviewTask.objects.exists()


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
    task = TheoryReviewTask.objects.create(work=work, file=asset, candidate_node=node, task_type="work_node",
        status=decision, evidence_text="人工决定与原证据")
    relation = WorkNodeRelation.objects.create(work=work, node=node, role="general_mention", status="published",
        reviewed_by=admin_user, reviewed_at=timezone.now(), confidence=.42)
    snippet = EvidenceSnippet.objects.create(work=work, file=asset, node=node, work_node_relation=relation,
        page_number=1, quote="人工核对后保留的原句", reviewed_by=admin_user, reviewed_at=timezone.now())
    for force in [False, True]:
        result = generate_theory_review_tasks(asset, actor=admin_user, force=force)
        assert result["retired"] and not result["enabled"]
    task.refresh_from_db(); relation.refresh_from_db(); snippet.refresh_from_db()
    assert (task.status, task.evidence_text) == (decision, "人工决定与原证据")
    assert relation.confidence == .42 and relation.reviewed_by == admin_user
    assert snippet.quote == "人工核对后保留的原句" and snippet.reviewed_by == admin_user
    assert TheoryReviewTask.objects.count() == WorkNodeRelation.objects.count() == EvidenceSnippet.objects.count() == 1
