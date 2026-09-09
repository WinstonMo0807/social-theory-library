import pytest

from catalog.models import CatalogFieldDecision, Contribution, PublicationBundleItem
from catalog.services.field_decisions import record_edition_field_decision
from ingestion.models import FieldLock, UploadBatch, UploadItem
from ingestion.services.publication import publication_preflight
from ingestion.serializers import MetadataReviewSerializer
from .test_resilient_publication_v260 import create_item_with_files


pytestmark = pytest.mark.django_db


def review_item(admin_user, settings, tmp_path):
    work, edition, _original, asset = create_item_with_files(settings, tmp_path)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, edition=edition, asset=asset, source_filename="review.pdf")
    return item, work, edition


def payload(**updates):
    return {"title": "人工复核书目", "document_type": "book", "language": "zh-CN", "authors": ["人工确认作者"],
            "publication_year": 2026, "publisher": "人工出版社", "retry_publication": False, **updates}


def test_editor_review_confirms_explicit_language_and_registers_only_draft_authors(api_client, admin_user, settings, tmp_path):
    admin_user.role = "editor"
    admin_user.save(update_fields=["role"])
    item, _work, edition = review_item(admin_user, settings, tmp_path)
    record_edition_field_decision(edition, "language", status="needs_review", value="zh-CN", provenance={"source": "machine"})
    api_client.force_authenticate(admin_user)
    response = api_client.put(f"/api/ingestion/items/{item.pk}/review/", payload(), format="json")
    assert response.status_code == 200, response.data
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name="language")
    assert decision.status == "confirmed" and decision.confirmed_by == admin_user
    assert decision.value == "zh-CN" and decision.provenance["source"] == "manual_metadata_review"
    assert FieldLock.objects.filter(edition=edition, field_name="language", locked_by=admin_user).exists()
    assert FieldLock.objects.get(edition=edition, field_name="publisher").locked_value == "人工出版社"
    edition.refresh_from_db()
    assert publication_preflight(edition)["blockers"] == []
    author = Contribution.objects.get(edition=edition, role="author").person
    assert author.authority_status == "draft"
    assert PublicationBundleItem.objects.filter(bundle__edition=edition, object_type="person", object_id=author.pk, action="create").exists()
    assert edition.active_catalog_revision_id is None


def test_omitted_language_is_preserved_without_an_invented_confirmation(api_client, admin_user, settings, tmp_path):
    item, work, edition = review_item(admin_user, settings, tmp_path)
    work.language = "en"
    work.save(update_fields=["language", "updated_at"])
    data = payload()
    data.pop("language")
    api_client.force_authenticate(admin_user)
    response = api_client.put(f"/api/ingestion/items/{item.pk}/review/", data, format="json")
    assert response.status_code == 200, response.data
    work.refresh_from_db()
    assert work.language == "en"
    assert not FieldLock.objects.filter(edition=edition, field_name="language").exists()
    assert not CatalogFieldDecision.objects.filter(edition=edition, field_name="language", status="confirmed").exists()
    edition.refresh_from_db()
    assert "正文语言尚未填写或确认" in publication_preflight(edition)["blockers"]


@pytest.mark.parametrize("field,value", [("isbn", "9780306406158"), ("doi", "not-a-doi")])
def test_review_rejects_invalid_identifiers_before_any_catalog_write(api_client, admin_user, settings, tmp_path, field, value):
    item, work, edition = review_item(admin_user, settings, tmp_path)
    old_title = work.title
    api_client.force_authenticate(admin_user)
    response = api_client.put(f"/api/ingestion/items/{item.pk}/review/", payload(**{field: value}), format="json")
    assert response.status_code == 400
    assert field in response.data["details"]
    work.refresh_from_db()
    assert work.title == old_title
    assert not Contribution.objects.filter(edition=edition).exists()
    assert not CatalogFieldDecision.objects.filter(edition=edition).exists()


def test_legacy_review_uses_the_shared_identifier_and_year_contract():
    serializer = MetadataReviewSerializer(data=payload(isbn="978-0-306-40615-7", doi="https://doi.org/10.1234/example", publication_year=1300))
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["isbn"] == "9780306406157"
    assert serializer.validated_data["doi"] == "10.1234/example"
    assert serializer.validated_data["publication_year"] == 1300


def test_review_saves_the_declared_publication_date_with_json_safe_confirmation(api_client, admin_user, settings, tmp_path):
    item, _work, edition = review_item(admin_user, settings, tmp_path)
    api_client.force_authenticate(admin_user)
    response = api_client.put(
        f"/api/ingestion/items/{item.pk}/review/",
        payload(publication_date="2026-09-09", lock_fields=["publication_date"]), format="json",
    )
    assert response.status_code == 200, response.data
    edition.refresh_from_db()
    assert edition.publication_date.isoformat() == "2026-09-09"
    assert CatalogFieldDecision.objects.get(edition=edition, field_name="publication_date").value == "2026-09-09"
    assert FieldLock.objects.get(edition=edition, field_name="publication_date").locked_value == "2026-09-09"
    invalid = MetadataReviewSerializer(data=payload(publication_date="2025-01-01"))
    assert not invalid.is_valid()
    assert "publication_date" in invalid.errors


def test_review_does_not_reactivate_archived_author_and_rolls_back_all_writes(api_client, admin_user, settings, tmp_path):
    from catalog.models import Person

    item, work, edition = review_item(admin_user, settings, tmp_path)
    old_title = work.title
    person = Person.objects.create(preferred_name="已归档的学者", sort_name="已归档的学者", authority_status="archived")
    api_client.force_authenticate(admin_user)
    response = api_client.put(
        f"/api/ingestion/items/{item.pk}/review/",
        payload(authors=[], author_person_ids=[str(person.pk)]), format="json",
    )
    assert response.status_code == 400, response.data
    assert "relations" in response.data["details"]
    work.refresh_from_db()
    person.refresh_from_db()
    assert work.title == old_title and person.authority_status == "archived"
    assert not Contribution.objects.filter(edition=edition).exists()
    assert not CatalogFieldDecision.objects.filter(edition=edition).exists()
