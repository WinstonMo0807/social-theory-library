"""Reference editor text edits keep manually reviewed timeline associations."""
import pytest

from catalog.models import Discipline, KnowledgeNode, TimelineEventRelation
from tests.test_relation_timeline_editorial_v306 import editor_object

pytestmark = pytest.mark.django_db


def timeline_with_context(published):
    event, url = editor_object("timeline_event", published=published)
    subject = event.normalized_relations.get()
    subject.description = "人工确认的主体说明"
    subject.sort_order = 17
    subject.save()
    discipline = Discipline.objects.create(name="关联学科", code="TIMELINE-CONTEXT", slug="timeline-context")
    context = TimelineEventRelation.objects.create(
        event=event, discipline=discipline, relation_type="context",
        description="保留背景出处说明", sort_order=29,
    )
    return event, url, subject, context


def payload_row(row):
    return {
        "relation_type": row.relation_type,
        "node": str(row.node_id) if row.node_id else None,
        "discipline": str(row.discipline_id) if row.discipline_id else None,
        "scholar": str(row.scholar_id) if row.scholar_id else None,
        "work": str(row.work_id) if row.work_id else None,
        "evidence": str(row.evidence_id) if row.evidence_id else None,
        "description": row.description, "sort_order": row.sort_order,
    }


def state(row):
    row.refresh_from_db()
    return {"id": row.pk, "created_at": row.created_at, "updated_at": row.updated_at, **payload_row(row)}


def save(client, url, payload):
    version = client.get(url).data["edit_version"]
    return client.patch(url, payload, format="json", HTTP_IF_MATCH=version)


@pytest.mark.parametrize("published", [False, True])
def test_text_save_and_publication_preserve_unchanged_relation_identity_and_times(api_client, admin_user, published):
    event, url, subject, context = timeline_with_context(published)
    original = [state(subject), state(context)]
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, {"description": "新事件说明", "relations": [payload_row(subject), payload_row(context)]})
    assert response.status_code == (202 if published else 200), response.data
    assert [row["id"] for row in response.data["relations"]] == [str(subject.pk), str(context.pk)]
    if published:
        event.refresh_from_db()
        assert event.description == "原说明"
        result = api_client.post(f"/api{response.data['editorial_revision']['publish_url']}", {}, format="json")
        assert result.status_code == 200, result.data
    assert [state(subject), state(context)] == original
    event.refresh_from_db()
    assert event.description == "新事件说明"


@pytest.mark.parametrize("published", [False, True])
def test_added_subject_keeps_existing_metadata_when_hidden_fields_are_omitted(api_client, admin_user, published):
    event, url, subject, context = timeline_with_context(published)
    original = [state(subject), state(context)]
    new_node = KnowledgeNode.objects.create(canonical_name_zh="新增主体", slug="new-timeline-subject", node_type="theory_tradition")
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, {"relations": [
        {"node": str(subject.node_id), "relation_type": "subject"},
        {"discipline": str(context.discipline_id), "relation_type": "context"},
        {"node": str(new_node.pk), "relation_type": "subject", "sort_order": 30},
    ]})
    assert response.status_code == (202 if published else 200), response.data
    assert [row["id"] for row in response.data["relations"][:2]] == [str(subject.pk), str(context.pk)]
    if published:
        result = api_client.post(f"/api{response.data['editorial_revision']['publish_url']}", {}, format="json")
        assert result.status_code == 200, result.data
    assert [state(subject), state(context)] == original
    assert event.normalized_relations.filter(node=new_node, sort_order=30).exists()


@pytest.mark.parametrize("published", [False, True])
def test_duplicate_subject_is_rejected_without_partial_changes(api_client, admin_user, published):
    event, url, subject, context = timeline_with_context(published)
    original = [state(subject), state(context)]
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, {"description": "不能写入", "relations": [payload_row(subject), payload_row(subject), payload_row(context)]})
    assert response.status_code == 400, response.data
    assert [state(subject), state(context)] == original
    event.refresh_from_db()
    assert event.description == "原说明"


def test_explicit_metadata_edit_keeps_id_and_only_removes_omitted_association(api_client, admin_user):
    event, url, subject, context = timeline_with_context(False)
    identifier, created_at = subject.pk, subject.created_at
    api_client.force_authenticate(admin_user)
    response = save(api_client, url, {"relations": [{**payload_row(subject), "description": "明确修改主体说明"}]})
    assert response.status_code == 200, response.data
    subject.refresh_from_db()
    assert (subject.pk, subject.created_at, subject.sort_order) == (identifier, created_at, 17)
    assert subject.description == "明确修改主体说明"
    assert not TimelineEventRelation.objects.filter(pk=context.pk).exists()
