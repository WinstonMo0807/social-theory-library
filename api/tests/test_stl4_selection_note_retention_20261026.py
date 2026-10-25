"""Deferred acceptance: removing selections must not erase authored notes."""
from uuid import uuid4

import pytest

from reading import research
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def test_notes_outlive_undo_window_and_source_lookup_stays_private(api_client, reader_user, admin_user):
    _, _, spans, _ = fixture_source(count=52)
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    project = research.change_selection(reader_user, project.pk, {"expected_revision": project.revision, "action": "add",
        "references": [{"evidence_span_id": str(span.pk)} for span in spans], "note": "本人逐页备注"})
    legacy = research.unpack(project)
    legacy.pop("selection_note_sources")
    project = research.save_data(project, legacy)
    project = research.change_selection(reader_user, project.pk, {"expected_revision": project.revision, "action": "apply",
        "expected_owner_id": reader_user.pk, "request_id": str(uuid4()), "additions": [], "removals": [str(span.pk) for span in spans]})
    saved = research.unpack(project)
    assert len(saved["removed_selections"]) == 50
    assert len(saved["selection_notes"]) == len(saved["selection_note_sources"]) == 52
    assert not saved["selections"]
    assert all("quote" not in value and "title" not in value for value in saved["selection_note_sources"].values())
    projection = research.serialize_record(project, reader_user)["data"]
    assert projection["selection_note_sources"][str(spans[0].pk)]["source_status"] == "unverified"
    api_client.force_authenticate(reader_user)
    endpoint = f"/api/reading/research-projects/{project.pk}/selection-note-source/"
    response = api_client.get(endpoint, {"reference_id": str(spans[0].pk)})
    assert response.status_code == 200 and response.data["source_status"] == "available"
    assert "quote" not in response.data and "text" not in response.data
    api_client.force_authenticate(admin_user)
    assert api_client.get(endpoint, {"reference_id": str(spans[0].pk)}).status_code == 404


def test_reselected_page_does_not_rebind_older_note_to_changed_text(reader_user):
    _, asset, spans, _ = fixture_source(count=1)
    raw = {"asset_id": str(asset.pk), "document_revision_id": str(spans[0].document_revision_id), "pdf_page": 1}
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    project = research.change_selection(reader_user, project.pk, {"expected_revision": project.revision, "action": "add", "references": [raw], "note": "旧原文上的判断"})
    key = research.reference_identity(raw)
    original_source = research.unpack(project)["selection_note_sources"][key]
    project = research.change_selection(reader_user, project.pk, {"expected_revision": project.revision, "action": "remove", "reference_id": key})
    page = spans[0].page
    page.text = "已修改的同页文字，不应变成旧备注的依据。"
    page.save(update_fields=["text"])
    project = research.change_selection(reader_user, project.pk, {"expected_revision": project.revision, "action": "add", "references": [raw]})
    assert research.unpack(project)["selection_note_sources"][key] == original_source
    assert research.selection_note_source(project, reader_user, key)["source_status"] == "unavailable"
    assert research.serialize_record(project, reader_user)["data"]["selections"][0]["source_status"] == "available"
    assert research.unpack(project)["selection_notes"][key] == "旧原文上的判断"
