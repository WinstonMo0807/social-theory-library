"""Deferred mixed-relation and merge-protection acceptance; not run in development."""
from uuid import uuid4
import pytest

from catalog.models import EditorialRevision, KnowledgeNode, KnowledgeRelation, Person, PersonNodeRelation, ScholarProfile
from catalog.services.knowledge_nodes import merge_nodes, rollback_merge
from catalog.services.theory_graph import _edge_payload

pytestmark = pytest.mark.django_db


def node(name="验收概念"):
    return KnowledgeNode.objects.create(node_type="concept", canonical_name_zh=name, slug=f"mixed-{uuid4()}", status="published")


def scholar():
    person = Person.objects.create(preferred_name="验收人物", authority_status="verified")
    return ScholarProfile.objects.create(person=person, slug=f"mixed-{uuid4()}", editorial_status="published")


def send(client, actor, url, body):
    return client.post(url, body, format="json", HTTP_X_EDITOR_OWNER=str(actor.pk), HTTP_IDEMPOTENCY_KEY=str(uuid4()))


def test_direction_is_explicit_and_public_graph_keeps_original_identity(api_client, admin_user):
    person, concept = scholar(), node()
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/scholars/{person.pk}/links/node/"
    data = {"action": "save", "target_id": str(concept.pk), "relation_label": "该理论影响了人物的后续论述", "source": "验收文献，第12页",
        "featured": False, "sort_order": 0, "relation_type": "influences", "direction": "directed", "node_is_source": True}
    saved = send(api_client, admin_user, url, data)
    assert saved.status_code == 200 and not saved.data["confirmed"]
    confirm = {**data, "action": "confirm", "id": saved.data["id"], "edit_version": saved.data["edit_version"]}
    assert send(api_client, admin_user, url, {**confirm, "relation_type": "proposes"}).status_code == 400
    assert send(api_client, admin_user, url, {**confirm, "direction": "undirected"}).status_code == 400
    accepted = send(api_client, admin_user, url, confirm)
    assert accepted.status_code == 200 and accepted.data["confirmed"]
    row = PersonNodeRelation.objects.select_related("person__scholar_profile", "node").get(pk=saved.data["id"])
    spec = (PersonNodeRelation, "scholar", "person", "knowledge_node", "node", "person_node", None)
    edge, source, target = _edge_payload(spec, row)
    assert edge["id"] == f"PersonNodeRelation:{row.pk}" and edge["relation_type"] == "person_node"
    assert edge["direction"] == "directed" and edge["relation_label"] == "影响"
    assert source == ("knowledge_node", concept) and target == ("scholar", person)
    assert edge["evidence_source"] == data["source"]


def test_one_directory_contains_original_types_drafts_and_legacy_people(api_client, admin_user, reader_user):
    current, original, other = node(), node(), node()
    profile = scholar()
    link = PersonNodeRelation.objects.create(person=profile.person, node=current, relation_type="criticizes", direction="directed")
    legacy = PersonNodeRelation.objects.create(person=Person.objects.create(preferred_name="尚无学者页的人物"), node=current)
    relation = KnowledgeRelation.objects.create(source_node=original, target_node=other, relation_type="criticizes", status="pending")
    EditorialRevision.objects.create(target_type="knowledge_relation", target_id=relation.pk, revision=1, status="draft",
        materialized_preview={"source_node": str(current.pk), "target_node": str(other.pk)}, idempotency_key=str(uuid4()))
    url = f"/api/catalog/admin/theory-system/nodes/{current.pk}/relations/"
    api_client.force_authenticate(admin_user)
    response = api_client.get(url, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["count"] == 3
    rows = {row["id"]: row for row in response.data["results"]}
    assert rows[str(link.pk)]["scholar_id"] == str(profile.pk)
    assert rows[str(legacy.pk)]["scholar_id"] is None and rows[str(legacy.pk)]["direction"] == "undirected"
    assert rows[str(relation.pk)]["has_unpublished_changes"] and rows[str(relation.pk)]["remains_in_draft"]
    only_people = api_client.get(url, {"kind": "person", "relation_type": "criticizes"})
    assert [row["id"] for row in only_people.data["results"]] == [str(link.pk)]
    assert api_client.get(url, {"page": 2}).status_code == 404
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403


def test_merge_preserves_semantics_and_rejects_conflicting_originals(admin_user):
    profile, first, second = scholar(), node("来源概念"), node("目标概念")
    old = PersonNodeRelation.objects.create(person=profile.person, node=first, relation_type="influences", direction="directed",
        node_is_source=True, source="验收出处", status="published")
    conflict = PersonNodeRelation.objects.create(person=profile.person, node=second, relation_type="criticizes", direction="directed", status="published")
    with pytest.raises(ValueError, match="关系类型"):
        merge_nodes(first.pk, second.pk, actor=admin_user)
    first.refresh_from_db()
    assert first.status == "published" and PersonNodeRelation.objects.filter(pk=old.pk).exists()
    conflict.delete()
    record = merge_nodes(first.pk, second.pk, actor=admin_user)
    copied = PersonNodeRelation.objects.get(person=profile.person, node=second)
    assert (copied.relation_type, copied.direction, copied.node_is_source, copied.source) == (old.relation_type, old.direction, old.node_is_source, old.source)
    rollback_merge(record.pk, actor=admin_user)
    old.refresh_from_db()
    assert old.status == "published" and old.node_is_source
    assert not PersonNodeRelation.objects.filter(pk=copied.pk).exists()


def test_rollback_never_deletes_later_relationship_edits(admin_user):
    profile, first, second = scholar(), node("回退来源"), node("回退目标")
    PersonNodeRelation.objects.create(person=profile.person, node=first, relation_type="influences", direction="directed", node_is_source=True, status="published")
    record = merge_nodes(first.pk, second.pk, actor=admin_user)
    copied = PersonNodeRelation.objects.get(person=profile.person, node=second)
    copied.source = "合并后人工补充的出处"
    copied.save(update_fields=["source", "updated_at"])
    with pytest.raises(ValueError, match="已经变化"):
        rollback_merge(record.pk, actor=admin_user)
    assert PersonNodeRelation.objects.get(pk=copied.pk).source == "合并后人工补充的出处"
    record.refresh_from_db()
    assert record.rolled_back_at is None
