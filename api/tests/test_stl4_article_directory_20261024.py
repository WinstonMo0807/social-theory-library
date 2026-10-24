"""Deferred article/homepage recovery acceptance. Authored only; not executed."""
from uuid import uuid4

import pytest
from accounts.models import User
from catalog.models import CurationProject, RecommendationIssue, RecommendationPolicy
from catalog.services.recommendations import ensure_default_policies
from ingestion.models import AuditEvent
from tests.test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def account(client, actor):
    client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))


def test_article_creation_replay_stop_and_scope(api_client, admin_user, reader_user):
    account(api_client, admin_user)
    path = "/api/catalog/admin/recommendation-issues/create/"
    body = {"request_id": str(uuid4()), "title": "待验收的合成文章", "kind": "research"}
    first = api_client.post(path, body, format="json")
    assert first.status_code == 201, first.data
    issue_id = first.data["issue_id"]
    lookup = f"{path}commands/{body['request_id']}/"
    assert api_client.post(path, body, format="json").data == first.data
    assert api_client.get(lookup).data == first.data
    assert api_client.post(lookup, {"action": "cancel_pending"}, format="json").data == first.data
    assert api_client.post(path, {**body, "title": "不同标题"}, format="json").status_code == 409
    assert RecommendationIssue.objects.filter(pk=issue_id).count() == 1
    listing = api_client.get("/api/catalog/admin/recommendation-issues/", {"scope": "draft"})
    item = next(row for row in listing.data["results"] if row["id"] == issue_id)
    assert item["is_public"] is False and item["article_metadata"]["kind"] == "research"
    assert api_client.get("/api/catalog/admin/recommendation-issues/", {"scope": "published"}).data["count"] == 0
    stopped = {**body, "request_id": str(uuid4())}
    assert api_client.post(f"{path}commands/{stopped['request_id']}/", {"action": "cancel_pending"}, format="json").data["state"] == "cancelled"
    assert api_client.post(path, stopped, format="json").data["state"] == "cancelled"
    assert RecommendationIssue.objects.count() == 1
    account(api_client, reader_user)
    assert api_client.post(path, body, format="json").status_code == 403
    account(api_client, admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.post(path, body, format="json").status_code == 403


def test_creation_receipt_cannot_reopen_a_newly_private_project(api_client, admin_user):
    account(api_client, admin_user)
    path = "/api/catalog/admin/recommendation-issues/create/"
    body = {"request_id": str(uuid4()), "title": "之后归组的合成文章", "kind": "article"}
    created = api_client.post(path, body, format="json")
    assert created.status_code == 201, created.data
    other = User.objects.create_user(username="project-owner-fixture", email="project-owner@example.org", role="editor")
    project = CurationProject.objects.create(title="其他团队的合成项目", owner=other, visibility="team")
    RecommendationIssue.objects.filter(pk=created.data["issue_id"]).update(project=project)
    recovered = api_client.get(f"{path}commands/{body['request_id']}/")
    assert recovered.status_code == 200
    assert recovered.data["state"] == "applied" and recovered.data["available"] is False
    assert recovered.data["issue_id"] is None and recovered.data["next_url"] == ""
    assert api_client.post(path, body, format="json").data == recovered.data
    assert api_client.get("/api/catalog/admin/recommendation-issues/", {"scope": "mine"}).data["count"] == 0
    assert RecommendationIssue.objects.count() == 1


def test_home_publication_recovery_never_republishes_and_stop_fences_late_request(api_client, admin_user, reader_user):
    account(api_client, admin_user)
    ensure_default_policies()
    published_edition("首页推荐恢复的合成文献")
    path = "/api/catalog/admin/recommendations/home_featured/refresh/"
    preview_path = "/api/catalog/admin/recommendations/home_featured/preview/"
    policy = RecommendationPolicy.objects.get(placement="home_featured")

    def command():
        preview = api_client.post(preview_path, {}, format="json")
        assert preview.status_code == 200, preview.data
        return {"request_id": str(uuid4()), "confirm": True, **{key: preview.data[key] for key in (
            "expected_snapshot_id", "expected_updated_at", "preview_token")}}

    body = command()
    result = api_client.post(path, body, format="json")
    assert result.status_code == 200 and result.data["state"] == "applied", result.data
    count = policy.snapshots.count()
    assert api_client.post(path, body, format="json").data["accepted_snapshot_id"] == result.data["accepted_snapshot_id"]
    assert policy.snapshots.count() == count
    second = api_client.post(path, command(), format="json")
    assert second.status_code == 200
    lookup = f"{path}commands/{body['request_id']}/"
    recovered = api_client.get(lookup)
    assert recovered.data["publication_effective"] is False
    assert recovered.data["current"]["id"] == second.data["current"]["id"]
    assert api_client.post(lookup, {"action": "cancel_pending"}, format="json").data["state"] == "applied"
    stopped = command()
    stop_path = f"{path}commands/{stopped['request_id']}/"
    assert api_client.post(stop_path, {"action": "cancel_pending"}, format="json").data["state"] == "cancelled"
    assert api_client.post(path, stopped, format="json").data["state"] == "cancelled"
    assert policy.snapshots.count() == count + 1
    assert AuditEvent.objects.filter(action="catalog.recommendations_published", request_id=stopped["request_id"]).count() == 1
    other = User.objects.create_user(username="another-editor-fixture", email="another-editor@example.org", role="editor")
    account(api_client, other)
    assert api_client.get(lookup).status_code == 404
    assert api_client.post(stop_path, {"action": "cancel_pending"}, format="json").status_code == 403
    account(api_client, reader_user)
    assert api_client.post(path, body, format="json").status_code == 403
    assert api_client.get(lookup).status_code == 403
