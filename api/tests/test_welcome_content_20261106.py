"""Focused welcome publication check, using an isolated database and synthetic book."""
from uuid import uuid4

import pytest
from catalog.models import CatalogPublicationRevision, Edition, SiteSetting, Work
from catalog.services import editorial_issues as ledger
from catalog.site_publication_review import review
from catalog.views import current_site_config
from catalog.welcome import WelcomeConfigSerializer


@pytest.mark.django_db
def test_welcome_draft_publication_and_withdrawal(api_client, admin_user, reader_user):
    work = Work.objects.create(title="草稿题名不得公开", document_type="book")
    edition = Edition.objects.create(work=work, version_label="合成版本", state="published", public_slug="welcome-check")
    publication = CatalogPublicationRevision.objects.create(edition=edition, revision=1, status="active", metadata_ready=True,
        snapshot={"work": {"title": "公开合成题名"}, "edition": {"version_label": "合成版本"}}, content_fingerprint=str(uuid4()))
    edition.active_catalog_revision = publication
    edition.save(update_fields=["active_catalog_revision"])
    SiteSetting.objects.update_or_create(key="site_config", defaults={"value": {"site_name": "合成书库"}, "public": True})
    payload = ledger.site_payload()
    payload["config"]["welcome"] = {"texts": {"history_title": "新的欢迎文字"}, "edition_ids": [str(edition.pk)]}
    payload["config"]["welcome_books"] = [{"title": "不能写入的伪造元数据"}]
    saved = ledger.save_site(payload, admin_user)
    assert saved["config"]["welcome_books"][0]["title"] == "公开合成题名"
    assert "welcome" not in current_site_config()
    checked = review(saved["edit_version"])
    assert checked["can_publish"] and any(row["label"] == "欢迎页展示书籍与顺序" for row in checked["changes"])
    ledger.publish_site(saved["edit_version"], admin_user)
    public = api_client.get("/api/catalog/site-config/")
    assert public.status_code == 200
    assert public.data["welcome"]["texts"]["history_title"] == "新的欢迎文字"
    assert public.data["welcome_books"][0]["id"] == str(edition.pk)
    # A published page reference does not keep a withdrawn edition public.
    edition.state = "draft"
    edition.save(update_fields=["state"])
    assert current_site_config()["welcome_books"] == []
    saved = ledger.save_site(ledger.site_payload(), admin_user)
    assert saved["config"]["welcome_books"][0]["available"] is False
    assert not review(saved["edit_version"])["can_publish"]
    api_client.force_authenticate(reader_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get("/api/catalog/admin/site-content/").status_code == 403
    assert not WelcomeConfigSerializer(data={"edition_ids": [str(edition.pk)] * 2}).is_valid()
    assert not WelcomeConfigSerializer(data={"texts": {"history_subjects": "社会学、政治学、人类学、其他"}}).is_valid()
