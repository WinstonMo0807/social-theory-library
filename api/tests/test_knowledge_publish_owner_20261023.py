"""Knowledge publication acceptance definitions; run at unified acceptance only."""
import pytest

from catalog.models import EditorialRevision, KnowledgePublicationEvent
from .test_editorial_edit_version_v306 import object_editor

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind,preview", [
    ("scholars", "scholar"), ("topics", "topic"),
    ("disciplines", "discipline"), ("subdisciplines", "subdiscipline"),
    ("theory-system/nodes", "theory"), ("theory-system/reading-paths", "reading_path"),
])
def test_owner_header_rejects_cookie_switch_on_every_knowledge_editor(api_client, admin_user, reader_user, kind, preview):
    row, url, field, _target = object_editor(kind, True)
    api_client.force_authenticate(admin_user)
    before = api_client.get(url)
    assert before.status_code == 200  # Legacy callers without the header still work.
    headers = {"HTTP_X_EDITOR_OWNER": str(reader_user.pk)}
    assert api_client.get(url, **headers).status_code == 403
    assert api_client.get(f"/api/catalog/admin/knowledge-preview/{preview}/{row.pk}/", **headers).status_code == 403
    assert api_client.patch(url, {field: "不能以另一账户保存"}, format="json", HTTP_IF_MATCH=before.data["edit_version"], **headers).status_code == 403
    assert not EditorialRevision.objects.filter(target_id=row.pk).exists()
    row.refresh_from_db()
    assert getattr(row, field) == "旧内容"
    assert api_client.get(url, HTTP_X_EDITOR_OWNER=str(admin_user.pk)).data["edit_version"] == before.data["edit_version"]


def test_matching_owner_does_not_grant_reader_edit_or_publish_capability(api_client, reader_user):
    row, url, field, _ = object_editor("topics", True)
    api_client.force_authenticate(reader_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(reader_user.pk)}
    assert api_client.get(url, **headers).status_code == 403
    assert api_client.patch(url, {field: "无权限"}, format="json", HTTP_IF_MATCH="a"*64, **headers).status_code == 403
    assert api_client.post(f"/api/catalog/admin/editorial-revisions/{row.pk}/publish/", {}, format="json", **headers).status_code == 403


def test_original_revision_owner_and_replay_remain_bound(api_client, admin_user, reader_user):
    row, url, field, _ = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    version = api_client.get(url).data["edit_version"]
    saved = api_client.patch(url, {field: "新内容"}, format="json", HTTP_IF_MATCH=version, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert saved.status_code == 202
    revision = saved.data["editorial_revision"]
    assert revision["target_id"] == str(row.pk) and revision["target_type"] == "topic"
    detail = f"/api/catalog/admin/editorial-revisions/{revision['id']}/"
    publish = detail + "publish/"
    assert api_client.get(detail, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    assert api_client.post(publish, {}, format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    assert EditorialRevision.objects.get(pk=revision["id"]).status == "draft"
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    first = api_client.post(publish, {}, format="json", **headers)
    assert first.status_code == 200 and first.data["status"] == "published"
    event_count = KnowledgePublicationEvent.objects.count()
    replay = api_client.post(publish, {}, format="json", **headers)
    assert replay.status_code == 200 and replay.data["id"] == first.data["id"]
    assert KnowledgePublicationEvent.objects.count() == event_count
    row.refresh_from_db()
    assert row.description == "新内容"


def test_superseded_original_revision_cannot_publish_newer_unreviewed_changes(api_client, admin_user):
    row, url, field, _ = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    first = api_client.patch(url, {field: "检查过的内容"}, format="json", HTTP_IF_MATCH=api_client.get(url).data["edit_version"], **headers)
    second = api_client.patch(url, {field: "稍后保存的内容"}, format="json", HTTP_IF_MATCH=first.data["edit_version"], **headers)
    original = first.data["editorial_revision"]["id"]
    response = api_client.post(f"/api/catalog/admin/editorial-revisions/{original}/publish/", {}, format="json", **headers)
    assert response.status_code == 409
    assert EditorialRevision.objects.get(pk=second.data["editorial_revision"]["id"]).status == "draft"
    row.refresh_from_db()
    assert row.description == "旧内容"
