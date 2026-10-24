"""Deferred dependency summary scope; never counts a reader's personal objects."""
import pytest
from catalog.lifecycle_views import _dependency_rows
from catalog.models import KnowledgeRelation, PersonNodeRelation, ScholarRelation, Work, WorkNodeRelation
from .test_stl4_person_node_directory_20261024 import node, scholar

pytestmark = pytest.mark.django_db


def test_node_summary_keeps_relation_roles_and_original_person_work_links():
    current, left, right = node(), node(), node()
    person = scholar()
    KnowledgeRelation.objects.create(source_node=current, target_node=right, relation_type="criticizes")
    KnowledgeRelation.objects.create(source_node=left, target_node=current, relation_type="criticizes")
    PersonNodeRelation.objects.create(person=person.person, node=current)
    WorkNodeRelation.objects.create(work=Work.objects.create(title="仅用于验收"), node=current)
    result = _dependency_rows(current)
    assert {row["accessor"] for row in result if row["key"] == "catalog.knowledgerelation"} == {"incoming_relations", "outgoing_relations"}
    assert next(row for row in result if row["key"] == "catalog.personnoderelation")["count"] == 1
    assert next(row for row in result if row["key"] == "catalog.worknoderelation")["count"] == 1
    assert all(not row["key"].startswith(("reading.", "accounts.")) for row in result)


def test_scholar_summary_includes_its_canonical_person_without_copying_links():
    current, other = scholar(), scholar()
    PersonNodeRelation.objects.create(person=current.person, node=node())
    ScholarRelation.objects.create(source_scholar=current, target_scholar=other, relation_type="influence")
    ScholarRelation.objects.create(source_scholar=other, target_scholar=current, relation_type="teaching")
    result = _dependency_rows(current)
    person = next(row for row in result if row["key"] == "catalog.personnoderelation")
    assert person["accessor"] == "person.node_relations" and person["count"] == 1
    relations = [row for row in result if row["key"] == "catalog.scholarrelation"]
    assert len(relations) == 2 and len({row["accessor"] for row in relations}) == 2
    assert {row["label"] for row in relations} == {"学者关系（作为来源）", "学者关系（作为目标）"}
