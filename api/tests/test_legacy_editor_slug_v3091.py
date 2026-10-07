import pytest

from catalog.models import Work
from .editorial_fixtures import editorial_request
from .test_editorial_edit_version_v306 import object_editor

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("kind", ["scholars", "topics", "disciplines", "subdisciplines", "theory-system/nodes"])
def test_existing_unicode_address_survives_editing_without_rewriting_published_content(
    api_client, admin_user, kind, published,
):
    row, url, field, _target = object_editor(kind, published)
    row.slug = "原有地址"
    row.save(update_fields=["slug"])
    api_client.force_authenticate(admin_user)
    saved = editorial_request(api_client, "patch", url, {"slug": row.slug, field: "保存后的内容"}, format="json")
    assert saved.status_code == (202 if published else 200), saved.data
    loaded = api_client.get(url)
    assert loaded.data["slug"] == "原有地址"
    assert loaded.data[field] == "保存后的内容"
    row.refresh_from_db()
    assert row.slug == "原有地址"
    assert getattr(row, field) == ("旧内容" if published else "保存后的内容")


def test_scholar_can_save_a_selected_library_work_with_its_legacy_address(api_client, admin_user):
    row, url, _field, _target = object_editor("scholars", False)
    row.slug = "w德斯科特"
    row.save(update_fields=["slug"])
    work = Work.objects.create(title="馆藏选择回归", document_type="book")
    api_client.force_authenticate(admin_user)
    selected = [str(work.pk)]
    saved = editorial_request(api_client, "patch", url, {"slug": row.slug, "curation": {"essential_work_ids": selected}}, format="json")
    assert saved.status_code == 200, saved.data
    assert api_client.get(url).data["curation"]["essential_work_ids"] == selected
    row.refresh_from_db()
    assert row.slug == "w德斯科特" and row.curation["essential_work_ids"] == selected
    assert row.editorial_status == "draft"


@pytest.mark.parametrize("slug", ["另一中文地址", "bad/slug", "bad slug", "bad?slug"])
def test_legacy_address_preservation_does_not_accept_a_new_invalid_address(api_client, admin_user, slug):
    row, url, field, _target = object_editor("scholars", False)
    row.slug = "w德斯科特"
    row.save(update_fields=["slug"])
    api_client.force_authenticate(admin_user)
    rejected = editorial_request(api_client, "patch", url, {"slug": slug, field: "不能写入"}, format="json")
    assert rejected.status_code == 400
    row.refresh_from_db()
    assert row.slug == "w德斯科特" and getattr(row, field) == "旧内容"


def test_legacy_address_does_not_bypass_revision_or_reader_permission(api_client, admin_user, reader_user):
    row, url, field, _target = object_editor("scholars", False)
    row.slug = "w德斯科特"
    row.save(update_fields=["slug"])
    body = {"slug": row.slug, field: "禁止覆盖"}
    api_client.force_authenticate(admin_user)
    assert api_client.patch(url, body, format="json").status_code == 428
    api_client.force_authenticate(reader_user)
    assert api_client.patch(url, body, format="json", HTTP_IF_MATCH="*").status_code == 403
    row.refresh_from_db()
    assert row.slug == "w德斯科特" and getattr(row, field) == "旧内容"
