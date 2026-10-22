"""Saved-preview version acceptance definitions, not run during implementation."""
from hashlib import sha256
import json

import pytest
from django.core.serializers.json import DjangoJSONEncoder

from catalog.models import EditorialRevision
from catalog.services import knowledge_studio
from .test_editorial_edit_version_v306 import object_editor

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("kind,preview", [("scholars", "scholar"), ("topics", "topic"),
    ("disciplines", "discipline"), ("subdisciplines", "subdiscipline"),
    ("theory-system/nodes", "theory"), ("theory-system/reading-paths", "reading_path")])
def test_saved_preview_uses_the_unchanged_editor_version_formula(api_client, admin_user, kind, preview):
    row, detail, _field, target = object_editor(kind, False)
    api_client.force_authenticate(admin_user)
    old_formula = {"type": target, "id": row.pk, "updated_at": row.updated_at, "canonical": 0, "draft": None}
    if target == "scholar_profile":
        old_formula["person"] = [row.person_id, row.person.updated_at]
    expected = sha256(json.dumps(old_formula, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()
    assert api_client.get(detail).data["edit_version"] == expected
    response = api_client.get(f"/api/catalog/admin/knowledge-preview/{preview}/{row.pk}/", {"edit_version": expected}, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == 200 and response.data["edit_version"] == expected
    assert response["Cache-Control"] == "private, no-store"
    assert not EditorialRevision.objects.filter(target_id=row.pk).exists()


def test_saved_change_and_duplicate_versions_reject_the_old_preview(api_client, admin_user):
    row, detail, field, _ = object_editor("topics", False)
    api_client.force_authenticate(admin_user)
    expected = api_client.get(detail).data["edit_version"]
    url = f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/"
    assert api_client.get(url+f"?edit_version={expected}&edit_version={expected}").status_code == 409
    assert api_client.patch(detail, {field: "较新的草稿"}, format="json", HTTP_IF_MATCH=expected).status_code == 200
    response = api_client.get(url, {"edit_version": expected})
    assert response.status_code == 409 and response.data["code"] == "preview_changed"
    assert "perspective" not in response.data


def test_change_during_projection_returns_conflict_instead_of_mixed_preview(api_client, admin_user, monkeypatch):
    row, detail, _field, _ = object_editor("topics", False)
    api_client.force_authenticate(admin_user)
    expected = api_client.get(detail).data["edit_version"]
    original = knowledge_studio.knowledge_object_preview_payload
    def change_during_preview(**kwargs):
        payload = original(**kwargs)
        row.description = "模拟另一入口稍后保存"
        row.save()
        return payload
    monkeypatch.setattr(knowledge_studio, "knowledge_object_preview_payload", change_during_preview)
    response = api_client.get(f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/", {"edit_version": expected})
    assert response.status_code == 409 and "perspective" not in response.data


def test_unsaved_topic_override_accepts_saved_version_without_mutating_record(api_client, admin_user):
    row, detail, _field, _ = object_editor("topics", False)
    api_client.force_authenticate(admin_user)
    expected = api_client.get(detail).data["edit_version"]
    url = f"/api/catalog/admin/knowledge-preview/topic/{row.pk}/?edit_version={expected}"
    response = api_client.post(url, {"parent": None, "curation": {}}, format="json")
    assert response.status_code == 200 and response.data["edit_version"] == expected
    assert api_client.get(detail).data["edit_version"] == expected
    assert not EditorialRevision.objects.filter(target_id=row.pk).exists()
    assert api_client.post(url+"&unknown=1", {}, format="json").status_code == 400
