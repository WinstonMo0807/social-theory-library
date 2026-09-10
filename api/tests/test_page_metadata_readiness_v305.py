import pytest

from catalog.models import Asset, CatalogPublicationRevision, Edition, Page, TextBlock, Work
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


def page_fixture(access_status="public", *, fulltext_ready=False):
    work = Work.objects.create(title="页码可读但正文未激活", document_type="book", language="zh-CN")
    edition = Edition.objects.create(work=work, state="published", public_slug=f"page-{work.pk}")
    asset = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status=access_status, sha256=str(work.pk).replace("-", "") * 2, page_count=1,
    )
    page = Page.objects.create(
        asset=asset, index=1, width=595, height=842, printed_label="iv",
        label_source="manual", is_label_manual=True, text_source="ocr",
        text="尚未激活的 OCR 文字", normalized_text="尚未激活的 OCR 文字",
        chapter_title="尚未确认的章节",
    )
    TextBlock.objects.create(
        page=page, order=1, text="尚未激活的文本块",
        normalized_text="尚未激活的文本块", bbox=[10, 10, 100, 50],
    )
    activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=fulltext_ready)
    return edition, asset, page


def test_metadata_only_reader_exposes_page_labels_without_unpublished_text(api_client):
    _edition, asset, page = page_fixture()
    response = api_client.get(f"/api/catalog/assets/{asset.pk}/pages/1/")
    assert response.status_code == 200
    assert response.data["printed_label"] == "iv"
    assert response.data["citation_page_label"] == "iv"
    assert response.data["width"] == 595 and response.data["height"] == 842
    assert response.data["text_available"] is False
    assert response.data["text_source"] == "none"
    assert response.data["text"] == "" and response.data["blocks"] == [] and response.data["chapter_title"] == ""
    assert "尚未激活" not in str(response.data)
    assert api_client.get(f"/api/catalog/assets/{asset.pk}/search/", {"q": "OCR"}).status_code == 404
    page.refresh_from_db()
    assert page.text == "尚未激活的 OCR 文字" and page.blocks.count() == 1


def test_formal_fulltext_revision_restores_page_text_and_blocks(api_client):
    _edition, asset, page = page_fixture(fulltext_ready=True)
    response = api_client.get(f"/api/catalog/assets/{asset.pk}/pages/1/")
    assert response.status_code == 200 and response.data["text_available"] is True
    assert response.data["text"] == page.text and response.data["blocks"][0]["text"] == "尚未激活的文本块"
    assert response.data["chapter_title"] == page.chapter_title
    assert response.data["text_source"] == "ocr"


@pytest.mark.parametrize("access", ["registered", "restricted", "private"])
def test_page_metadata_keeps_file_permissions(api_client, reader_user, access):
    edition, asset, _page = page_fixture(access)
    endpoint = f"/api/catalog/assets/{asset.pk}/pages/1/"
    assert api_client.get(endpoint).status_code == 404
    api_client.force_authenticate(reader_user)
    assert api_client.get(endpoint).status_code == (200 if access == "registered" else 404)
    edition.state = "withdrawn"
    edition.save(update_fields=["state", "updated_at"])
    assert api_client.get(endpoint).status_code == 404


@pytest.mark.parametrize("ineligible", ["draft", "no_revision", "superseded", "other_edition"])
def test_page_metadata_requires_own_active_catalog_revision(api_client, ineligible):
    edition, asset, _page = page_fixture()
    if ineligible == "draft":
        edition.state = "draft"
        edition.save(update_fields=["state", "updated_at"])
    elif ineligible == "no_revision":
        edition.active_catalog_revision = None
        edition.save(update_fields=["active_catalog_revision", "updated_at"])
    elif ineligible == "superseded":
        CatalogPublicationRevision.objects.filter(pk=edition.active_catalog_revision_id).update(
            status=CatalogPublicationRevision.Status.SUPERSEDED,
        )
    else:
        other_edition, _other_asset, _other_page = page_fixture()
        edition.active_catalog_revision = other_edition.active_catalog_revision
        edition.save(update_fields=["active_catalog_revision", "updated_at"])
    assert api_client.get(f"/api/catalog/assets/{asset.pk}/pages/1/").status_code == 404


def test_unselected_asset_does_not_expose_page_metadata(api_client):
    edition, _selected, _page = page_fixture()
    unselected = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        access_status="public", sha256="a" * 64, version=2,
    )
    Page.objects.create(asset=unselected, index=1, text_source="none", printed_label="99")
    assert api_client.get(f"/api/catalog/assets/{unselected.pk}/pages/1/").status_code == 404


@pytest.mark.parametrize("fulltext_ready", [False, True])
def test_access_text_capability_matches_formal_page_content(api_client, settings, fulltext_ready):
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    edition, asset, _page = page_fixture(fulltext_ready=fulltext_ready)
    edition.ocr_status = "succeeded"
    edition.save(update_fields=["ocr_status", "updated_at"])
    access = api_client.get(f"/api/distribution/assets/{asset.pk}/access/")
    assert access.status_code == 200
    assert access.data["ocr_status"] == "succeeded"
    assert access.data["ocr_text_available"] is fulltext_ready
    page = api_client.get(f"/api/catalog/assets/{asset.pk}/pages/1/")
    assert page.data["text_available"] is fulltext_ready


def test_metadata_only_page_can_anchor_private_reader_records(api_client, reader_user, admin_user):
    _edition, asset, page = page_fixture()
    api_client.force_authenticate(reader_user)
    payload = api_client.get(f"/api/catalog/assets/{asset.pk}/pages/1/").data
    assert payload["text_available"] is False
    bookmark = api_client.post("/api/reading/bookmarks/", {
        "asset": str(asset.pk), "page": payload["page_id"], "label": payload["citation_page_label"],
    }, format="json")
    assert bookmark.status_code == 201, bookmark.data
    assert str(bookmark.data["page"]) == str(page.pk)
    annotation = api_client.post("/api/reading/annotations/", {
        "asset": str(asset.pk), "page": payload["page_id"], "kind": "note",
        "selector": {"page_index": 1, "bboxes": [[10, 10, 100, 50]]},
        "body": "只属于读者的页码笔记", "color": "yellow",
    }, format="json")
    assert annotation.status_code == 201, annotation.data
    assert annotation.data["body_text"] == "只属于读者的页码笔记"
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/bookmarks/{bookmark.data['id']}/").status_code == 404
    assert api_client.get(f"/api/reading/annotations/{annotation.data['id']}/").status_code == 404
