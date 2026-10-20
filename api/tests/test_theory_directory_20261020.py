"""Final-acceptance cases for PDF54; definitions only during implementation."""
from uuid import uuid4

import pytest

from catalog.models import (
    Discipline, KnowledgeNode, KnowledgeNodeAlias, KnowledgeNodeDiscipline,
    KnowledgeRelation, Person, PersonNodeRelation, ScholarProfile, Subdiscipline,
)
from catalog.theory_serializers import KnowledgeRelationSerializer

pytestmark = pytest.mark.django_db
URL = "/api/catalog/theory-system/directory/"


@pytest.fixture(autouse=True)
def enable_theories(settings):
    settings.THEORY_SYSTEM_ENABLED = True


def node(name="Synthetic theory", **values):
    return KnowledgeNode.objects.create(
        canonical_name_zh=name, slug=f"directory-{uuid4()}",
        **{"node_type": "theory_tradition", "status": "published", **values},
    )


def discipline(name="Synthetic discipline", **values):
    key = f"directory-{uuid4()}"
    return Discipline.objects.create(
        name=name, slug=key, code=key, **{"editorial_status": "published", **values},
    )


def items(data):
    return [item for group in data["groups"] for item in group["items"]]


def test_directory_pages_keep_real_parent_groups_and_counts(client):
    parent = node("Editorial parent")
    children = [node(f"Child {number:02}", parent=parent) for number in range(23)]
    node("Hidden child", parent=parent, status="draft")
    first = client.get(URL, {"parent": str(parent.pk)})
    assert first.status_code == 200
    data = first.json()
    assert data["count"] == 23 and data["total_pages"] == 2
    assert len(items(data)) == 20
    assert len(data["groups"]) == 1 and data["groups"][0]["title"] == parent.canonical_name_zh
    assert data["groups"][0]["parent"]["id"] == str(parent.pk)
    assert data["breadcrumbs"][-1]["id"] == str(parent.pk)
    second = client.get(URL, {"parent": parent.slug, "page": 2}).json()
    assert len(items(second)) == 3
    assert {row["id"] for row in items(data) + items(second)} == {str(row.pk) for row in children}
    assert client.get(URL, {"parent": parent.slug, "page": 3}).status_code == 404
    parents = client.get(URL, {"q": parent.canonical_name_zh}).json()
    assert next(row for row in items(parents) if row["id"] == str(parent.pk))["child_count"] == 23


def test_hidden_parent_does_not_leak_identity_and_cannot_be_opened(client):
    secret = node("Private parent", status="draft")
    child = node("Public independent description", parent=secret)
    response = client.get(URL)
    data = response.json()
    assert response.status_code == 200 and data["count"] == 1
    assert items(data)[0]["id"] == str(child.pk)
    assert items(data)[0]["parent_id"] is None
    assert data["groups"][0]["parent"] is None and data["groups"][0]["title"] == "公开条目"
    assert str(secret.pk) not in response.content.decode()
    assert secret.canonical_name_zh not in response.content.decode()
    assert client.get(URL, {"parent": secret.slug}).status_code == 404


def test_independent_subdiscipline_identity_excludes_historical_mirror(client):
    field = discipline()
    parent = Subdiscipline.objects.create(name="Parent field", slug="parent-field", discipline=field, editorial_status="published")
    child = Subdiscipline.objects.create(name="Child field", slug="child-field", discipline=field, parent=parent, editorial_status="published")
    mirror = node("Obsolete mirror", node_type="subdiscipline")
    data = client.get(URL, {"type": "subdiscipline", "parent": parent.slug}).json()
    assert data["count"] == 1
    assert items(data)[0]["id"] == str(child.pk)
    assert items(data)[0]["kind"] == "subdiscipline"
    assert items(data)[0]["href"] == f"/subdisciplines/{child.slug}"
    assert str(mirror.pk) not in str(data)
    assert client.get(URL, {"type": "subdiscipline", "parent": str(mirror.pk)}).status_code == 404


def test_overview_and_discipline_counts_use_independent_subdisciplines(client):
    field = discipline()
    Subdiscipline.objects.create(
        name="Published independent field", slug="independent-field",
        discipline=field, editorial_status="published",
    )
    Subdiscipline.objects.create(
        name="Draft independent field", slug="draft-field",
        discipline=field, editorial_status="draft",
    )
    for index in range(2):
        node(f"Obsolete mirror {index}", node_type="subdiscipline", primary_discipline=field)
    response = client.get("/api/catalog/theory-system/overview/")
    assert response.status_code == 200
    data = response.json()
    assert data["browse"]["subdisciplines"] == 1
    assert next(row for row in data["disciplines"] if row["id"] == str(field.pk))["counts"]["subdisciplines"] == 1
    response = client.get(f"/api/catalog/theory-system/disciplines/{field.slug}/")
    assert response.status_code == 200
    assert response.json()["counts"]["subdisciplines"] == 1


def test_discipline_relations_are_public_and_unique_before_pagination(client):
    first, other, hidden = discipline(), discipline("Other"), discipline("Hidden", editorial_status="draft")
    shared = node(primary_discipline=first)
    KnowledgeNodeDiscipline.objects.create(node=shared, discipline=first, status="published")
    outsider = node("Other node", primary_discipline=other)
    KnowledgeNodeDiscipline.objects.create(node=outsider, discipline=first, status="pending")
    data = client.get(URL, {"discipline": str(first.pk)}).json()
    assert data["discipline"] == first.slug
    assert data["count"] == 1 and items(data)[0]["id"] == str(shared.pk)
    assert hidden.slug not in str(data["disciplines"])
    assert client.get(URL, {"discipline": hidden.slug}).status_code == 404


@pytest.mark.parametrize("query,expected", [("Public alias", 1), ("Candidate alias", 0), ("Published scholar", 1), ("Draft scholar", 0)])
def test_directory_search_uses_public_names_and_representatives(client, query, expected):
    target = node()
    KnowledgeNodeAlias.objects.create(node=target, alias="Public alias", is_verified=True)
    KnowledgeNodeAlias.objects.create(node=target, alias="Candidate alias", is_verified=False)
    for name, status in [("Published scholar", "published"), ("Draft scholar", "draft")]:
        person = Person.objects.create(preferred_name=name, authority_status="verified")
        ScholarProfile.objects.create(person=person, slug=f"scholar-{uuid4()}", editorial_status=status)
        PersonNodeRelation.objects.create(person=person, node=target, is_representative=True, status="published")
    data = client.get(URL, {"q": query}).json()
    assert data["count"] == expected
    if expected:
        assert items(data)[0]["id"] == str(target.pk)


def test_corrupt_parent_cycles_are_bounded_without_inventing_hierarchy(client):
    first = node("First")
    second = node("Second", parent=first)
    KnowledgeNode.objects.filter(pk=first.pk).update(parent=second)
    response = client.get(URL, {"parent": first.slug})
    assert response.status_code == 200
    data = response.json()
    assert data["hierarchy_truncated"] is True
    assert len(data["breadcrumbs"]) == 2
    assert len({row["id"] for row in data["breadcrumbs"]}) == 2


@pytest.mark.parametrize("params", [
    {"type": "topic"}, {"type": "discipline"}, {"page": 0}, {"page": "-1"}, {"page": "wrong"}, {"q": "x" * 241},
])
def test_invalid_directory_filters_are_explicit_not_empty(client, params):
    assert client.get(URL, params).status_code == 400


def test_true_empty_directory_has_no_fake_groups(client):
    data = client.get(URL).json()
    assert data["count"] == 0 and data["groups"] == []
    assert data["page"] == data["total_pages"] == 1
    assert data["parent"] is None and data["breadcrumbs"] == []


def test_relation_end_types_are_actual_identities_not_name_inferences():
    source, target = node("Same title"), node("Same title", node_type="concept")
    relation = KnowledgeRelation.objects.create(
        source_node=source, target_node=target, relation_type="borrows_concept_from", status="published",
    )
    payload = KnowledgeRelationSerializer(relation).data
    assert payload["source_node_type"] == "theory_tradition"
    assert payload["target_node_type"] == "concept"
