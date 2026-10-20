"""Synthetic PDF33–35 regressions; authored, not run during development."""
from io import BytesIO
from uuid import uuid4

import pytest

from catalog.models import Asset, CatalogPublicationRevision, Edition, Page, Work
from .v304_helpers import activate_catalog_revision


def publish(work=None, *, title="Synthetic published title", primary=True, readable=False, cover=""):
    work = work or Work.objects.create(title=title, document_type="book")
    work.title, work.original_title, work.subtitle, work.cover = title, f"Original {title}", "Published subtitle", cover
    work.save(update_fields=["title", "original_title", "subtitle", "cover"])
    edition = Edition.objects.create(work=work, state="published", is_primary=primary,
        public_slug=f"synthetic-{uuid4()}", publisher=f"Publisher {title}", publication_year=2001)
    asset = None
    if readable:
        asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
            access_status="public", file=f"synthetic/{uuid4()}.pdf", sha256=uuid4().hex * 2, page_count=2)
        Page.objects.create(asset=asset, index=1, chapter_title=f"Chapter {title}", text="Synthetic public text")
    activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=readable)
    return work, edition, asset


def detail(client, edition_or_slug):
    return client.get(f"/api/catalog/works/{getattr(edition_or_slug, 'public_slug', edition_or_slug)}/")


@pytest.mark.django_db
def test_selected_version_binds_title_bibliography_asset_and_outline(api_client):
    work, first, first_asset = publish(title="First", readable=True)
    _, second, second_asset = publish(work, title="Second", primary=False, readable=True)
    first_data, second_data = detail(api_client, first).data, detail(api_client, second).data
    for data, edition, asset, title in ((first_data, first, first_asset, "First"), (second_data, second, second_asset, "Second")):
        assert data["title"] == title and data["original_title"] == f"Original {title}"
        assert data["edition"]["id"] == str(edition.pk)
        assert data["edition"]["publisher"] == f"Publisher {title}"
        assert data["edition"]["readable_asset"]["id"] == str(asset.pk)
        assert [row["chapter_title"] for row in data["outline"]] == [f"Chapter {title}"]
        assert {row["id"] for row in data["editions"]} == {str(first.pk), str(second.pk)}


@pytest.mark.django_db
def test_only_snapshot_slug_and_edition_uuid_resolve_not_draft_slug(api_client):
    work, edition, _ = publish()
    published_slug = edition.public_slug
    edition.public_slug = f"unpublished-{uuid4()}"
    edition.save(update_fields=["public_slug"])
    assert detail(api_client, published_slug).status_code == 200
    assert detail(api_client, str(edition.pk)).data["edition"]["id"] == str(edition.pk)
    assert detail(api_client, edition.public_slug).status_code == 404
    assert detail(api_client, str(work.pk)).status_code == 404


@pytest.mark.django_db
def test_metadata_only_secondary_version_has_no_primary_reader_or_outline(api_client):
    work, _, _ = publish(readable=True)
    _, secondary, _ = publish(work, primary=False)
    response = detail(api_client, secondary)
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    assert response.data["edition"]["availability"] == "metadata"
    assert response.data["edition"]["readable_asset"] is None and response.data["outline"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("access,validation", [("private", "valid"), ("registered", "valid"),
    ("restricted", "valid"), ("public", "invalid"), ("public", "pending")])
def test_public_detail_never_upgrades_reading_permissions_for_admin(api_client, admin_user, access, validation):
    _, edition, asset = publish(readable=True)
    asset.access_status, asset.validation_status = access, validation
    asset.save(update_fields=["access_status", "validation_status"])
    api_client.force_authenticate(admin_user)
    response = detail(api_client, edition)
    assert response.status_code == 200
    assert response.data["edition"]["readable_asset"] is None
    assert response.data["outline"] == []
    expected = "metadata" if access == "private" else access if validation == "valid" else "unavailable"
    assert response.data["edition"]["access_state"] == expected


@pytest.mark.django_db
@pytest.mark.parametrize("change", ["edition_withdrawn", "revision_withdrawn", "metadata_unready", "no_primary"])
def test_unpublished_or_withdrawn_state_is_not_a_detail_entry(api_client, change):
    work, first, _ = publish()
    _, selected, _ = publish(work, primary=False)
    if change == "edition_withdrawn":
        Edition.objects.filter(pk=selected.pk).update(state="withdrawn")
    elif change == "revision_withdrawn":
        CatalogPublicationRevision.objects.filter(pk=selected.active_catalog_revision_id).update(status="withdrawn")
    elif change == "metadata_unready":
        CatalogPublicationRevision.objects.filter(pk=selected.active_catalog_revision_id).update(metadata_ready=False)
    else:
        Edition.objects.filter(pk=first.pk).update(state="withdrawn")
    assert detail(api_client, selected).status_code == 404


@pytest.mark.django_db
def test_historical_omissions_do_not_fall_back_to_private_editorial_fields(api_client):
    work = Work.objects.create(title="Private draft title", subtitle="Private draft subtitle", original_title="Private original")
    edition = Edition.objects.create(work=work, state="published", is_primary=True, public_slug=f"synthetic-{uuid4()}",
        publisher="Private publisher")
    revision = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active",
        metadata_ready=True, snapshot={"work": {"id": str(work.pk), "title": "Historical title"},
            "edition": {"id": str(edition.pk), "public_slug": edition.public_slug}}, content_fingerprint="0" * 64)
    Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=revision)
    response = detail(api_client, edition)
    assert response.status_code == 200 and response.data["title"] == "Historical title"
    assert response.data["subtitle"] == "" and response.data["original_title"] == ""
    assert response.data["edition"]["publisher"] == ""
    assert "Private" not in str(response.data)


@pytest.mark.django_db
def test_selected_cover_reads_that_snapshot_and_rejects_other_work(api_client, monkeypatch):
    work, first, _ = publish(title="First", cover="synthetic/first.jpg")
    _, second, _ = publish(work, title="Second", primary=False, cover="synthetic/second.jpg")
    _, outsider, _ = publish(title="Outsider", cover="synthetic/outsider.jpg")
    storage = Work._meta.get_field("cover").storage
    monkeypatch.setattr(storage, "exists", lambda name: True)
    monkeypatch.setattr(storage, "open", lambda name, *args: BytesIO(name.encode()))
    for edition, expected in ((first, b"synthetic/first.jpg"), (second, b"synthetic/second.jpg")):
        response = detail(api_client, edition)
        assert f"edition_id={edition.pk}" in response.data["cover"]
        image = api_client.get(response.data["cover"])
        assert image.status_code == 200 and b"".join(image.streaming_content) == expected
        image.close()
    assert api_client.get(f"/api/catalog/works/{work.pk}/cover/?edition_id={outsider.pk}").status_code == 404
    Edition.objects.filter(pk=second.pk).update(state="withdrawn")
    assert api_client.get(f"/api/catalog/works/{work.pk}/cover/?edition_id={second.pk}").status_code == 404
