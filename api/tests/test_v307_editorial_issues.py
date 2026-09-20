"""Critical isolation and command boundaries for fixed 3.0.7 editors."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from catalog.models import (AboutPageBlock, CatalogPublicationRevision, CatalogingSession, Edition,
                            EditorialRevision, RecommendationIssue, SiteSetting, Work)
from catalog.services import editorial_issues as service
from ingestion.models import UploadItem
from ingestion.serializers import UploadBatchCreateSerializer
from reading.models import ReadingList

pytestmark = pytest.mark.django_db


def test_admin_issue_summary_uses_whole_inventory_and_approved_schedule(api_client, admin_user):
    for index in range(14):
        service.create_issue({"title": f"未发布 {index}"}, admin_user)
    live = service.create_issue(issue_data(), admin_user)
    service.publish_issue(live.pk, service.issue_payload(live)["edit_version"], admin_user)
    scheduled = []
    for index in range(4):
        row = service.create_issue({**issue_data(), "title": f"排期 {index}", "display_from": (timezone.now() + timedelta(days=index + 1)).isoformat()}, admin_user)
        service.publish_issue(row.pk, service.issue_payload(row)["edit_version"], admin_user)
        scheduled.append(row)
    service.save_issue(scheduled[0].pk, {**service.issue_payload(scheduled[0]), "title": "不可混入排期的未发布稿"}, admin_user)
    api_client.force_authenticate(admin_user)
    response = api_client.get("/api/catalog/admin/recommendation-issues/?q=不存在&page=2")
    assert response.status_code == 200
    assert response.data["count"] == 0
    assert response.data["summary"] == {"total": 19, "published": 1, "drafts": 15, "scheduled": 4}
    assert response.data["current"]["id"] == str(live.pk)
    assert [row["title"] for row in response.data["upcoming"]] == ["排期 0", "排期 1", "排期 2"]
    public = api_client.get("/api/catalog/recommendation-issues/").data
    assert "summary" not in public and "upcoming" not in public


def test_existing_planned_identity_cannot_be_silently_changed(admin_user):
    issue = service.create_issue(issue_data(), admin_user)
    payload = service.issue_payload(issue)
    different = Edition.objects.create(work=Work.objects.create(title="其他草稿"))
    payload["items"][0].update(work_id=str(different.work_id), edition_id=str(different.pk))
    with pytest.raises(ValidationError, match="草稿身份不能替换"):
        service.save_issue(issue.pk, payload, admin_user)


def public_edition(title="公开馆藏", *, snapshot=None, reader_attributes=None):
    work = Work.objects.create(title=title)
    edition = Edition.objects.create(work=work, state="published", publication_mode="bibliographic", public_slug=f"test-{work.pk}")
    from catalog.models import Asset
    reader = Asset.objects.create(edition=edition, **reader_attributes) if reader_attributes else None
    revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active", metadata_ready=True,
        snapshot=snapshot or {"work": {"id": str(work.pk), "title": title}}, reader_asset=reader, content_fingerprint=f"v307-test:{edition.pk}")
    edition.active_catalog_revision = revision
    edition.save(update_fields=["active_catalog_revision"])
    return edition


def issue_data(edition=None):
    items = [{"kind": "planned", "title": "计划上架的文献", "authors": "编辑确认的作者", "version_note": "中文版，版次待核对", "note": "计划项推介语"}]
    if edition:
        items.insert(0, {"kind": "catalog", "work_id": str(edition.work_id), "edition_id": str(edition.pk), "title": "公开馆藏", "note": "既有馆藏推介语"})
    return {"title": "推荐第一期", "public_byline": "联合策展", "introduction": "本期导语", "body_blocks": [{"type": "paragraph", "text": "正文"}], "items": items}


def test_issue_draft_and_planned_identity_are_not_public(api_client, admin_user):
    issue = service.create_issue(issue_data(), admin_user)
    assert service.published_issues().count() == 0
    item = issue.items.get()
    assert item.cataloging_session.source_type == "manual"
    assert item.cataloging_session.edition.publication_mode == "bibliographic"
    assert UploadItem.objects.filter(edition=item.cataloging_session.edition).count() == 0
    assert api_client.get(f"/api/catalog/recommendation-issues/{issue.slug}/").status_code == 404
    assert api_client.get(f"/api/catalog/admin/recommendation-issues/{issue.pk}/preview/").status_code in (401, 403)


def test_issue_public_snapshot_survives_draft_and_conflicts(admin_user):
    issue = service.create_issue(issue_data(public_edition()), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    payload = service.issue_payload(issue)
    old = payload["edit_version"]
    service.save_issue(issue.pk, {**payload, "title": "未公开改题"}, admin_user)
    issue.refresh_from_db()
    assert service.issue_payload(issue, public=True)["title"] == "推荐第一期"
    assert service.issue_payload(issue)["title"] == "未公开改题"
    with pytest.raises(service.EditConflict):
        service.save_issue(issue.pk, {**payload, "edit_version": old, "title": "迟到的覆盖"}, admin_user)
    with pytest.raises(service.EditConflict):
        service.publish_issue(issue.pk, old, admin_user)


def test_planned_public_copy_does_not_read_draft_work(admin_user):
    issue = service.create_issue(issue_data(), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    item = issue.items.get()
    Work.objects.filter(pk=item.planned_work_id).update(title="后台未公开修改")
    issue.refresh_from_db()
    row = service.issue_payload(issue, public=True)["items"][0]
    assert row["title"] == "计划上架的文献"
    assert row["status"] == "planned"
    assert "cataloging_session_id" not in row and "work_id" not in row


def test_scheduling_never_publishes_an_unconfirmed_draft(admin_user):
    future = timezone.now() + timedelta(days=3)
    issue = service.create_issue({**issue_data(), "display_from": future.isoformat()}, admin_user)
    assert not service.published_issues().exists()
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    assert not service.published_issues().exists()
    with patch("catalog.services.editorial_issues.timezone.now", return_value=future + timedelta(seconds=1)):
        issue = service.published_issues().get(pk=issue.pk)
        assert service.issue_payload(issue, public=True)["title"] == "推荐第一期"


def test_future_revision_keeps_the_previous_public_issue(admin_user):
    issue = service.create_issue(issue_data(), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    payload = service.issue_payload(issue)
    service.save_issue(issue.pk, {**payload, "title": "下期修订", "display_from": (timezone.now() + timedelta(days=2)).isoformat()}, admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue = service.published_issues().get(pk=issue.pk)
    assert service.issue_payload(issue, public=True)["title"] == "推荐第一期"


def test_explicit_planned_link_preserves_edition_and_recommendation_text(admin_user):
    issue = service.create_issue(issue_data(), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    version = service.issue_payload(issue)["edit_version"]
    item = issue.items.get()
    edition = public_edition("后续上架")
    with pytest.raises(ValidationError):
        service.link_planned_item(issue.pk, item.pk, {"edit_version": version, "work_id": str(edition.work_id), "edition_id": str(edition.pk)}, admin_user)
    service.link_planned_item(issue.pk, item.pk, {"edit_version": version, "work_id": str(edition.work_id), "edition_id": str(edition.pk), "confirm_version": True}, admin_user)
    row = service.issue_payload(issue, public=True)["items"][0]
    assert row["available_edition_id"] == str(edition.pk)
    assert row["note"] == "计划项推介语"
    assert service.issue_payload(issue)["edit_version"] != version
    with pytest.raises(service.EditConflict):
        service.link_planned_item(issue.pk, item.pk, {"edit_version": version, "work_id": str(edition.work_id), "edition_id": str(edition.pk), "confirm_version": True}, admin_user)


def test_save_issue_list_is_private_and_retry_safe(api_client, admin_user):
    issue = service.create_issue(issue_data(public_edition()), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    url = f"/api/catalog/recommendation-issues/{issue.slug}/save-list/"
    assert api_client.post(url, {}, format="json").status_code in (401, 403)
    first = User.objects.create_user(username="v307-reader-one", email="v307-one@example.org", role="reader")
    second = User.objects.create_user(username="v307-reader-two", email="v307-two@example.org", role="reader")
    api_client.force_authenticate(first)
    result = api_client.post(url, {}, format="json")
    retry = api_client.post(url, {}, format="json")
    assert result.status_code == retry.status_code == 200
    assert result.data["id"] == retry.data["id"] and result.data["item_count"] == 1
    api_client.force_authenticate(second)
    other = api_client.post(url, {}, format="json")
    assert other.data["id"] != result.data["id"]
    assert ReadingList.objects.filter(user=first).count() == 1


def test_website_save_is_draft_and_legacy_write_cannot_bypass(api_client, admin_user):
    SiteSetting.objects.update_or_create(key="site_config", defaults={"value": {"site_name": "原网站"}, "public": True})
    AboutPageBlock.objects.create(key="v307-original", block_type="intro", title="原说明", visible=True)
    payload = service.site_payload()
    payload["config"]["site_name"] = "新网站"
    saved = service.save_site(payload, admin_user)
    assert service.site_public_payload()["config"]["site_name"] == "原网站"
    assert saved["config"]["site_name"] == "新网站"
    service.publish_site(saved["edit_version"], admin_user)
    assert service.site_public_payload()["config"]["site_name"] == "新网站"
    api_client.force_authenticate(admin_user)
    result = api_client.put("/api/catalog/site-config/", payload["config"], format="json")
    assert result.status_code == 409


@pytest.mark.parametrize("count,valid", [(1, True), (5, True), (6, False)])
def test_upload_batch_limit_and_local_default(count, valid):
    serializer = UploadBatchCreateSerializer(data={"expected_count": count})
    assert serializer.is_valid() is valid
    if valid:
        assert serializer.validated_data["external_enrichment_enabled"] is False
    external = UploadBatchCreateSerializer(data={"expected_count": 1, "external_enrichment_enabled": True})
    assert not external.is_valid()


def test_bibliographic_lookup_does_not_access_sources_without_explicit_action(api_client, admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="本地书目"))
    api_client.force_authenticate(admin_user)
    with patch("ingestion.services.provider_gateway.invoke_provider") as provider:
        result = api_client.post("/api/catalog/admin/bibliographic-candidates/", {"edition_id": str(edition.pk), "form_context": {"title": "本地书目", "private_notes": "不得进入上下文"}}, format="json")
    assert result.status_code == 200
    provider.assert_not_called()
    assert result.data["external_requested"] is False
    assert "private_notes" not in str(result.data)


def test_quotes_and_unsafe_images_are_rejected(admin_user):
    with pytest.raises(ValidationError):
        service.create_issue({**issue_data(), "body_blocks": [{"type": "quote", "text": "无出处引文"}]}, admin_user)
    with pytest.raises(ValidationError):
        service.create_issue({**issue_data(), "cover_url": "https://example.com/private.png"}, admin_user)
    with pytest.raises(ValidationError):
        service.safe_image_url("/images/%2e%2e/api/reading/private.png")


def test_inline_draft_does_not_link_or_change_existing_form_state(api_client, admin_user):
    work = Work.objects.create(title="未保存表单所在作品")
    edition = Edition.objects.create(work=work)
    api_client.force_authenticate(admin_user)
    result = api_client.post("/api/catalog/admin/field-assistant/create/", {"edition_id": str(edition.pk), "field_name": "author", "label": "新建作者测试", "defer_link": True}, format="json")
    assert result.status_code == 201
    assert result.data["linked"] is False
    assert not edition.contributions.exists()
    assert result.data["entity"]["edit_url"].startswith("/admin/scholars/")


def test_existing_planned_draft_is_reused_without_overwriting_its_fields(admin_user):
    from catalog.services.cataloging_sessions import open_cataloging_session
    session, _ = open_cataloging_session(actor=admin_user, source_type="manual", title="已有人工草稿")
    edition = session.edition
    edition.version_label = "已确认版次"
    edition.save(update_fields=["version_label"])
    payload = issue_data()
    payload["items"][0].update(work_id=str(session.work_id), edition_id=str(edition.pk))
    before = (Work.objects.count(), Edition.objects.count(), CatalogingSession.objects.count())
    issue = service.create_issue(payload, admin_user)
    assert (Work.objects.count(), Edition.objects.count(), CatalogingSession.objects.count()) == before
    assert issue.items.get().cataloging_session_id == session.pk
    edition.refresh_from_db()
    assert edition.version_label == "已确认版次"
    assert edition.work.title == "已有人工草稿"


def test_issue_uses_selected_edition_snapshot_instead_of_live_work(admin_user):
    edition = public_edition(snapshot={"work": {"title": "选定版本的公开题名", "cover": "covers/exact-edition.jpg"},
        "contributions": [{"role": "author", "name": "已公开作者"}], "edition": {"version_label": "第二版"}})
    edition.work.title = "未公开题名变更"
    edition.work.save(update_fields=["title"])
    issue = service.create_issue(issue_data(edition), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    row = service.issue_payload(issue, public=True)["items"][0]
    assert row["title"] == "选定版本的公开题名"
    assert row["authors"] == "已公开作者"
    assert row["version_note"] == "第二版"
    assert row["cover_url"].endswith(f"/items/{row['id']}/cover/")
    assert "cover_path" not in row


def test_reading_path_internal_note_stays_in_admin_serialization_only():
    from catalog.models import ReadingPath, ReadingPathItem
    from catalog.theory_serializers import ReadingPathSerializer
    path = ReadingPath.objects.create(title="公开阅读路径", slug="v307-path", status="published")
    ReadingPathItem.objects.create(reading_path=path, work=public_edition().work, stage_name="起步", editorial_note="仅后台的编辑备注", recommendation_reason="公开推荐理由")
    public = ReadingPathSerializer(path).data
    assert "editorial_note" not in public["items"][0]
    assert public["items"][0]["recommendation_reason"] == "公开推荐理由"
    private = ReadingPathSerializer(path, context={"include_unpublished_items": True}).data
    assert private["items"][0]["editorial_note"] == "仅后台的编辑备注"


@pytest.mark.parametrize("kind,validation,access,readable", [
    ("normalized", "valid", "public", True),
    ("normalized", "pending", "public", False),
    ("normalized", "invalid", "public", False),
    ("normalized", "valid", "registered", False),
    ("normalized", "valid", "private", False),
    ("original", "valid", "public", False),
])
def test_issue_reader_link_requires_valid_exact_public_reader_source(admin_user, kind, validation, access, readable):
    edition = public_edition(reader_attributes={"kind": kind, "status": "ready", "validation_status": validation,
        "access_status": access, "is_current": False, "file": "synthetic/issue-reader.pdf", "sha256": "f" * 64, "byte_size": 20})
    issue = service.create_issue(issue_data(edition), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    row = service.issue_payload(issue, public=True)["items"][0]
    assert bool(row["reader_url"]) is readable
    assert row["status"] == ("available" if readable else "bibliographic")
