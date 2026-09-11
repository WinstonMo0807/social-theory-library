import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Person, PersonNameVariant
from catalog.services.person_merges import merge_people, prepare_person_merge
from catalog.services.query_lexicon.sync import ensure_query_lexicon_state

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("role", ["editor", "admin"])
def test_staff_can_find_people_without_scholar_profiles_and_only_verified_variants(role):
    client = APIClient()
    client.force_authenticate(User.objects.create_user(username=role, role=role))
    source = Person.objects.create(preferred_name="馆内来源", authority_status="verified")
    for name, verified in [("Confirmed alternative", True), ("Unchecked alternative", False)]:
        PersonNameVariant.objects.create(person=source, name=name, variant_type="alias", source_kind="editorial", is_verified=verified)
    result = client.get("/api/catalog/admin/people/", {"search": "Confirmed alternative"})
    assert result.status_code == 200
    assert result["Cache-Control"] == "private, no-store"
    assert [row["id"] for row in result.data["results"]] == [str(source.pk)]
    assert not source.merged_into_id
    assert client.get("/api/catalog/admin/people/", {"search": "Unchecked alternative"}).data["results"] == []
    assert client.get("/api/catalog/admin/people/", {"limit": 51}).status_code == 400
    assert client.get("/api/catalog/admin/people/merge-records/", {"source_person": source.pk}).status_code == 403


def test_person_search_is_bounded_and_reader_denied():
    client = APIClient()
    client.force_authenticate(User.objects.create_user(username="editor", email="editor-ui@example.test", role="editor"))
    for name in ["甲", "乙"]:
        Person.objects.create(preferred_name=name)
    result = client.get("/api/catalog/admin/people/", {"limit": 1})
    assert len(result.data["results"]) == 1 and result.data["has_more"]
    client.force_authenticate(User.objects.create_user(username="reader", email="reader-ui@example.test", role="reader"))
    assert client.get("/api/catalog/admin/people/").status_code == 403
    client.force_authenticate(None)
    assert client.get("/api/catalog/admin/people/").status_code == 401


def test_person_search_does_not_load_full_biography_or_unrequested_metadata():
    client = APIClient()
    client.force_authenticate(User.objects.create_user(username="editor", role="editor"))
    Person.objects.create(preferred_name="摘要候选", biography="详情不应被列表查询加载")
    with CaptureQueriesContext(connection) as queries:
        response = client.get("/api/catalog/admin/people/", {"search": "摘要"})
    assert response.status_code == 200
    selects = [row["sql"] for row in queries.captured_queries if 'FROM "catalog_person"' in row["sql"]]
    assert len(selects) == 1
    assert "biography" not in selects[0] and "external_ids" not in selects[0]


def test_owner_can_recover_operation_record_without_snapshot_or_private_data(settings):
    owner = User.objects.create_user(username="owner", email="owner-ui@example.test", role="admin")
    settings.LIBRARY_OWNER_EMAIL = owner.email
    source = Person.objects.create(preferred_name="来源", authority_status="verified")
    target = Person.objects.create(preferred_name="保留", authority_status="verified")
    ensure_query_lexicon_state()
    record = merge_people(source.pk, target.pk, actor=owner, confirmed=True,
                          expected_fingerprint=prepare_person_merge(source, target)["fingerprint"], idempotency_key="ui-history")
    client = APIClient()
    client.force_authenticate(owner)
    with CaptureQueriesContext(connection) as queries:
        result = client.get("/api/catalog/admin/people/merge-records/", {"source_person": source.pk})
    assert result.status_code == 200
    assert result["Cache-Control"] == "private, no-store"
    assert result.data[0]["id"] == str(record.pk)
    assert set(result.data[0]) == {"id", "source_person_id", "target_person_id", "created_at", "rolled_back_at"}
    selects = [row["sql"] for row in queries.captured_queries if 'FROM "catalog_personmergerecord"' in row["sql"]]
    assert len(selects) == 1
    assert "snapshot" not in selects[0] and "rollback_fingerprint" not in selects[0]
    assert client.get("/api/catalog/admin/people/merge-records/", {"source_person": target.pk}).data == []
    assert client.get("/api/catalog/admin/people/merge-records/").status_code == 400
