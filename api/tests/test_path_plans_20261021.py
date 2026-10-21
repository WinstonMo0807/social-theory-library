"""Pinned path copies, explicit upgrades and owner receipts; unified acceptance only."""
from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Edition, KnowledgeNode, ReadingPath, ReadingPathItem, ReadingPathStage
from catalog.services.public_reading_paths import capture_reading_path_publication, public_reading_path_snapshot
from reading import path_plans, privacy, research
from reading.path_models import PlanCommandReceipt
from reading.research_models import PersonalReadingPlan
from tests.test_privacy_atlas_20261018 import operation, command as privacy_command, run
from tests.test_theory_publication_20261020 import source

pytestmark = pytest.mark.django_db
BASE = "/api/reading/path-follows/"


@pytest.fixture(autouse=True)
def enabled(settings):
    settings.THEORY_SYSTEM_ENABLED = True


def public_path(actor):
    path = ReadingPath.objects.create(title="合成公共路径", slug=f"path-private-{uuid4()}", status="published")
    stages = [ReadingPathStage.objects.create(reading_path=path, name=f"第{index + 1}阶段", position=index) for index in range(2)]
    work, edition, _ = source()
    bibliography, bibliographic, _ = source(fulltext=False)
    node = KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="合成路径概念",
        slug=f"path-node-{uuid4()}", status="published")
    items = []
    for index, chapter in enumerate(("第一章", "第二章")):
        items.append(ReadingPathItem.objects.create(reading_path=path, stage=stages[0], stage_name=stages[0].name,
            work=work, edition=edition, material_kind="chapter", chapter_title=chapter, page_start=1, page_end=1,
            reading_order=index, position=index, recommendation_reason=f"合成章节理由{index}"))
    items.append(ReadingPathItem.objects.create(reading_path=path, stage=stages[0], stage_name=stages[0].name,
        node=node, material_kind="node", reading_order=2, position=2))
    items.append(ReadingPathItem.objects.create(reading_path=path, stage=stages[1], stage_name=stages[1].name,
        work=bibliography, edition=bibliographic, reading_order=3, position=0))
    capture_reading_path_publication(path, actor=actor)
    return path, stages, items


def follow(user, path, *, bookmarked=True):
    snapshot = public_reading_path_snapshot(path.pk)
    raw = {"request_id": str(uuid4()), "path_id": str(path.pk),
        "expected_source_revision": snapshot["revision"]["token"], "bookmarked": bookmarked}
    return raw, path_plans.create_follow(user, raw)


def copy(user, record):
    raw = {"request_id": str(uuid4()), "expected_revision": record["revision"], "title": "合成私人阅读目标"}
    return raw, path_plans.copy_plan(user, record["id"], raw)


def patch(user, record, **values):
    return path_plans.update_follow(user, record["id"], {"request_id": str(uuid4()), "expected_revision": record["revision"], **values})["record"]


def test_copy_preserves_public_item_and_stage_identity_without_skipping_nodes_or_bibliography(reader_user, admin_user):
    path, stages, items = public_path(admin_user)
    _, first = follow(reader_user, path, bookmarked=False)
    _, copied = copy(reader_user, first["record"])
    record = PersonalReadingPlan.objects.get(pk=copied["record"]["id"])
    payload = research.unpack(record)
    assert record.public_path_id is None and record.task_pending is False
    assert payload["origin"]["type"] == "public_path_copy"
    assert payload["enhancement_status"] == "not_requested"
    assert [row["source_item_id"] for row in payload["items"]] == [str(row.pk) for row in items]
    assert [row["source_stage_id"] for row in payload["items"]] == [str(stages[0].pk)] * 3 + [str(stages[1].pk)]
    assert payload["items"][0]["work_id"] == payload["items"][1]["work_id"]
    assert payload["items"][2]["kind"] == "node" and payload["items"][2]["edition_id"] is None
    assert payload["items"][3]["source_status"] == "no_fulltext"
    assert len(payload["items"]) == 4 and payload["schedule"]["unknown_duration_count"] == 3
    assert copied["record"]["type"] == "personal_plan" and not first["record"]["bookmarked"]
    assert "合成私人阅读目标".encode() not in bytes(record.data_ciphertext)


def test_owner_header_queryset_and_staff_never_expand_private_path_access(api_client, reader_user, admin_user):
    path, _, _ = public_path(admin_user)
    _, first = follow(reader_user, path)
    _, copied = copy(reader_user, first["record"])
    api_client.force_authenticate(reader_user)
    assert api_client.get(BASE).status_code == 403
    headers = {"HTTP_X_READER_OWNER": str(reader_user.pk)}
    rows = api_client.get("/api/reading/reading-plans/", **headers)
    assert [row["id"] for row in rows.data["results"]] == [copied["record"]["id"]]
    assert api_client.get(f"/api/reading/reading-plans/{first['record']['id']}/", **headers).status_code == 404
    assert api_client.delete(f"/api/reading/reading-plans/{first['record']['id']}/", {
        "request_id": str(uuid4()), "expected_revision": first["record"]["revision"]}, format="json", **headers).status_code == 404
    assert api_client.get(f"/api/reading/reading-plans/{copied['record']['id']}/").status_code == 403
    own = api_client.get(BASE, **headers)
    assert own["Cache-Control"] == "private, no-store" and own.data["owner_id"] == str(reader_user.pk)
    assert api_client.get(f"{BASE}{copied['record']['id']}/", **headers).data["record"]["type"] == "personal_plan"
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_READER_OWNER": str(admin_user.pk)}
    assert api_client.get(f"{BASE}{first['record']['id']}/", **headers).status_code == 404
    assert api_client.get(f"{BASE}by-request/", {"request_id": first["receipt"]["request_id"]}, **headers).status_code == 404
    assert api_client.get(f"/api/reading/reading-plans/{copied['record']['id']}/", **headers).status_code == 404


def test_follow_progress_and_notes_use_cas_and_nonce_without_overwriting_prior_completion(reader_user, admin_user):
    path, _, items = public_path(admin_user)
    raw, first = follow(reader_user, path)
    record = first["record"]
    command = {"request_id": str(uuid4()), "expected_revision": record["revision"],
        "action": "progress", "item_id": str(items[0].pk), "status": "completed"}
    changed = path_plans.update_follow(reader_user, record["id"], command)
    assert path_plans.update_follow(reader_user, record["id"], command) == changed
    assert path_plans.create_follow(reader_user, raw)["record"]["revision"] == changed["record"]["revision"]
    with pytest.raises(research.ResearchConflict):
        path_plans.update_follow(reader_user, record["id"], {**command, "request_id": str(uuid4())})
    changed = patch(reader_user, changed["record"], action="note", item_id=str(items[0].pk), note="已完成后补充的本人笔记")
    changed = patch(reader_user, changed, action="bookmark", bookmarked=False)
    assert changed["progress"][str(items[0].pk)] == {"status": "completed", "note": "已完成后补充的本人笔记"}
    assert changed["completed_items"] == 1 and changed["bookmarked"] is False
    with pytest.raises(research.ResearchConflict):
        patch(reader_user, changed, action="progress", item_id=str(items[0].pk), status="pending")
    with pytest.raises(NotFound):
        path_plans.by_request(reader_user, uuid4())


def test_upgrade_is_explicit_preserves_completed_sources_and_archives_removed_notes(reader_user, admin_user):
    path, stages, items = public_path(admin_user)
    _, first = follow(reader_user, path)
    record = patch(reader_user, first["record"], action="progress", item_id=str(items[0].pk), status="completed")
    record = patch(reader_user, record, action="note", item_id=str(items[1].pk), note="移除材料仍保留的本人笔记")
    old_source = deepcopy(record["source_revision"])
    old_reason = record["path"]["items"][0]["reason"]
    items[0].recommendation_reason = "更新后的公共理由"
    items[0].save(update_fields=["recommendation_reason"])
    removed_id = str(items[1].pk)
    items[1].delete()
    ReadingPathItem.objects.create(reading_path=path, stage=stages[1], stage_name=stages[1].name,
        node=items[2].node, material_kind="node", reading_order=4, position=1)
    capture_reading_path_publication(path, actor=admin_user, change_note="合成显式升级")
    latest = public_reading_path_snapshot(path.pk)["revision"]
    before = path_plans.by_path(reader_user, path.pk)["record"]
    assert before["source_revision"] == old_source and before["revision"] == record["revision"]
    preview = path_plans.upgrade_preview(reader_user, record["id"], latest["token"])
    assert removed_id in preview["diff"]["removed"] and len(preview["diff"]["added"]) == 1
    assert str(items[0].pk) in preview["retained_completed"] and removed_id in preview["retained_notes"]
    assert PersonalReadingPlan.objects.get(pk=record["id"]).revision == record["revision"]
    command = {"request_id": str(uuid4()), "expected_revision": record["revision"], "target_revision": latest["token"]}
    upgraded = path_plans.upgrade(reader_user, record["id"], command)
    assert path_plans.upgrade(reader_user, record["id"], command) == upgraded
    completed = next(row for row in upgraded["record"]["data"]["items"] if row["source_item_id"] == str(items[0].pk))
    assert completed["status"] == "completed" and completed["source_revision"] == old_source and completed["reason"] == old_reason
    archived = upgraded["record"]["history"][-1]["removed_items"][0]
    assert archived["source_item_id"] == removed_id and archived["note"] == "移除材料仍保留的本人笔记"
    with pytest.raises(research.ResearchConflict):
        path_plans.upgrade_preview(reader_user, record["id"], old_source["token"])


def test_copy_edits_preserve_repeated_chapters_and_write_receipt_precedes_stale_cas(reader_user, admin_user):
    path, _, _ = public_path(admin_user)
    _, first = follow(reader_user, path)
    _, copied = copy(reader_user, first["record"])
    record = copied["record"]
    command = {"request_id": str(uuid4()), "expected_revision": 1, "item_id": record["data"]["items"][1]["id"], "item_minutes": 17}
    changed = research.update_plan(reader_user, record["id"], command)
    assert research.update_plan(reader_user, record["id"], command).revision == changed.revision
    payload = research.unpack(changed)
    assert len(payload["items"]) == 4 and payload["items"][1]["estimated_minutes"] == 17
    assert payload["items"][0]["estimated_minutes"] is None
    assert path_plans.by_request(reader_user, command["request_id"])["receipt"]["applied_revision"] == changed.revision
    preview = research.update_plan(reader_user, record["id"], {"expected_revision": changed.revision, "preview": True, "budget_minutes": 10})
    assert preview.revision == changed.revision
    assert research.unpack(preview)["schedule"]["budget_minutes"] == 10
    assert research.unpack(PersonalReadingPlan.objects.get(pk=record["id"]))["schedule"]["budget_minutes"] is None
    unchanged = path_plans.upgrade_preview(reader_user, record["id"], record["source_revision"]["token"])
    assert unchanged["diff"]["changed"] == []
    assert len(unchanged["diff"]["unchanged"]) == 4
    with pytest.raises(ValidationError):
        research.update_plan(reader_user, record["id"], {"expected_revision": changed.revision, "note": "没有固定请求"})
    with pytest.raises(ValidationError):
        research.update_plan(reader_user, first["record"]["id"], {"expected_revision": 1, "goal": "误作私人计划"})


def test_withdrawal_keeps_owned_notes_but_blocks_new_copy_and_live_source_links(reader_user, admin_user):
    path, _, items = public_path(admin_user)
    _, first = follow(reader_user, path)
    ReadingPath.objects.filter(pk=path.pk).update(status="archived")
    record = patch(reader_user, first["record"], action="note", item_id=str(items[0].pk), note="路径撤回后的本人记录")
    assert record["source_status"] == "unavailable"
    assert all(row["reader_url"] is None and row["href"] is None for row in record["path"]["items"])
    assert record["progress"][str(items[0].pk)]["note"] == "路径撤回后的本人记录"
    assert "source_snapshot" not in record["data"]
    export = operation(reader_user, "export", categories=["plans"])
    run(export)
    exported = privacy.download_operation(reader_user, export.pk)["records"][0]["record"]["data"]
    assert "source_snapshot" not in exported
    assert all(row["reader_url"] is None and row["href"] is None for row in exported["items"])
    with pytest.raises(NotFound):
        copy(reader_user, record)
    with pytest.raises(NotFound):
        follow(admin_user, path)


def test_copy_replacement_preserves_stable_identity_notes_and_history_and_rechecks_source(reader_user, admin_user):
    path, _, items = public_path(admin_user)
    _, first = follow(reader_user, path)
    _, copied = copy(reader_user, first["record"])
    record = copied["record"]
    original = record["data"]["items"][0]
    _, replacement, asset = source()
    replacement.refresh_from_db()
    command = {"request_id": str(uuid4()), "expected_revision": record["revision"],
        "item_id": original["id"], "note": "本人的替换说明", "reference": {"asset_id": str(asset.pk),
            "document_revision_id": str(replacement.active_catalog_revision.document_revision_id), "pdf_page": 1}}
    saved = research.update_plan(reader_user, record["id"], command)
    item = research.unpack(saved)["items"][0]
    assert item["source_item_id"] == original["source_item_id"] and item["source_stage_id"] == original["source_stage_id"]
    assert item["work_id"] != original["work_id"] and item["owner_override"] is True
    assert item["note"] == "本人的替换说明" and item["estimated_minutes"] is None
    assert "quote" not in item["reference"] and item["source_history"][0]["work_id"] == original["work_id"]
    items[0].recommendation_reason = "公开策划改变了此项理由"
    items[0].save(update_fields=["recommendation_reason"])
    capture_reading_path_publication(path, actor=admin_user)
    upgraded = path_plans.upgrade(reader_user, record["id"], {"request_id": str(uuid4()), "expected_revision": saved.revision,
        "target_revision": public_reading_path_snapshot(path.pk)["revision"]["token"]})["record"]
    assert upgraded["data"]["items"][0]["work_id"] == item["work_id"]
    assert upgraded["data"]["items"][0]["upgrade_status"] == "owner_replacement_preserved"
    Edition.objects.filter(pk=replacement.pk).update(state="archived")
    current = path_plans.record_output(PersonalReadingPlan.objects.get(pk=record["id"]), reader_user)
    assert current["data"]["items"][0]["source_status"] == "unavailable"
    assert current["data"]["items"][0]["reader_url"] is None
    assert current["data"]["items"][0]["note"] == "本人的替换说明"
    assert current["data"]["items"][0]["source_history"][0]["reader_url"] is None


def test_generic_copy_patch_and_delete_use_owner_nonce_cas_and_tombstones(api_client, reader_user, admin_user):
    path, _, _ = public_path(admin_user)
    _, first = follow(reader_user, path)
    _, copied = copy(reader_user, first["record"])
    record = copied["record"]
    url = f"/api/reading/reading-plans/{record['id']}/"
    api_client.force_authenticate(reader_user)
    headers = {"HTTP_X_READER_OWNER": str(reader_user.pk)}
    command = {"request_id": str(uuid4()), "expected_revision": record["revision"],
        "item_id": record["data"]["items"][1]["id"], "item_minutes": 17, "status": "completed"}
    assert api_client.patch(url, command, format="json").status_code == 403
    saved = api_client.patch(url, command, format="json", **headers)
    assert saved.status_code == 200 and saved.data["data"]["items"][1]["estimated_minutes"] == 17
    assert api_client.patch(url, command, format="json", **headers).data["revision"] == saved.data["revision"]
    assert api_client.patch(url, {**command, "request_id": str(uuid4())}, format="json", **headers).status_code == 409
    assert api_client.patch(url, {**command, "request_id": str(uuid4()), "expected_revision": saved.data["revision"],
        "reference": {"asset_id": record["data"]["items"][0]["asset_id"],
            "document_revision_id": record["data"]["items"][0]["document_revision_id"], "pdf_page": 1}}, format="json", **headers).status_code == 409
    nonce = str(uuid4())
    deletion = {"request_id": nonce, "expected_revision": saved.data["revision"]}
    removed = api_client.delete(url, deletion, format="json", **headers)
    assert removed.status_code == 200 and removed.data["receipt"]["deleted"]
    assert api_client.delete(url, deletion, format="json", **headers).data == removed.data
    assert path_plans.by_request(reader_user, command["request_id"])["receipt"]["deleted"] is True
    assert path_plans.by_request(reader_user, command["request_id"])["record"] is None


def test_legacy_generation_cannot_silently_drop_public_path_materials(reader_user, admin_user):
    path, _, _ = public_path(admin_user)
    with pytest.raises(ValidationError):
        research.generate_plan(reader_user, {"request_id": str(uuid4()), "goal": "保留全部材料", "reading_path_id": str(path.pk)})
    assert not PersonalReadingPlan.objects.filter(user=reader_user).exists()


def test_delete_and_privacy_erasure_keep_tombstones_and_cannot_recreate_old_commands(reader_user, admin_user):
    path, _, _ = public_path(admin_user)
    raw, first = follow(reader_user, path)
    copy_raw, copied = copy(reader_user, first["record"])
    export = operation(reader_user, "export", categories=["plans"])
    run(export)
    exported = privacy.download_operation(reader_user, export.pk)
    assert {row["record"]["id"] for row in exported["records"]} == {first["record"]["id"], copied["record"]["id"]}
    targets = [privacy.target_of(row, "plans") for row in PersonalReadingPlan.objects.filter(user=reader_user)]
    removal = operation(reader_user, "erase", targets=targets)
    privacy_command(reader_user, removal, "confirm")
    run(removal)
    assert not PersonalReadingPlan.objects.filter(user=reader_user).exists()
    assert PlanCommandReceipt.objects.filter(user=reader_user, record__isnull=True).count() == 2
    for replay in (path_plans.create_follow(reader_user, raw), path_plans.copy_plan(reader_user, first["record"]["id"], copy_raw)):
        assert replay["record"] is None and replay["receipt"]["deleted"] is True
    assert not PersonalReadingPlan.objects.filter(user=reader_user).exists()


@pytest.mark.parametrize("change", [{"bookmarked": "true"}, {"bookmarked": 1}, {"items": []},
    {"expected_source_revision": "preview:not-public"}])
def test_follow_rejects_forged_material_or_non_boolean_flags(reader_user, admin_user, change):
    path, _, _ = public_path(admin_user)
    raw = {"request_id": str(uuid4()), "path_id": str(path.pk),
        "expected_source_revision": public_reading_path_snapshot(path.pk)["revision"]["token"], **change}
    with pytest.raises((ValidationError, research.ResearchConflict)):
        path_plans.create_follow(reader_user, raw)
    assert not PersonalReadingPlan.objects.filter(user=reader_user).exists()
