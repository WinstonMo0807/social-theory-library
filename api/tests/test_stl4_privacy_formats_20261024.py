"""Deferred acceptance for the PDF privacy export format choices; not run in development."""
import csv
import io
import json
from uuid import uuid4
from zipfile import ZipFile

import pytest
from rest_framework.exceptions import NotFound, ValidationError

from reading import privacy, privacy_exports, research
from tests.test_confirmed_memory_atlas_20261018 import memory_for


def payload():
    return {"schema_version": 1, "owner_id": "1", "operation_id": str(uuid4()), "prepared_at": "2026-10-24T00:00:00Z", "downloaded_at": "2026-10-24T00:01:00Z",
        "records": [{"id": str(uuid4()), "category": "memories", "revision": "3", "record": {"data": {"title": "=SUM(1,2)", "body": "中文私人笔记\n含逗号,与引号\""}}}],
        "failed": [{"id": str(uuid4()), "category": "notes", "error_code": "revision_changed"}],
        "unavailable_since_preparation": [{"id": str(uuid4()), "category": "plans", "reason": "资料已变化"}], "notice": "不含原件"}


def test_zip_keeps_complete_records_and_failure_manifest_without_user_paths():
    value = payload()
    body, mime = privacy_exports.render(value, "zip")
    assert mime == "application/zip"
    with ZipFile(io.BytesIO(body)) as archive:
        path = f"memories/{value['records'][0]['id']}.json"
        assert set(archive.namelist()) == {path, "manifest.json", "说明.txt"}
        assert json.loads(archive.read(path)) == value["records"][0]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["failed"] == value["failed"]
        assert manifest["unavailable_since_preparation"] == value["unavailable_since_preparation"]
        assert manifest["files"][0]["revision"] == "3"
    value["records"][0]["category"] = "../../escape"
    with pytest.raises(ValidationError):
        privacy_exports.render(value, "zip")


def test_csv_preserves_full_json_unicode_and_neutralizes_formula_titles():
    value = payload()
    body, mime = privacy_exports.render(value, "csv")
    assert mime.startswith("text/csv") and body.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(io.StringIO(body.decode("utf-8-sig"))))
    assert rows[1][4] == "'=SUM(1,2)"
    assert json.loads(rows[1][6]) == value["records"][0]["record"]
    assert rows[2][0] == "准备未完成" and rows[3][0] == "下载时已变化"


def test_read_time_is_not_a_source_revision_but_withdrawal_is():
    value = payload()
    value["records"][0].update(category="source_follows", record={"source": {"checked_at": "first", "status": "available"}})
    before = privacy_exports.snapshot_digest(value)
    value["records"][0]["record"]["source"]["checked_at"] = "second"
    assert before == privacy_exports.snapshot_digest(value)
    value["records"][0]["record"]["source"]["status"] = "unavailable"
    assert before != privacy_exports.snapshot_digest(value)


@pytest.mark.django_db
def test_download_uses_existing_owner_task_and_rejects_changes_during_render(reader_user, admin_user, monkeypatch):
    memory = memory_for(reader_user)
    task = privacy.create_operation(reader_user, {"request_id": str(uuid4()), "kind": "export", "targets": [privacy.target_of(memory, "memories")]})
    privacy.run_operation(task.pk, task.generation, task.task_id)
    response = privacy_exports.download(reader_user, task.pk, "zip")
    assert response["X-Reader-Owner"] == str(reader_user.pk)
    assert response["X-Privacy-Operation"] == str(task.pk)
    with pytest.raises(NotFound):
        privacy_exports.download(admin_user, task.pk, "zip")
    original = privacy_exports.render
    def render_then_change(value, format_):
        result = original(value, format_)
        research.update_memory(reader_user, memory.pk, {"expected_revision": memory.revision, "body": "导出格式化途中修改"})
        return result
    monkeypatch.setattr(privacy_exports, "render", render_then_change)
    with pytest.raises(research.ResearchConflict):
        privacy_exports.download(reader_user, task.pk, "csv")
