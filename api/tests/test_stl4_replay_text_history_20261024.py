"""Deferred encrypted manual-history, restore and privacy-export acceptance."""
from uuid import uuid4

import pytest

from reading import privacy, research, research_replay, research_replay_history
from reading.models import ResearchProject, ResearchTurn, ResearchReplayRevision

pytestmark = pytest.mark.django_db


def source(user):
    project = ResearchProject.objects.create(user=user, data_ciphertext=research.pack({"title": "合成研究"}))
    turn = ResearchTurn.objects.create(project=project, status="completed", data_ciphertext=research.pack({
        "question": "不可被恢复改写的原问题", "scope": {}, "selected_refs": [],
        "replay_title": "保存前名称", "replay_note": "保存前本人文字", "replay_tags": ["原标签"]}))
    return project, turn


def account(client, user):
    client.force_authenticate(user)
    client.credentials(HTTP_X_READER_OWNER=str(user.pk))


def test_edits_and_restoration_append_history_without_rewriting_original_inputs(reader_user):
    project, turn = source(reader_user)
    original = research.unpack(turn)
    command = {"expected_revision": 1, "title": "新版名称", "notes": "新版本人文字", "tags": ["新标签"]}
    result = research_replay.edit_turn(reader_user, project.pk, turn.pk, command)
    assert result["turn"]["revision"] == 2 and result["tags"] == ["新标签"]
    snapshots = list(turn.replay_revisions.order_by("revision"))
    assert len(snapshots) == 2 and snapshots[0].kind == "baseline" and snapshots[1].kind == "edit"
    assert research.unpack(snapshots[0])["notes"] == "保存前本人文字"
    assert "保存前本人文字".encode() not in bytes(snapshots[0].data_ciphertext)
    assert research_replay.edit_turn(reader_user, project.pk, turn.pk, command)["turn"]["revision"] == 2
    restore = {"expected_revision": 2, "restore_id": snapshots[0].pk}
    restored = research_replay.edit_turn(reader_user, project.pk, turn.pk, restore)
    assert restored["notes"] == "保存前本人文字" and restored["tags"] == ["原标签"]
    assert turn.replay_revisions.count() == 3
    assert research_replay.edit_turn(reader_user, project.pk, turn.pk, restore)["turn"]["revision"] == 3
    assert turn.replay_revisions.count() == 3
    turn.refresh_from_db()
    assert all(research.unpack(turn)[key] == original[key] for key in ("question", "scope", "selected_refs"))
    assert turn.replay_revisions.first().kind == "restore"


def test_history_is_owner_and_turn_bound_and_private_export_includes_it(api_client, reader_user, admin_user):
    project, turn = source(reader_user)
    research_replay.edit_turn(reader_user, project.pk, turn.pk, {"expected_revision": 1, "notes": "明确保存的笔记"})
    snapshot = turn.replay_revisions.first()
    other_project, other_turn = source(reader_user)
    account(api_client, reader_user)
    path = f"/api/reading/research-projects/{project.pk}/replay-history/"
    summary = api_client.get(path, {"turn_id": turn.pk})
    assert summary.status_code == 200 and "no-store" in summary["Cache-Control"]
    assert all("notes" not in row for row in summary.data["results"])
    detail = api_client.get(path, {"turn_id": turn.pk, "revision_id": snapshot.pk})
    assert detail.data["selected"]["notes"] == "明确保存的笔记"
    wrong = api_client.patch(f"/api/reading/research-projects/{other_project.pk}/replay/", {
        "turn_id": str(other_turn.pk), "expected_revision": 1, "restore_id": str(snapshot.pk)}, format="json")
    assert wrong.status_code == 404
    exported = privacy._export_item(reader_user, "research", project)
    assert exported["turns"][0]["data"]["replay_history"][-1]["notes"] == "明确保存的笔记"
    account(api_client, admin_user)
    assert api_client.get(path, {"turn_id": turn.pk, "revision_id": snapshot.pk}).status_code == 404
    turn.delete()
    assert not ResearchReplayRevision.objects.filter(pk=snapshot.pk).exists()
    assert ResearchProject.objects.filter(pk=project.pk).exists()


def test_tags_validation_missing_history_active_turn_and_stale_revision(api_client, reader_user):
    project, turn = source(reader_user)
    account(api_client, reader_user)
    path = f"/api/reading/research-projects/{project.pk}/replay/"
    base = {"turn_id": str(turn.pk), "expected_revision": 1}
    for tags in (["Ａ", "a"], [""] , [str(value) for value in range(13)]):
        assert api_client.patch(path, {**base, "tags": tags}, format="json").status_code == 400
    assert api_client.patch(path, {**base, "restore_id": str(uuid4()), "notes": "不能混合"}, format="json").status_code == 400
    assert research_replay_history.history(reader_user, project.pk, turn.pk)["count"] == 0
    turn.status = "running"
    turn.save(update_fields=["status"])
    assert api_client.patch(path, {**base, "notes": "不能覆盖处理中的轮次"}, format="json").status_code == 409
    turn.status = "completed"
    turn.save(update_fields=["status"])
    first = api_client.patch(path, {**base, "notes": "第一版"}, format="json")
    assert first.status_code == 200
    assert api_client.patch(path, {**base, "notes": "冲突覆盖"}, format="json").status_code == 409
    assert turn.replay_revisions.count() == 2
    project.delete()
    assert not ResearchReplayRevision.objects.exists()


def test_revoked_session_cannot_edit_or_stop_a_fork(api_client, reader_user):
    from accounts.models import User
    project, turn = source(reader_user)
    account(api_client, reader_user)
    User.objects.filter(pk=reader_user.pk).update(token_version=reader_user.token_version + 1)
    edited = api_client.patch(f"/api/reading/research-projects/{project.pk}/replay/", {
        "turn_id": str(turn.pk), "expected_revision": 1, "notes": "已失效会话不得写入"}, format="json")
    assert edited.status_code == 403
    stopped = api_client.post("/api/reading/research-projects/replay-fork-receipt/", {
        "request_id": str(uuid4()), "action": "cancel_pending"}, format="json")
    assert stopped.status_code == 403 and not ResearchReplayRevision.objects.exists()


def test_new_evidence_is_difference_of_saved_results_not_a_new_search(reader_user, monkeypatch):
    project, parent = source(reader_user)
    refs = [{"asset_id": str(uuid4()), "document_revision_id": str(uuid4()), "pdf_page": 1} for _ in range(4)]
    payload = research.unpack(parent)
    payload.update(result_refs=refs[:2])
    research.save_data(parent, payload)
    child = ResearchTurn.objects.create(project=project, parent=parent, status="partial", data_ciphertext=research.pack({
        "question": "本轮问题", "selected_refs": [refs[2]], "result_refs": [*refs, refs[3]], "scope": {}}))
    def resolve(raw, user, **kwargs):
        assert user.pk == reader_user.pk
        return {**raw, "source_status": "unavailable", "quote": "", "reference_id": research.reference_identity(raw)}
    monkeypatch.setattr(research, "resolve_reference", resolve)
    result = research_replay.detail(reader_user, project.pk, child.pk)
    assert len(result["evidence"]) == 1 and result["evidence"][0]["asset_id"] == refs[3]["asset_id"]
    assert result["evidence"][0]["quote"] == "" and result["evidence"][0]["source_status"] == "unavailable"
    assert len(result["materials"]) == 1
