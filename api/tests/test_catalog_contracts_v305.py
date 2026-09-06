import pytest

from catalog.contracts.fields import BIBLIOGRAPHY_FIELDS, FIELD_CONTRACTS, FIELDS, SECTION_FIELDS
from catalog.contracts.identifiers import normalize_doi, normalize_isbn, valid_doi, valid_isbn
from catalog.contracts.validation import field_error
from catalog.models import Asset, Contribution, Edition, KnowledgePublicationEvent, Person, ProjectionState
from catalog.services.admin_workflow import build_edition_workflow
from catalog.services.cataloging_sessions import open_cataloging_session
from catalog.services.knowledge_publication import process_knowledge_event
from catalog.services.publication_eligibility import active_catalog_snapshot
from catalog.workflow_serializers import BibliographySectionSerializer
from ingestion.services.publication import publication_preflight, publish_edition


def test_registry_is_unique_and_legacy_imports_share_the_same_contract():
    from catalog.services import admin_workflow, field_decisions

    assert len(FIELDS) == len(FIELD_CONTRACTS)
    assert field_decisions.SECTION_FIELDS is SECTION_FIELDS
    assert admin_workflow.BIBLIOGRAPHY_FIELDS is BIBLIOGRAPHY_FIELDS
    for field in FIELDS:
        assert set(field.dependencies) <= FIELD_CONTRACTS.keys()
        assert field.payload()["key"] == field.key


@pytest.mark.parametrize("value,length", [("0-306-40615-2", 10), ("978-0-306-40615-7", 13), ("0-8044-2957-X", 10)])
def test_valid_isbn_normalizes_and_checks_checksum(value, length):
    assert valid_isbn(value, length)
    assert len(normalize_isbn(value)) == length


@pytest.mark.parametrize("value", ["9780306406158", "0-306-40615-3", "9770306406150", "isbn:not-a-number"])
def test_invalid_isbn_is_blocking(value):
    assert not valid_isbn(value)


def test_doi_normalization_preserves_suffix_and_does_not_claim_resolution():
    assert normalize_doi("https://doi.org/10.1000/ABC%2FDEF") == "10.1000/abc/def"
    assert valid_doi("doi:10.1000/test-suffix")
    assert not valid_doi("not-a-doi")
    assert not valid_doi("10.1000/has spaces")
    assert valid_doi("")


def test_workflow_serializer_and_publication_use_identical_identifier_rules():
    good = BibliographySectionSerializer(data={"isbn13": "978-0-306-40615-7", "doi": "https://doi.org/10.1000/ABC"})
    assert good.is_valid(), good.errors
    assert good.validated_data["isbn13"] == "9780306406157"
    assert good.validated_data["doi"] == "10.1000/abc"
    bad = BibliographySectionSerializer(data={"isbn13": "9780306406158"})
    assert not bad.is_valid()
    assert field_error("isbn13", "9780306406158")["severity"] == "blocking"
    assert field_error("publication_year", "2020") is None
    assert field_error("publication_year", "2020.5") is not None
    assert field_error("publication_year", True) is not None


def _manual_ready(admin_user):
    session, _created = open_cataloging_session(actor=admin_user, source_type="manual", title="真实纯书目")
    person = Person.objects.create(preferred_name="人工确认作者", sort_name="人工确认作者", authority_status="verified")
    Contribution.objects.create(edition=session.edition, person=person, role="author", approved=True)
    return session.edition


@pytest.mark.django_db
def test_manual_bibliography_publishes_through_existing_revision_and_public_detail(admin_user, api_client):
    edition = _manual_ready(admin_user)
    preflight = publication_preflight(edition)
    assert preflight["blockers"] == []
    assert not any("OCR" in value for value in preflight["background_tasks"])
    steps = {row["key"]: row for row in build_edition_workflow(edition)["steps"]}
    assert steps["reader"]["status"] == "skipped"
    assert steps["file"]["status"] == "skipped"
    published = publish_edition(edition, actor=admin_user, confirm_warnings=True)
    event = KnowledgePublicationEvent.objects.get(catalog_revision__edition=edition)
    assert edition.cataloging_sessions.get().status == "publishing"
    # Controlled consumer completion exercises the existing activation service;
    # this is not evidence that external production projections are available.
    ProjectionState.objects.filter(object_type="edition", object_id=edition.pk).update(
        status="current", projected_revision=event.domain_event.canonical_revision,
    )
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    assert edition.cataloging_sessions.get().status == "published"
    assert active_catalog_snapshot(edition)["work"]["title"] == "真实纯书目"
    assert not edition.active_catalog_revision.fulltext_ready
    assert edition.active_catalog_revision.reader_asset_id is None
    assert published.public_slug
    response = api_client.get(f"/api/catalog/works/{published.public_slug}/")
    assert response.status_code == 200
    assert response.data["edition"]["readable_asset"] is None


@pytest.mark.django_db
def test_bibliography_mode_never_masks_an_attached_broken_file(admin_user):
    edition = _manual_ready(admin_user)
    Asset.objects.create(edition=edition, kind="original", status="failed", sha256="d" * 64)
    preflight = publication_preflight(edition)
    assert any("PDF" in reason for reason in preflight["blockers"])
    assert any("锚点" in reason for reason in preflight["blockers"])


@pytest.mark.django_db
def test_legacy_document_mode_still_requires_readable_document(admin_user):
    edition = _manual_ready(admin_user)
    edition.publication_mode = Edition.PublicationMode.DOCUMENT
    edition.save(update_fields=["publication_mode", "updated_at"])
    assert publication_preflight(edition)["blockers"]


@pytest.mark.django_db
def test_invalid_identifier_blocks_publication_even_when_human_confirmed(admin_user):
    edition = _manual_ready(admin_user)
    edition.isbn13 = "9780306406158"
    edition.save(update_fields=["isbn13", "updated_at"])
    assert any("ISBN" in reason for reason in publication_preflight(edition)["blockers"])
