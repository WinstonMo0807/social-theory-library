"""R38/R39: protected drafts and real public reads from the dedicated editors."""
import pytest
from rest_framework.test import APIClient

from catalog.models import (
    CanonicalObjectRevision, EditorialRevision, KnowledgeNode, KnowledgeRelation,
    TheoryTimelineEvent, TimelineEventRelation, TheoryReviewTask,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind", ["relation", "timeline", "review"])
def test_A31_dedicated_lists_filter_before_pagination_and_keep_tied_rows(api_client, admin_user, kind):
    from django.utils import timezone
    from urllib.parse import parse_qs, urlsplit
    api_client.force_authenticate(admin_user)
    source = KnowledgeNode.objects.create(canonical_name_zh="分页起点", slug="pages-start", node_type="concept")
    targets = KnowledgeNode.objects.bulk_create([
        KnowledgeNode(canonical_name_zh=f"范围内{index}", slug=f"pages-{index}", node_type="concept") for index in range(35)
    ])
    if kind == "relation":
        rows = KnowledgeRelation.objects.bulk_create([
            KnowledgeRelation(source_node=source, target_node=target, relation_type="criticizes", status="pending", description="筛选测试资料") for target in targets
        ])
        KnowledgeRelation.objects.create(source_node=targets[0], target_node=source, relation_type="criticizes", description="不应显示", status="pending")
        KnowledgeRelation.objects.filter(pk__in=[row.pk for row in rows]).update(updated_at=timezone.now())
        url = "/api/catalog/admin/theory-system/relations/?q=筛选测试资料&status=pending"
    elif kind == "timeline":
        rows = TheoryTimelineEvent.objects.bulk_create([
            TheoryTimelineEvent(title="筛选测试资料", start_year=1900, display_order=0, review_status="suggested") for _ in targets
        ])
        TheoryTimelineEvent.objects.create(title="不应显示", start_year=1900)
        url = "/api/catalog/admin/theory-timeline/?q=筛选测试资料&review_status=suggested"
    else:
        rows = TheoryReviewTask.objects.bulk_create([
            TheoryReviewTask(task_type="new_node", suggested_node_name="筛选测试资料", status="pending") for _ in targets
        ])
        TheoryReviewTask.objects.create(task_type="new_node", suggested_node_name="不应显示", status="pending")
        TheoryReviewTask.objects.filter(pk__in=[row.pk for row in rows]).update(created_at=timezone.now())
        url = "/api/catalog/admin/theory-system/review-tasks/?q=筛选测试资料&status=pending"
    # Match a browser's UTF-8 URL encoding; raw Unicode QUERY_STRING corrupts
    # Django test-client build_absolute_uri() and its next-page query.
    endpoint = urlsplit(url).path
    filters = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
    first = api_client.get(endpoint, filters)
    assert first.status_code == 200
    assert first.data["count"] == 35
    assert len(first.data["results"]) == 24
    second = api_client.get(first.data["next"])
    assert second.status_code == 200 and second.data["next"] is None, {"next": first.data["next"], "error": second.data}
    ids = [item["id"] for item in first.data["results"] + second.data["results"]]
    assert len(ids) == len(set(ids)) == 35
    assert set(map(str, ids)) == {str(row.pk) for row in rows}
    repeated = api_client.get(endpoint, filters)
    assert [item["id"] for item in repeated.data["results"]] == ids[:24]


def editor_object(kind, published=True):
    source = KnowledgeNode.objects.create(canonical_name_zh="关系起点", slug="relation-start", node_type="theory_tradition", status="published")
    if kind == "knowledge_relation":
        target = KnowledgeNode.objects.create(canonical_name_zh="关系终点", slug="relation-end", node_type="theory_tradition", status="published")
        row = KnowledgeRelation.objects.create(source_node=source, target_node=target, relation_type="criticizes", description="原说明", evidence_source="合成测试来源，第1页", status="published" if published else "pending")
        return row, f"/api/catalog/admin/theory-system/relations/{row.pk}/"
    row = TheoryTimelineEvent.objects.create(title="原时间线事件", description="原说明", event_type="development", review_status="approved" if published else "suggested", start_year=2000)
    TimelineEventRelation.objects.create(event=row, node=source)
    return row, f"/api/catalog/admin/theory-timeline/{row.pk}/"


@pytest.mark.parametrize("kind", ["knowledge_relation", "timeline_event"])
@pytest.mark.parametrize("published", [False, True])
def test_A14_dedicated_editor_requires_current_version_and_preserves_public_data(api_client, admin_user, kind, published):
    row, url = editor_object(kind, published)
    api_client.force_authenticate(admin_user)
    before = api_client.get(url)
    assert before.status_code == 200
    assert "edit_version" in before.data, "专门编辑页必须收到当前修改版本"
    assert before["Cache-Control"] == "private, no-store"
    version = before.data["edit_version"]
    assert api_client.patch(url, {"description": "缺版本"}, format="json").status_code == 428
    saved = api_client.patch(url, {"description": "甲保存的新说明"}, format="json", HTTP_IF_MATCH=version)
    assert saved.status_code == (202 if published else 200), saved.data
    assert saved.data["edit_version"] != version
    assert api_client.patch(url, {"description": "乙旧窗口覆盖"}, format="json", HTTP_IF_MATCH=version).status_code == 409
    row.refresh_from_db()
    assert row.description == ("原说明" if published else "甲保存的新说明")
    assert api_client.get(url).data["description"] == "甲保存的新说明"


@pytest.mark.parametrize("kind", ["knowledge_relation", "timeline_event"])
def test_A32_save_draft_does_not_publish_and_explicit_publication_is_idempotent(api_client, admin_user, reader_user, kind):
    row, url = editor_object(kind)
    api_client.force_authenticate(admin_user)
    before = api_client.get(url)
    saved = api_client.patch(url, {"description": "正式发布的新说明"}, format="json", HTTP_IF_MATCH=before.data.get("edit_version", "baseline"))
    assert saved.status_code == 202, "保存已公开内容只能建立编辑草稿"
    revision = saved.data["editorial_revision"]
    row.refresh_from_db()
    assert row.description == "原说明"
    assert revision["materialized_preview"]["description"] == "正式发布的新说明"
    public_url = "/api/catalog/theory-system/nodes/relation-start/" if kind == "knowledge_relation" else "/api/catalog/theory-system/timeline/"
    public = APIClient().get(public_url)
    assert public.status_code == 200
    assert "正式发布的新说明" not in str(public.data)
    publish_url = f"/api{revision['publish_url']}"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    assert api_client.post(publish_url, {}, format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.post(publish_url, {}, format="json").status_code == 200
    row.refresh_from_db()
    assert row.description == "正式发布的新说明"
    public = APIClient().get(public_url)
    assert public.status_code == 200
    assert "正式发布的新说明" in str(public.data)
    canonical = CanonicalObjectRevision.objects.get(object_type=kind, object_id=row.pk)
    version = canonical.current_revision
    assert api_client.post(publish_url, {}, format="json").status_code == 200
    canonical.refresh_from_db()
    assert canonical.current_revision == version
    assert EditorialRevision.objects.get(pk=revision["id"]).status == "published"


@pytest.mark.parametrize("kind", ["knowledge_relation", "timeline_event"])
def test_new_public_item_stays_private_until_explicit_publish(api_client, admin_user, kind):
    row, detail = editor_object(kind, False)
    api_client.force_authenticate(admin_user)
    if kind == "knowledge_relation":
        payload = {"source_node": str(row.source_node_id), "target_node": str(row.target_node_id), "relation_type": "responds_to", "description": "新关系", "evidence_source": "合成来源", "status": "published"}
        status_field, public_value = "status", "published"
    else:
        payload = {"title": "新时间线", "event_type": "development", "review_status": "approved", "relations": [{"node": str(row.normalized_relations.get().node_id), "relation_type": "subject"}]}
        status_field, public_value = "review_status", "approved"
    response = api_client.post(detail.rsplit(str(row.pk), 1)[0], payload, format="json")
    assert response.status_code == 201, response.data
    created = type(row).objects.get(pk=response.data["id"])
    assert getattr(created, status_field) != public_value
    assert response.data["editorial_revision"]["status"] == "draft"
    assert response.data["public_status"] != public_value
    assert response.data["has_unpublished_changes"] is True
    published = api_client.post(f"/api{response.data['editorial_revision']['publish_url']}", {}, format="json")
    assert published.status_code == 200, published.data
    created.refresh_from_db()
    assert getattr(created, status_field) == public_value


def test_timeline_draft_preserves_relation_metadata_and_id(api_client, admin_user):
    row, url = editor_object("timeline_event")
    linked = row.normalized_relations.get()
    linked.description = "不可丢失的来源说明"
    linked.save()
    api_client.force_authenticate(admin_user)
    before = api_client.get(url)
    rows = [{"node": str(linked.node_id), "relation_type": "subject", "description": "新来源说明", "sort_order": 5}]
    saved = api_client.patch(url, {"relations": rows}, format="json", HTTP_IF_MATCH=before.data["edit_version"])
    assert saved.status_code == 202, saved.data
    assert saved.data["relations"][0]["node_name"] == "关系起点"
    assert saved.data["relations"][0]["description"] == "新来源说明"
    linked.refresh_from_db()
    assert linked.description == "不可丢失的来源说明"
    published = api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json")
    assert published.status_code == 200, published.data
    linked.refresh_from_db()
    assert linked.description == "新来源说明" and linked.sort_order == 5
    assert row.normalized_relations.count() == 1


@pytest.mark.parametrize("kind", ["knowledge_relation", "timeline_event"])
def test_withdraw_is_a_saved_draft_until_publisher_confirms(api_client, admin_user, kind):
    row, url = editor_object(kind)
    api_client.force_authenticate(admin_user)
    version = api_client.get(url).data["edit_version"]
    field, before, after = ("status", "published", "archived") if kind == "knowledge_relation" else ("review_status", "approved", "rejected")
    saved = api_client.patch(url, {field: after}, format="json", HTTP_IF_MATCH=version)
    assert saved.status_code == 202, saved.data
    row.refresh_from_db()
    assert getattr(row, field) == before
    published = api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json")
    assert published.status_code == 200, published.data
    row.refresh_from_db()
    assert getattr(row, field) == after


def test_relation_publication_rechecks_evidence_after_draft(api_client, admin_user):
    row, url = editor_object("knowledge_relation")
    api_client.force_authenticate(admin_user)
    saved = api_client.patch(url, {"description": "新说明"}, format="json", HTTP_IF_MATCH=api_client.get(url).data["edit_version"])
    assert saved.status_code == 202, saved.data
    row.evidence_source = ""
    row.save()
    response = api_client.post(f"/api{saved.data['editorial_revision']['publish_url']}", {}, format="json")
    assert response.status_code in {400, 409}
    row.refresh_from_db()
    assert row.description == "原说明"


@pytest.mark.parametrize("kind", ["knowledge_relation", "timeline_event"])
def test_editor_can_save_and_publish_without_second_approver(api_client, kind):
    from accounts.models import User
    user = User.objects.create_user(username="editor", email="editor@example.test", role="editor")
    api_client.force_authenticate(user)
    row, url = editor_object(kind)
    before = api_client.get(url)
    field, value = ("status", "published") if kind == "knowledge_relation" else ("review_status", "approved")
    response = api_client.patch(url, {"description": "复核员保存的草稿", field: value}, format="json", HTTP_IF_MATCH=before.data["edit_version"])
    assert response.status_code == 202, response.data
    assert api_client.post(f"/api{response.data['editorial_revision']['publish_url']}", {}, format="json").status_code == 200
    row.refresh_from_db()
    assert row.description == "复核员保存的草稿"


@pytest.mark.parametrize("patch", [
    {"start_year": "invalid"}, {"start_year": 2020, "end_year": 2000},
    {"timeline_relations": []}, {"timeline_relations": [{"description": "没有关联对象"}]},
    {"image": "../../private/secret.png"},
])
def test_generic_editorial_endpoint_cannot_bypass_timeline_validation(api_client, admin_user, patch):
    row, _ = editor_object("timeline_event")
    api_client.force_authenticate(admin_user)
    response = api_client.post("/api/catalog/admin/editorial-revisions/", {"target_type": "timeline_event", "target_id": str(row.pk), "patch": patch}, format="json")
    assert response.status_code == 400, response.data
    assert not EditorialRevision.objects.filter(target_id=row.pk).exists()
