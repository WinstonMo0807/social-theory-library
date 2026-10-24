"""M24 read-only preview acceptance definitions; not executed during development."""
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from catalog.editorial_read import current_editorial_version
from catalog.models import EditorialRevision, KnowledgeNode, ReadingPath, ReadingPathItem, ReadingPathStage
from catalog.services.reading_paths import reading_path_stage_groups
from .test_reading_paths_20261021 import path_with_items, source

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/theory-system/reading-paths/preview/"


def body(path=None):
    return {"path_id": str(path.pk) if path else None,
        "edit_version": current_editorial_version("reading_path", path.pk) if path else "",
        "title": "合成未保存路线", "slug": "unsaved-synthetic-path", "introduction": "", "learning_goal": "",
        "audience": "", "difficulty": "beginner", "estimated_reading": "", "primary_discipline": None,
        "stage_groups": reading_path_stage_groups(path) if path else []}


def request(user, payload):
    client = APIClient(); client.force_authenticate(user=user)
    return client.post(URL, payload, format="json", HTTP_X_EDITOR_OWNER=str(user.pk))


def test_new_unsaved_selection_uses_exact_public_source_without_any_path_write(admin_user):
    work, edition, asset, catalog = source()
    material = str(uuid4()); payload = body()
    payload["stage_groups"] = [{"id": str(uuid4()), "name": "合成阶段", "items": [{"id": material,
        "work": str(work.pk), "edition": str(edition.pk), "asset": str(asset.pk),
        "document_revision": str(catalog.document_revision_id), "page_start": 2, "page_end": 2,
        "editorial_note": "编辑备注不可公开", "learning_goal": "合成材料目标"}]}]
    before = (ReadingPath.objects.count(), ReadingPathStage.objects.count(), ReadingPathItem.objects.count(), EditorialRevision.objects.count())
    response = request(admin_user, payload)
    assert response.status_code == 200
    item = response.data["items"][0]
    assert item["id"] == material and item["reader_url"].endswith(f"page=2&revision={catalog.document_revision_id}")
    assert "编辑备注不可公开" not in str(response.data)
    assert response.data["slug"] == payload["slug"] and response["Cache-Control"] == "private, no-store"
    assert before == (ReadingPath.objects.count(), ReadingPathStage.objects.count(), ReadingPathItem.objects.count(), EditorialRevision.objects.count())


def test_preview_checks_saved_version_owner_and_foreign_material_identity(admin_user):
    path, _, _, _ = path_with_items(); payload = body(path)
    payload["edit_version"] = "obsolete"
    assert request(admin_user, payload).status_code == 409
    client = APIClient(); client.force_authenticate(user=admin_user)
    assert client.post(URL, body(path), format="json", HTTP_X_EDITOR_OWNER=str(uuid4())).status_code == 403
    payload = body(); payload["stage_groups"] = reading_path_stage_groups(path)
    assert request(admin_user, payload).status_code == 400
    assert APIClient().post(URL, body(), format="json").status_code in (401, 403)


def test_hidden_and_withdrawn_sources_remain_truthful_and_empty_selection_is_allowed(admin_user):
    payload = body(); assert request(admin_user, payload).data["items"] == []
    node = KnowledgeNode.objects.create(canonical_name_zh="草稿题名不可公开", slug=f"preview-{uuid4()}", status="draft")
    payload["stage_groups"] = [{"name": "合成阶段", "items": [{"node": str(node.pk), "recommendation_reason": "私人草稿理由"}]}]
    response = request(admin_user, payload)
    assert response.status_code == 200 and response.data["items"][0]["source_status"] == "unavailable"
    assert all(text not in str(response.data) for text in ("草稿题名不可公开", "私人草稿理由"))
    payload["stage_groups"][0]["items"] *= 601
    assert request(admin_user, payload).status_code == 400
