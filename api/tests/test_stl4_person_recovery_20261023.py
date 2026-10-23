"""Deferred recovery coverage; no runtime execution during implementation."""
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Person
from catalog.services.person_authority import FIELDS, digest, state


@pytest.mark.django_db
def test_person_stop_prevents_late_save_and_returns_applied_receipt():
    actor = User.objects.create_user(username="person-recovery", role="admin")
    person = Person.objects.create(preferred_name="原规范名称", authority_status="draft")
    client = APIClient(); client.force_authenticate(actor)
    headers = {"HTTP_X_EDITOR_OWNER": str(actor.pk)}
    base = "/api/catalog/admin/people/workspace/"
    values = {key: getattr(person, key) for key in FIELDS}
    values["authority_note"] = "新增核对说明"
    payload = {"operation": "update", "person_id": str(person.pk), "expected_version": digest(state(person)),
        "values": values, "variants": [], "reason": "核对来源"}
    preview = client.post(f"{base}preview/", payload, format="json", **headers)
    assert preview.status_code == 200
    request_id = str(uuid4())
    command = {**payload, "request_id": request_id, "confirmed": True, "preview_hash": preview.data["preview_hash"]}
    stopped = client.post(f"{base}receipts/{request_id}/", {"action": "cancel_pending"}, format="json", **headers)
    assert stopped.status_code == 200 and stopped.data["state"] == "cancelled" and stopped.data["person_id"] is None
    assert client.post(f"{base}command/", command, format="json", **headers).data == stopped.data
    person.refresh_from_db()
    assert person.authority_note == ""
    command["request_id"] = str(uuid4())
    saved = client.post(f"{base}command/", command, format="json", **headers)
    assert saved.status_code == 200 and saved.data["state"] == "applied"
    assert client.post(f"{base}receipts/{command['request_id']}/", {"action": "cancel_pending"}, format="json", **headers).data == saved.data
    other = User.objects.create_user(username="other-person-recovery", role="admin")
    client.force_authenticate(other)
    assert client.post(f"{base}receipts/{command['request_id']}/", {"action": "cancel_pending"}, format="json",
        HTTP_X_EDITOR_OWNER=str(other.pk)).status_code == 409
    assert client.get(f"{base}receipts/{command['request_id']}/", HTTP_X_EDITOR_OWNER=str(other.pk)).status_code == 404
