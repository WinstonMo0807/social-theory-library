"""Synthetic reader identity regressions; authored, not run during development."""
from uuid import uuid4

import pytest

from catalog.models import (
    Asset, CatalogPublicationRevision, Contribution, DocumentRevision, Edition, EvidenceSpan,
    KnowledgeNode, Page, Passage, Person, ScholarProfile, SemanticChunk, Topic, Work,
    WorkNodeRelation, WorkTopicRelation,
)
from .v304_helpers import activate_catalog_revision


def published_pdf(work=None, *, title="Reader fixture", primary=True, fulltext=True, access="public"):
    work = work or Work.objects.create(title=title, document_type="book")
    work.title, work.cover = title, f"synthetic/{uuid4()}.jpg"
    work.save(update_fields=["title", "cover"])
    edition = Edition.objects.create(work=work, state="published", is_primary=primary,
        public_slug=f"reader-{uuid4()}", publisher=f"{title} publisher", publication_year=2002)
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready",
        validation_status="valid", access_status=access, file=f"synthetic/{uuid4()}.pdf",
        sha256=uuid4().hex * 2, page_count=3)
    Page.objects.create(asset=asset, index=1, chapter_title=f"{title} chapter", text="Synthetic text")
    activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=fulltext)
    return work, edition, asset


def manifest(client, asset):
    return client.get(f"/api/catalog/assets/{asset.pk}/manifest/")


@pytest.mark.django_db
def test_reader_bibliography_cover_and_versions_bind_requested_secondary_pdf(api_client, monkeypatch):
    from catalog.public_work_detail import PublicWorkDetailSerializer

    def forbidden_detail_hydration(*args):
        raise AssertionError("A reader manifest must not hydrate the full detail relationships.")

    monkeypatch.setattr(PublicWorkDetailSerializer, "get_relations", forbidden_detail_hydration)
    monkeypatch.setattr(PublicWorkDetailSerializer, "get_curated_claims", forbidden_detail_hydration)
    work, first, first_asset = published_pdf(title="First")
    _, second, second_asset = published_pdf(work, title="Second", primary=False)
    work.title = "Unpublished title"
    work.save(update_fields=["title"])
    for edition, asset, title in ((first, first_asset, "First"), (second, second_asset, "Second")):
        response = manifest(api_client, asset)
        data = response.data
        assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
        assert data["asset_id"] == str(asset.pk) and data["edition_id"] == str(edition.pk)
        assert data["work"]["title"] == title
        assert data["work"]["edition"]["publisher"] == f"{title} publisher"
        assert data["work"]["edition"]["id"] == str(edition.pk)
        assert data["work"]["edition"]["readable_asset"]["id"] == str(asset.pk)
        assert f"edition_id={edition.pk}" in data["work"]["cover"]
        assert {row["id"] for row in data["work"]["editions"]} == {str(first.pk), str(second.pk)}
        assert data["document_revision_id"] == str(edition.active_catalog_revision.document_revision_id)
        assert "relations" not in data["work"] and "curated_claims" not in data["work"]


@pytest.mark.django_db
def test_reader_keeps_metadata_ready_pdf_without_activated_fulltext(api_client):
    _, edition, asset = published_pdf(fulltext=False)
    response = manifest(api_client, asset)
    assert response.status_code == 200
    assert response.data["document_revision_id"] is None
    assert response.data["edition_id"] == str(edition.pk)
    assert response.data["work"]["edition"]["readable_asset"]["id"] == str(asset.pk)


@pytest.mark.django_db
@pytest.mark.parametrize("access", ["registered", "restricted", "private"])
def test_reader_authorized_current_file_does_not_open_other_versions(api_client, admin_user, access):
    work, selected, asset = published_pdf(access=access)
    _, other, _ = published_pdf(work, primary=False, access="private")
    assert manifest(api_client, asset).status_code == 404
    api_client.force_authenticate(admin_user)
    response = manifest(api_client, asset)
    assert response.status_code == 200
    assert response.data["work"]["edition"]["readable_asset"]["id"] == str(asset.pk)
    assert all(row["readable_asset"] is None for row in response.data["work"]["editions"])
    assert {row["id"] for row in response.data["work"]["editions"]} == {str(selected.pk), str(other.pk)}


@pytest.mark.django_db
def test_reader_rejects_withdrawn_edition_and_superseded_asset(api_client):
    _, edition, first = published_pdf()
    replacement = Asset.objects.create(edition=edition, kind="normalized", status="ready",
        validation_status="valid", access_status="public", file=f"synthetic/{uuid4()}.pdf",
        sha256=uuid4().hex * 2, page_count=1)
    activate_catalog_revision(edition, reader_asset=replacement)
    assert manifest(api_client, first).status_code == 404
    assert manifest(api_client, replacement).status_code == 200
    Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    assert manifest(api_client, replacement).status_code == 404


@pytest.mark.django_db
def test_reader_links_follow_current_public_entities_and_mask_withdrawal(api_client, admin_user):
    work, edition, asset = published_pdf()
    person = Person.objects.create(preferred_name="Synthetic author", authority_status="verified",
        birth_year=1901, portrait="synthetic/portrait.jpg")
    scholar = ScholarProfile.objects.create(person=person, slug=f"author-{uuid4()}", editorial_status="published")
    Contribution.objects.create(edition=edition, person=person, role="author", approved=True)
    node = KnowledgeNode.objects.create(node_type="theory_tradition", canonical_name_zh="Synthetic theory",
        slug=f"theory-{uuid4()}", status="published")
    topic = Topic.objects.create(name=f"Synthetic topic {uuid4()}", slug=f"topic-{uuid4()}", editorial_status="published")
    WorkNodeRelation.objects.create(work=work, node=node, status="published")
    WorkTopicRelation.objects.create(work=work, topic=topic, review_status="approved")
    activate_catalog_revision(edition, reader_asset=asset)
    scholar.slug, node.slug, topic.slug = f"current-{uuid4()}", f"current-{uuid4()}", f"current-{uuid4()}"
    scholar.save(update_fields=["slug"])
    node.save(update_fields=["slug"])
    topic.save(update_fields=["slug"])
    first = manifest(api_client, asset).data
    assert first["related_scholars"][0]["slug"] == scholar.slug
    assert first["related_scholars"][0]["portrait"].endswith("synthetic/portrait.jpg")
    assert first["related_theories"][0]["slug"] == node.slug
    assert first["related_topics"][0]["slug"] == topic.slug
    Person.objects.filter(pk=person.pk).update(authority_status="archived")
    KnowledgeNode.objects.filter(pk=node.pk).update(status="withdrawn")
    Topic.objects.filter(pk=topic.pk).update(editorial_status="draft")
    api_client.force_authenticate(admin_user)
    withdrawn = manifest(api_client, asset).data
    assert withdrawn["related_scholars"] == []
    assert withdrawn["related_theories"] == [] and withdrawn["related_topics"] == []
    assert withdrawn["work"]["edition"]["contributors"][0]["person"]["preferred_name"] == "Synthetic author"
    assert withdrawn["work"]["edition"]["contributors"][0]["person"]["scholar_slug"] is None


def focus_source(kind, asset):
    page = asset.pages.get(index=1)
    if kind == "passage":
        return Passage.objects.create(page=page, order=0, text=page.text, normalized_text=page.text.casefold())
    if kind == "span":
        return EvidenceSpan.objects.create(page=page, page_number=page.index,
            document_revision=asset.edition.active_catalog_revision.document_revision,
            original_text=page.text, content_hash=uuid4().hex * 2, start_offset=0, end_offset=len(page.text))
    return SemanticChunk.objects.create(asset=asset, work=asset.edition.work, order=0,
        page_start=1, page_end=1, original_text=page.text, normalized_text=page.text.casefold(),
        document_type="book", parser_version="fixture", chunk_version="fixture",
        document_id=uuid4().hex, content_hash=uuid4().hex * 2, locators=[{"page_index": 1}])


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["passage", "span", "chunk"])
def test_secondary_focus_uses_exact_active_source_and_preserves_access_limits(api_client, admin_user, kind):
    work, primary, _ = published_pdf(title="Primary")
    _, selected, asset = published_pdf(work, title="Secondary", primary=False)
    Edition.objects.filter(pk=primary.pk).update(state="withdrawn")
    source = focus_source(kind, asset)
    url = f"/api/catalog/passages/{source.pk}/focus/"
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data["asset_id"] == str(asset.pk)
    assert response.data["title"] == "Secondary"
    assert response.data["document_revision_id"] == str(selected.active_catalog_revision.document_revision_id)
    CatalogPublicationRevision.objects.filter(pk=selected.active_catalog_revision_id).update(fulltext_ready=False)
    assert api_client.get(url).status_code == 404
    CatalogPublicationRevision.objects.filter(pk=selected.active_catalog_revision_id).update(fulltext_ready=True)
    Asset.objects.filter(pk=asset.pk).update(access_status="private")
    assert api_client.get(url).status_code == 404
    api_client.force_authenticate(admin_user)
    assert api_client.get(url).status_code == 200
    Edition.objects.filter(pk=selected.pk).update(state="withdrawn")
    assert api_client.get(url).status_code == 404


@pytest.mark.django_db
def test_secondary_span_rejects_stale_revision_and_different_reader_anchor(api_client):
    _, edition, asset = published_pdf(primary=False)
    span = focus_source("span", asset)
    url = f"/api/catalog/passages/{span.pk}/focus/"
    EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=True)
    assert api_client.get(url).status_code == 404
    EvidenceSpan.objects.filter(pk=span.pk).update(is_stale=False)
    replacement = Asset.objects.create(edition=edition, kind="normalized", status="ready",
        access_status="public", file=f"synthetic/{uuid4()}.pdf", sha256=uuid4().hex * 2)
    catalog = CatalogPublicationRevision.objects.filter(pk=edition.active_catalog_revision_id)
    # A span's document revision alone is insufficient when the reader points
    # at a different file. No text or locator may cross that source boundary.
    catalog.update(reader_asset=replacement)
    assert api_client.get(url).status_code == 404
    catalog.update(reader_asset=asset)
    new_revision = DocumentRevision.objects.create(asset=asset, revision=2,
        source_checksum=asset.sha256, text_checksum=uuid4().hex * 2)
    catalog.update(document_revision=new_revision)
    assert api_client.get(url).status_code == 404
