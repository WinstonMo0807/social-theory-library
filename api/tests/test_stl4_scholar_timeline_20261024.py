"""Deferred scholar-event membership acceptance; no execution in development."""
from uuid import uuid4
import pytest
from catalog.models import EditorialRevision, Person, ScholarProfile, TheoryTimelineEvent
from catalog.timeline_editor import timeline_for_scholar

pytestmark = pytest.mark.django_db


def profile():
    return ScholarProfile.objects.create(person=Person.objects.create(preferred_name="验收人物"), slug=f"accept-{uuid4()}")


def draft(event, data):
    return EditorialRevision.objects.create(target_type="timeline_event", target_id=event.pk, revision=1, status="draft", materialized_preview=data, idempotency_key=str(uuid4()))


def test_member_added_only_in_unpublished_draft_is_visible():
    scholar = profile()
    event = TheoryTimelineEvent.objects.create(title="草稿新增关联")
    draft(event, {"scholar": str(scholar.pk), "start_year": 1920, "timeline_relations": []})
    result = timeline_for_scholar(TheoryTimelineEvent.objects.all(), scholar.pk)
    assert list(result.values_list("pk", "scholar_sort_year")) == [(event.pk, 1920)]


def test_multiple_roles_and_removed_draft_keep_original_event_identity():
    scholar = profile()
    linked = TheoryTimelineEvent.objects.create(title="参与的事件")
    draft(linked, {"scholar": None, "start_year": None, "timeline_relations": [{"scholar": str(scholar.pk), "relation_type": "context"}]})
    removed = TheoryTimelineEvent.objects.create(title="公开关联待撤", scholar=scholar)
    draft(removed, {"scholar": None, "timeline_relations": []})
    unrelated = TheoryTimelineEvent.objects.create(title="其他人物")
    draft(unrelated, {"timeline_relations": [None, "无关", {"node": str(uuid4())}]})
    assert set(timeline_for_scholar(TheoryTimelineEvent.objects.all(), scholar.pk).values_list("pk", flat=True)) == {linked.pk, removed.pk}


def test_detail_scope_rejects_unrelated_and_readers(api_client, admin_user, reader_user):
    scholar = profile()
    unrelated = TheoryTimelineEvent.objects.create(title="不属于该学者")
    url = f"/api/catalog/admin/theory-timeline/{unrelated.pk}/?scholar={scholar.pk}"
    api_client.force_authenticate(admin_user)
    assert api_client.get(url, HTTP_X_EDITOR_OWNER=str(admin_user.pk)).status_code == 404
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
