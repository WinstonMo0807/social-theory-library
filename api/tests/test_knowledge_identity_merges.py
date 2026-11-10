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
from tests.test_stl4_node_merge_20261026 import pair as node_pair, command

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


def old_node_fingerprint(source, target, *, before_core=False):
    from catalog.services.knowledge_merge_guard import merge_scope_queries
    from catalog.services.knowledge_identity import identity_scope
    from catalog.services.person_authority import digest
    knowledge_names = identity_scope(m.Entity.objects.none()).keys()
    snapshots = {}
    for name, rows in merge_scope_queries(source.pk, target.pk).items():
        if before_core and name in knowledge_names:
            continue
        values = list(rows.order_by("pk").values())
        if name == "Entity":
            for row in values:
                for key in ("organization_id", "timeline_event_id", "research_object_id"):
                    row.pop(key)
        snapshots[name] = [digest(row) for row in values]
    return digest(snapshots)


def test_pre_core_node_receipt_only_compatible_while_knowledge_empty(node_pair, superadmin_user, monkeypatch):
    monkeypatch.setattr("catalog.services.knowledge_identity.merge_identity", lambda *a: {})
    left, right = node_pair
    record = commands.merge(left.pk, right.pk, **command(node_pair, superadmin_user))
    record.rollback_payload["scope_fingerprint"] = old_node_fingerprint(left, right, before_core=True)
    record.save(update_fields=["rollback_payload"])
    assert commands.rollback_state(record)["can_rollback"]
    entity_for_legacy(left)
    assert not commands.rollback_state(record)["can_rollback"]
    with pytest.raises(ValueError, match="已经变化"):
        knowledge_nodes.rollback_merge(record.pk, actor=superadmin_user)


def test_pre_profile_node_receipt_preserves_later_edits(node_pair, superadmin_user):
    left, right = node_pair
    record = commands.merge(left.pk, right.pk, **command(node_pair, superadmin_user))
    record.rollback_payload["scope_fingerprint"] = old_node_fingerprint(left, right)
    record.save(update_fields=["rollback_payload"])
    assert commands.rollback_state(record)["can_rollback"]
    m.Entity.objects.filter(node=right).update(definition="归并之后的新定义")
    assert not commands.rollback_state(record)["can_rollback"]


@pytest.mark.parametrize("before_core", [False, True])
def test_person_older_receipt_retains_knowledge_guard(merge_owner, monkeypatch, before_core):
    from catalog.services import person_merges as service
    left, right = people()
    if before_core:
        from types import SimpleNamespace
        state = service._state(left, right, [])[0]
        legacy = {key: value for key, value in state.items() if key != "knowledge"}
        record = SimpleNamespace(source_snapshot=state["source"], target_snapshot=state["target"],
                                 rollback_fingerprint=service._digest(legacy))
        assert service._rollback_digest(record, state) == record.rollback_fingerprint
        entity_for_legacy(right)
        assert service._rollback_digest(record, service._state(left, right, [])[0]) != record.rollback_fingerprint
        return
    prepared = prepare_person_merge(left, right)
    record = merge_people(left.pk, right.pk, actor=merge_owner, confirmed=True,
        expected_fingerprint=prepared["fingerprint"], idempotency_key=f"historic-person-{before_core}")
    left.refresh_from_db(); right.refresh_from_db()
    state = service._state(left, right, record.affected_edition_ids)[0]
    for row in state["knowledge"]["Entity"]:
        for key in ("organization_id", "timeline_event_id", "research_object_id"):
            row.pop(key)
    record.rollback_fingerprint = service._digest(state)
    # Present an older receipt to preview without rewriting immutable history.
    assert rollback_preview(record)["can_rollback"]
    m.Entity.objects.filter(person=right).update(definition="合并之后保留的新说明")
    assert not rollback_preview(record)["can_rollback"]
