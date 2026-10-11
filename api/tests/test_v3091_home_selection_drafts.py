"""Only new saved home-selection behavior; previous signed-preview tests are reused."""
from uuid import uuid4

import pytest

from catalog.models import EditorialRevision, RecommendationPolicy, RecommendationSnapshot, Topic
from catalog.services.recommendations import generate_snapshot

pytestmark = pytest.mark.django_db


@pytest.fixture
def selection(api_client, admin_user):
    policy = RecommendationPolicy.objects.get(placement="home_topics")
    policy.item_count = 2
    policy.save(update_fields=["item_count", "updated_at"])
    topics = [Topic.objects.create(name=f"公开主题{index}", slug=f"draft-topic-{index}", editorial_status="published") for index in range(2)]
    snapshot = generate_snapshot(policy, actor=admin_user, selected_targets=topics)
    api_client.force_authenticate(admin_user)
    return policy, topics, snapshot


def draft_request(client, policy, topics):
    response = client.get(f"/api/catalog/admin/recommendations/{policy.placement}/draft/")
    assert response.status_code == 200
    return {"items": [{"id": str(topic.pk), "target_type": "topic"} for topic in reversed(topics)],
            "edit_version": response.data["edit_version"], "expected_updated_at": response.data["expected_updated_at"],
            "expected_snapshot_id": response.data["expected_snapshot_id"], "request_key": str(uuid4())}


def test_save_and_reload_home_draft_never_publish_or_change_policy(api_client, admin_user, selection):
    policy, topics, snapshot = selection
    policy.refresh_from_db(); before = policy.updated_at
    request = draft_request(api_client, policy, topics)
    saved = api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json")
    assert saved.status_code == 200 and saved.data["exists"] and saved.data["public_unchanged"]
    assert [row["id"] for row in saved.data["items"]] == [str(topic.pk) for topic in reversed(topics)]
    assert [row["name"] for row in saved.data["items"]] == [topic.name for topic in reversed(topics)]
    assert saved["Cache-Control"] == "private, no-store"
    reload = api_client.get("/api/catalog/admin/recommendations/home_topics/draft/")
    assert reload.data == saved.data
    policy.refresh_from_db(); snapshot.refresh_from_db()
    assert policy.updated_at == before and snapshot.is_current and RecommendationSnapshot.objects.filter(policy=policy).count() == 1
    assert list(snapshot.items.order_by("position").values_list("topic_id", flat=True)) == [topic.pk for topic in topics]
    assert EditorialRevision.objects.filter(target_type="recommendation_policy", target_id=policy.pk, status="draft").count() == 1


def test_draft_replay_and_stale_editor_keep_the_newer_selection(api_client, selection):
    policy, topics, _ = selection
    request = draft_request(api_client, policy, topics)
    first = api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json")
    assert first.status_code == 200
    replay = api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json")
    assert replay.status_code == 200 and replay.data == first.data
    stale = {**request, "request_key": str(uuid4()), "items": list(reversed(request["items"]))}
    rejected = api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", stale, format="json")
    assert rejected.status_code == 409
    assert EditorialRevision.objects.filter(target_type="recommendation_policy", target_id=policy.pk).count() == 1
    assert api_client.get("/api/catalog/admin/recommendations/home_topics/draft/").data == first.data


@pytest.mark.parametrize("invalid", ["duplicate", "wrong_type", "private", "too_many", "malformed"])
def test_home_draft_rejects_invalid_targets_without_any_revision(api_client, selection, invalid):
    policy, topics, _ = selection
    request = draft_request(api_client, policy, topics)
    if invalid == "duplicate": request["items"] = [request["items"][0]] * 2
    if invalid == "wrong_type": request["items"][0]["target_type"] = "work"
    if invalid == "private":
        topic = Topic.objects.create(name="尚未公开主题", slug="private-draft-topic", editorial_status="draft")
        request["items"][0]["id"] = str(topic.pk)
    if invalid == "too_many": request["items"] += [request["items"][0]]
    if invalid == "malformed": request["items"][0]["id"] = "not-a-uuid"
    response = api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json")
    assert response.status_code == 400
    assert not EditorialRevision.objects.filter(target_type="recommendation_policy", target_id=policy.pk).exists()


def test_changed_live_snapshot_blocks_old_draft_save(api_client, admin_user, selection):
    policy, topics, _ = selection
    request = draft_request(api_client, policy, topics)
    generate_snapshot(policy, actor=admin_user, selected_targets=list(reversed(topics)))
    response = api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json")
    assert response.status_code == 409
    assert not EditorialRevision.objects.filter(target_type="recommendation_policy", target_id=policy.pk).exists()


def test_private_draft_requires_editor_capability(api_client, reader_user, selection):
    policy, topics, _ = selection
    request = draft_request(api_client, policy, topics)
    api_client.force_authenticate(reader_user)
    assert api_client.get("/api/catalog/admin/recommendations/home_topics/draft/").status_code == 403
    assert api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json").status_code == 403
    assert not EditorialRevision.objects.filter(target_type="recommendation_policy", target_id=policy.pk).exists()


def test_confirmed_publication_consumes_only_the_exact_saved_draft(api_client, selection):
    policy, topics, snapshot = selection
    request = draft_request(api_client, policy, topics)
    saved = api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json")
    assert saved.status_code == 200
    preview = api_client.post("/api/catalog/admin/recommendations/home_topics/preview/", {"items": request["items"]}, format="json")
    assert preview.status_code == 200
    body = {"confirm": True, "request_key": str(uuid4()), "items": request["items"],
            "expected_updated_at": preview.data["expected_updated_at"], "expected_snapshot_id": preview.data["expected_snapshot_id"],
            "preview_token": preview.data["preview_token"], "draft_version": saved.data["edit_version"]}
    stale = api_client.post("/api/catalog/admin/recommendations/home_topics/refresh/", {**body, "draft_version": "stale"}, format="json")
    assert stale.status_code == 409
    snapshot.refresh_from_db(); assert snapshot.is_current
    published = api_client.post("/api/catalog/admin/recommendations/home_topics/refresh/", body, format="json")
    assert published.status_code == 200 and published.data["publication_effective"]
    current = RecommendationSnapshot.objects.get(policy=policy, is_current=True)
    assert list(current.items.order_by("position").values_list("topic_id", flat=True)) == [topic.pk for topic in reversed(topics)]
    state = api_client.get("/api/catalog/admin/recommendations/home_topics/draft/")
    assert not state.data["exists"]
    assert EditorialRevision.objects.get(target_type="recommendation_policy", target_id=policy.pk).status == "published"


def test_new_home_draft_is_discoverable_in_existing_queue(api_client, selection):
    policy, topics, _ = selection
    request = draft_request(api_client, policy, topics)
    assert api_client.put("/api/catalog/admin/recommendations/home_topics/draft/", request, format="json").status_code == 200
    queue = api_client.get("/api/catalog/admin/curation-drafts/", {"q": policy.title, "group": "site"})
    assert queue.status_code == 200
    row = next(row for row in queue.data["results"] if row["object_type"] == "recommendation_policy" and row["object_id"] == str(policy.pk))
    assert row["edit_url"] == "/admin/recommendations?view=home&placement=home_topics"
    assert row["title"] == policy.title and row["can_edit"]
    assert row["changed_fields"] == ["home_selection"]
