"""Deferred acceptance: unknown private requests must not create late duplicate work."""
from uuid import uuid4

import pytest
from django.urls import reverse
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User
from ingestion.models import AuditEvent
from reading import privacy, research
from reading.models import ReaderDataOperation
from tests.test_confirmed_memory_atlas_20261018 import memory_for

pytestmark = pytest.mark.django_db


def test_stopped_request_cannot_arrive_late_and_is_owner_scoped(reader_user, admin_user):
    key = uuid4()
    assert privacy.stop_request(reader_user, key)["state"] == "cancelled"
    assert privacy.stop_request(reader_user, key)["state"] == "cancelled"
    assert AuditEvent.objects.filter(actor=reader_user, action=privacy.REQUEST_STOPPED, request_id=str(key)).count() == 1
    with pytest.raises(research.ResearchConflict):
        privacy.create_operation(reader_user, {"request_id": str(key), "kind": "export", "categories": ["notes"]})
    assert not ReaderDataOperation.objects.filter(user=reader_user, request_id=key).exists()
    with pytest.raises(NotFound):
        privacy.request_receipt(admin_user, key)
    assert privacy.stop_request(admin_user, key)["owner_id"] == str(admin_user.pk)


def test_created_erasure_preview_is_returned_without_cancellation_or_erasure(reader_user):
    memory = memory_for(reader_user)
    key = uuid4()
    data = {"request_id": str(key), "kind": "erase", "targets": [privacy.target_of(memory, "memories")]}
    operation = privacy.create_operation(reader_user, data)
    receipt = privacy.stop_request(reader_user, key)
    assert receipt["state"] == "applied" and receipt["operation_id"] == str(operation.pk)
    operation.refresh_from_db()
    assert operation.status == "preview"
    assert memory.__class__.objects.filter(pk=memory.pk).exists()
    assert privacy.create_operation(reader_user, data).pk == operation.pk
    assert not AuditEvent.objects.filter(actor=reader_user, action=privacy.REQUEST_STOPPED, request_id=str(key)).exists()


@pytest.mark.parametrize("change", [{"is_active": False}, {"token_version": 9}])
def test_changed_account_cannot_prepare_stop_or_change_retention(reader_user, change):
    User.objects.filter(pk=reader_user.pk).update(**change)
    with pytest.raises(PermissionDenied):
        privacy.stop_request(reader_user, uuid4())
    with pytest.raises(PermissionDenied):
        privacy.create_operation(reader_user, {"request_id": str(uuid4()), "kind": "export", "categories": ["notes"]})
    with pytest.raises(PermissionDenied):
        privacy.update_preferences(reader_user, {"expected_revision": 1, "retention": {"search_history": True}})


def test_receipt_requires_current_owner_and_strict_stop_action(api_client, reader_user, admin_user):
    key = uuid4()
    privacy.stop_request(reader_user, key)
    url = reverse("reader-privacy-request", kwargs={"request_id": key})
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    response = api_client.get(url, HTTP_X_READER_OWNER=str(reader_user.pk))
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert api_client.post(url, {"action": "cancel_pending", "owner": admin_user.pk}, format="json", HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 400
    api_client.force_authenticate(admin_user)
    assert api_client.get(url, HTTP_X_READER_OWNER=str(admin_user.pk)).status_code == 404
