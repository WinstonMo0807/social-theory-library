"""Launch registration remains usable without mail, without verifying ownership."""
import pytest
from rest_framework.test import APIClient
from accounts.models import User, RecoveryCode


@pytest.mark.django_db
def test_registration_without_mail_can_login_but_cannot_become_admin(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEBUG = False
    settings.JWT_COOKIE_AUTH_ENABLED = True
    settings.JWT_RETURN_TOKENS_IN_BODY = False
    client = APIClient(enforce_csrf_checks=True)
    assert client.get("/api/auth/login/").data["email_delivery_available"] is False
    csrf = client.cookies["csrftoken"].value
    credentials = {"email": "launch-reader@example.invalid", "username": "launchreader",
                   "display_name": "Launch reader", "password": "Launch-Reader-2026!",
                   "role": "admin", "email_verified_at": "2026-11-07T00:00:00Z"}
    denied = client.post("/api/auth/register/", credentials, format="json")
    assert denied.status_code == 403
    registered = client.post("/api/auth/register/", credentials, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert registered.status_code == 201
    assert registered.data["verification_requested"] is False
    assert "登录" in registered.data["notice"]
    user = User.objects.get(email=credentials["email"])
    assert user.role == User.Role.READER and user.email_verified_at is None and not user.is_staff
    assert not RecoveryCode.objects.filter(user=user).exists()
    login = client.post("/api/auth/login/", {"email":user.email,"password":credentials["password"]}, format="json", HTTP_X_CSRFTOKEN=csrf)
    assert login.status_code == 200 and login.data["session"] == "cookie"
    assert "access" not in login.data and "refresh" not in login.data
    assert login.cookies[settings.JWT_ACCESS_COOKIE_NAME]["httponly"]
    assert client.get("/api/auth/me/").status_code == 200
    assert client.get("/api/admin/schema/").status_code == 403
