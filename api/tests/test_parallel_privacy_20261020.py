"""Parallel notes privacy integration; authored for the unified acceptance run."""
from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from reading import parallel_reading, privacy, research
from reading.parallel_models import ParallelCalibration, ParallelReadingReceipt, ParallelReadingTask
from reading.privacy_serializers import PrivacyTargetInput
from tests.test_parallel_sources_20261020 import publish, ref
from tests.test_privacy_atlas_20261018 import command, operation, run

pytestmark = pytest.mark.django_db


def task_for(user):
    work, left, left_asset, left_page = publish(text="Synthetic original paragraph")
    _, right, right_asset, right_page = publish(work, primary=False, text="Synthetic second version paragraph")
    data = {
        "left_asset_id": str(left_asset.id), "right_asset_id": str(right_asset.id),
        "left_document_revision_id": str(left.active_catalog_revision.document_revision_id),
        "right_document_revision_id": str(right.active_catalog_revision.document_revision_id),
        "positions": {"left_page": 1, "right_page": 1}, "sync_scroll": True,
        "alignments": [{"id": str(uuid4()), "left": ref(left, left_asset, left_page),
                        "right": ref(right, right_asset, right_page), "status": "confirmed", "note": "合成私人对齐笔记"}],
        "terms": [{"id": str(uuid4()), "original": "Synthetic term", "translation": "合成术语",
                   "note": "合成私人术语说明"}],
    }
    result = parallel_reading.create_task(user, {"request_id": str(uuid4()), "data": data})
    return ParallelReadingTask.objects.get(pk=result["id"]), data, left, right


def test_personal_notes_and_export_include_only_owned_parallel_tasks(reader_user, admin_user):
    own, _, _, _ = task_for(reader_user)
    other, _, _, _ = task_for(admin_user)
    public = parallel_reading.create_calibration(reader_user, {
        "request_id": str(uuid4()), "task_id": str(own.id), "expected_revision": own.revision,
        "scope": "bibliography", "basis": "合成的独立公共投稿依据",
    })
    summary = privacy.privacy_summary(reader_user)
    assert "parallel_alignments" not in summary["retention"]
    assert summary["export_counts"]["notes"] == summary["erase_counts"]["personal_notes"] == 1
    listed = privacy.list_items(reader_user, "personal_notes")["results"]
    assert [(row["id"], row["category"]) for row in listed] == [(str(own.id), "parallel_alignments")]
    job = operation(reader_user, categories=["notes"])
    assert [(row["id"], row["category"]) for row in research.unpack(job)["targets"]] == [(str(own.id), "parallel_alignments")]
    assert str(other.id) not in str(research.unpack(job)) and public["id"] not in str(research.unpack(job))
    with pytest.raises(NotFound):
        operation(reader_user, "erase", targets=[privacy.target_of(other, "parallel_alignments")])


def test_parallel_export_rechecks_withdrawn_source_and_keeps_authored_notes(reader_user):
    own, _, left, _ = task_for(reader_user)
    job = operation(reader_user, categories=["notes"])
    assert run(job)["completed"] == 1
    available = privacy.download_operation(reader_user, job.id)["records"][0]["record"]
    assert available["data"]["alignments"][0]["left"]["quote"] == "Synthetic original paragraph"
    left.state = "withdrawn"
    left.save(update_fields=["state"])
    downloaded = privacy.download_operation(reader_user, job.id)["records"][0]["record"]
    assert downloaded["pair_sources"] is None and downloaded["source_available"] is False
    assert downloaded["data"]["alignments"][0]["left"]["quote"] == ""
    assert downloaded["data"]["alignments"][0]["right"]["quote"] == ""
    assert downloaded["data"]["alignments"][0]["note"] == "合成私人对齐笔记"
    assert downloaded["data"]["terms"][0]["note"] == "合成私人术语说明"
    described = privacy.describe_item(reader_user, "parallel_alignments", own)
    assert described["title"] == "来源当前不可用的私人并读记录"
    assert "Synthetic original paragraph" not in str(described)


def test_parallel_erasure_keeps_only_replay_guard_and_preserves_public_record_and_account(reader_user):
    own, data, left, right = task_for(reader_user)
    public = parallel_reading.create_calibration(reader_user, {
        "request_id": str(uuid4()), "task_id": str(own.id), "expected_revision": own.revision,
        "scope": "bibliography", "basis": "合成公共书目级校准",
    })
    submission = ParallelCalibration.objects.get(pk=public["id"])
    original_public = bytes(submission.data_ciphertext), submission.revision, submission.status
    account = reader_user.id, reader_user.password, reader_user.role
    receipt = ParallelReadingReceipt.objects.get(task=own)
    saved_nonce = receipt.request_id
    job = operation(reader_user, "erase", targets=[privacy.target_of(own, "parallel_alignments")])
    preview = privacy.operation_output(job)["preview"][0]
    assert "公共校准记录独立保留" in preview["impact"]["message"]
    assert run(command(reader_user, job, "confirm"))["completed"] == 1
    assert not ParallelReadingTask.objects.filter(pk=own.id).exists()
    receipt.refresh_from_db()
    assert receipt.task_id is None and receipt.request_id == saved_nonce
    with pytest.raises(NotFound):
        parallel_reading.task_by_request(reader_user, saved_nonce)
    with pytest.raises(research.ResearchConflict):
        parallel_reading.create_task(reader_user, {"request_id": str(saved_nonce), "data": data})
    assert privacy.privacy_summary(reader_user)["export_counts"]["notes"] == 0
    submission.refresh_from_db()
    assert (bytes(submission.data_ciphertext), submission.revision, submission.status) == original_public
    assert left.assets.exists() and right.assets.exists()
    reader_user.refresh_from_db()
    assert (reader_user.id, reader_user.password, reader_user.role) == account


def test_new_revision_invalidates_parallel_delete_preview(reader_user):
    own, data, _, _ = task_for(reader_user)
    job = operation(reader_user, "erase", targets=[privacy.target_of(own, "parallel_alignments")])
    revised = deepcopy(data)
    revised["terms"][0]["note"] = "预览后修改的私人说明"
    parallel_reading.update_task(reader_user, own.id, {
        "request_id": str(uuid4()), "expected_revision": own.revision, "data": revised,
    })
    with pytest.raises(research.ResearchConflict):
        command(reader_user, job, "confirm")
    own.refresh_from_db()
    assert research.unpack(own)["terms"][0]["note"] == "预览后修改的私人说明"


def test_notes_retention_blocks_new_parallel_save_but_preserves_edit(reader_user):
    own, data, _, _ = task_for(reader_user)
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"],
        "retention": {"personal_notes": False}})
    with pytest.raises(ValidationError):
        parallel_reading.create_task(reader_user, {"request_id": str(uuid4()), "data": data})
    revised = deepcopy(data)
    revised["alignments"][0]["note"] = "关闭新建后的已有记录编辑"
    saved = parallel_reading.update_task(reader_user, own.id, {
        "request_id": str(uuid4()), "expected_revision": own.revision, "data": revised,
    })
    assert saved["data"]["alignments"][0]["note"] == "关闭新建后的已有记录编辑"


def test_privacy_target_accepts_private_parallel_leaf_but_not_public_calibration():
    target = {"id": str(uuid4()), "revision": "1"}
    assert PrivacyTargetInput(data={**target, "category": "parallel_alignments"}).is_valid()
    assert not PrivacyTargetInput(data={**target, "category": "parallel_calibrations"}).is_valid()
