"""Deferred explicit private-topic selection and withdrawal acceptance."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Topic
from reading import booklist_related, booklists, privacy
from reading.booklist_views import ListCommand
from reading.models import ReadingList
from reading.serializers import ReadingListSerializer

pytestmark = pytest.mark.django_db


def command(row, action, topic, *, request_id=None):
    payload = ListCommand(data={"list_id": str(row.pk), "expected_version": booklists.version(row),
        "request_id": str(request_id or uuid4()), "action": action, "topic_id": str(topic.pk)})
    payload.is_valid(raise_exception=True)
    return payload.validated_data


def test_topic_selection_is_private_and_repeated_request_is_idempotent(reader_user):
    row = ReadingList.objects.create(user=reader_user, title="合成主题关联")
    topic = Topic.objects.create(name="合成正式主题", slug="synthetic-manual-topic", editorial_status="published")
    data = command(row, "topic_add", topic)
    before = topic.updated_at
    first = booklists.command(reader_user, data)
    assert booklists.command(reader_user, data) == first
    row.refresh_from_db(); topic.refresh_from_db()
    assert row.topic_ids == [str(topic.pk)] and topic.updated_at == before
    related = booklist_related.related(SimpleNamespace(user=reader_user), row.pk,
        {"expected_version": booklists.version(row), "section": "topics", "page": 1})
    assert related["topics"][0]["selected"] is True and related["topics"][0]["source_count"] == 0
    assert privacy.export_item(reader_user, "reading_lists", row)["topic_ids"] == [str(topic.pk)]


def test_withdrawn_topic_retains_only_removable_identity(reader_user):
    row = ReadingList.objects.create(user=reader_user, title="合成撤回关联")
    topic = Topic.objects.create(name="撤回后不回显这个题名", slug="synthetic-withdrawn-topic", editorial_status="published")
    booklists.command(reader_user, command(row, "topic_add", topic))
    topic.editorial_status = "draft"; topic.save(update_fields=["editorial_status"])
    row.refresh_from_db()
    result = booklist_related.related(SimpleNamespace(user=reader_user), row.pk,
        {"expected_version": booklists.version(row), "section": "topics", "page": 1})
    assert result["topics"][0]["href"] is None and result["topics"][0]["title"] == "主题当前不可用"
    booklists.command(reader_user, command(row, "topic_remove", topic))
    row.refresh_from_db()
    assert row.topic_ids == [] and Topic.objects.filter(pk=topic.pk).exists()


def test_cross_owner_draft_and_legacy_field_cannot_create_links(reader_user, admin_user):
    row = ReadingList.objects.create(user=reader_user, title="合成权限关联")
    topic = Topic.objects.create(name="未公开主题", slug="synthetic-draft-topic", editorial_status="draft")
    with pytest.raises(NotFound):
        booklists.command(admin_user, command(row, "topic_add", topic))
    with pytest.raises(ValidationError):
        booklists.command(reader_user, command(row, "topic_add", topic))
    serializer = ReadingListSerializer(row, data={"topic_ids": [str(topic.pk)]}, partial=True,
        context={"request": SimpleNamespace(user=reader_user)})
    serializer.is_valid(raise_exception=True)
    assert "topic_ids" not in serializer.validated_data
    row.refresh_from_db()
    assert row.topic_ids == []


def test_private_topic_limit_rejects_new_link_without_dropping_old_selections(reader_user):
    selected = [str(uuid4()) for _ in range(12)]
    row = ReadingList.objects.create(user=reader_user, title="合成主题上限", topic_ids=selected)
    topic = Topic.objects.create(name="第十三项", slug="synthetic-thirteenth-topic", editorial_status="published")
    with pytest.raises(ValidationError):
        booklists.command(reader_user, command(row, "topic_add", topic))
    row.refresh_from_db()
    assert row.topic_ids == selected
