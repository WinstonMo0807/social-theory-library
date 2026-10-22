"""M18 acceptance definitions, intentionally not run during implementation."""
from uuid import uuid4

import pytest
from django.http import Http404
from catalog.models import CatalogPublicationRevision, KnowledgePublicationEvent
from catalog.services.publication_desk import desk, version
from catalog.services.publication_commands import PublicationCommandError, publication_history, rollback_revision
from .test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def test_desk_reads_saved_and_public_versions_without_writes():
    edition, active = published_edition("正式旧标题")
    edition.work.title = "未发布新标题"
    edition.work.save()
    result = desk(edition, selected_revision=active.pk)
    assert result["title"] == "未发布新标题"
    assert result["history"]["results"][0]["is_current"]
    title = next(row for row in result["preparation"]["changes"] if row["field"] == "title")
    assert title["before_display"] == "正式旧标题" and title["after_display"] == "未发布新标题"
    assert CatalogPublicationRevision.objects.filter(edition=edition).count() == 1
    assert not KnowledgePublicationEvent.objects.exists()
    assert set(result["dependencies"]["summary"]) == {"catalog_evidence", "reader_annotations", "reader_bookmarks", "reader_progress"}
    assert "owner" not in result["dependencies"] and "notes" not in result["dependencies"]


def test_history_is_paginated_and_selected_revision_cannot_cross_editions():
    edition, active = published_edition("当前作品")
    for number in range(2, 23):
        CatalogPublicationRevision.objects.create(edition=edition, revision=number, status="failed", metadata_ready=True, snapshot={"work": {"title": f"隔离修订{number}"}}, content_fingerprint=str(number)*10)
    first, second = desk(edition), desk(edition, page=2)
    assert first["history"]["count"] == 22 and first["history"]["pages"] == 2
    assert len(first["history"]["results"]) == 20 and len(second["history"]["results"]) == 2
    assert next(row for row in second["history"]["results"] if row["id"] == str(active.pk))["is_current"]
    _, unrelated = published_edition("其他作品")
    with pytest.raises(Http404):
        desk(edition, selected_revision=unrelated.pk)


def test_withdrawn_pointer_is_not_current_or_implicitly_restorable():
    edition, old = published_edition("撤回作品")
    edition.state = "withdrawn"
    edition.save(update_fields=["state", "updated_at"])
    result = desk(edition)
    assert result["publication"]["public_state"] == "withdrawn"
    assert not result["history"]["results"][0]["is_current"]
    assert not result["history"]["results"][0]["can_rollback"]
    assert not publication_history(edition)[0]["is_current"]
    assert not publication_history(edition)[0]["can_rollback"]


def test_stale_restore_cannot_create_a_revision(admin_user):
    edition, old = published_edition("恢复前公开内容")
    expected = version(edition)
    edition.work.title = "后来保存的标题"
    edition.work.save()
    with pytest.raises(PublicationCommandError, match="已经变化"):
        rollback_revision(edition, old.pk, actor=admin_user, idempotency_key="desk-stale", reason="隔离验收", expected_version=expected)
    assert not KnowledgePublicationEvent.objects.exists()


def test_restore_receipt_replays_before_cas_but_rejects_changed_reason(admin_user):
    edition, old = published_edition("需要恢复的正式内容")
    expected = version(edition)
    event = rollback_revision(edition, old.pk, actor=admin_user, idempotency_key="desk-replay", reason="隔离验收", expected_version=expected)
    repeated = rollback_revision(edition, old.pk, actor=admin_user, idempotency_key="desk-replay", reason="隔离验收", expected_version=expected)
    assert repeated.pk == event.pk and edition.catalog_revisions.count() == 2
    with pytest.raises(PublicationCommandError, match="其他恢复操作"):
        rollback_revision(edition, old.pk, actor=admin_user, idempotency_key="desk-replay", reason="不同原因", expected_version=expected)
    old.refresh_from_db()
    assert old.snapshot["work"]["title"] == "需要恢复的正式内容"


def test_desk_api_permissions_owner_page_and_foreign_revision(api_client, admin_user, reader_user):
    edition, old = published_edition("权限验收")
    url = f"/api/catalog/admin/editions/{edition.pk}/publication/history/"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url, {"view": "desk"}).status_code == 403
    api_client.force_authenticate(admin_user)
    response = api_client.get(url, {"view": "desk"})
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    assert api_client.get(url, {"view": "desk", "page": 99}).status_code == 400
    assert api_client.get(url, {"view": "desk", "revision": str(uuid4())}).status_code == 404
    assert api_client.get(url, {"view": "desk"}, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    assert api_client.post(f"/api/catalog/admin/knowledge-publications/{uuid4()}/retry/", {}, format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    assert isinstance(api_client.get(url).data, list)


def test_withdraw_stale_version_and_switched_owner_preserve_public_content(api_client, admin_user, reader_user):
    edition, old = published_edition("保留当前公开")
    expected = version(edition)
    edition.work.title = "新的保存内容"
    edition.work.save()
    url = f"/api/catalog/admin/library/works/{edition.work_id}/publication/"
    payload = {"edition_id": str(edition.pk), "action": "withdraw", "reason": "隔离验收", "expected_version": expected}
    api_client.force_authenticate(admin_user)
    assert api_client.post(url, payload, format="json").status_code == 409
    payload["expected_version"] = version(edition)
    assert api_client.post(url, payload, format="json", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    edition.refresh_from_db()
    assert edition.state == "published" and edition.active_catalog_revision_id == old.pk
    assert not KnowledgePublicationEvent.objects.exists()
