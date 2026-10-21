"""Unsaved scholar selector checks, reserved for the final acceptance run."""
from hashlib import sha256
from uuid import uuid4

import pytest

from catalog.models import Contribution, EditorialRevision, EvidenceSpan, ReadingPath
from catalog.services import shared_curation
from catalog.services.editorial_revision import create_editorial_revision
from catalog.services.public_scholars import public_scholar_detail
from .test_public_scholars_20261021 import profile
from .test_reading_paths_20261021 import path_with_items, source
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def published_quotes(scholar, actor, count=13):
    _, _, asset, revision = source()
    page = asset.pages.get(index=1)
    quotations = [f"Synthetic preview quotation {number:02d}." for number in range(count)]
    page.text = " ".join(quotations)
    page.save(update_fields=["text"])
    spans = []
    for text in quotations:
        offset = page.text.index(text)
        spans.append(EvidenceSpan.objects.create(document_revision=revision.document_revision, page=page, page_number=1,
            original_text=text, normalized_text=text, start_offset=offset, end_offset=offset + len(text), content_hash=sha256(text.encode()).hexdigest()))
    saved = shared_curation.save_curation("scholar", scholar.pk, {"items": [
        {"source_type": "span", "source_id": str(span.pk), "group_title": "Synthetic sources"} for span in spans]}, actor)
    shared_curation.publish_curation("scholar", scholar.pk, saved["edit_version"], actor)
    return saved["items"]


def test_unsaved_quote_and_paths_resolve_beyond_first_page_without_mutation(api_client, admin_user):
    scholar = profile()
    quotes = published_quotes(scholar, admin_user)
    scholar.curation = {"featured_source_id": quotes[0]["id"]}
    scholar.save(update_fields=["curation"])
    automatic, _, materials, edition = path_with_items()
    Contribution.objects.create(edition=edition, person=scholar.person, role="author", approved=True)
    activate_catalog_revision(edition, reader_asset=materials[0].asset, document_revision=materials[0].document_revision)
    manual = [ReadingPath.objects.create(title=f"Synthetic manual path {number:02d}", slug=f"preview-path-{uuid4()}", status="published") for number in range(13)]
    hidden = ReadingPath.objects.create(title="Private path must not appear", slug=f"preview-hidden-{uuid4()}", status="draft")
    draft = create_editorial_revision(target_type="scholar_profile", target_id=scholar.pk,
        patch={"short_description": "Saved draft description"}, actor=admin_user, idempotency_key=f"preview-{uuid4()}")
    revision_count = EditorialRevision.objects.count()
    original_patch = draft.patch.copy()
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/knowledge-preview/scholar/{scholar.pk}/"
    response = api_client.get(url, {"featured_source_id": quotes[-1]["id"], "reading_path_ids": ",".join(str(row.pk) for row in [*manual, hidden])})
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    data = response.data["perspective"]["data"]
    assert data["short_description"] == "Saved draft description"
    assert data["featured_quote"]["id"] == quotes[-1]["id"]
    assert quotes[-1]["id"] not in {row["id"] for row in data["evidence"]["results"]}
    assert data["paths"]["count"] == data["counts"]["paths"] == 14
    assert len(data["paths"]["results"]) == 12 and data["paths"]["total_pages"] == 2 and data["paths"]["next"]
    assert "Private path must not appear" not in str(response.data)
    assert response.data["perspectives"]["published"]["data"]["featured_quote"]["id"] == quotes[0]["id"]
    cleared = api_client.get(url, {"featured_source_id": "", "reading_path_ids": ""}).data["perspective"]["data"]
    assert cleared["featured_quote"] is None
    assert cleared["paths"]["count"] == 1 and cleared["paths"]["results"][0]["id"] == str(automatic.pk)
    scholar.refresh_from_db()
    draft.refresh_from_db()
    assert scholar.curation == {"featured_source_id": quotes[0]["id"]}
    assert draft.patch == original_patch and EditorialRevision.objects.count() == revision_count
    assert public_scholar_detail(scholar.slug)["featured_quote"]["id"] == quotes[0]["id"]


def test_unsaved_preview_revalidates_source_and_blocks_other_scholar_reference(api_client, admin_user):
    scholar, other = profile(), profile("Other synthetic scholar")
    quote, foreign = published_quotes(scholar, admin_user, 1)[0], published_quotes(other, admin_user, 1)[0]
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/knowledge-preview/scholar/{scholar.pk}/"
    assert api_client.get(url, {"featured_source_id": foreign["id"]}).status_code == 400
    span = EvidenceSpan.objects.get(pk=quote["source_id"])
    span.page.asset.access_status = "restricted"
    span.page.asset.save(update_fields=["access_status"])
    response = api_client.get(url, {"featured_source_id": quote["id"]})
    assert response.status_code == 200
    assert response.data["perspective"]["data"]["featured_quote"] is None


@pytest.mark.parametrize("query", [
    "featured_source_id=not-a-uuid", "featured_source_id=&featured_source_id=", "reading_path_ids=not-a-uuid",
    "reading_path_ids=" + ",".join([str(uuid4())] * 101), "include_candidates=true",
])
def test_preview_selection_query_is_bounded_and_stays_protected(api_client, admin_user, reader_user, query):
    scholar = profile()
    url = f"/api/catalog/admin/knowledge-preview/scholar/{scholar.pk}/?{query}"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.get(url).status_code == 400


def test_scholar_selection_overrides_cannot_target_another_object_type(api_client, admin_user):
    path = ReadingPath.objects.create(title="Synthetic path", slug=f"preview-{uuid4()}")
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"/api/catalog/admin/knowledge-preview/reading_path/{path.pk}/", {"featured_source_id": ""})
    assert response.status_code == 400
