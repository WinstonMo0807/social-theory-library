"""Identity merge never collapses source-specific assertions or rewrites their endpoints."""
from uuid import uuid4
import pytest
from catalog import models as m
from catalog.services import knowledge_nodes, knowledge_merge_commands as commands
from catalog.services.knowledge_core import entity_for_legacy, match_entities
from catalog.services.knowledge_identity import canonical_entity
from catalog.services.knowledge_migration import migrate_relation, migrate_assertion_page
from catalog.services.academic_projection import person_node_links
from catalog.services.knowledge_public import assertion_public
from catalog.services.person_merges import prepare_person_merge, merge_people, rollback_preview, rollback_person_merge
from tests.test_person_merge_v305 import merge_owner, pair as people

pytestmark = pytest.mark.django_db


def node(label):
    return m.KnowledgeNode.objects.create(canonical_name_zh=label, node_type="concept", slug=str(uuid4()), status="published")


def test_node_merge_preserves_two_interpretations_and_historical_identity(superadmin_user, monkeypatch, api_client, settings):
    settings.THEORY_SYSTEM_ENABLED = True
    monkeypatch.setattr(knowledge_nodes, "record_admin_canonical_change", lambda **kw: None)
    monkeypatch.setattr(knowledge_nodes, "_publish_merged_work_metadata", lambda *a, **kw: None)
    left, right = node("同名概念"), node("同名概念")
    person = m.Person.objects.create(preferred_name="原主张者", authority_status="verified")
    m.ScholarProfile.objects.create(person=person, slug=str(uuid4()), editorial_status="published")
    originals = [m.PersonNodeRelation.objects.create(person=person, node=value, status="published",
        relation_type=predicate, source=citation) for value, predicate, citation in
        [(left, "uses", "作品甲原人工出处"), (right, "criticizes", "作品乙原人工出处")]]
    statements = [m.Assertion.objects.get(pk=migrate_relation(row).target_id) for row in originals]
    original_ids = list(m.AssertionParticipant.objects.order_by("id").values("id", "entity_id"))
    reviewed = commands.preview(left, right)
    record = commands.merge(left.pk, right.pk, actor=superadmin_user, request_id=uuid4(), confirmed=True, fingerprint=reviewed["fingerprint"])
    assert m.PersonNodeRelation.objects.count() == 2
    assert list(m.AssertionParticipant.objects.order_by("id").values("id", "entity_id")) == original_ids
    links = list(person_node_links(node_ids=[right.pk]))
    assert {v.relation_type for v in links} == {"uses", "criticizes"}
    assert {v.node_id for v in links} == {right.pk}
    assert all(assertion_public(row) for row in statements)
    assert canonical_entity(entity_for_legacy(left)).pk == entity_for_legacy(right).pk
    response = api_client.get(f"/api/catalog/theory-system/nodes/{left.slug}/")
    assert response.status_code == 200 and response.data["id"] == str(right.pk)
    state = commands.rollback_state(record)
    assert state["can_rollback"]
    commands.rollback(record.pk, actor=superadmin_user, confirmed=True, fingerprint=state["fingerprint"])
    assert [v.relation_type for v in person_node_links(node_ids=[left.pk])] == ["uses"]


def test_person_merge_preserves_canonical_endpoints_and_rejects_later_statement_edit(merge_owner, api_client):
    source, target = people()
    m.ScholarProfile.objects.create(person=source, slug=str(uuid4()), editorial_status="published")
    concept = node("理论使用")
    old = m.PersonNodeRelation.objects.create(person=source, node=concept, status="published", relation_type="uses", source="原始人工出处")
    first = entity_for_legacy(source)
    statement = m.Assertion.objects.get(pk=migrate_relation(old).target_id)
    page = m.KnowledgePage.objects.get(pk=migrate_assertion_page(statement).provenance["page_id"])
    original_blocks = page.body_blocks
    reviewed = prepare_person_merge(source, target)
    record = merge_people(source.pk, target.pk, actor=merge_owner, confirmed=True, expected_fingerprint=reviewed["fingerprint"], idempotency_key="knowledge-person-merge")
    old.refresh_from_db()
    assert old.person_id == source.pk
    statement = m.Assertion.objects.get(participants__entity=first)
    assert assertion_public(statement)
    assert list(person_node_links(person_ids=[target.pk]))[0].person_id == target.pk
    matches = match_entities(source.preferred_name, "person")
    assert any(v["id"] == str(entity_for_legacy(target).pk) for v in matches)
    pages = api_client.get(f"/api/knowledge/objects/person/{target.pk}/").data["pages"]
    assert pages[0]["id"] == str(page.pk) and pages[0]["blocks"] == original_blocks
    assert rollback_preview(record)["can_rollback"]
    m.AssertionSource.objects.create(assertion=statement, citation="后续编辑补充的另一出处")
    assert not rollback_preview(record)["can_rollback"]
    with pytest.raises(ValueError):
        rollback_person_merge(record.pk, actor=merge_owner, confirmed=True, expected_fingerprint=record.rollback_fingerprint)
    assert m.AssertionSource.objects.filter(citation="后续编辑补充的另一出处").exists()
