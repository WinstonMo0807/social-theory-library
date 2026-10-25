"""Deferred offline selection acceptance; never run during the current development stage."""
from uuid import uuid4

import pytest

from reading import research
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def prepared(user):
    _, _, spans, _ = fixture_source(count=3)
    project = research.create_project(user, {"request_id": str(uuid4())})
    project = research.change_selection(user, project.pk, {"expected_revision": project.revision,
        "action": "add", "references": [{"evidence_span_id": str(spans[0].pk)}]})
    project = research.update_project(user, project.pk, {"expected_revision": project.revision, "notes": "本人原有笔记"})
    body = {"expected_owner_id": user.pk, "expected_revision": project.revision, "request_id": str(uuid4()),
        "action": "apply", "additions": [{"evidence_span_id": str(spans[1].pk)}], "removals": [str(spans[0].pk)]}
    return project, spans, body


def test_atomic_selection_sync_and_original_receipt(api_client, reader_user, admin_user):
    project, spans, body = prepared(reader_user)
    api_client.force_authenticate(reader_user)
    endpoint = f"/api/reading/research-projects/{project.pk}/selections/"
    first = api_client.post(endpoint, body, format="json")
    again = api_client.post(endpoint, body, format="json")
    assert first.status_code == again.status_code == 200
    assert first.data["revision"] == again.data["revision"]
    assert first.data["data"]["selection_receipts"] == [body["request_id"]]
    assert [item["reference_id"] for item in first.data["data"]["selections"]] == [str(spans[1].pk)]
    assert first.data["data"]["notes"] == "本人原有笔记"
    changed = {**body, "additions": [{"evidence_span_id": str(spans[2].pk)}]}
    assert api_client.post(endpoint, changed, format="json").status_code == 409
    api_client.force_authenticate(admin_user)
    assert api_client.post(endpoint, body, format="json").status_code == 403
    assert api_client.post(endpoint, {**body, "expected_owner_id": admin_user.pk}, format="json").status_code == 404


def test_one_withdrawn_source_keeps_entire_batch_and_receipt_unsaved(api_client, reader_user):
    project, spans, body = prepared(reader_user)
    before = research.unpack(project)
    spans[2].is_stale = True
    spans[2].save(update_fields=["is_stale"])
    body["additions"].append({"evidence_span_id": str(spans[2].pk)})
    api_client.force_authenticate(reader_user)
    result = api_client.post(f"/api/reading/research-projects/{project.pk}/selections/", body, format="json")
    assert result.status_code == 400
    project.refresh_from_db()
    assert research.unpack(project) == before and project.revision == body["expected_revision"]


def test_changed_revision_and_conflicting_intents_never_partially_apply(api_client, reader_user):
    project, _, body = prepared(reader_user)
    project = research.update_project(reader_user, project.pk, {"expected_revision": project.revision, "notes": "另一端更新"})
    before = research.unpack(project)
    api_client.force_authenticate(reader_user)
    endpoint = f"/api/reading/research-projects/{project.pk}/selections/"
    assert api_client.post(endpoint, body, format="json").status_code == 409
    same_reference = {**body, "expected_revision": project.revision, "removals": [body["additions"][0]["evidence_span_id"]]}
    assert api_client.post(endpoint, same_reference, format="json").status_code == 409
    project.refresh_from_db()
    assert research.unpack(project) == before


def test_legacy_single_selection_request_keeps_its_original_fingerprint(api_client, reader_user):
    project, spans, _ = prepared(reader_user)
    body = {"expected_revision": project.revision, "request_id": str(uuid4()), "action": "add", "references": [{"evidence_span_id": str(spans[2].pk)}]}
    project = research.change_selection(reader_user, project.pk, body)
    old_fingerprint = research.request_fingerprint(body, ("action", "references", "reference_id", "order", "note", "notes"))
    assert research.unpack(project)["selection_requests"][-1]["fingerprint"] == old_fingerprint
    api_client.force_authenticate(reader_user)
    result = api_client.post(f"/api/reading/research-projects/{project.pk}/selections/", body, format="json")
    assert result.status_code == 200 and result.data["revision"] == project.revision
