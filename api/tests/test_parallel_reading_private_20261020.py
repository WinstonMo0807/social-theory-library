"""PDF41–43 private decisions and public opt-in. Authored; not yet executed."""
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from catalog.models import Asset, Edition, Page, Work
from reading import parallel_reading as service
from reading import privacy, research
from reading.parallel_models import ParallelCalibration, ParallelReadingReceipt, ParallelReadingTask
from tests.v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


@pytest.fixture
def parallel_source():
    work = Work.objects.create(title="并读验收合成材料", document_type="book")
    sources = []
    for index in (1, 2):
        edition = Edition.objects.create(work=work, state="published", is_primary=index == 1, public_slug=uuid4().hex)
        asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
            file=f"public/parallel-synthetic-{index}.pdf", sha256=uuid4().hex * 2, access_status="public", page_count=2)
        page = Page.objects.create(asset=asset, index=1, text=f"合成版本{index}的可核对原文", width=595, height=842)
        Page.objects.create(asset=asset, index=2, text=f"合成版本{index}的另一页", width=595, height=842)
        revision = activate_catalog_revision(edition, reader_asset=asset).document_revision
        reference = {"asset_id": str(asset.id), "document_revision_id": str(revision.id),
            "pdf_page": 1, "content_hash": sha256(page.text.encode()).hexdigest(), "evidence_span_id": None,
            "selection_start": 0, "selection_end": len(page.text)}
        sources.append((edition, asset, page, revision, reference))
    return sources


def task_command(sources):
    left, right = sources
    return {"request_id": str(uuid4()), "data": {
        "left_asset_id": str(left[1].id), "right_asset_id": str(right[1].id),
        "left_document_revision_id": str(left[3].id), "right_document_revision_id": str(right[3].id),
        "positions": {"left_page": 1, "right_page": 1, "left_segment_id": None, "right_segment_id": None},
        "sync_scroll": True,
        "alignments": [{"id": str(uuid4()), "left": left[4], "right": right[4],
            "status": "confirmed", "note": "私人对齐判断"}],
        "terms": [{"id": str(uuid4()), "original": "原词", "translation": "译词", "note": "仅本人术语思考",
            "left": left[4], "right": right[4]}],
    }}


def submit_calibration(user, created, scope="passages"):
    return service.create_calibration(user, {"request_id": str(uuid4()), "task_id": created["id"],
        "expected_revision": created["revision"], "alignment_id": created["data"]["alignments"][0]["id"],
        "scope": scope, "basis": "已明确授权公开的合成校准依据"})


def review_command(revision, note=""):
    return {"request_id": str(uuid4()), "expected_revision": revision, "note": note}


def test_task_encrypts_user_text_and_rehydrates_exact_references(reader_user, parallel_source):
    created = service.create_task(reader_user, task_command(parallel_source))
    record = ParallelReadingTask.objects.get(pk=created["id"])
    stored = research.unpack(record)
    assert created["source_available"] is True
    assert created["data"]["alignments"][0]["left"]["quote"] == parallel_source[0][2].text
    assert "私人对齐判断".encode() not in bytes(record.data_ciphertext)
    assert stored["terms"][0]["note"] == "仅本人术语思考"
    assert "quote" not in stored["alignments"][0]["left"]
    assert "title" not in stored["alignments"][0]["right"]
    assert created["applied_revision"] == created["revision"] == 1


def test_create_patch_and_unknown_receipt_never_replay_over_later_revision(reader_user, parallel_source):
    command = task_command(parallel_source)
    created = service.create_task(reader_user, command)
    assert service.create_task(reader_user, command)["id"] == created["id"]
    changed = deepcopy(command)
    changed["data"]["terms"][0]["note"] = "不同的新输入"
    with pytest.raises(research.ResearchConflict):
        service.create_task(reader_user, changed)
    update = {"request_id": str(uuid4()), "expected_revision": 1, "data": command["data"]}
    update["data"]["terms"][0]["note"] = "修订二"
    second = service.update_task(reader_user, created["id"], update)
    next_update = deepcopy(update)
    next_update.update(request_id=str(uuid4()), expected_revision=2)
    next_update["data"]["terms"][0]["note"] = "修订三"
    third = service.update_task(reader_user, created["id"], next_update)
    replay = service.update_task(reader_user, created["id"], update)
    assert replay["revision"] == third["revision"] == 3
    assert replay["applied_revision"] == second["revision"] == 2
    assert replay["data"]["terms"][0]["note"] == "修订三"
    receipt = service.task_by_request(reader_user, update["request_id"])
    assert receipt["revision"] == 3 and receipt["applied_revision"] == 2
    stale = deepcopy(update)
    stale["request_id"] = str(uuid4())
    with pytest.raises(research.ResearchConflict):
        service.update_task(reader_user, created["id"], stale)
    assert ParallelReadingTask.objects.filter(user=reader_user).count() == 1


@pytest.mark.parametrize("status,left,right,valid", [
    ("confirmed", True, True, True), ("no_match", True, False, True), ("addition", False, True, True),
    ("confirmed", True, False, False), ("no_match", True, True, False), ("addition", True, False, False),
])
def test_alignment_status_is_an_explicit_user_decision(reader_user, parallel_source, status, left, right, valid):
    command = task_command(parallel_source)
    row = command["data"]["alignments"][0]
    row.update(status=status, left=row["left"] if left else None, right=row["right"] if right else None)
    if valid:
        result = service.create_task(reader_user, command)
        assert result["data"]["alignments"][0]["status"] == status
    else:
        with pytest.raises(ValidationError):
            service.create_task(reader_user, command)


def test_wrong_side_revision_and_replacing_pair_are_rejected(reader_user, parallel_source):
    command = task_command(parallel_source)
    wrong = deepcopy(command)
    wrong["data"]["alignments"][0]["left"] = wrong["data"]["alignments"][0]["right"]
    with pytest.raises(ValidationError):
        service.create_task(reader_user, wrong)
    created = service.create_task(reader_user, command)
    changed = deepcopy(command["data"])
    for suffix in ("asset_id", "document_revision_id"):
        changed[f"left_{suffix}"], changed[f"right_{suffix}"] = changed[f"right_{suffix}"], changed[f"left_{suffix}"]
    with pytest.raises(ValidationError):
        service.update_task(reader_user, created["id"],
            {"request_id": str(uuid4()), "expected_revision": 1, "data": changed})


def test_withdrawal_hides_original_text_but_allows_existing_private_notes(reader_user, parallel_source):
    command = task_command(parallel_source)
    created = service.create_task(reader_user, command)
    left_edition = parallel_source[0][0]
    left_edition.state = "draft"
    left_edition.save(update_fields=["state"])
    record = ParallelReadingTask.objects.get(pk=created["id"])
    result = service.task_output(record, reader_user)
    assert result["source_available"] is False and result["pair_sources"] is None
    for row in result["data"]["alignments"]:
        assert row["left"]["quote"] == row["right"]["quote"] == ""
        assert row["left"]["reader_url"] is None
    revised = deepcopy(command["data"])
    revised["terms"][0]["note"] = "来源撤回后保留的本人新思考"
    saved = service.update_task(reader_user, record.id,
        {"request_id": str(uuid4()), "expected_revision": 1, "data": revised})
    assert saved["data"]["terms"][0]["note"] == revised["terms"][0]["note"]
    forged = deepcopy(revised)
    forged["alignments"][0]["left"]["selection_end"] -= 1
    with pytest.raises((ValidationError, NotFound)):
        service.update_task(reader_user, record.id,
            {"request_id": str(uuid4()), "expected_revision": 2, "data": forged})
    assert service.task_by_request(reader_user, command["request_id"])["id"] == created["id"]


def test_changed_page_hash_cannot_leak_old_text_or_block_private_note_edit(reader_user, parallel_source):
    command = task_command(parallel_source)
    created = service.create_task(reader_user, command)
    page = parallel_source[0][2]
    page.text = "同修订中已变化的合成原文"
    page.save(update_fields=["text"])
    command["data"]["alignments"][0]["note"] = "修改私人判断"
    saved = service.update_task(reader_user, created["id"],
        {"request_id": str(uuid4()), "expected_revision": 1, "data": command["data"]})
    assert saved["data"]["alignments"][0]["left"]["quote"] == ""
    assert saved["data"]["alignments"][0]["note"] == "修改私人判断"


def test_owner_header_private_queryset_and_service_guard(api_client, reader_user, admin_user, parallel_source):
    command = task_command(parallel_source)
    api_client.force_authenticate(reader_user)
    assert api_client.post("/api/reading/parallel-tasks/", command, format="json").status_code == 403
    response = api_client.post("/api/reading/parallel-tasks/", command, format="json",
        HTTP_X_READER_OWNER=str(reader_user.id))
    assert response.status_code == 201
    record = ParallelReadingTask.objects.get(pk=response.data["id"])
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"/api/reading/parallel-tasks/{record.id}/",
        HTTP_X_READER_OWNER=str(admin_user.id)).status_code == 404
    assert api_client.get(f"/api/reading/parallel-tasks/by-request/?request_id={command['request_id']}",
        HTTP_X_READER_OWNER=str(admin_user.id)).status_code == 404
    with pytest.raises(PermissionDenied):
        service.task_output(record, admin_user)


def test_retention_off_blocks_new_writes_but_preserves_existing_receipt_and_delete(reader_user, parallel_source):
    command = task_command(parallel_source)
    created = service.create_task(reader_user, command)
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"],
        "retention": {"personal_notes": False}})
    with pytest.raises(ValidationError):
        service.create_task(reader_user, task_command(parallel_source))
    with pytest.raises(ValidationError):
        service.update_task(reader_user, created["id"],
            {"request_id": str(uuid4()), "expected_revision": 1, "data": command["data"]})
    assert service.create_task(reader_user, command)["id"] == created["id"]
    service.delete_task(reader_user, created["id"], 1)
    assert not ParallelReadingTask.objects.filter(pk=created["id"]).exists()


def test_delete_keeps_only_nonce_tombstone_and_cannot_resurrect_private_content(reader_user, parallel_source):
    command = task_command(parallel_source)
    created = service.create_task(reader_user, command)
    service.delete_task(reader_user, created["id"], 1)
    assert not ParallelReadingTask.objects.filter(pk=created["id"]).exists()
    tombstone = ParallelReadingReceipt.objects.get(user=reader_user, request_id=command["request_id"])
    assert tombstone.task_id is None
    with pytest.raises(research.ResearchConflict):
        service.create_task(reader_user, command)
    with pytest.raises(NotFound):
        service.task_by_request(reader_user, command["request_id"])
    assert not ParallelReadingTask.objects.filter(user=reader_user).exists()
    assert Asset.objects.filter(pk=parallel_source[0][1].pk).exists()


@pytest.mark.parametrize("scope,rows", [("bibliography", 0), ("passages", 1)])
def test_explicit_public_scope_never_copies_private_notes_or_terms(reader_user, parallel_source, scope, rows):
    task = service.create_task(reader_user, task_command(parallel_source))
    result = submit_calibration(reader_user, task, scope)
    calibration = ParallelCalibration.objects.get(pk=result["id"])
    stored = research.unpack(calibration)
    assert calibration.status == "submitted"
    assert len(stored["alignments"]) == rows
    assert "terms" not in stored and "positions" not in stored
    assert all("note" not in row for row in stored["alignments"])
    assert service.calibration_output(calibration, reader_user, public=True) is None
    service.delete_task(reader_user, task["id"], task["revision"])
    assert ParallelCalibration.objects.filter(pk=result["id"]).exists()


def test_calibration_replay_precedes_later_task_edit_and_rejects_private_fields(reader_user, parallel_source):
    source_command = task_command(parallel_source)
    task = service.create_task(reader_user, source_command)
    command = {"request_id": str(uuid4()), "task_id": task["id"], "expected_revision": 1,
        "alignment_id": task["data"]["alignments"][0]["id"], "scope": "passages", "basis": "明确公开依据"}
    result = service.create_calibration(reader_user, command)
    service.update_task(reader_user, task["id"], {"request_id": str(uuid4()), "expected_revision": 1,
        "data": source_command["data"]})
    assert service.create_calibration(reader_user, command)["id"] == result["id"]
    with pytest.raises(ValidationError):
        service.create_calibration(reader_user, {**command, "terms": [{"note": "不可泄露"}]})
    with pytest.raises(research.ResearchConflict):
        service.create_calibration(reader_user, {**command, "basis": "不同依据"})


def test_review_publish_and_old_command_replay_never_roll_back_publication(reader_user, admin_user, parallel_source):
    task = service.create_task(reader_user, task_command(parallel_source))
    proposal = submit_calibration(reader_user, task)
    with pytest.raises(PermissionDenied):
        service.review_calibration(reader_user, proposal["id"], "review", review_command(1))
    with pytest.raises(research.ResearchConflict):
        service.review_calibration(admin_user, proposal["id"], "publish", review_command(1))
    command = review_command(1, "审核依据")
    reviewed = service.review_calibration(admin_user, proposal["id"], "review", command)
    published = service.review_calibration(admin_user, proposal["id"], "publish", review_command(reviewed["revision"]))
    replay = service.review_calibration(admin_user, proposal["id"], "review", command)
    assert replay["status"] == "published" and replay["revision"] == published["revision"]
    assert replay["applied_revision"] == reviewed["revision"] and replay["request_id"] == command["request_id"]
    with pytest.raises(research.ResearchConflict):
        service.review_calibration(admin_user, proposal["id"], "reject", command)
    record = ParallelCalibration.objects.get(pk=proposal["id"])
    assert service.calibration_output(record, reader_user, public=True)["data"]["alignments"]
    rejected = service.review_calibration(admin_user, proposal["id"], "reject", review_command(record.revision, "重新核验"))
    assert rejected["status"] == "rejected"
    record.refresh_from_db()
    assert service.calibration_output(record, reader_user, public=True) is None


def test_public_submission_and_readback_recheck_anonymous_source_access(reader_user, admin_user, parallel_source):
    task = service.create_task(reader_user, task_command(parallel_source))
    proposal = submit_calibration(reader_user, task)
    reviewed = service.review_calibration(admin_user, proposal["id"], "review", review_command(1))
    service.review_calibration(admin_user, proposal["id"], "publish", review_command(reviewed["revision"]))
    asset = parallel_source[1][1]
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    record = ParallelCalibration.objects.get(pk=proposal["id"])
    assert service.calibration_output(record, admin_user, public=True) is None
    admin_view = service.calibration_output(record, admin_user, admin=True)
    assert admin_view["source_available"] is False and admin_view["pair_sources"] is None
    assert admin_view["data"]["alignments"][0]["right"]["quote"] == ""
    with pytest.raises((NotFound, ValidationError)):
        submit_calibration(reader_user, task)


def test_public_list_requires_source_and_does_not_claim_unverified_total(api_client, reader_user, parallel_source):
    api_client.force_authenticate(None)
    assert api_client.get("/api/reading/parallel-calibrations/public/").status_code == 400
    response = api_client.get(f"/api/reading/parallel-calibrations/public/?left_asset={parallel_source[0][1].id}")
    assert response.status_code == 200
    assert response.data["count"] is None and response.data["results"] == []
    assert response["Cache-Control"] == "no-store"


def test_public_list_rechecks_at_most_twenty_candidates_per_request(api_client, reader_user, parallel_source, monkeypatch):
    left, right = parallel_source
    for _ in range(21):
        ParallelCalibration.objects.create(user=reader_user, left_asset=left[1], right_asset=right[1],
            scope="bibliography", status="published")
    checked = []

    def current_output(record, user, *, public=False):
        assert public is True
        checked.append(record.id)
        return None  # This page's candidates were withdrawn; still offer the next page.

    monkeypatch.setattr(service, "calibration_output", current_output)
    response = api_client.get(f"/api/reading/parallel-calibrations/public/?left_asset={left[1].id}")
    assert response.status_code == 200 and len(checked) == 20
    assert response.data["count"] is None and response.data["results"] == []
    assert response.data["next"] and response.data["notice"]
