"""Topic follows and existing collections: acceptance definitions, not executed here."""
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import EditorialRevision, Topic
from reading import knowledge_saves, privacy, research, source_follow as follows, topic_saves
from reading.knowledge_models import KnowledgeSaveReceipt
from reading.models import SavedTopic
from reading.serializers import SavedTopicSerializer
from reading.source_models import SourceFollow, SourceFollowEvent

pytestmark = pytest.mark.django_db
FOLLOW = "/api/reading/source-follows/"
SAVED = "/api/reading/saved-topics/"


def topic():
    return Topic.objects.create(name="合成公开主题", slug=f"topic-{uuid4()}", description="已发布导读", editorial_status="published")


def follow_command(row, **changes):
    return {"path": f"/topics/{row.slug}", "topic_id": row.pk, "action": "subscribe", "expected_revision": 0,
            "request_id": uuid4(), **changes}


def save_command(row, **changes):
    return {"topic": row.pk, "saved": True, "expected_version": "0", "request_id": uuid4(), **changes}


def test_follow_uuid_survives_slug_reuse_without_creating_a_collection(reader_user):
    row = topic()
    created = follows.command(reader_user, follow_command(row))["record"]
    old_slug = row.slug
    row.slug = f"renamed-{uuid4()}"
    row.save(update_fields=["slug"])
    other = topic()
    other.slug = old_slug
    other.save(update_fields=["slug"])
    current = follows.output(follows.refresh(created["id"], reader_user.pk))
    assert current["topic_id"] == str(row.pk) and current["path"] == f"/topics/{row.slug}"
    assert follows.command(reader_user, follow_command(other))["record"]["id"] != current["id"]
    assert not SavedTopic.objects.filter(user=reader_user).exists()


def test_formal_topic_revision_alone_changes_fingerprint_and_masks_live_edits(reader_user):
    row = topic()
    published = EditorialRevision.objects.create(target_type="topic", target_id=row.pk, revision=1, status="published",
        idempotency_key=str(uuid4()), published_at=timezone.now(), materialized_preview={"name": row.name, "slug": row.slug, "description": row.description})
    created = follows.command(reader_user, follow_command(row))["record"]
    row.name, row.description = "未发布内部题名", "不可公开描述"
    row.save(update_fields=["name", "description"])
    draft = EditorialRevision.objects.create(target_type="topic", target_id=row.pk, revision=2, status="draft",
        idempotency_key=str(uuid4()), materialized_preview={"name": row.name, "slug": row.slug, "description": row.description})
    EditorialRevision.objects.create(target_type="knowledge_node", target_id=uuid4(), revision=1, status="published", idempotency_key=str(uuid4()))
    unchanged = follows.refresh(created["id"], reader_user.pk)
    assert unchanged.revision == created["revision"]
    assert follows.output(unchanged)["source"]["title"] == "合成公开主题"
    formal_slug = row.slug
    row.slug = f"unpublished-slug-{uuid4()}"
    row.save(update_fields=["slug"])
    assert follows.resolve_public_source(f"/topics/{row.slug}")["can_subscribe"] is False
    assert follows.resolve_public_source(f"/topics/{formal_slug}")["topic_id"] == str(row.pk)
    published.status = "superseded"
    published.save(update_fields=["status"])
    draft.status, draft.published_at = "published", timezone.now()
    draft.save(update_fields=["status", "published_at"])
    current = follows.refresh(created["id"], reader_user.pk)
    follows.refresh(created["id"], reader_user.pk)
    assert current.events.filter(action="changed").count() == 1


@pytest.mark.parametrize("remove", [False, True])
def test_unpublished_or_deleted_topic_stays_cancelable_without_historical_text(reader_user, remove):
    row = topic()
    body = follow_command(row)
    created = follows.command(reader_user, body)["record"]
    if remove:
        row.delete()
    else:
        row.editorial_status = "draft"
        row.save(update_fields=["editorial_status"])
    current = follows.refresh(created["id"], reader_user.pk)
    exported = privacy.export_item(reader_user, "source_follows", current)
    assert exported["source"]["title"] == "来源当前不可用" and not exported["source"]["href"]
    assert "合成公开主题" not in str(exported)
    canceled = follows.command(reader_user, {**body, "action": "unsubscribe", "expected_revision": current.revision, "request_id": uuid4()})
    assert canceled["record"]["active"] is False


def test_follow_privacy_erasure_keeps_only_non_replaying_receipt(reader_user):
    row = topic()
    body = follow_command(row)
    created = follows.command(reader_user, body)["record"]
    record = SourceFollow.objects.get(pk=created["id"])
    SourceFollowEvent.objects.create(user=reader_user, follow=record, action="changed", revision=2)
    target = privacy.target_of(record, "source_follows")
    privacy.erase_item(reader_user, target, record, privacy.erase_impact(reader_user, "source_follows", record), contexts=[])
    assert not SourceFollowEvent.objects.filter(user=reader_user, request_id__isnull=True).exists()
    assert follows.by_request(reader_user, body["request_id"])["receipt"]["deleted"]
    assert follows.command(reader_user, body)["record"] is None
    assert not SourceFollow.objects.filter(user=reader_user).exists()


@pytest.mark.parametrize("change", [{"topic_id": "invalid"}, {"scholar_profile_id": str(uuid4())}, {"expected_revision": True}, {"body": "no text retention"}])
def test_follow_rejects_invalid_or_ambiguous_target(api_client, reader_user, change):
    row = topic()
    api_client.force_authenticate(reader_user)
    body = {key: str(value) if key in {"topic_id", "request_id"} else value for key, value in follow_command(row).items()}
    response = api_client.post(FOLLOW, {**body, **change}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk))
    assert response.status_code == 400 and not SourceFollow.objects.exists()


def test_follow_privacy_pause_stops_writes_but_permits_cancel(reader_user):
    row = topic()
    created = follows.command(reader_user, follow_command(row))["record"]
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"], "retention": {"source_follows": False}})
    with pytest.raises(ValidationError):
        follows.command(reader_user, follow_command(topic()))
    current = follows.refresh(created["id"], reader_user.pk)
    assert follows.output(current)["updates_paused"]
    assert not follows.command(reader_user, follow_command(row, action="unsubscribe", expected_revision=current.revision))["record"]["active"]


def test_collection_uses_formal_projection_and_cannot_be_rebound(api_client, reader_user):
    row = topic()
    EditorialRevision.objects.create(target_type="topic", target_id=row.pk, revision=1, status="published", idempotency_key=str(uuid4()),
        materialized_preview={"name": row.name, "slug": row.slug, "description": row.description})
    created = topic_saves.command(reader_user, save_command(row))
    row.name, row.description = "隐藏草稿名称", "隐藏草稿正文"
    row.save(update_fields=["name", "description"])
    assert topic_saves.state(reader_user, row.pk)["record"]["name"] == "合成公开主题"
    row.editorial_status = "draft"
    row.save(update_fields=["editorial_status"])
    record = SavedTopic.objects.get(pk=created["record"]["id"])
    exported = SavedTopicSerializer(record).data
    assert exported["name"] == "当前不可用的主题" and exported["slug"] == exported["description"] == ""
    assert privacy.describe_item(reader_user, "followed_topics", record)["source"]["path"] == ""
    api_client.force_authenticate(reader_user)
    assert api_client.patch(SAVED + str(record.pk) + "/", {"topic": str(topic().pk)}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 405
    assert not topic_saves.command(reader_user, save_command(row, saved=False, expected_version=created["version"]))["saved"]


@pytest.mark.parametrize("erase", [False, True])
def test_collection_replay_after_delete_or_privacy_erase_cannot_recreate(reader_user, erase):
    row = topic()
    body = save_command(row)
    created = topic_saves.command(reader_user, body)
    assert topic_saves.command(reader_user, body)["record"]["id"] == created["record"]["id"]
    if erase:
        record = SavedTopic.objects.get(pk=created["record"]["id"])
        target = privacy.target_of(record, "followed_topics")
        privacy.erase_item(reader_user, target, record, privacy.erase_impact(reader_user, "followed_topics", record), contexts=[])
    else:
        topic_saves.command(reader_user, save_command(row, saved=False, expected_version=created["version"]))
    assert not topic_saves.command(reader_user, body)["saved"]
    assert topic_saves.state(reader_user, row.pk, body["request_id"])["receipt"]["applied_saved"]
    assert not SavedTopic.objects.filter(user=reader_user).exists()
    assert not SourceFollow.objects.filter(user=reader_user).exists()


def test_collection_nonce_namespace_cas_and_cross_owner(api_client, reader_user, admin_user):
    row = topic()
    body = save_command(row)
    created = topic_saves.command(reader_user, body)
    assert len(topic_saves.target_key(row.pk)) == KnowledgeSaveReceipt._meta.get_field("target_key").max_length
    assert topic_saves.target_key(row.pk) != knowledge_saves.target_key(row.pk)
    with pytest.raises(research.ResearchConflict):
        knowledge_saves.receipt_for(reader_user, row.pk, body["request_id"])
    with pytest.raises(research.ResearchConflict):
        topic_saves.command(reader_user, {**body, "saved": False})
    with pytest.raises(research.ResearchConflict):
        topic_saves.command(reader_user, save_command(row, saved=False))
    with pytest.raises(NotFound):
        topic_saves.state(admin_user, row.pk, body["request_id"])
    api_client.force_authenticate(admin_user)
    assert api_client.get(SAVED + "state/", {"topic": str(row.pk)}, HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 403
    assert api_client.get(SAVED + "state/", {"topic": str(row.pk), "request_id": str(body["request_id"])}, HTTP_X_READER_OWNER=str(admin_user.pk)).status_code == 404
    assert SavedTopic.objects.filter(pk=created["record"]["id"], user=reader_user).exists()


@pytest.mark.parametrize("change", [{"saved": "true"}, {"topic": "invalid"}, {"include_candidates": True}, {"request_id": None}])
def test_collection_command_rejects_invalid_data_and_missing_owner(api_client, reader_user, change):
    row = topic()
    api_client.force_authenticate(reader_user)
    body = {key: str(value) if key in {"topic", "request_id"} else value for key, value in save_command(row).items()}
    assert api_client.post(SAVED + "command/", body, format="json").status_code == 403
    assert api_client.post(SAVED + "command/", {**body, **change}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 400
    assert not SavedTopic.objects.filter(user=reader_user).exists()


def test_collection_retention_is_distinct_from_topic_updates(reader_user):
    row = topic()
    created = topic_saves.command(reader_user, save_command(row))
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"], "retention": {"followed_topics": False}})
    with pytest.raises(ValidationError):
        topic_saves.command(reader_user, save_command(topic()))
    assert follows.command(reader_user, follow_command(row))["record"]["active"]
    assert not topic_saves.command(reader_user, save_command(row, saved=False, expected_version=created["version"]))["saved"]
