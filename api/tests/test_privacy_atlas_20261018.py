"""PDF 223–225 privacy operations. Authored for the later unified acceptance run."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, Throttled, ValidationError

from accounts.models import ReaderProfile
from catalog.discovery_models import DiscoverySearchSession
from reading import privacy, research
from reading.models import Annotation, ReaderDataOperation, ReaderSearchRecord, ReadingHistory, ResearchMemory, ResearchTurn
from reading.services import encrypt_private_text
from tests.test_confirmed_memory_atlas_20261018 import grant, memory_for, project_for
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def operation(user, kind="export", **kwargs):
    return privacy.create_operation(user, {"request_id": str(uuid4()), "kind": kind, **kwargs})


def erase(user, *memories):
    return operation(user, "erase", targets=[privacy.target_of(memory, "memories") for memory in memories])


def command(user, row, action):
    row.refresh_from_db()
    return privacy.command_operation(user, row.id, {"expected_revision": row.revision, "action": action})


def run(row):
    privacy.run_operation(row.id, row.generation, row.task_id)
    row.refresh_from_db()
    return privacy.operation_output(row)


def make_note(user):
    _, asset, spans, _ = fixture_source(count=1)
    note = Annotation.objects.create(user=user, asset=asset, page=spans[0].page, kind="note",
        body_ciphertext=encrypt_private_text("合成私人笔记"), quote=spans[0].original_text, asset_sha256=asset.sha256)
    return note, asset


def test_missing_profile_defaults_and_new_search_history_is_opt_in(reader_user):
    ReaderProfile.objects.filter(user=reader_user).delete()
    assert privacy.preferences(reader_user)["retention"] == privacy.RETENTION
    privacy.remember_search(reader_user, uuid4(), "未授权保存的检索", {})
    assert not ReaderSearchRecord.objects.filter(user=reader_user).exists()
    saved = privacy.update_preferences(reader_user, {"expected_revision": 1, "retention": {"search_history": True}})
    assert saved["retention"]["search_history"] is True
    session_id = uuid4()
    privacy.remember_search(reader_user, session_id, "主动保存的检索", {"languages": ["zh"]})
    privacy.remember_search(reader_user, session_id, "主动保存的检索", {"languages": ["zh"]})
    history = ReaderSearchRecord.objects.get(user=reader_user)
    assert research.unpack(history)["query"] == "主动保存的检索"
    assert "主动保存".encode() not in bytes(history.data_ciphertext)
    privacy.update_preferences(reader_user, {"expected_revision": saved["revision"], "retention": {"search_history": False}})
    privacy.remember_search(reader_user, uuid4(), "关闭后的检索", {})
    assert ReaderSearchRecord.objects.filter(user=reader_user).count() == 1


def test_preference_conflict_does_not_override_current_choices(reader_user):
    first = privacy.preferences(reader_user)
    privacy.update_preferences(reader_user, {"expected_revision": first["revision"], "retention": {"reading_history": False}})
    with pytest.raises(research.ResearchConflict):
        privacy.update_preferences(reader_user, {"expected_revision": first["revision"], "retention": {"reading_history": True}})
    with pytest.raises(ValidationError):
        privacy.update_preferences(reader_user, {"expected_revision": first["revision"] + 1, "retention": {"global_memory_use": True}})
    assert not privacy.preferences(reader_user)["retention"]["reading_history"]


def test_notes_off_blocks_new_note_but_preserves_existing_edit_and_replayed_create(reader_user):
    request_id = str(uuid4())
    body = {"request_id": request_id, "body": "原有私人认识"}
    existing = research.create_memory(reader_user, body)
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"], "retention": {"personal_notes": False}})
    with pytest.raises(ValidationError):
        research.create_memory(reader_user, {"request_id": str(uuid4()), "body": "尚未保存的输入"})
    assert research.create_memory(reader_user, body).id == existing.id
    updated = research.update_memory(reader_user, existing.id, {"expected_revision": existing.revision, "body": "保留现有编辑"})
    assert research.unpack(updated)["body"] == "保留现有编辑"


def test_reading_history_off_does_not_write_or_remove_previous_records(api_client, reader_user):
    _, asset, _, _ = fixture_source(count=1)
    old = ReadingHistory.objects.create(user=reader_user, asset=asset, page_index=1)
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"], "retention": {"reading_history": False}})
    api_client.force_authenticate(reader_user)
    response = api_client.post("/api/reading/history/", {"asset": str(asset.id), "page_index": 1, "session_seconds": 2}, format="json")
    assert response.status_code == 200 and response.data["recorded"] is False
    old.refresh_from_db()
    assert old.session_seconds == 0 and ReadingHistory.objects.filter(user=reader_user).count() == 1


def test_export_owner_idempotency_and_no_store(api_client, reader_user, admin_user):
    own, other = memory_for(reader_user), memory_for(admin_user)
    body = {"request_id": str(uuid4()), "kind": "export", "categories": ["notes"]}
    first = privacy.create_operation(reader_user, body)
    assert privacy.create_operation(reader_user, body).id == first.id
    with pytest.raises(research.ResearchConflict):
        privacy.create_operation(reader_user, {**body, "categories": ["plans"]})
    payload = research.unpack(first)
    assert [target["id"] for target in payload["targets"]] == [str(own.id)]
    assert str(other.id) not in str(payload)
    assert run(first)["completed"] == 1
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/privacy/operations/{first.id}/").status_code == 404
    assert api_client.get(f"/api/reading/privacy/operations/{first.id}/download/").status_code == 404
    api_client.force_authenticate(reader_user)
    response = api_client.get(f"/api/reading/privacy/operations/{first.id}/download/")
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert response.data["records"][0]["record"]["id"] == str(own.id)


def test_delete_preview_and_stale_revision_do_not_delete(reader_user):
    memory = memory_for(reader_user)
    job = erase(reader_user, memory)
    assert job.status == "preview" and ResearchMemory.objects.filter(pk=memory.id).exists()
    memory = research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, "body": "已经修改"})
    with pytest.raises(research.ResearchConflict):
        command(reader_user, job, "confirm")
    job.refresh_from_db()
    assert job.status == "preview" and research.unpack(memory)["body"] == "已经修改"


def test_worker_rechecks_each_revision_without_blocking_other_items(reader_user):
    first, second = memory_for(reader_user), memory_for(reader_user)
    job = command(reader_user, erase(reader_user, first, second), "confirm")
    research.update_memory(reader_user, first.id, {"expected_revision": first.revision, "body": "提交后修改"})
    result = run(job)
    assert result["status"] == "partial" and result["completed"] == result["failed"] == 1
    assert ResearchMemory.objects.filter(pk=first.id).exists() and not ResearchMemory.objects.filter(pk=second.id).exists()


def test_cancel_invalidates_late_worker_and_retry_requires_new_confirmation(reader_user):
    memory = memory_for(reader_user)
    job = command(reader_user, erase(reader_user, memory), "confirm")
    old_generation, old_task = job.generation, job.task_id
    command(reader_user, job, "cancel")
    privacy.run_operation(job.id, old_generation, old_task)
    assert ResearchMemory.objects.filter(pk=memory.id).exists()
    result = command(reader_user, job, "retry")
    assert result.status == "preview" and ResearchMemory.objects.filter(pk=memory.id).exists()
    assert run(command(reader_user, result, "confirm"))["completed"] == 1


def test_erasure_retry_records_missing_item_and_allows_remaining_preview(reader_user):
    first, second = memory_for(reader_user), memory_for(reader_user)
    job = command(reader_user, erase(reader_user, first, second), "cancel")
    research.delete_memory(reader_user, first.id, first.revision)
    retry = command(reader_user, job, "retry")
    output = privacy.operation_output(retry)
    assert retry.status == "preview" and len(output["preview"]) == 1
    assert output["failed"] == 1 and output["preview"][0]["id"] == str(second.id)
    assert run(command(reader_user, retry, "confirm"))["completed"] == 1
    assert not ResearchMemory.objects.filter(pk=second.id).exists()


def test_memory_erasure_revokes_scope_and_keeps_original_note_public_file_and_account(reader_user):
    note, asset = make_note(reader_user)
    memory = memory_for(reader_user, annotation_id=str(note.id))
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    password, role, user_id = reader_user.password, reader_user.role, reader_user.id
    result = run(command(reader_user, erase(reader_user, memory), "confirm"))
    assert result["completed"] == 1
    project.refresh_from_db()
    assert not research.unpack(project)["confirmed_memory_ids"]
    assert Annotation.objects.filter(pk=note.id).exists()
    assert type(asset).objects.filter(pk=asset.id).exists()
    reader_user.refresh_from_db()
    assert (reader_user.password, reader_user.role, reader_user.id) == (password, role, user_id)


@pytest.mark.parametrize("legacy", [False, True])
def test_original_note_erasure_revokes_related_scope_but_keeps_authored_memory(api_client, reader_user, legacy):
    note, _ = make_note(reader_user)
    memory = memory_for(reader_user, annotation_id=str(note.id))
    project = project_for(reader_user)
    memory = grant(reader_user, memory, project)
    if legacy:
        api_client.force_authenticate(reader_user)
        assert api_client.delete(f"/api/reading/annotations/{note.id}/").status_code == 204
    else:
        job = operation(reader_user, "erase", targets=[privacy.target_of(note, "annotations")])
        assert run(command(reader_user, job, "confirm"))["completed"] == 1
    memory.refresh_from_db()
    project.refresh_from_db()
    assert research.unpack(memory)["body"] == "制度与社会关系"
    assert research.serialize_record(memory, reader_user)["data"]["origin_note"]["available"] is False
    assert not research.unpack(project)["confirmed_memory_ids"]


def test_authorization_change_after_preview_requires_new_impact(reader_user):
    memory = memory_for(reader_user)
    project = project_for(reader_user)
    job = erase(reader_user, memory)
    grant(reader_user, memory, project)
    with pytest.raises(research.ResearchConflict):
        command(reader_user, job, "confirm")
    assert ResearchMemory.objects.filter(pk=memory.id).exists()


def test_download_revalidates_source_and_never_returns_withdrawn_quote(reader_user):
    note, asset = make_note(reader_user)
    job = operation(reader_user, categories=["notes"])
    assert run(job)["completed"] == 1
    asset.edition.active_catalog_revision.fulltext_ready = False
    asset.edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    output = privacy.download_operation(reader_user, job.id)
    assert output["records"][0]["record"]["quote"] == ""
    assert output["records"][0]["record"]["body_text"] == "合成私人笔记"
    assert output["records"][0]["record"]["source"]["source_status"] == "unavailable"


def test_changed_record_after_export_is_not_replaced_with_unreviewed_content(reader_user):
    memory = memory_for(reader_user)
    job = operation(reader_user, categories=["notes"])
    run(job)
    research.update_memory(reader_user, memory.id, {"expected_revision": memory.revision, "body": "导出准备后修改"})
    output = privacy.download_operation(reader_user, job.id)
    assert output["records"] == []
    assert output["unavailable_since_preparation"][0]["id"] == str(memory.id)


def test_export_download_rechecks_child_revision_after_serializing(reader_user, monkeypatch):
    project = project_for(reader_user)
    turn = ResearchTurn.objects.create(project=project, status="completed", data_ciphertext=research.pack({"references": []}))
    job = operation(reader_user, categories=["research"])
    assert run(job)["completed"] == 1
    original = privacy.export_item
    def changes_during_read(user, category, row):
        result = original(user, category, row)
        research.save_data(turn, {"references": [], "question": "并发修改的轮次"})
        return result
    monkeypatch.setattr(privacy, "export_item", changes_during_read)
    output = privacy.download_operation(reader_user, job.id)
    assert output["records"] == []
    assert output["unavailable_since_preparation"][0]["id"] == str(project.id)


def test_partial_export_retry_preserves_success_and_does_not_repeat_completed_items(reader_user, monkeypatch):
    first, second = memory_for(reader_user), memory_for(reader_user)
    original = privacy.export_item
    calls = []
    def unavailable(user, category, row):
        calls.append(str(row.id))
        if row.id == first.id:
            raise RuntimeError("synthetic unavailable source")
        return original(user, category, row)
    monkeypatch.setattr(privacy, "export_item", unavailable)
    job = operation(reader_user, categories=["notes"])
    assert run(job)["status"] == "partial"
    monkeypatch.setattr(privacy, "export_item", original)
    result = run(command(reader_user, job, "retry"))
    assert result["completed"] == 2 and result["failed"] == 0
    assert calls.count(str(second.id)) == 1


def test_export_limits_and_owner_admission_leave_content_untouched(reader_user, monkeypatch):
    memory = memory_for(reader_user)
    first = operation(reader_user, categories=["notes"])
    operation(reader_user, categories=["notes"])
    with pytest.raises(Throttled):
        operation(reader_user, categories=["notes"])
    monkeypatch.setattr(privacy, "MAX_DOWNLOAD_BYTES", 10)
    output = run(first)
    assert output["status"] == "failed" and output["results"][0]["error_code"] == "content_limit"
    assert ResearchMemory.objects.filter(pk=memory.id).exists()


def test_stale_task_can_recover_without_late_generation_writes(reader_user):
    memory_for(reader_user)
    job = operation(reader_user, categories=["notes"])
    old_generation, old_task = job.generation, job.task_id
    ReaderDataOperation.objects.filter(pk=job.id).update(updated_at=timezone.now() - timedelta(minutes=11))
    privacy.close_stale(reader_user)
    job.refresh_from_db()
    assert job.status == "failed"
    job = command(reader_user, job, "retry")
    privacy.run_operation(job.id, old_generation, old_task)
    job.refresh_from_db()
    assert job.status == "queued"
    assert run(job)["completed"] == 1


def test_search_history_delete_preserves_working_session(reader_user):
    session = DiscoverySearchSession.objects.create(owner=reader_user, token_hash="synthetic", query="仍需进行的检索",
        expires_at=timezone.now() + timedelta(hours=24))
    history = ReaderSearchRecord.objects.create(user=reader_user, request_id=session.id,
        data_ciphertext=research.pack({"query": "主动保存的检索", "filters": {}}))
    job = operation(reader_user, "erase", targets=[privacy.target_of(history, "search_history")])
    assert run(command(reader_user, job, "confirm"))["completed"] == 1
    assert DiscoverySearchSession.objects.filter(pk=session.id).exists()
    assert not ReaderSearchRecord.objects.filter(pk=history.id).exists()


def test_history_storage_failure_reports_warning_without_failing_query(reader_user, monkeypatch):
    session = DiscoverySearchSession.objects.create(owner=reader_user, token_hash="synthetic", query="可继续的检索",
        expires_at=timezone.now() + timedelta(hours=24))
    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic storage interruption")
    monkeypatch.setattr(privacy, "remember_search", unavailable)
    privacy.remember_search_after_commit(reader_user, session.id, session.query, {})
    session.refresh_from_db()
    assert session.status == "queued" and session.warnings[-1]["code"] == "history_not_saved"


def test_erase_context_lock_precedes_target_lock(reader_user, monkeypatch):
    memory = memory_for(reader_user)
    job = command(reader_user, erase(reader_user, memory), "confirm")
    contexts, verify = research.memory_contexts, privacy.verify_target
    order = []
    def tracked_contexts(user, *, lock=False):
        if lock:
            order.append("contexts")
        return contexts(user, lock=lock)
    def tracked_verify(user, target, *, lock=False):
        if lock:
            order.append("target")
        return verify(user, target, lock=lock)
    monkeypatch.setattr(research, "memory_contexts", tracked_contexts)
    monkeypatch.setattr(privacy, "verify_target", tracked_verify)
    assert run(job)["completed"] == 1
    assert order.index("contexts") < order.index("target")
