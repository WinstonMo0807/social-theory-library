import pytest
from django.contrib.auth import authenticate
from rest_framework.test import APIClient

from accounts.models import User


@pytest.mark.django_db
def test_reader_display_preferences_are_synced_through_account(api_client, reader_user):
    api_client.force_authenticate(reader_user)
    updated = api_client.patch(
        "/api/auth/me/",
        {
            "reading_preferences": {
                "text_size": "large",
                "font_family": "serif",
            }
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["reading_preferences"] == {
        "text_size": "large",
        "font_family": "serif",
    }

    reader_user.reader_profile.refresh_from_db()
    assert reader_user.reader_profile.reading_preferences["text_size"] == "large"
    current = api_client.get("/api/auth/me/")
    assert current.data["reading_preferences"]["font_family"] == "serif"


@pytest.mark.django_db
def test_django_superuser_is_also_library_admin():
    user = User.objects.create_superuser(
        username="root@example.org",
        email="root@example.org",
        password="Root-Secure-Password-2026",
    )
    assert user.role == User.Role.ADMIN


@pytest.mark.django_db
def test_password_is_argon2_hash_and_login_uses_email(api_client, reader_user):
    reader_user.refresh_from_db()
    assert reader_user.password.startswith("argon2$")
    assert "Reader-Secure-Password-2026" not in reader_user.password

    response = api_client.post(
        "/api/auth/login/",
        {
            "email": reader_user.email,
            "password": "Reader-Secure-Password-2026",
        },
        format="json",
    )
    assert response.status_code == 200
    assert response.data["access"]
    assert response.data["user"]["role"] == User.Role.READER


@pytest.mark.django_db
def test_admin_can_set_new_password_but_cannot_read_old_password(api_client, admin_user, reader_user):
    login = api_client.post(
        "/api/auth/login/",
        {
            "email": reader_user.email,
            "password": "Reader-Secure-Password-2026",
        },
        format="json",
    )
    old_access = login.data["access"]
    old_refresh = login.data["refresh"]

    api_client.force_authenticate(admin_user)
    response = api_client.post(
        f"/api/auth/users/{reader_user.id}/set-password/",
        {"new_password": "New-Direct-Reset-Password-2026"},
        format="json",
    )
    assert response.status_code == 200
    reader_user.refresh_from_db()
    assert reader_user.check_password("New-Direct-Reset-Password-2026")
    assert "New-Direct-Reset-Password-2026" not in reader_user.password
    assert reader_user.token_version == 1
    assert "旧密码从未以可读取形式保存" in response.data["detail"]

    api_client.force_authenticate(user=None)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
    assert api_client.get("/api/auth/me/").status_code == 401
    api_client.credentials()
    assert api_client.post(
        "/api/auth/token/refresh/",
        {"refresh": old_refresh},
        format="json",
    ).status_code == 401

    next_login = api_client.post(
        "/api/auth/login/",
        {
            "email": reader_user.email,
            "password": "New-Direct-Reset-Password-2026",
        },
        format="json",
    )
    assert next_login.status_code == 200


@pytest.mark.django_db
def test_logout_blacklists_refresh_token(api_client, reader_user):
    login = api_client.post(
        "/api/auth/login/",
        {
            "email": reader_user.email,
            "password": "Reader-Secure-Password-2026",
        },
        format="json",
    )
    access = login.data["access"]
    refresh = login.data["refresh"]

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    logout = api_client.post(
        "/api/auth/logout/",
        {"refresh": refresh},
        format="json",
    )
    assert logout.status_code == 204

    api_client.credentials()
    refreshed = api_client.post(
        "/api/auth/token/refresh/",
        {"refresh": refresh},
        format="json",
    )
    assert refreshed.status_code == 401


@pytest.mark.django_db
def test_refresh_token_for_deleted_user_returns_unauthorized(api_client, reader_user):
    login = api_client.post(
        "/api/auth/login/",
        {
            "email": reader_user.email,
            "password": "Reader-Secure-Password-2026",
        },
        format="json",
    )
    refresh = login.data["refresh"]
    reader_user.delete()

    response = api_client.post(
        "/api/auth/token/refresh/",
        {"refresh": refresh},
        format="json",
    )

    assert response.status_code == 401
    assert "账户已不存在" in response.data["error"]["detail"]["detail"]


@pytest.mark.django_db
def test_browser_session_uses_httponly_cookies_and_csrf(settings, reader_user):
    settings.JWT_COOKIE_AUTH_ENABLED = True
    settings.JWT_RETURN_TOKENS_IN_BODY = False
    settings.SESSION_COOKIE_SECURE = True
    client = APIClient(enforce_csrf_checks=True)

    login = client.post(
        "/api/auth/login/",
        {
            "email": reader_user.email,
            "password": "Reader-Secure-Password-2026",
        },
        format="json",
    )
    assert login.status_code == 200
    assert "access" not in login.data
    assert "refresh" not in login.data
    assert login.data["session"] == "cookie"
    assert login.cookies[settings.JWT_ACCESS_COOKIE_NAME]["httponly"]
    assert login.cookies[settings.JWT_ACCESS_COOKIE_NAME]["secure"]
    assert login.cookies[settings.JWT_REFRESH_COOKIE_NAME]["httponly"]
    assert client.get("/api/auth/me/").status_code == 200

    rejected = client.patch("/api/auth/me/", {"display_name": "被拒绝"}, format="json")
    assert rejected.status_code == 403

    csrf = client.cookies[settings.CSRF_COOKIE_NAME].value
    accepted = client.patch(
        "/api/auth/me/",
        {"display_name": "Cookie 读者"},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert accepted.status_code == 200

    refreshed = client.post(
        "/api/auth/token/refresh/",
        {},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert refreshed.status_code == 200
    assert "access" not in refreshed.data

    logout = client.post(
        "/api/auth/logout/",
        {},
        format="json",
        HTTP_X_CSRFTOKEN=csrf,
    )
    assert logout.status_code == 204
    assert logout.cookies[settings.JWT_ACCESS_COOKIE_NAME]["max-age"] == 0
    assert logout.cookies[settings.JWT_REFRESH_COOKIE_NAME]["max-age"] == 0


@pytest.mark.django_db
def test_trusted_lan_login_keeps_cookie_session_on_http(settings, reader_user):
    settings.JWT_COOKIE_AUTH_ENABLED = True
    settings.JWT_RETURN_TOKENS_IN_BODY = False
    settings.SESSION_COOKIE_SECURE = True
    settings.LAN_HOST = "192.168.5.6"
    settings.LAN_PROXY_TOKEN = "lan-proxy-token-for-tests-2026-000001"
    client = APIClient(enforce_csrf_checks=True)

    login = client.post(
        "/api/auth/login/",
        {
            "email": reader_user.email,
            "password": "Reader-Secure-Password-2026",
        },
        format="json",
        HTTP_HOST="192.168.5.6:18080",
        HTTP_X_LIBRARY_LAN="1",
        HTTP_X_LIBRARY_LAN_TOKEN=settings.LAN_PROXY_TOKEN,
    )

    assert login.status_code == 200
    assert not login.cookies[settings.JWT_ACCESS_COOKIE_NAME]["secure"]
    assert not login.cookies[settings.JWT_REFRESH_COOKIE_NAME]["secure"]
    assert client.get(
        "/api/auth/me/",
        HTTP_HOST="192.168.5.6:18080",
        HTTP_X_LIBRARY_LAN="1",
        HTTP_X_LIBRARY_LAN_TOKEN=settings.LAN_PROXY_TOKEN,
    ).status_code == 200
