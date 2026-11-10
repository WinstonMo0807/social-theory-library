"""Risk-based scholar acceptance definitions; not run during implementation."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import Contribution, Edition, EditorialRevision, Person, PersonNameVariant, ScholarProfile, Work
from catalog.services.public_scholars import (preview_scholar, public_scholar_detail, scholar_directory,
    scholar_follow_summary, validate_scholar_curation)
from catalog.services.editorial_revision import create_editorial_revision, publish_editorial_revision
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def profile(name="Synthetic scholar", **person_values):
    person = Person.objects.create(preferred_name=name, authority_status="verified", **person_values)
    return ScholarProfile.objects.create(person=person, slug=f"scholar-{uuid4()}", editorial_status="published")


def edition(person, role="author", *, work=None, primary=True, scope=None):
    work = work or Work.objects.create(title=f"Synthetic work {uuid4()}")
    row = Edition.objects.create(work=work, state="published", is_primary=primary, publication_mode="bibliographic", public_slug=f"scholar-work-{uuid4()}")
    Contribution.objects.create(person=person, edition=row, role=role, scope=scope or {}, approved=True)
    activate_catalog_revision(row, fulltext_ready=False)
    return row


def test_exact_public_edition_roles_exclude_hidden_second_edition_and_live_edits():
    scholar, other = profile(), profile("Another")
    public = edition(other.person)
    hidden = Edition.objects.create(work=public.work, state="draft", is_primary=False)
    Contribution.objects.create(edition=hidden, person=scholar.person, role="author", approved=True)
    own = edition(scholar.person, "editor")
    Contribution.objects.filter(edition=own).update(role="author")
    payload = public_scholar_detail(scholar.slug)
    assert payload["works"]["count"] == 1
    assert payload["works"]["results"][0]["edition_id"] == str(own.pk)
    assert payload["works"]["results"][0]["roles"] == ["editor"]
    assert payload["authored_work_count"] == 0
    assert public_scholar_detail(scholar.slug, {"role": "author"})["works"]["count"] == 0


def test_formal_alias_namesakes_signed_dates_and_pagination():
    scholar = profile("Same name", birth_year=-500, death_year=-400)
    other = profile("Same name", birth_year=1900, death_year=1980)
    PersonNameVariant.objects.create(person=scholar.person, name="Confirmed alias", variant_type="translation", source_kind="editorial", is_verified=True, displayable=True)
    PersonNameVariant.objects.create(person=scholar.person, name="Private candidate", variant_type="alias", source_kind="pdf_evidence", is_verified=False)
    hit = scholar_directory({"q": "Confirmed alias"})
    assert hit["count"] == 1 and hit["results"][0]["matched_alias"] == "Confirmed alias"
    assert scholar_directory({"q": "Private candidate"})["count"] == 0
    payload = scholar_directory({"q": "Same name", "page_size": "1"})
    assert payload["count"] == 2 and payload["total_pages"] == 2 and payload["next"]
    assert scholar_directory({"period": "classical"})["results"][0]["id"] == str(scholar.pk)
    assert public_scholar_detail(scholar.slug)["disambiguation"][0]["id"] == str(other.pk)


@pytest.mark.parametrize("year", [0, -10000, 9999])
def test_invalid_person_years_are_not_silently_saved(year):
    with pytest.raises(ModelValidationError):
        profile(birth_year=year)


def test_draft_preview_and_follow_summary_keep_formal_identity(admin_user, api_client):
    scholar = profile()
    published = create_editorial_revision(target_type="scholar_profile", target_id=scholar.pk, patch={"short_description": "Formal description"},
        actor=admin_user, idempotency_key=f"scholar-public-{uuid4()}")
    publish_editorial_revision(published.pk, actor=admin_user)
    draft = create_editorial_revision(target_type="scholar_profile", target_id=scholar.pk,
        patch={"person": {"preferred_name": "Unpublished identity"}}, actor=admin_user, idempotency_key=f"scholar-draft-{uuid4()}")
    scholar.refresh_from_db()
    assert public_scholar_detail(scholar.slug)["person"]["preferred_name"] == "Synthetic scholar"
    assert scholar_follow_summary(scholar.pk)["public_revision"] == f"{published.pk}:{published.revision}"
    preview = preview_scholar(scholar, snapshot=draft.materialized_preview, request=SimpleNamespace(user=admin_user))
    assert preview["person"]["preferred_name"] == "Unpublished identity" and preview["public_revision"]["token"] == "preview"
    with pytest.raises(PermissionDenied):
        preview_scholar(scholar, snapshot=draft.materialized_preview)
    person = Person.objects.get(pk=scholar.person_id)
    person.preferred_name, person.portrait = "Live unpublished identity", "private/draft-portrait.jpg"
    person.save(update_fields=["preferred_name", "portrait"])
    formal = public_scholar_detail(scholar.slug)
    assert formal["person"]["preferred_name"] == "Synthetic scholar" and formal["person"]["portrait"] == ""
    assert scholar_follow_summary(scholar.pk)["portrait_url"] == ""
    assert scholar_directory({"q": "Live unpublished identity"})["count"] == 0
    assert api_client.get(f"/api/catalog/people/{scholar.person_id}/portrait/").status_code == 404


def test_candidates_require_editorial_capabilities_and_do_not_change_formal_count(admin_user):
    from catalog.models import ScholarRelation
    scholar, other = profile(), profile("Related")
    row = ScholarRelation.objects.create(source_scholar=scholar, target_scholar=other, relation_type="influence")
    EditorialRevision.objects.create(target_type="scholar_relation", target_id=row.pk, revision=1, status="draft",
        materialized_preview={"source_scholar": str(scholar.pk), "target_scholar": str(other.pk), "relation_type": "influence", "direction": "directed", "summary": "Historical draft relation", "source": "Synthetic citation"}, idempotency_key=str(uuid4()))
    public = public_scholar_detail(scholar.slug)
    assert public["relations"]["count"] == 0 and public["candidate_relations"] is None
    with pytest.raises(PermissionDenied):
        public_scholar_detail(scholar.slug, {"include_candidates": "true"})
    editor = public_scholar_detail(scholar.slug, {"include_candidates": "true"}, request=SimpleNamespace(user=admin_user))
    assert editor["candidate_relations"]["count"] == 1 and editor["relations"]["count"] == 0
    other.editorial_status = "draft"
    other.save(update_fields=["editorial_status"])
    assert public_scholar_detail(scholar.slug, {"include_candidates": "true"}, request=SimpleNamespace(user=admin_user))["candidate_relations"]["count"] == 0


def test_free_text_quote_never_becomes_original_and_sources_are_validated():
    scholar = profile()
    scholar.featured_quote, scholar.quote_source = "Unverified quotation", "Invented page 99"
    scholar.save()
    assert public_scholar_detail(scholar.slug)["featured_quote"] is None
    with pytest.raises(ValidationError):
        validate_scholar_curation({"profile_sources": [{"id": str(uuid4()), "title": "Synthetic", "url": "javascript:alert(1)", "fields": ["biography"]}]})
    with pytest.raises(ValidationError):
        validate_scholar_curation({"featured_source_id": str(uuid4())}, scholar)


def test_reading_paths_follow_formal_items_and_current_exact_edition(admin_user):
    from .test_reading_paths_20261021 import path_with_items
    from catalog.services.public_reading_paths import capture_reading_path_publication
    path, _, items, material = path_with_items()
    scholar = profile()
    Contribution.objects.create(edition=material, person=scholar.person, role="editor", approved=True)
    material.catalog_revisions.filter(status="active").update(status="superseded")
    activate_catalog_revision(material, reader_asset=items[0].asset, document_revision=items[0].document_revision)
    capture_reading_path_publication(path, actor=admin_user)
    path.items.all().delete()  # Simulate an unpublished editor change; published membership survives.
    result = public_scholar_detail(scholar.slug)["paths"]
    assert result["count"] == 1 and result["results"][0]["id"] == str(path.pk)
    material.state = "draft"
    material.save(update_fields=["state"])
    assert public_scholar_detail(scholar.slug)["paths"]["count"] == 0


def test_work_cover_and_reader_keep_exact_version_and_source_checksum():
    from .test_reading_paths_20261021 import source
    _, material, asset, initial = source()
    scholar = profile()
    Contribution.objects.create(edition=material, person=scholar.person, role="author", approved=True)
    material.work.cover = "public/synthetic-cover.jpg"
    material.work.save(update_fields=["cover"])
    material.catalog_revisions.filter(status="active").update(status="superseded")
    revision = activate_catalog_revision(material, reader_asset=asset, document_revision=initial.document_revision)
    row = public_scholar_detail(scholar.slug)["works"]["results"][0]
    assert f"edition_id={material.pk}" in row["cover_url"] and row["reader_href"]
    document = revision.document_revision
    document.source_checksum = "b" * 64
    document.save(update_fields=["source_checksum"])
    changed = public_scholar_detail(scholar.slug)["works"]["results"][0]
    assert changed["reader_href"] == "" and changed["source_status"] == "no_fulltext"
