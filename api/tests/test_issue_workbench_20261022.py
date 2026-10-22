"""Draft receipt, restore and readonly-source contracts; run at unified acceptance."""
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.http import Http404
from rest_framework.exceptions import ValidationError

from catalog.models import EditorialRevision, KnowledgeNode, RecommendationIssueItem
from catalog.services import editorial_issues as service
from ingestion.models import AuditEvent
from .test_v307_editorial_issues import public_edition

pytestmark = pytest.mark.django_db


def new_issue(actor, **data):
    return service.create_issue({"title": "编辑器隔离验收材料", "body_blocks": [{"id": str(uuid4()), "type": "paragraph", "text": "人工导读"}], **data}, actor)


def command(issue, **data):
    return {**service.issue_draft_payload(issue), "edit_version": service.edit_version("recommendation_issue", issue.pk), "request_id": str(uuid4()), **data}


def test_replayed_save_keeps_one_revision_and_one_planned_identity(admin_user):
    issue = new_issue(admin_user)
    data = command(issue, autosave=True, items=[{"id": str(uuid4()), "kind": "planned", "title": "仅供验收的计划书目"}])
    first = service.save_issue(issue.pk, data, admin_user)
    version = service.edit_version("recommendation_issue", issue.pk)
    item = issue.items.get()
    repeat = service.save_issue(issue.pk, deepcopy(data), admin_user)
    assert service.edit_version("recommendation_issue", issue.pk) == version
    assert EditorialRevision.objects.filter(target_type="recommendation_issue", target_id=issue.pk).count() == 2
    assert RecommendationIssueItem.objects.filter(issue=issue).count() == 1
    assert issue.items.get().cataloging_session_id == item.cataloging_session_id
    assert service.issue_payload(first)["request_found"] is True
    assert service.issue_payload(repeat)["is_current_revision"] is True
    assert service._latest("recommendation_issue", issue.pk).change_note == "自动保存"
    assert issue.active_revision_id is None


def test_same_save_nonce_cannot_change_content_and_late_receipt_is_explicit(admin_user):
    issue = new_issue(admin_user)
    data = command(issue, title="第一次保存")
    service.save_issue(issue.pk, data, admin_user)
    with pytest.raises(service.EditConflict):
        service.save_issue(issue.pk, {**data, "title": "另一份输入"}, admin_user)
    service.save_issue(issue.pk, command(issue, title="后来的修订"), admin_user)
    result = service.issue_payload(service.save_issue(issue.pk, data, admin_user))
    assert result["request_found"] and not result["is_current_revision"]
    assert result["title"] == "后来的修订"


def test_receipt_is_actor_and_issue_scoped(api_client, admin_user, reader_user):
    issue = new_issue(admin_user)
    data = command(issue)
    service.save_issue(issue.pk, data, admin_user)
    assert service.issue_save_receipt(issue, data["request_id"], reader_user) is None
    other = new_issue(admin_user)
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/recommendation-issues/{issue.pk}/"
    found = api_client.get(url, {"request_id": data["request_id"]})
    assert found.status_code == 200 and found.data["request_found"]
    assert found["Cache-Control"] == "private, no-store"
    assert api_client.get(url.replace(str(issue.pk), str(other.pk)), {"request_id": data["request_id"]}).data["request_found"] is False
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, {"request_id": data["request_id"]}).status_code == 403


def test_editor_owner_header_blocks_cookie_switch_before_save(api_client, admin_user):
    issue = new_issue(admin_user)
    before = service.edit_version("recommendation_issue", issue.pk)
    api_client.force_authenticate(admin_user)
    result = api_client.put(f"/api/catalog/admin/recommendation-issues/{issue.pk}/", command(issue, title="不可写入"), format="json", HTTP_X_EDITOR_OWNER="another-owner")
    assert result.status_code == 403
    assert service.edit_version("recommendation_issue", issue.pk) == before


def test_history_is_paginated_and_revision_cannot_cross_issue(api_client, admin_user):
    issue = new_issue(admin_user)
    for number in range(25):
        service.save_issue(issue.pk, command(issue, title=f"修订验收 {number}"), admin_user)
    other = new_issue(admin_user)
    foreign = service._latest("recommendation_issue", other.pk)
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/recommendation-issues/{issue.pk}/"
    response = api_client.get(url + "history/")
    assert response.status_code == 200 and response.data["count"] == 26
    assert len(response.data["results"]) == 24 and response.data["next"]
    assert response.data["results"][0]["is_current"] is True
    assert api_client.get(url, {"revision": str(foreign.pk)}).status_code == 404
    assert api_client.put(url, command(issue, restore_revision_id=str(foreign.pk)), format="json").status_code == 404


def test_restore_creates_draft_and_never_replaces_public_snapshot(admin_user):
    issue = new_issue(admin_user)
    original = service._latest("recommendation_issue", issue.pk)
    service.publish_issue(issue.pk, service.edit_version("recommendation_issue", issue.pk), admin_user)
    service.save_issue(issue.pk, command(issue, title="后来修改"), admin_user)
    restored = {**original.materialized_preview, "edit_version": service.edit_version("recommendation_issue", issue.pk), "restore_revision_id": str(original.pk), "request_id": str(uuid4())}
    service.save_issue(issue.pk, restored, admin_user)
    issue.refresh_from_db()
    latest = service._latest("recommendation_issue", issue.pk)
    assert latest.status == "draft" and latest.pk != original.pk
    assert latest.change_note == f"恢复自修订 {original.revision}"
    assert issue.active_revision_id == original.pk


def test_saved_missing_source_can_retain_guide_but_not_publish_or_forge(admin_user):
    edition = public_edition()
    block = {"id": str(uuid4()), "type": "work", "text": "原导读", "target": {"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)}}
    issue = new_issue(admin_user, body_blocks=[block])
    changed = {**block, "text": "保留人工导读"}
    with patch("catalog.services.editorial_blocks.resolve_target", side_effect=Http404):
        service.save_issue(issue.pk, command(issue, body_blocks=[changed]), admin_user)
        assert service.issue_draft_payload(issue)["body_blocks"][0]["text"] == "保留人工导读"
        assert service.issue_payload(issue)["body_blocks"][0]["source_status"] == "unavailable"
        with pytest.raises(ValidationError):
            service.publish_issue(issue.pk, service.edit_version("recommendation_issue", issue.pk), admin_user)
        for forged in ({**changed, "id": str(uuid4())}, {**changed, "target": {**block["target"], "id": str(uuid4())}}):
            with pytest.raises(Http404):
                service.save_issue(issue.pk, command(issue, body_blocks=[forged]), admin_user)


def test_source_only_article_can_publish_after_current_eligibility_check(admin_user):
    edition = public_edition()
    issue = new_issue(admin_user, body_blocks=[{"type": "work", "text": "", "target": {"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)}}])
    service.publish_issue(issue.pk, service.edit_version("recommendation_issue", issue.pk), admin_user)
    issue.refresh_from_db()
    assert issue.active_revision_id


def test_preview_resolves_sources_without_saving_or_creating_plans(api_client, admin_user):
    issue = new_issue(admin_user)
    edition = public_edition()
    before = (EditorialRevision.objects.count(), RecommendationIssueItem.objects.count(), AuditEvent.objects.count())
    api_client.force_authenticate(admin_user)
    data = command(issue, body_blocks=[{"id": str(uuid4()), "type": "work", "text": "尚未保存的导读", "target": {"type": "work", "id": str(edition.work_id), "edition_id": str(edition.pk)}}], items=[{"kind": "planned", "title": "预览不得创建"}])
    result = api_client.post(f"/api/catalog/admin/recommendation-issues/{issue.pk}/preview/", data, format="json")
    assert result.status_code == 200
    assert result.data["body_blocks"][0]["resolved_sources"][0]["edition_id"] == str(edition.pk)
    assert before == (EditorialRevision.objects.count(), RecommendationIssueItem.objects.count(), AuditEvent.objects.count())
    assert service.issue_draft_payload(issue)["body_blocks"][0]["type"] == "paragraph"


def test_concept_picker_filters_before_pagination(api_client, admin_user):
    issue = new_issue(admin_user)
    concept = KnowledgeNode.objects.create(canonical_name_zh="编辑器验收概念", node_type="concept", slug="workbench-concept")
    KnowledgeNode.objects.create(canonical_name_zh="编辑器验收理论", node_type="theory", slug="workbench-theory")
    api_client.force_authenticate(admin_user)
    result = api_client.get(f"/api/catalog/admin/recommendation-issues/{issue.pk}/sources/", {"type": "node", "node_type": "concept", "q": "编辑器验收"})
    assert result.status_code == 200 and result.data["count"] == 1
    assert result.data["results"][0]["target"]["id"] == str(concept.pk)
