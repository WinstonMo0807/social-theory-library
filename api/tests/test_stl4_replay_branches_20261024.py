"""Deferred private branch graph and late-create fencing acceptance."""
from uuid import uuid4

import pytest

from reading import research, research_replay, research_replay_tree
from reading.models import ResearchProject, ResearchTurn

pytestmark = pytest.mark.django_db


def project(user, title, origin=None):
    return ResearchProject.objects.create(user=user, data_ciphertext=research.pack({"title": title, **({"replay_origin": origin} if origin else {})}))


def turn(parent_project, title, parent=None):
    return ResearchTurn.objects.create(project=parent_project, parent=parent, status="completed", data_ciphertext=research.pack({"question": title, "scope": {}, "selected_refs": []}))


def account(client, user):
    client.force_authenticate(user)
    client.credentials(HTTP_X_READER_OWNER=str(user.pk))


def test_turn_branches_paginate_and_never_expand_another_project(api_client, reader_user, admin_user):
    own = project(reader_user, "本人研究")
    root = turn(own, "起始轮次")
    children = [turn(own, f"分支{i}", root) for i in range(21)]
    nested = turn(own, "下一层", children[0])
    other = project(admin_user, "他人研究")
    alien = turn(other, "他人轮次", root)
    legacy = turn(own, "旧的异常父关系", alien)
    first = research_replay_tree.turn_tree(reader_user, own.pk)
    assert {value["id"] for value in first["results"]} == {str(root.pk), str(legacy.pk)}
    assert next(value for value in first["results"] if value["id"] == str(root.pk))["child_count"] == 21
    assert research_replay.descriptor(legacy)["parent_id"] is None
    page = research_replay_tree.turn_tree(reader_user, own.pk, root.pk, 2)
    assert page["count"] == 21 and len(page["results"]) == 1
    assert research_replay_tree.turn_tree(reader_user, own.pk, children[0].pk)["results"][0]["id"] == str(nested.pk)
    account(api_client, reader_user)
    path = f"/api/reading/research-projects/{own.pk}/replay-tree/"
    assert api_client.get(path, {"parent_id": alien.pk}).status_code == 404
    assert "no-store" in api_client.get(path, {"parent_id": root.pk})["Cache-Control"]
    account(api_client, admin_user)
    assert api_client.get(path).status_code == 404


def test_cross_project_links_are_only_actual_own_forks_and_survive_source_turn_deletion(reader_user, admin_user):
    original = project(reader_user, "原研究")
    first = turn(original, "来源轮次")
    child = project(reader_user, "派生研究", {"project_id": str(original.pk), "turn_id": str(first.pk)})
    grandchild = project(reader_user, "下级研究", {"project_id": str(child.pk), "turn_id": str(uuid4())})
    project(reader_user, "无关研究")
    project(admin_user, "其他账户的记录", {"project_id": str(original.pk), "turn_id": str(first.pk)})
    links = research_replay_tree.project_links(reader_user, original.pk)
    assert [value["id"] for value in links["results"]] == [str(child.pk)]
    assert links["results"][0]["turn_id"] == str(first.pk)
    assert research_replay_tree.project_links(reader_user, child.pk)["parent"]["id"] == str(original.pk)
    assert research_replay_tree.project_links(reader_user, child.pk)["results"][0]["id"] == str(grandchild.pk)
    first.delete()
    assert research_replay_tree.project_links(reader_user, child.pk)["parent"]["turn_id"] is None
    original.delete()
    links = research_replay_tree.project_links(reader_user, child.pk)
    assert links["origin_unavailable"] and links["parent"] is None
    assert ResearchProject.objects.filter(pk=child.pk).exists()


def test_stop_fences_late_fork_and_returns_existing_result(api_client, reader_user):
    source = project(reader_user, "合成来源")
    origin = turn(source, "合成轮次")
    request_id = uuid4()
    account(api_client, reader_user)
    receipt_path = "/api/reading/research-projects/replay-fork-receipt/"
    stopped = api_client.post(receipt_path, {"request_id": str(request_id), "action": "cancel_pending"}, format="json")
    assert stopped.status_code == 200 and stopped.data["state"] == "cancelled"
    late = research_replay.fork_project(reader_user, source.pk, origin.pk, {"request_id": request_id})
    assert late["state"] == "cancelled" and late["project_id"] is None and not late["deleted"]
    assert ResearchProject.objects.filter(user=reader_user).count() == 1
    from reading.models import ResearchImportReceipt
    child = project(reader_user, "已有分支", {"project_id": str(source.pk), "turn_id": str(origin.pk)})
    existing_id = uuid4()
    ResearchImportReceipt.objects.create(user=reader_user, request_id=existing_id, project=child, fingerprint="a" * 64)
    completed = api_client.post(receipt_path, {"request_id": str(existing_id), "action": "cancel_pending"}, format="json")
    assert completed.data["state"] == "applied" and completed.data["project_id"] == str(child.pk)
    assert ResearchProject.objects.filter(pk=child.pk).exists()
