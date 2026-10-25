"""Deferred acceptance for lost research responses, always within one owner/project."""
from uuid import uuid4

import pytest

from reading import research
from reading.models import ResearchTurn

pytestmark = pytest.mark.django_db


def test_lookup_and_replay_original_request(api_client, reader_user, admin_user, monkeypatch):
    monkeypatch.setattr("reading.tasks.enqueue_research_turn", lambda *args: None)
    project = research.create_project(reader_user, {"request_id": str(uuid4()), "title": "合成回执研究"})
    api_client.force_authenticate(reader_user)
    api_client.credentials(HTTP_X_READER_OWNER=str(reader_user.pk))
    endpoint = f"/api/reading/research-projects/{project.id}/turns/"
    data = {"expected_revision": project.revision, "request_id": str(uuid4()), "question": "需要核对哪些条件", "scope": {"kind": "library"}}
    assert api_client.get(endpoint, {"request_id": data["request_id"]}).data["results"] == []
    first = api_client.post(endpoint, data, format="json")
    receipt = api_client.get(endpoint, {"request_id": data["request_id"]})
    assert first.status_code == 202 and receipt.status_code == 200
    assert receipt.data["count"] == 1 and receipt.data["results"][0]["id"] == first.data["id"]
    assert receipt.data["results"][0]["request_id"] == data["request_id"]
    again = api_client.post(endpoint, data, format="json")
    assert again.status_code == 202 and again.data["id"] == first.data["id"]
    assert ResearchTurn.objects.filter(project=project).count() == 1
    other = research.create_project(reader_user, {"request_id": str(uuid4())})
    assert api_client.get(f"/api/reading/research-projects/{other.id}/turns/", {"request_id": data["request_id"]}).data["results"] == []
    api_client.force_authenticate(admin_user)
    assert api_client.get(endpoint, {"request_id": data["request_id"]}).status_code == 403
    api_client.credentials(HTTP_X_READER_OWNER=str(admin_user.pk))
    assert api_client.get(endpoint, {"request_id": data["request_id"]}).status_code == 404


def test_lookup_rejects_invalid_request_identity(api_client, reader_user):
    project = research.create_project(reader_user, {"request_id": str(uuid4())})
    api_client.force_authenticate(reader_user)
    result = api_client.get(f"/api/reading/research-projects/{project.id}/turns/", {"request_id": "not-a-uuid"})
    assert result.status_code == 400
