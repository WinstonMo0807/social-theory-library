"""Deferred R31 mail/credential/appeal acceptance. Never run during source implementation."""
import json
from datetime import timedelta
from urllib.parse import urlsplit, parse_qs
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts import email_links
from accounts.models import RecoveryCode
from accounts.email_link_views import AccountRecoveryAppealInput, AccountRecoveryAppealView
from reading.services import encrypt_private_text, decrypt_private_text

pytestmark = pytest.mark.django_db


def issue(user, purpose, settings, monkeypatch):
    settings.DEBUG = True
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.PUBLIC_WEB_URL = "https://library.example.invalid"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    mail = []
    monkeypatch.setattr(email_links, "send_mail", lambda *args, **kwargs: mail.append(args) or 1)
    payload = encrypt_private_text(json.dumps({"email": user.email, "purpose": purpose,
        "next": "/account/research/?turn=original", "requested_at": timezone.now().isoformat()})).decode("ascii")
    email_links.deliver(payload)
    assert len(mail) == 1
    link = next(line for line in mail[0][1].splitlines() if line.startswith("https://"))
    assert "token=" not in urlsplit(link).query
    return parse_qs(urlsplit(link).fragment)["token"][0]


def test_single_use_and_purpose_isolation_preserve_original_account(reader_user, settings, monkeypatch):
    password, version, role = reader_user.password, reader_user.token_version, reader_user.role
    token = issue(reader_user, RecoveryCode.Purpose.VERIFY_EMAIL, settings, monkeypatch)
    row = RecoveryCode.objects.get(pk=token.split(":")[0])
    assert token.split(":")[1] not in row.code_hash
    assert timedelta(hours=23) < row.expires_at - timezone.now() <= timedelta(hours=24)
    assert email_links.operate(token, row.purpose, "inspect")["state"] == "ready"
    with pytest.raises(ValidationError):
        email_links.operate(token, RecoveryCode.Purpose.PASSWORD_LINK, "confirm", "unrelated-example")
    with pytest.raises(ValidationError):
        email_links.operate(token, row.purpose, "confirm", "not-the-account-password")
    assert email_links.operate(token, row.purpose, "confirm", "Reader-Secure-Password-2026")["state"] == "completed"
    assert email_links.operate(token, row.purpose, "confirm")["state"] == "completed"
    reader_user.refresh_from_db()
    assert reader_user.email_verified_at
    assert (reader_user.password, reader_user.token_version, reader_user.role) == (password, version, role)


def test_reset_is_idempotent_revokes_credentials_and_cannot_use_changed_account(reader_user, settings, monkeypatch):
    token = issue(reader_user, RecoveryCode.Purpose.PASSWORD_LINK, settings, monkeypatch)
    version = reader_user.token_version
    password = "Synthetic-Account-Only-2026!"
    assert email_links.operate(token, RecoveryCode.Purpose.PASSWORD_LINK, "confirm", password)["state"] == "completed"
    assert email_links.operate(token, RecoveryCode.Purpose.PASSWORD_LINK, "confirm", "different-valid-input!")["state"] == "completed"
    reader_user.refresh_from_db()
    assert reader_user.check_password(password) and reader_user.token_version == version + 1
    second = issue(reader_user, RecoveryCode.Purpose.PASSWORD_LINK, settings, monkeypatch)
    reader_user.is_active = False
    reader_user.save(update_fields=["is_active"])
    assert email_links.operate(second, RecoveryCode.Purpose.PASSWORD_LINK, "inspect")["state"] == "unavailable"


def test_new_link_invalidates_old_and_delivery_failure_does_not_claim_success(reader_user, settings, monkeypatch):
    first = issue(reader_user, RecoveryCode.Purpose.PASSWORD_LINK, settings, monkeypatch)
    second = issue(reader_user, RecoveryCode.Purpose.PASSWORD_LINK, settings, monkeypatch)
    assert email_links.operate(first, RecoveryCode.Purpose.PASSWORD_LINK, "inspect")["state"] == "expired"
    assert email_links.operate(second, RecoveryCode.Purpose.PASSWORD_LINK, "inspect")["state"] == "ready"
    monkeypatch.setattr(email_links, "send_mail", lambda *a, **k: 0)
    payload = encrypt_private_text(json.dumps({"email": reader_user.email, "purpose": RecoveryCode.Purpose.PASSWORD_LINK,
        "requested_at": timezone.now().isoformat()})).decode("ascii")
    with pytest.raises(email_links.MailUnavailable):
        email_links.deliver(payload)
    assert not reader_user.recovery_codes.filter(used_at__isnull=True, expires_at__gt=timezone.now()).exists()


def test_queue_has_no_plaintext_identity_or_link_and_console_is_not_delivery(settings, monkeypatch):
    from accounts.tasks import deliver_account_link
    settings.DEBUG = True
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.PUBLIC_WEB_URL = "https://library.example.invalid"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    cache.clear()
    calls = []
    monkeypatch.setattr(deliver_account_link, "apply_async", lambda **kwargs: calls.append(kwargs))
    email_links.enqueue("absent@example.invalid", RecoveryCode.Purpose.PASSWORD_LINK, "//attacker.invalid")
    assert len(calls) == 1 and "absent@" not in calls[0]["args"][0]
    decoded = json.loads(decrypt_private_text(calls[0]["args"][0].encode("ascii")))
    assert decoded["next"] == "/account"
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    with pytest.raises(email_links.MailUnavailable):
        email_links.enqueue("another@example.invalid", RecoveryCode.Purpose.VERIFY_EMAIL)


def test_appeal_reuses_original_receipt_without_changing_or_enumerating_accounts(reader_user, rf, settings):
    from catalog.models import PublicFeedback
    settings.JWT_COOKIE_AUTH_ENABLED = False
    original = (reader_user.password, reader_user.email, reader_user.role)
    payload = {"request_id": str(uuid4()), "username": reader_user.username, "contact": "contact@example.invalid",
        "note": "合成申请：无法访问原邮箱", "consent": True}
    for _ in range(2):
        response = AccountRecoveryAppealView.as_view()(rf.post("/api/auth/recovery/appeal/", data=json.dumps(payload), content_type="application/json"))
        assert response.status_code in (200, 201)
        assert "email" not in response.data and "password" not in response.data
    assert PublicFeedback.objects.filter(request_id=payload["request_id"]).count() == 1
    reader_user.refresh_from_db()
    assert (reader_user.password, reader_user.email, reader_user.role) == original
    invalid = AccountRecoveryAppealInput(data={**payload, "consent": False})
    assert not invalid.is_valid()
