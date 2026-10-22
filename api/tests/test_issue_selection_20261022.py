"""Selection and assistant review contracts; execute only at unified acceptance."""
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError

from catalog.models import KnowledgeNode
from catalog.services import editorial_assistance as assistant, editorial_issues as ledger
from catalog.services.editorial_selection import normalize
from ingestion.models import AuditEvent
from .test_issue_workbench_20261022 import new_issue, command

pytestmark = pytest.mark.django_db


def chosen(actor):
    node = KnowledgeNode.objects.create(canonical_name_zh="选材验收概念", node_type="concept", slug=f"selection-{uuid4().hex}", status="published")
    reference = {"type": "node", "id": str(node.pk)}
    issue = new_issue(actor, selection_workspace={"question": "只供验收的策划问题", "query": "概念", "filters": {}, "references": [reference]})
    return issue, node, reference


def generated_job(actor):
    issue, node, reference = chosen(actor)
    job = assistant.request_assistance(issue.pk, {"request_id": str(uuid4()), "edit_version": ledger.edit_version("recommendation_issue", issue.pk),
        "operation": "guide", "question": "校对材料", "references": [reference]}, actor)
    suggestion = {"id": str(uuid4()), "kind": "paragraph", "text": "仅供隔离验收的候选", "source_keys": ["s1"], "gap": "缺少直接原文"}
    job.status = "succeeded"
    job.stats = {**job.stats, "suggestions": [suggestion], "stage": "candidate"}
    job.save(update_fields=["status", "stats", "updated_at"])
    return issue, node, job, suggestion


def review(job, suggestion, action="adopt", **extra):
    return {"action": action, "request_id": str(uuid4()), "edit_version": job.stats["edit_version"], "suggestion_ids": [suggestion["id"]], **extra}


def test_selection_persists_only_ids_and_never_reaches_public_payload(admin_user):
    issue, node, reference = chosen(admin_user)
    payload = ledger.issue_payload(issue)
    payload["selection_workspace"]["materials"] = [{"text": "不能信任或保存的客户端来源"}]
    ledger.save_issue(issue.pk, payload, admin_user)
    raw = ledger.issue_draft_payload(issue)["selection_workspace"]
    assert raw["references"] == [reference] and "materials" not in raw
    assert ledger.issue_payload(issue)["selection_workspace"]["materials"][0]["source"]["title"] == node.canonical_name_zh
    ledger.publish_issue(issue.pk, ledger.edit_version("recommendation_issue", issue.pk), admin_user)
    issue.refresh_from_db()
    assert "selection_workspace" not in ledger.issue_payload(issue, public=True)
    assert "selection_workspace" not in ledger.issue_payload(issue, include_body=False)


def test_selected_source_withdrawal_is_explicit_and_cannot_generate(admin_user):
    issue, node, reference = chosen(admin_user)
    KnowledgeNode.objects.filter(pk=node.pk).update(status="draft")
    material = ledger.issue_payload(issue)["selection_workspace"]["materials"][0]
    assert material["available"] and not material["public_eligible"]
    from django.http import Http404
    with pytest.raises(Http404):
        assistant.request_assistance(issue.pk, {"request_id": str(uuid4()), "edit_version": ledger.edit_version("recommendation_issue", issue.pk), "operation": "outline", "question": "检查资格", "references": [reference]}, admin_user)


def test_selection_rejects_scope_bypass_and_duplicate_identity(admin_user):
    issue, node, reference = chosen(admin_user)
    for value in ({"filters": {"access": ["restricted"]}}, {"references": [reference, reference]}, {"filters": {"year_min": 2020, "year_max": 1900}}):
        with pytest.raises(ValidationError):
            normalize(value)
    by_slug = normalize({"filters": {"topic_ids": ["topic-example"], "theory_node_ids": ["theory-example"]}})
    assert normalize(by_slug) == by_slug


def test_reviewed_candidate_appends_draft_once_and_keeps_original_text(admin_user):
    issue, node, job, suggestion = generated_job(admin_user)
    previous = deepcopy(ledger.issue_draft_payload(issue)["body_blocks"])
    data = review(job, suggestion, edits={suggestion["id"]: "管理员明确修改后的候选文字"})
    assistant.assistance_action(job.pk, data, admin_user)
    version = ledger.edit_version("recommendation_issue", issue.pk)
    assistant.assistance_action(job.pk, data, admin_user)
    assert ledger.edit_version("recommendation_issue", issue.pk) == version
    blocks = ledger.issue_draft_payload(issue)["body_blocks"]
    assert blocks[:len(previous)] == previous
    assert blocks[-2]["text"] == data["edits"][suggestion["id"]]
    assert blocks[-1]["text"] == "材料缺口：缺少直接原文"
    issue.refresh_from_db()
    assert issue.active_revision_id is None
    with pytest.raises(ledger.EditConflict):
        assistant.assistance_action(job.pk, {**data, "edits": {suggestion["id"]: "同编号不同输入"}}, admin_user)


def test_dismiss_remains_possible_after_source_and_draft_change(admin_user):
    issue, node, job, suggestion = generated_job(admin_user)
    ledger.save_issue(issue.pk, command(issue, introduction="后续人工内容"), admin_user)
    KnowledgeNode.objects.filter(pk=node.pk).update(status="draft")
    version = ledger.edit_version("recommendation_issue", issue.pk)
    data = review(job, suggestion, "dismiss")
    assistant.assistance_action(job.pk, data, admin_user)
    result = assistant.assistance_action(job.pk, data, admin_user)
    assert result.stats["dismissed_ids"] == [suggestion["id"]]
    assert ledger.edit_version("recommendation_issue", issue.pk) == version


def test_stale_adoption_and_cross_candidate_edits_do_not_save(admin_user):
    issue, node, job, suggestion = generated_job(admin_user)
    with pytest.raises(ValidationError):
        assistant.assistance_action(job.pk, review(job, suggestion, edits={str(uuid4()): "其他建议"}), admin_user)
    ledger.save_issue(issue.pk, command(issue, title="另一位编辑的标题"), admin_user)
    with pytest.raises(ledger.EditConflict):
        assistant.assistance_action(job.pk, review(job, suggestion), admin_user)
    assert len(ledger.issue_draft_payload(issue)["body_blocks"]) == 1


def test_retry_receipt_does_not_cancel_or_restart_a_later_attempt(admin_user):
    issue, node, job, suggestion = generated_job(admin_user)
    job.status = "failed"
    job.save(update_fields=["status"])
    data = {"action": "retry", "request_id": str(uuid4()), "task_token": job.task_id}
    first = assistant.assistance_action(job.pk, data, admin_user)
    token = first.task_id
    second = assistant.assistance_action(job.pk, data, admin_user)
    assert token == second.task_id and second.status == "pending"
    receipt = AuditEvent.objects.get(action="editorial.assistance.retry", request_id=data["request_id"])
    assert receipt.before["suggestions"] == [suggestion]
    assert not second.stats["suggestions"]
    with pytest.raises(ledger.EditConflict):
        assistant.assistance_action(job.pk, {"action": "cancel", "request_id": str(uuid4()), "task_token": data["task_token"]}, admin_user)


def test_partial_generation_keeps_only_complete_validated_candidates(admin_user):
    issue, node, job, suggestion = generated_job(admin_user)
    job.status = "pending"
    job.stats = {**job.stats, "suggestions": []}
    job.save(update_fields=["status", "stats"])
    output = {"suggestions": [{"kind": "paragraph", "text": "已经校验的候选", "source_keys": ["s1"], "gap": ""}, {"kind": "paragraph", "text": "错误来源", "source_keys": ["invented"], "gap": ""}]}
    with patch("reading.local_analysis.generate_local", return_value=(output, {"model": "isolated-fixture"})):
        result = assistant.run_assistance(job.pk, job.task_id)
    payload = assistant.assistance_payload(result, admin_user)
    assert result.status == "failed" and payload["stage"] == "partial"
    assert len(payload["suggestions"]) == 1 and payload["can_adopt"]


def test_cancel_partial_task_keeps_validated_candidates_for_review(admin_user):
    issue, node, job, suggestion = generated_job(admin_user)
    job.status = "failed"
    job.stats = {**job.stats, "stage": "partial"}
    job.save(update_fields=["status", "stats"])
    data = {"action": "cancel", "request_id": str(uuid4()), "task_token": job.task_id}
    canceled = assistant.assistance_action(job.pk, data, admin_user)
    assert canceled.status == "canceled" and canceled.stats["suggestions"] == [suggestion]
    assert assistant.assistance_payload(canceled, admin_user)["can_adopt"]
    assert len(ledger.issue_draft_payload(issue)["body_blocks"]) == 1


def test_editor_owner_and_reader_cannot_change_assistant(api_client, admin_user, reader_user):
    issue, node, job, suggestion = generated_job(admin_user)
    url = f"/api/catalog/admin/recommendation-issues/{issue.pk}/assistant/{job.pk}/"
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, review(job, suggestion), format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.post(url, review(job, suggestion), format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
