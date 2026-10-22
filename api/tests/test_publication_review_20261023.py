"""PDF 136 acceptance definitions. Do not run until unified acceptance."""
import pytest
from catalog.models import CatalogPublicationRevision, Edition, KnowledgePublicationEvent, Person
from catalog.services.publication_desk import desk, review_details, version
from .test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def test_review_reads_current_revision_even_when_it_is_not_on_first_history_page():
    edition, active = published_edition("隔离发布检查")
    for number in range(2, 23):
        CatalogPublicationRevision.objects.create(edition=edition, revision=number, status="failed", metadata_ready=False, snapshot={}, content_fingerprint=str(number)*10)
    result = desk(edition, include_review=True)
    assert str(active.pk) not in [row["id"] for row in result["history"]["results"]]
    assert result["review"]["current"]["id"] == str(active.pk)
    assert edition.catalog_revisions.count() == 22
    assert not KnowledgePublicationEvent.objects.exists()


def test_bibliography_checks_do_not_claim_pdf_ocr_or_pages_are_complete():
    edition, _ = published_edition("隔离纯书目")
    edition.publication_mode = Edition.PublicationMode.BIBLIOGRAPHIC
    edition.save()
    result = desk(edition, include_review=True)
    checks = {row["key"]: row for row in result["review"]["checks"]}
    assert all(checks[key]["state"] == "notice" for key in ("file", "ocr", "pages"))
    assert result["review"]["page_count_after"] is None
    assert not KnowledgePublicationEvent.objects.exists()


def test_relations_use_object_identity_for_added_removed_and_unchanged():
    edition, _ = published_edition("隔离关联")
    before = Person.objects.create(preferred_name="原作者")
    after = Person.objects.create(preferred_name="新增作者")
    result = review_details(edition, {"changes": [{"field": "authors", "before": [str(before.pk)], "after": [str(after.pk)]}]})
    people = next(row for row in result["relations"] if row["field"] == "authors")
    assert people["count"] == 1
    assert {(row["label"], row["change"]) for row in people["items"]} == {("原作者", "removed"), ("新增作者", "added")}


def test_preview_rejects_stale_version_and_missing_or_stale_fingerprint(api_client, admin_user):
    edition, _ = published_edition("隔离版本绑定")
    result = desk(edition, include_review=True)
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/page-preview/editions/{edition.pk}/"
    assert api_client.get(url, {"version": result["version"]}).status_code == 409
    assert api_client.get(url, {"version": result["version"], "fingerprint": "0"*64}).status_code == 409
    edition.work.title = "已被另一编辑保存"
    edition.work.save()
    assert api_client.get(url, {"version": result["version"], "fingerprint": result["preparation"]["fingerprint"]}).status_code == 409
    assert not KnowledgePublicationEvent.objects.exists()


def test_review_and_preview_keep_owner_and_backoffice_boundaries(api_client, admin_user, reader_user):
    edition, _ = published_edition("隔离权限")
    history = f"/api/catalog/admin/editions/{edition.pk}/publication/history/?view=review"
    preview = f"/api/catalog/admin/page-preview/editions/{edition.pk}/"
    api_client.force_authenticate(reader_user)
    assert api_client.get(history).status_code == 403
    assert api_client.get(preview).status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.get(preview, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    assert api_client.get(history, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    response = api_client.get(history, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["review"]
    assert "no-store" in response["Cache-Control"]
    assert not KnowledgePublicationEvent.objects.exists()


def test_preview_returns_the_same_saved_edition_without_publishing(api_client, admin_user):
    edition, active = published_edition("隔离当前预览")
    result = desk(edition, include_review=True)
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"/api/catalog/admin/page-preview/editions/{edition.pk}/", {"version": version(edition), "fingerprint": result["preparation"]["fingerprint"]}, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200
    assert str(response.data["work"]["edition"]["id"]) == str(edition.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == active.pk
    assert not KnowledgePublicationEvent.objects.exists()


def test_preview_uses_saved_edition_values_while_public_detail_keeps_its_snapshot(api_client, admin_user):
    from catalog.serializers import EditionCompactSerializer
    edition, active = published_edition("隔离出版信息")
    active.snapshot["edition"] = {"publisher": "旧出版社", "version_label": "旧出版版", "publication_year": 2001}
    active.save()
    edition.publisher, edition.version_label, edition.publication_year = "新出版社", "已保存新版", 2026
    edition.publication_mode = Edition.PublicationMode.BIBLIOGRAPHIC
    edition.save()
    edition.refresh_from_db()
    public = EditionCompactSerializer(edition).data
    assert public["publisher"] == "旧出版社" and public["publication_year"] == 2001
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"/api/catalog/admin/page-preview/editions/{edition.pk}/")
    assert response.status_code == 200
    saved = response.data["work"]["edition"]
    assert saved["publisher"] == "新出版社" and saved["publication_year"] == 2026
    assert saved["version_label"] == "已保存新版" and saved["readable_asset"] is None
    assert response.data["pdf_preview_url"] == "" and response.data["work"]["outline"] == []
    assert not KnowledgePublicationEvent.objects.exists()
