"""Deferred acceptance for refresh-safe assistance commands; never dispatch a model."""
from uuid import uuid4

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import User
from catalog.models import RecommendationIssue
from catalog.editorial_assistance_views import EditorialAssistanceReceiptView
from catalog.services import editorial_assistance as service, editorial_issues as ledger
from ingestion.models import AuditEvent, ProcessingJob


@pytest.mark.django_db
def test_stopping_unknown_request_blocks_late_generation_without_creating_a_job(admin_user):
    issue = RecommendationIssue.objects.create(title="恢复助手", slug="recover-assistance")
    request_id = uuid4()
    request = APIRequestFactory().post("/assistant/commands/", {"action":"cancel_pending"}, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    force_authenticate(request, user=admin_user)
    response = EditorialAssistanceReceiptView.as_view()(request, issue_id=issue.pk, request_id=request_id)
    assert response.status_code == 200 and response.data["state"] == "cancelled"
    initial = ProcessingJob.objects.count()
    with pytest.raises(ledger.EditConflict):
        service.request_assistance(issue.pk, {"request_id":str(request_id), "edit_version":"0", "operation":"outline", "question":"迟到请求", "references":[]}, admin_user)
    assert ProcessingJob.objects.count() == initial


@pytest.mark.django_db
def test_applied_receipt_is_bound_to_actor_and_article(admin_user):
    issue = RecommendationIssue.objects.create(title="原文章", slug="receipt-article")
    other_issue = RecommendationIssue.objects.create(title="另一文章", slug="receipt-other-article")
    other = User.objects.create_user(username="other-receipt", email="other-receipt@example.test", role="admin")
    request_id = uuid4()
    job = ProcessingJob.objects.create(job_type=service.JOB_TYPE, status="succeeded", created_by=admin_user,
        stats={"issue_id":str(issue.pk), "assistant_operation":"outline", "edit_version":ledger.edit_version("recommendation_issue", issue.pk), "references":[]})
    AuditEvent.objects.create(actor=admin_user, request_id=str(request_id), action="editorial.assistance.adopt", object_type="ProcessingJob", object_id=str(job.pk))
    initial = AuditEvent.objects.count()
    receipt = service.command_receipt(issue.pk, request_id, admin_user)
    assert receipt["state"] == "applied" and receipt["operation"] == "adopt" and receipt["task"]["id"] == str(job.pk)
    assert service.command_receipt(other_issue.pk, request_id, admin_user) is None
    assert service.command_receipt(issue.pk, request_id, other) is None
    assert AuditEvent.objects.count() == initial
