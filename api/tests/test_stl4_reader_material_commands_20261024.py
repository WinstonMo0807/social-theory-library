"""Deferred R22 acceptance: original records, atomic batches, private command receipts."""
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User
from reading import material_preferences, privacy, reader_center, reader_material_commands as commands, research
from reading.models import ReadingList, ReaderMaterialPreference
from tests.test_confirmed_memory_atlas_20261018 import grant, memory_for, project_for

pytestmark = pytest.mark.django_db


def target(row, kind, title=None):
    return {"id": str(row.pk), "kind": kind, "revision": reader_center.command_revision(row, kind), **({"title": title} if title is not None else {})}


def test_rename_original_project_and_list_replays_without_rewriting(reader_user):
    project = project_for(reader_user)
    booklist = ReadingList.objects.create(user=reader_user, title="原书单", description="保留说明")
    data = {"request_id": str(uuid4()), "action": "rename", "targets": [target(project, "research", "新的研究名称"), target(booklist, "lists", "新的书单名称")]}
    first = commands.command(reader_user, data)
    project.refresh_from_db(); booklist.refresh_from_db()
    assert research.unpack(project)["title"] == "新的研究名称"
    assert booklist.title == "新的书单名称" and booklist.description == "保留说明"
    versions = (project.revision, booklist.updated_at)
    assert commands.command(reader_user, data) == first
    project.refresh_from_db(); booklist.refresh_from_db()
    assert (project.revision, booklist.updated_at) == versions
    assert commands.stop(reader_user, data["request_id"]) == first


def test_one_changed_row_rolls_back_entire_batch(reader_user):
    project = project_for(reader_user)
    booklist = ReadingList.objects.create(user=reader_user, title="保留原名称")
    stale = target(booklist, "lists", "不得采用")
    stale["revision"] = "old"
    data = {"request_id": str(uuid4()), "action": "rename", "targets": [target(project, "research", "同样不得采用"), stale]}
    with pytest.raises(research.ResearchConflict):
        commands.command(reader_user, data)
    project.refresh_from_db(); booklist.refresh_from_db()
    assert research.unpack(project)["title"] == "本人的研究" and booklist.title == "保留原名称"
    with pytest.raises(NotFound):
        commands.receipt(reader_user, data["request_id"])


def test_archive_restore_and_cancel_pending_preserve_original_content(reader_user, admin_user):
    project = project_for(reader_user)
    original = research.unpack(project)
    data = {"request_id": str(uuid4()), "action": "archive", "targets": [target(project, "research")]}
    commands.command(reader_user, data)
    project.refresh_from_db()
    assert project.archived and research.unpack(project) == original
    with pytest.raises(NotFound):
        commands.receipt(admin_user, data["request_id"])
    restore = {"request_id": str(uuid4()), "action": "restore", "targets": [target(project, "research")]}
    commands.stop(reader_user, restore["request_id"])
    with pytest.raises(research.ResearchConflict):
        commands.command(reader_user, restore)
    project.refresh_from_db(); assert project.archived
    restore["request_id"] = str(uuid4())
    commands.command(reader_user, restore)
    project.refresh_from_db(); assert not project.archived


def test_display_truncation_does_not_become_rename_input_and_old_session_cannot_write(reader_user):
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "完整名称" * 50})
    value = reader_center.material(reader_user, "research", project)
    assert len(value["title"]) == 160 and value["editable_title"] == "完整名称" * 50
    User.objects.filter(pk=reader_user.pk).update(token_version=reader_user.token_version + 1)
    with pytest.raises(PermissionDenied):
        commands.command(reader_user, {"request_id": str(uuid4()), "action": "archive", "targets": [target(project, "research")]})


def test_display_name_preserves_memory_grant_and_invalidates_private_snapshot(reader_user, admin_user):
    project = project_for(reader_user)
    memory = grant(reader_user, memory_for(reader_user), project)
    original, revision = research.unpack(memory), memory.revision
    snapshot = privacy.target_of(memory, "memories")
    commands.command(reader_user, {"request_id": str(uuid4()), "action": "rename", "targets": [target(memory, "confirmed", "自己的显示名")]})
    memory.refresh_from_db()
    assert research.unpack(memory) == original and memory.revision == revision and memory.state == "confirmed"
    with pytest.raises(research.ResearchConflict):
        privacy.verify_target(reader_user, snapshot)
    assert privacy.export_item(reader_user, "memories", memory)["reader_center"]["title"] == "自己的显示名"
    assert material_preferences.export_all(admin_user) == []
    value = reader_center.materials(reader_user, kind="confirmed", q="自己的显示名")["results"][0]
    assert value["id"] == str(memory.pk) and value["title"] == "自己的显示名"
    with pytest.raises(NotFound):
        commands.command(admin_user, {"request_id": str(uuid4()), "action": "archive", "targets": [target(memory, "confirmed")]})


def test_mixed_archive_filter_and_hard_delete_cleanup(reader_user):
    project = project_for(reader_user)
    memory = memory_for(reader_user)
    booklist = ReadingList.objects.create(user=reader_user, title="原书单")
    pairs = [(project, "research"), (memory, "confirmed"), (booklist, "lists")]
    commands.command(reader_user, {"request_id": str(uuid4()), "action": "archive", "targets": [target(row, kind) for row, kind in pairs]})
    assert reader_center.materials(reader_user, visibility="archived")["count"] == 3
    assert reader_center.materials(reader_user, visibility="active")["count"] == 0
    assert ReaderMaterialPreference.objects.filter(user=reader_user).count() == 2
    for row, kind in pairs:
        row.refresh_from_db()
    commands.command(reader_user, {"request_id": str(uuid4()), "action": "restore", "targets": [target(row, kind) for row, kind in pairs]})
    assert reader_center.materials(reader_user, visibility="active")["count"] == 3
    assert reader_center.materials(reader_user, visibility="archived")["count"] == 0
    memory.delete()
    assert not ReaderMaterialPreference.objects.filter(user=reader_user, kind="confirmed").exists()
