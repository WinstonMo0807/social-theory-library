from uuid import uuid4
import pytest
from catalog import models as m
from catalog.services.knowledge_core import entity_for_legacy
from catalog.services.knowledge_migration import migrate_relation
from tests.test_theory_graph_20261021 import node, scholar, graph
from tests.v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def test_source_specific_opposing_relations_and_context_filter(api_client):
    profile, concept = scholar(), node()
    person_entity, concept_entity = entity_for_legacy(profile.person), entity_for_legacy(concept)
    statements, works = [], []
    for predicate, context in [("uses", "第一部作品的使用"), ("criticizes", "第二部作品的批评")]:
        work = m.Work.objects.create(title=context)
        edition = m.Edition.objects.create(work=work, state="published", public_slug=str(uuid4()))
        activate_catalog_revision(edition, fulltext_ready=False)
        statement = m.Assertion.objects.create(text=context, predicate=predicate, status="published", source_quality="human_citation", conditions={"concept_usage":context})
        m.AssertionParticipant.objects.create(assertion=statement, role="subject", entity=person_entity)
        m.AssertionParticipant.objects.create(assertion=statement, role="object", entity=concept_entity)
        m.AssertionSource.objects.create(assertion=statement, work=work, citation=f"{context}，人工出处")
        statements.append(statement); works.append(work)
    data = graph(api_client, concept)
    assert {v["relation_type"] for v in data["edges"]} == {"uses", "criticizes"}
    assert len(data["nodes"]) == 2 and not data["truncated"]
    assert all(v["model"] == "Assertion" for v in data["edges"])
    data = graph(api_client, concept, source_work=str(works[1].pk), context="批评", assertion_direction="directed")
    assert len(data["edges"]) == 1 and data["edges"][0]["entity_id"] == str(statements[1].pk)
    m.Edition.objects.filter(work=works[1]).update(state="withdrawn")
    assert {v["relation_type"] for v in graph(api_client, concept)["edges"]} == {"uses"}


def test_migrated_manual_relation_keeps_one_edge_and_its_evidence_gap(api_client):
    profile, concept = scholar(), node()
    old = m.PersonNodeRelation.objects.create(person=profile.person, node=concept, relation_type="uses", status="published", source="历史人工说明")
    mapped = migrate_relation(old)
    result = graph(api_client, concept)
    assert len(result["edges"]) == 1
    assert result["edges"][0]["id"] == f"Assertion:{mapped.target_id}"
    assert result["edges"][0]["source_quality"] == "legacy_source_gap"
    assert m.PersonNodeRelation.objects.filter(pk=old.pk).exists()
