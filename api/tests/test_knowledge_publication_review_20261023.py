"""M17 acceptance definitions. Deliberately not run during implementation."""
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.models import CanonicalObjectRevision, EditorialRevision
from .test_editorial_edit_version_v306 import object_editor

pytestmark = pytest.mark.django_db


def review(api_client, row, detail, kind="topic", **extra):
    version = api_client.get(detail).data["edit_version"]
    return api_client.get(f"/api/catalog/admin/knowledge-preview/{kind}/{row.pk}/", {"edit_version": version, "review": "1", **extra})


@pytest.mark.parametrize("kind,preview", [("scholars", "scholar"), ("topics", "topic"),
    ("disciplines", "discipline"), ("subdisciplines", "subdiscipline"),
    ("theory-system/nodes", "theory"), ("theory-system/reading-paths", "reading_path")])
def test_review_uses_saved_public_projection_without_writes(api_client, admin_user, kind, preview):
    row, detail, _, _ = object_editor(kind, False)
    api_client.force_authenticate(admin_user)
    with CaptureQueriesContext(connection) as queries:
        response = review(api_client, row, detail, preview)
    assert response.status_code == 200, response.data
    report = response.data["publication_review"]
    assert report["has_draft"] and report["draft_revision_id"] is None
    assert response["Cache-Control"] == "private, no-store"
    assert report["actor_label"] and report["checked_at"]
    assert any(item["code"] == "source_review" for item in report["checks"])
    assert all(not item["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for item in queries)
    assert not EditorialRevision.objects.filter(target_id=row.pk).exists()


def test_review_requires_exact_saved_version_and_rejects_unsaved_overrides(api_client, admin_user):
    row, detail, _, _ = object_editor("topics", False)
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/"
    version = api_client.get(detail).data["edit_version"]
    assert api_client.get(url, {"review": "1"}).status_code == 400
    assert api_client.get(url, {"review": "true", "edit_version": version}).status_code == 400
    assert api_client.get(url+f"?review=1&review=1&edit_version={version}").status_code == 400
    assert review(api_client, row, detail, parent="").status_code == 400
    assert api_client.get(url, {"review": "1", "edit_version": "0"*64}).status_code == 409


def test_review_preserves_draft_changes_and_original_withdrawal(api_client, admin_user):
    row, detail, field, target = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    version = api_client.get(detail).data["edit_version"]
    saved = api_client.patch(detail, {field: "保存的新导读", "editorial_status": "archived"}, format="json", HTTP_IF_MATCH=version)
    assert saved.status_code == 202
    draft = EditorialRevision.objects.get(target_type=target, target_id=row.pk, status="draft")
    response = review(api_client, row, detail)
    report = response.data["publication_review"]
    assert report["withdrawing"] and report["draft_revision_id"] == str(draft.pk)
    assert any(item["after"].get("description") == "保存的新导读" and item["changed"] for item in report["changes"])
    draft.refresh_from_db(); row.refresh_from_db()
    assert draft.status == "draft" and row.editorial_status == "published" and row.description == "旧内容"


def test_revision_conflict_blocks_review_without_rebasing(api_client, admin_user):
    row, detail, field, target = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    version = api_client.get(detail).data["edit_version"]
    api_client.patch(detail, {field: "待检查导读"}, format="json", HTTP_IF_MATCH=version)
    draft = EditorialRevision.objects.get(target_id=row.pk, status="draft")
    CanonicalObjectRevision.objects.filter(object_type=target, object_id=row.pk).update(current_revision=draft.base_revision+1)
    report = review(api_client, row, detail).data["publication_review"]
    assert not report["can_publish"]
    assert any(item["code"] == "revision_conflict" and item["severity"] == "blocking" for item in report["checks"])
    draft.refresh_from_db()
    assert draft.base_revision != report["current_revision"]


def test_published_object_without_a_draft_is_read_only(api_client, admin_user):
    row, detail, _, _ = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    report = review(api_client, row, detail).data["publication_review"]
    assert not report["has_draft"] and not report["can_publish"]
    assert not any(item["changed"] for item in report["changes"])


def test_archived_person_cannot_be_silently_revived_by_scholar_review(api_client, admin_user):
    row, detail, _, _ = object_editor("scholars", False)
    row.person.authority_status = "archived"; row.person.save()
    api_client.force_authenticate(admin_user)
    report = review(api_client, row, detail, "scholar").data["publication_review"]
    assert not report["can_publish"]
    assert any(item["code"] == "person_unavailable" for item in report["checks"])
    row.person.refresh_from_db()
    assert row.person.authority_status == "archived"


def test_reader_and_changed_owner_cannot_obtain_review(api_client, admin_user, reader_user):
    row, detail, _, _ = object_editor("topics", False)
    api_client.force_authenticate(admin_user)
    version = api_client.get(detail).data["edit_version"]
    url = f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/?review=1&edit_version={version}"
    assert api_client.get(url, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403


def test_image_reminders_inspect_the_selected_immutable_metadata(api_client, admin_user, settings, tmp_path):
    from catalog.services.editorial_drafts import save_object_editorial_patch
    from catalog.services.knowledge_media import image_selection
    from catalog.services.media import ingest_image, build_rendition, update_media_metadata
    from .test_media_v305 import picture
    settings.MEDIA_ROOT = tmp_path
    row, detail, _, _ = object_editor("topics", True)
    asset, _ = ingest_image(picture(size=(1200, 800)), actor=admin_user, metadata={"alt_text": "隔离图片"})
    rendition = build_rendition(asset.pk, kind="hero", width=640)
    save_object_editorial_patch("topic", row.pk, {"image_selection": {**image_selection(row), "rendition_id": str(rendition.pk)}}, actor=admin_user)
    update_media_metadata(asset.pk, actor=admin_user, metadata={"source_label": "后来填写的出处", "license": "后来填写的许可", "credit": "后来填写的署名"})
    api_client.force_authenticate(admin_user)
    response = review(api_client, row, detail)
    assert response.status_code == 200, response.data
    assert any(item["code"] == "image_rights" and item["severity"] == "warning" for item in response.data["publication_review"]["checks"])
    rendition.refresh_from_db()
    assert not rendition.metadata_snapshot.get("license")
    assert EditorialRevision.objects.get(target_id=row.pk, status="draft").patch["image_selection"]["rendition_id"] == str(rendition.pk)
