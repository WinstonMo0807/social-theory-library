"""Deferred invitation acceptance and authority scenarios; not run in development."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import account_activation
from accounts.models import User
from ingestion.models import AuditEvent

BASE = "/api/auth/users/"
ACTIVATION = "/api/auth/activation/"


def administrator(user):
    client = APIClient()
    client.force_authenticate(user)
    client.credentials(HTTP_X_EDITOR_OWNER=str(user.pk))
    return client


def issue_command(client, payload):
    preview = client.post(BASE + "preview/", payload, format="json")
    assert preview.status_code == 200, preview.data
    command = {**payload, "confirmed": True, "request_id": str(uuid4()), "preview_hash": preview.data["preview_hash"]}
    response = client.post(BASE + "command/", command, format="json")
    assert response.status_code == 200, response.data
    return response.data


def new_invitation(client):
    receipt = issue_command(client, {"operation": "create", "username": "invite_reader", "email": "invite@example.invalid",
        "display_name": "受邀读者", "role": "reader", "is_active": False, "invite": True})
    target = User.objects.get(pk=receipt["user_id"])
    response = client.get(BASE + f"{target.pk}/invitation/")
    assert response.status_code == 200 and response.data["token"]
    return target, response.data["token"]


@pytest.mark.django_db
def test_invitation_uses_existing_account_and_cannot_reset_accepted_password(admin_user, reader_user, settings):
    settings.JWT_COOKIE_AUTH_ENABLED = False
    client = administrator(admin_user)
    old_identity = (reader_user.pk, reader_user.password, reader_user.role, reader_user.token_version)
    target, token = new_invitation(client)
    assert not target.is_active and not target.has_usable_password()
    pending = client.get(BASE + "workspace/?state=pending_activation").data["results"]
    assert [row["id"] for row in pending] == [target.pk]
    public = APIClient()
    assert public.post(ACTIVATION, {"action": "inspect", "token": token}, format="json").data["state"] == "ready"
    payload = {"action": "activate", "token": token, "password": "Distinct-Reading-42!", "confirmed": True}
    applied = public.post(ACTIVATION, payload, format="json")
    assert applied.status_code == 200 and applied.data["state"] == "activated"
    target.refresh_from_db()
    assert target.is_active and target.check_password(payload["password"]) and target.email_verified_at is None
    password_hash, token_version = target.password, target.token_version
    repeated = public.post(ACTIVATION, {**payload, "password": "Different-Replay-43!"}, format="json")
    assert repeated.data["state"] == "activated"
    target.refresh_from_db()
    assert (target.password, target.token_version) == (password_hash, token_version)
    assert AuditEvent.objects.filter(action="account_activate", object_id=str(target.pk)).count() == 1
    assert payload["password"] not in str(list(AuditEvent.objects.values("before", "after")))
    reader_user.refresh_from_db()
    assert (reader_user.pk, reader_user.password, reader_user.role, reader_user.token_version) == old_identity
    assert public.get(BASE + f"{target.pk}/invitation/").status_code in {401, 403}


@pytest.mark.django_db
def test_expiry_renewal_revocation_and_ordinary_disabled_accounts(admin_user, reader_user, settings):
    settings.JWT_COOKIE_AUTH_ENABLED = False
    client = administrator(admin_user)
    target, old_token = new_invitation(client)
    event = account_activation.latest(target)
    event.after["activation_expires_at"] = (timezone.now() - timedelta(seconds=1)).isoformat()
    event.save(update_fields=["after"])
    assert account_activation.inspect(old_token)["state"] == "expired"
    snapshot = client.get(BASE + f"workspace/?user_id={target.pk}").data["selected"]
    issue_command(client, {"operation": "invite", "user_id": target.pk, "expected_version": snapshot["version"]})
    current = client.get(BASE + f"{target.pk}/invitation/").data
    assert current["token"] != old_token and account_activation.inspect(old_token)["state"] == "unavailable"
    snapshot = client.get(BASE + f"workspace/?user_id={target.pk}").data["selected"]
    issue_command(client, {"operation": "revoke_invite", "user_id": target.pk, "expected_version": snapshot["version"]})
    assert account_activation.inspect(current["token"])["state"] == "unavailable"
    target.refresh_from_db()
    assert not target.is_active and not target.has_usable_password()
    reader_user.is_active = False
    reader_user.save(update_fields=["is_active"])
    directory = client.get(BASE + "workspace/?state=inactive").data["results"]
    assert {row["id"] for row in directory} == {target.pk, reader_user.pk}
    snapshot = next(row for row in directory if row["id"] == reader_user.pk)
    refused = client.post(BASE + "preview/", {"operation": "invite", "user_id": reader_user.pk, "expected_version": snapshot["version"]}, format="json")
    assert refused.status_code == 400


@pytest.mark.django_db
def test_changed_account_or_issuer_cannot_activate_stale_invitation(admin_user, settings):
    settings.JWT_COOKIE_AUTH_ENABLED = False
    client = administrator(admin_user)
    target, token = new_invitation(client)
    snapshot = client.get(BASE + f"workspace/?user_id={target.pk}").data["selected"]
    issue_command(client, {"operation": "update", "user_id": target.pk, "expected_version": snapshot["version"], "display_name": "已核对新名称"})
    assert account_activation.inspect(token)["state"] == "unavailable"
    snapshot = client.get(BASE + f"workspace/?user_id={target.pk}").data["selected"]
    issue_command(client, {"operation": "invite", "user_id": target.pk, "expected_version": snapshot["version"]})
    token = client.get(BASE + f"{target.pk}/invitation/").data["token"]
    admin_user.is_active = False
    admin_user.save(update_fields=["is_active"])
    response = APIClient().post(ACTIVATION, {"action": "activate", "token": token, "password": "Unused-Reading-45!", "confirmed": True}, format="json")
    assert response.data["state"] == "unavailable"
    target.refresh_from_db()
    assert not target.is_active and not target.has_usable_password()
