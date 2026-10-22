"""M18 acceptance definitions; execution deferred to unified acceptance."""
from uuid import uuid4
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.editorial_read import current_editorial_version
from catalog.models import EditorialRevision, KnowledgePublicationEvent
from catalog.services.editorial_revision import create_editorial_revision, editorial_target_snapshot
from .test_editorial_edit_version_v306 import object_editor

pytestmark = pytest.mark.django_db


def url(row, kind="topic"):
    return f"/api/catalog/admin/knowledge-publications/{kind}/{row.pk}/history/"


def command(row, target, **values):
    return {"action": "withdraw", "request_key": str(uuid4()), "expected_version": current_editorial_version(target, row.pk),
            "reason": "隔离验收中的明确操作说明", **values}


def historical(row, target, field):
    snapshot = editorial_target_snapshot(target_type=target, target=row)
    snapshot[field] = "历史保存内容"
    return EditorialRevision.objects.create(target_type=target, target_id=row.pk, base_revision=0, revision=1,
        patch={field: "历史保存内容"}, materialized_preview=snapshot, status="published", idempotency_key=str(uuid4()))


@pytest.mark.parametrize("kind,view", [("scholars", "scholar"), ("topics", "topic"), ("disciplines", "discipline"),
    ("subdisciplines", "subdiscipline"), ("theory-system/nodes", "theory"), ("theory-system/reading-paths", "reading_path")])
def test_history_is_private_read_only_and_does_not_invent_versions(api_client, admin_user, kind, view):
    row, _, _, _ = object_editor(kind, True)
    api_client.force_authenticate(admin_user)
    with CaptureQueriesContext(connection) as queries:
        response = api_client.get(url(row, view))
    assert response.status_code == 200, response.data
    assert response["Cache-Control"] == "private, no-store"
    assert response.data["history"]["count"] == 0 and response.data["selected"] is None
    assert response.data["is_public"] and response.data["can_withdraw"]
    assert all(not query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for query in queries)


def test_withdrawal_is_a_draft_and_same_request_recovers_before_version_check(api_client, admin_user):
    row, _, _, target = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    body = command(row, target)
    first = api_client.post(url(row), body, format="json")
    assert first.status_code == 202, first.data
    again = api_client.post(url(row), body, format="json")
    assert again.status_code == 202 and again.data["revision_id"] == first.data["revision_id"]
    assert first.data["edit_version"] != body["expected_version"]
    draft = EditorialRevision.objects.get(pk=first.data["revision_id"])
    row.refresh_from_db()
    assert draft.patch == {"editorial_status": "archived"} and draft.status == "draft"
    assert row.editorial_status == "published" and EditorialRevision.objects.filter(target_id=row.pk).count() == 1
    assert not KnowledgePublicationEvent.objects.filter(object_id=row.pk).exists()
    changed = api_client.post(url(row), {**body, "reason": "另一项意图"}, format="json")
    assert changed.status_code == 409


def test_restore_preserves_original_and_creates_only_an_editable_draft(api_client, admin_user):
    row, detail, field, target = object_editor("topics", True)
    source = historical(row, target, field)
    row.editorial_status = "archived"; row.save()
    api_client.force_authenticate(admin_user)
    body = command(row, target, action="restore", source_revision_id=str(source.pk))
    response = api_client.post(url(row), body, format="json")
    assert response.status_code == 202, response.data
    row.refresh_from_db(); source.refresh_from_db()
    assert row.description == "旧内容" and row.editorial_status == "archived" and source.status == "published"
    restored = EditorialRevision.objects.get(pk=response.data["revision_id"])
    assert restored.patch[field] == "历史保存内容" and restored.patch["editorial_status"] == "published"
    saved = api_client.get(detail)
    assert saved.data[field] == "历史保存内容" and saved.data["editorial_revision"]["id"] == str(restored.pk)
    changed = api_client.patch(detail, {field: "恢复后进一步修正"}, format="json", HTTP_IF_MATCH=saved.data["edit_version"])
    assert changed.status_code == 202
    row.refresh_from_db(); assert row.description == "旧内容"


def test_pending_manual_draft_and_stale_version_are_never_overwritten(api_client, admin_user):
    row, _, field, target = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    stale = command(row, target)
    draft = create_editorial_revision(target_type=target, target_id=row.pk, patch={field: "人工保存"}, actor=admin_user, idempotency_key=str(uuid4()))
    assert api_client.post(url(row), stale, format="json").status_code == 409
    assert api_client.post(url(row), command(row, target), format="json").status_code == 409
    draft.refresh_from_db()
    assert draft.status == "draft" and draft.patch[field] == "人工保存"
    assert EditorialRevision.objects.filter(target_id=row.pk).count() == 1


def test_history_selection_is_scoped_and_paginated(api_client, admin_user):
    row, _, field, target = object_editor("topics", True)
    source = historical(row, target, field)
    for number in range(2, 23):
        EditorialRevision.objects.create(target_type=target, target_id=row.pk, base_revision=0, revision=number,
            patch={field: str(number)}, materialized_preview={field: str(number)}, status="superseded", idempotency_key=str(uuid4()))
    api_client.force_authenticate(admin_user)
    response = api_client.get(url(row), {"page": 2, "selected": str(source.pk)})
    assert response.status_code == 200 and response.data["history"]["count"] == 22
    assert len(response.data["history"]["results"]) == 2 and response.data["selected"]["id"] == str(source.pk)
    assert any(item["field"] == field and item["after"] == "历史保存内容" for item in response.data["changes"])
    assert api_client.get(url(row), {"selected": str(uuid4())}).status_code == 404
    assert api_client.get(url(row), {"page": 99}).status_code == 404


def test_foreign_superseded_and_withdrawal_revisions_cannot_restore(api_client, admin_user):
    row, _, field, target = object_editor("topics", True)
    source = historical(row, target, field)
    api_client.force_authenticate(admin_user)
    assert api_client.post(url(row), command(row, target, action="restore", source_revision_id=str(uuid4())), format="json").status_code == 400
    source.status = "superseded"; source.save()
    assert api_client.post(url(row), command(row, target, action="restore", source_revision_id=str(source.pk)), format="json").status_code == 400
    source.status = "published"; source.materialized_preview["editorial_status"] = "archived"; source.save()
    assert api_client.post(url(row), command(row, target, action="restore", source_revision_id=str(source.pk)), format="json").status_code == 400
    assert not EditorialRevision.objects.filter(target_id=row.pk, status="draft").exists()


def test_owner_reader_and_wrong_node_type_are_rejected(api_client, admin_user, reader_user):
    row, _, _, target = object_editor("topics", True)
    api_client.force_authenticate(admin_user)
    body = command(row, target)
    assert api_client.get(url(row), HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    assert api_client.post(url(row), body, format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    api_client.force_authenticate(reader_user)
    assert api_client.get(url(row)).status_code == 403
    assert api_client.post(url(row), body, format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    node, _, _, _ = object_editor("theory-system/nodes", True)
    assert api_client.get(url(node, "concept")).status_code == 404
