"""Deferred account recovery scenarios; authored, not executed during development."""
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from ingestion.models import AuditEvent


@pytest.mark.django_db
def test_stop_serializes_with_original_account_command_and_preserves_applied_result():
    actor = User.objects.create_user(username="account-recovery-admin", email="ar-admin@example.invalid", role="admin")
    reader = User.objects.create_user(username="account-recovery-reader", email="ar-reader@example.invalid", display_name="原显示名")
    client = APIClient()
    client.force_authenticate(actor)
    headers = {"HTTP_X_EDITOR_OWNER": str(actor.pk)}
    base = "/api/auth/users/"
    snapshot = client.get(f"{base}workspace/?user_id={reader.pk}", **headers).data["selected"]
    payload = {"operation": "update", "user_id": reader.pk, "expected_version": snapshot["version"], "display_name": "已核对显示名"}
    preview = client.post(f"{base}preview/", payload, format="json", **headers)
    assert preview.status_code == 200
    request_id = str(uuid4())
    command = {**payload, "request_id": request_id, "confirmed": True, "preview_hash": preview.data["preview_hash"]}
    stop = {"request_id": request_id, "action": "cancel_pending"}
    cancelled = client.post(f"{base}receipt/", stop, format="json", **headers)
    assert cancelled.status_code == 200 and cancelled.data["state"] == "cancelled"
    assert client.post(f"{base}command/", command, format="json", **headers).status_code == 409
    reader.refresh_from_db()
    assert reader.display_name == "原显示名" and reader.token_version == 0
    assert client.get(f"{base}receipt/?request_id={request_id}", **headers).data == cancelled.data
    command["request_id"] = str(uuid4())
    applied = client.post(f"{base}command/", command, format="json", **headers)
    assert applied.status_code == 200 and applied.data["state"] == "applied"
    count = AuditEvent.objects.count()
    stop["request_id"] = command["request_id"]
    assert client.post(f"{base}receipt/", stop, format="json", **headers).data == applied.data
    assert AuditEvent.objects.count() == count
    reader.refresh_from_db()
    assert reader.display_name == "已核对显示名"
    other = User.objects.create_user(username="other-account-admin", email="ar-other@example.invalid", role="admin")
    client.force_authenticate(other)
    other_headers = {"HTTP_X_EDITOR_OWNER": str(other.pk)}
    assert client.get(f"{base}receipt/?request_id={command['request_id']}", **other_headers).status_code == 404
    assert client.post(f"{base}receipt/", stop, format="json", **other_headers).status_code == 409
