"""Publication review acceptance definitions. Not executed during implementation."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import EditorialRevision, KnowledgeNode
from catalog.services import editorial_issues as ledger
from catalog.services.issue_publication_review import review
from catalog.services.media import ingest_image, build_rendition, update_media_metadata
from .test_issue_workbench_20261022 import new_issue, command
from .test_media_v305 import picture

pytestmark = pytest.mark.django_db


def test_review_is_read_only_and_compares_public_snapshot_to_saved_draft(admin_user):
    issue = new_issue(admin_user, title="旧公开标题")
    ledger.publish_issue(issue.pk, ledger.edit_version("recommendation_issue", issue.pk), admin_user)
    issue.refresh_from_db()
    public_id = issue.active_revision_id
    ledger.save_issue(issue.pk, command(issue, title="未发布的新标题", selection_workspace={"question": "内部选材问题"}), admin_user)
    count = EditorialRevision.objects.filter(target_id=issue.pk).count()
    value = review(issue, admin_user)
    assert value["current_revision_id"] == str(public_id) and value["has_draft"] and value["can_publish"]
    title = next(row for row in value["changes"] if row["field"] == "title")
    assert title["before_display"] == "旧公开标题" and title["after_display"] == "未发布的新标题"
    assert "selection_workspace" not in value["reader_preview"]
    assert value["reader_preview"]["published_at"] is None
    assert EditorialRevision.objects.filter(target_id=issue.pk).count() == count
    assert ledger.issue_payload(issue, public=True)["title"] == "旧公开标题"


def test_source_withdrawal_blocks_publish_and_preview_hides_nonpublic_content(admin_user):
    node = KnowledgeNode.objects.create(canonical_name_zh="隔离公开来源", node_type="concept", slug=f"review-{uuid4().hex}", status="published")
    issue = new_issue(admin_user)
    ledger.publish_issue(issue.pk, ledger.edit_version("recommendation_issue", issue.pk), admin_user)
    issue.refresh_from_db(); public_id = issue.active_revision_id
    block_id = str(uuid4())
    ledger.save_issue(issue.pk, command(issue, body_blocks=[{"id": block_id, "type": "node", "text": "草稿说明不能误作公开", "target": {"type": "node", "id": str(node.pk)}}]), admin_user)
    before = review(issue, admin_user)
    assert before["can_publish"]
    node.status = "draft";node.save(update_fields=["status"])
    after = review(issue, admin_user)
    assert after["blocking_count"] == 1 and not after["can_publish"]
    assert after["checks"][0]["block_id"] == block_id
    assert after["reader_preview"]["body_blocks"][0]["text"] == ""
    with pytest.raises(ValidationError) as failed:
        ledger.publish_issue(issue.pk, before["edit_version"], admin_user)
    assert "publication_checks" in failed.value.detail
    issue.refresh_from_db()
    assert issue.active_revision_id == public_id
    assert ledger._latest("recommendation_issue", issue.pk).status == "draft"


def test_image_rights_warning_uses_selected_immutable_metadata(admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    media, _ = ingest_image(picture(), actor=admin_user, metadata={"alt_text": "仅供隔离测试", "source_label": "测试资料"})
    rendition = build_rendition(media.pk, kind="cover", width=320)
    issue = new_issue(admin_user, cover_rendition_id=str(rendition.pk))
    update_media_metadata(media.pk, actor=admin_user, metadata={"license": "后来补充的许可"})
    value = review(issue, admin_user)
    assert value["can_publish"] and not value["blocking_count"]
    assert any(row["code"] == "media_rights_missing" and row["section"] == "cover" for row in value["checks"])
    assert value["reader_preview"]["cover_url"].startswith("/api/catalog/admin/media/")
    ledger.publish_issue(issue.pk, value["edit_version"], admin_user)
    assert ledger._latest("recommendation_issue", issue.pk).status == "published"


def test_scheduled_version_does_not_replace_current_comparison_early(admin_user):
    issue = new_issue(admin_user, title="目前公开")
    ledger.publish_issue(issue.pk, ledger.edit_version("recommendation_issue", issue.pk), admin_user)
    issue.refresh_from_db(); current = issue.active_revision_id
    ledger.save_issue(issue.pk, command(issue, title="明天展示", display_from=(timezone.now()+timedelta(days=1)).isoformat()), admin_user)
    ledger.publish_issue(issue.pk, ledger.edit_version("recommendation_issue", issue.pk), admin_user)
    issue.refresh_from_db()
    value = review(issue, admin_user)
    assert value["current_revision_id"] == str(current)
    assert value["has_draft"] is False and value["can_publish"] is False
    assert value["reader_preview"]["title"] == "明天展示"
    assert next(row for row in value["changes"] if row["field"] == "title")["before_display"] == "目前公开"


def test_review_api_requires_admin_and_exact_saved_version(api_client, admin_user, reader_user):
    issue = new_issue(admin_user)
    url = f"/api/catalog/admin/recommendation-issues/{issue.pk}/preview/"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, {"review": "true"}).status_code == 403
    api_client.force_authenticate(admin_user)
    result = api_client.get(url, {"review": "true", "edit_version": ledger.edit_version("recommendation_issue", issue.pk)})
    assert result.status_code == 200 and result["Cache-Control"] == "private, no-store"
    ledger.save_issue(issue.pk, command(issue, title="下一版"), admin_user)
    assert api_client.get(url, {"review": "true", "edit_version": result.data["edit_version"]}).status_code == 409
    assert api_client.get(url).data["title"] == "下一版"


def test_old_blocks_without_ids_can_be_compared_and_empty_article_stays_blocked(admin_user):
    issue = new_issue(admin_user)
    latest = ledger._latest("recommendation_issue", issue.pk)
    latest.materialized_preview["body_blocks"][0].pop("id")
    latest.save(update_fields=["materialized_preview"])
    assert review(issue, admin_user)["can_publish"]
    ledger.save_issue(issue.pk, command(issue, body_blocks=[]), admin_user)
    result = review(issue, admin_user)
    assert any(row["code"] == "empty_article" for row in result["checks"])
    assert not result["can_publish"]


def test_analysis_requires_sources_but_independent_manual_prose_remains_allowed(admin_user):
    issue = new_issue(admin_user)
    # Legacy saved content may predate the current save-time source constraint.
    latest = ledger._latest("recommendation_issue", issue.pk)
    latest.materialized_preview["body_blocks"] = [{"id": str(uuid4()), "type": "analysis", "text": "需要依据的分析", "style": "paragraph", "references": []}]
    latest.save(update_fields=["materialized_preview"])
    result = review(issue, admin_user)
    assert any(row["code"] == "analysis_source_missing" for row in result["checks"])
    with pytest.raises(ValidationError):
        ledger.publish_issue(issue.pk, result["edit_version"], admin_user)
    ledger.save_issue(issue.pk, command(issue, body_blocks=[{"type": "paragraph", "text": "编辑独立撰写的导读"}]), admin_user)
    assert review(issue, admin_user)["can_publish"]


def test_current_image_can_be_found_and_rights_corrected_without_changing_public_version(api_client, admin_user, reader_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    media, _ = ingest_image(picture(), actor=admin_user)
    old = build_rendition(media.pk, kind="hero", width=1280)
    issue = new_issue(admin_user, cover_rendition_id=str(old.pk))
    ledger.publish_issue(issue.pk, ledger.edit_version("recommendation_issue", issue.pk), admin_user)
    url = "/api/catalog/admin/media/collection/"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, {"rendition_id": str(old.pk)}).status_code == 403
    api_client.force_authenticate(admin_user)
    found = api_client.get(url, {"rendition_id": str(old.pk)})
    assert found.status_code == 200 and found.data["count"] == 1
    assert found.data["results"][0]["id"] == str(media.pk)
    assert api_client.get(url, {"rendition_id": "not-a-uuid"}).status_code == 400
    assert api_client.get(url, {"rendition_id": str(uuid4())}).data["count"] == 0
    expected = found.data["results"][0]["updated_at"]
    assert api_client.patch(f"/api/catalog/admin/media/{media.pk}/", {"expected_updated_at": expected, "license": "过期账户窗口"}, format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    media.refresh_from_db()
    assert not media.license
    response = api_client.patch(f"/api/catalog/admin/media/{media.pk}/", {"expected_updated_at": expected, "license": "隔离测试许可"}, format="json")
    assert response.status_code == 200
    new = build_rendition(media.pk, kind="hero", width=1280)
    assert new.pk != old.pk and new.metadata_snapshot["license"] == "隔离测试许可"
    issue.refresh_from_db()
    assert issue.active_revision.materialized_preview["cover_rendition_id"] == str(old.pk)
    ledger.save_issue(issue.pk, command(issue, cover_rendition_id=str(new.pk)), admin_user)
    assert not any(row["code"] == "media_rights_missing" for row in review(issue, admin_user)["checks"])
    assert api_client.patch(f"/api/catalog/admin/media/{media.pk}/", {"expected_updated_at": expected, "license": "旧窗口"}, format="json").status_code == 400
