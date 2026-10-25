"""Deferred merge-scope/receipt/recovery definitions; not executed in development."""
from uuid import uuid4

import pytest
from rest_framework.exceptions import PermissionDenied

from accounts.models import User
from catalog.models import EditorialRevision, KnowledgeNode, KnowledgeNodeMergeRecord, KnowledgeRelation
from catalog.services import knowledge_merge_commands as service, knowledge_nodes
from catalog.services.person_authority import AuthorityConflict
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def pair(settings, monkeypatch):
    settings.THEORY_SYSTEM_ENABLED = True
    # These definitions exercise original row changes, not real publication jobs.
    monkeypatch.setattr(knowledge_nodes, "record_admin_canonical_change", lambda **kwargs: None)
    monkeypatch.setattr(knowledge_nodes, "_publish_merged_work_metadata", lambda *args, **kwargs: None)
    return tuple(KnowledgeNode.objects.create(node_type="concept", canonical_name_zh=name,
        slug=f"node-merge-{uuid4()}", status="published") for name in ("合成来源概念", "合成保留概念"))


def command(pair, user, request_id=None):
    source, target = pair
    state = service.preview(source, target)
    return dict(actor=user, request_id=request_id or uuid4(), fingerprint=state["fingerprint"], confirmed=True)


def headers(user, request_id=None):
    return {"HTTP_X_EDITOR_OWNER": str(user.pk), "HTTP_IDEMPOTENCY_KEY": str(request_id or uuid4())}


def test_original_merge_is_recoverable_and_replays_without_duplicate_changes(pair, superadmin_user, api_client):
    source, target = pair
    data = command(pair, superadmin_user)
    record = service.merge(source.pk, target.pk, **data)
    assert service.merge(source.pk, target.pk, **data).pk == record.pk
    assert KnowledgeNodeMergeRecord.objects.count() == 1
    source.refresh_from_db(); target.refresh_from_db()
    assert source.status == "archived" and target.status == "published"
    assert target.aliases.filter(alias=source.canonical_name_zh).count() == 1
    with pytest.raises(AuthorityConflict):
        service.merge(source.pk, target.pk, **{**data, "change_note": "另一项操作"})
    api_client.force_authenticate(superadmin_user)
    receipt = api_client.get(f"/api/catalog/admin/theory-system/merges/commands/{data['request_id']}/", **headers(superadmin_user))
    assert receipt.data["node_merge_id"] == str(record.pk) and receipt.data["state"] == "applied"
    history = api_client.get(f"/api/catalog/admin/theory-system/nodes/{source.pk}/merges/", **headers(superadmin_user))
    assert history.data["count"] == 1 and history.data["results"][0]["id"] == str(record.pk)


def test_changed_scope_rejects_confirmation_without_changes(pair, superadmin_user):
    source, target = pair
    data = command(pair, superadmin_user)
    target.summary = "另一管理员后续保存的说明"
    target.save(update_fields=["summary", "updated_at"])
    with pytest.raises(AuthorityConflict):
        service.merge(source.pk, target.pk, **data)
    source.refresh_from_db()
    assert source.status == "published" and not KnowledgeNodeMergeRecord.objects.exists()
    assert not AuditEvent.objects.filter(pk=data["request_id"]).exists()


def test_merge_preview_retains_relation_drafts_and_distinguishes_node_types(pair, superadmin_user):
    source, target = pair
    relation = KnowledgeRelation.objects.create(source_node=source, target_node=target, relation_type="related", status="pending")
    EditorialRevision.objects.create(target_type="knowledge_relation", target_id=relation.pk, revision=1,
        idempotency_key=f"synthetic-{uuid4()}", patch={"description": "未发布关系修改"})
    assert not service.preview(source, target)["can_merge"]
    target.node_type = "theory"
    target.save(update_fields=["node_type", "updated_at"])
    assert any("类型不同" in row for row in service.preview(source, target)["blockers"])
    with pytest.raises(AuthorityConflict):
        service.merge(source.pk, target.pk, **command(pair, superadmin_user))
    assert KnowledgeRelation.objects.get(pk=relation.pk).status == "pending"


def test_cancelled_request_and_old_payload_cannot_merge(pair, superadmin_user, api_client):
    source, target = pair
    api_client.force_authenticate(superadmin_user)
    data = command(pair, superadmin_user)
    url = f"/api/catalog/admin/theory-system/nodes/{source.pk}/merge/"
    receipt_url = f"/api/catalog/admin/theory-system/merges/commands/{data['request_id']}/"
    assert api_client.post(receipt_url, {"action": "cancel_pending"}, format="json", **headers(superadmin_user)).data["state"] == "cancelled"
    payload = {"target_node": str(target.pk), "fingerprint": data["fingerprint"], "confirmed": True}
    assert api_client.post(url, payload, format="json", **headers(superadmin_user, data["request_id"])).status_code == 409
    assert api_client.post(url, {"target_node": str(target.pk)}, format="json", **headers(superadmin_user)).status_code == 400
    assert not KnowledgeNodeMergeRecord.objects.exists()


def test_reader_admin_owner_header_and_revoked_session_boundaries(pair, superadmin_user, admin_user, reader_user, api_client):
    source, target = pair
    url = f"/api/catalog/admin/theory-system/nodes/{source.pk}/merge-preview/?target_node={target.pk}"
    for user in (reader_user, admin_user):
        api_client.force_authenticate(user)
        assert api_client.get(url, **headers(user)).status_code == 403
    api_client.force_authenticate(superadmin_user)
    assert api_client.get(url, **headers(reader_user)).status_code == 403
    assert api_client.get(url).status_code == 403
    data = command(pair, superadmin_user)
    User.objects.filter(pk=superadmin_user.pk).update(token_version=superadmin_user.token_version + 1)
    with pytest.raises(PermissionDenied):
        service.merge(source.pk, target.pk, **data)
    assert not KnowledgeNodeMergeRecord.objects.exists()


def test_rollback_preserves_later_edits_and_repeated_restore_is_safe(pair, superadmin_user):
    source, target = pair
    record = service.merge(source.pk, target.pk, **command(pair, superadmin_user))
    state = service.rollback_state(record)
    assert state["can_rollback"]
    restored = service.rollback(record.pk, actor=superadmin_user, fingerprint=state["fingerprint"], confirmed=True)
    assert service.rollback(record.pk, actor=superadmin_user, fingerprint=state["fingerprint"], confirmed=True).pk == restored.pk
    source.refresh_from_db(); target.refresh_from_db()
    assert source.status == "published" and not target.aliases.filter(alias=source.canonical_name_zh).exists()
    again = service.merge(source.pk, target.pk, **command(pair, superadmin_user))
    state = service.rollback_state(again)
    target.summary = "合并后新增说明"
    target.save(update_fields=["summary", "updated_at"])
    assert not service.rollback_state(again)["can_rollback"]
    with pytest.raises(AuthorityConflict):
        service.rollback(again.pk, actor=superadmin_user, fingerprint=state["fingerprint"], confirmed=True)
    target.refresh_from_db()
    assert target.summary == "合并后新增说明"
