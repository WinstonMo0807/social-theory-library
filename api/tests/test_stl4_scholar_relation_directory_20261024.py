"""Deferred scholar-centred mixed directory and original scope acceptance."""
from uuid import uuid4
import pytest

from catalog.models import EditorialRevision, PersonNodeRelation, ScholarRelation
from .test_stl4_person_node_directory_20261024 import node, scholar

pytestmark = pytest.mark.django_db


def directory(profile):
    return f"/api/catalog/admin/scholars/{profile.pk}/knowledge-relations/"


def revision(row, first, second):
    return EditorialRevision.objects.create(target_type="scholar_relation", target_id=row.pk, revision=1, status="draft",
        idempotency_key=str(uuid4()), materialized_preview={"source_scholar": str(first.pk), "target_scholar": str(second.pk),
            "relation_type": "influence", "direction": "bidirectional", "summary": "草稿中的双向解释", "source": "原材料出处"})


def test_mixed_rows_keep_original_identity_direction_filters_and_permissions(api_client, admin_user, reader_user):
    first, second = scholar(), scholar()
    concept = node("可定位的概念")
    link = PersonNodeRelation.objects.create(person=first.person, node=concept, relation_type="influences", direction="directed", node_is_source=True)
    relation = ScholarRelation.objects.create(source_scholar=first, target_scholar=second, relation_type="teaching")
    revision(relation, first, second)
    api_client.force_authenticate(admin_user)
    response = api_client.get(directory(first), HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["count"] == 2
    rows = {row["kind"]: row for row in response.data["results"]}
    assert rows["person"]["id"] == str(link.pk) and rows["person"]["source_name"] == concept.canonical_name_zh
    assert rows["scholar"]["id"] == str(relation.pk) and rows["scholar"]["direction"] == "bidirectional"
    assert rows["scholar"]["has_unpublished_changes"]
    filtered = api_client.get(directory(first), {"direction": "bidirectional", "relation_type": "influence", "kind": "scholar"})
    assert filtered.data["count"] == 1 and filtered.data["results"][0]["id"] == str(relation.pk)
    assert api_client.get(directory(first), {"q": "可定位"}).data["results"][0]["id"] == str(link.pk)
    assert api_client.patch(directory(first), {}, format="json").status_code == 405
    api_client.force_authenticate(reader_user)
    assert api_client.get(directory(first)).status_code == 403


def test_original_and_draft_scholar_scope_share_one_detail_boundary(api_client, admin_user):
    old, retained, new, unrelated = scholar(), scholar(), scholar(), scholar()
    relation = ScholarRelation.objects.create(source_scholar=old, target_scholar=retained, relation_type="influence", status="published")
    revision(relation, new, retained)
    api_client.force_authenticate(admin_user)
    for center in (old, retained, new):
        listing = api_client.get(directory(center))
        assert listing.status_code == 200 and listing.data["count"] == 1
        assert listing.data["results"][0]["remains_in_draft"] == (center.pk != old.pk)
        assert api_client.get(f"/api/catalog/admin/scholar-relations/{relation.pk}/", {"scholar": str(center.pk)}).status_code == 200
    assert api_client.get(directory(unrelated)).data["count"] == 0
    assert api_client.get(f"/api/catalog/admin/scholar-relations/{relation.pk}/", {"scholar": str(unrelated.pk)}).status_code == 404
    assert api_client.get(f"/api/catalog/admin/scholar-relations/{relation.pk}/", {"scholar": "invalid"}).status_code == 400


def test_mixed_directory_paginates_before_reading_original_rows(api_client, admin_user):
    first, other = scholar(), scholar()
    for index in range(25):
        PersonNodeRelation.objects.create(person=first.person, node=node(f"分页概念{index}"))
    ScholarRelation.objects.create(source_scholar=first, target_scholar=other, relation_type="teaching")
    api_client.force_authenticate(admin_user)
    first_page = api_client.get(directory(first)).data
    second_page = api_client.get(directory(first), {"page": 2}).data
    assert first_page["count"] == second_page["count"] == 26
    assert len(first_page["results"]) == 24 and len(second_page["results"]) == 2
    assert len({row["id"] for row in [*first_page["results"], *second_page["results"]]}) == 26
    assert api_client.get(directory(first), {"page": 3}).status_code == 404
