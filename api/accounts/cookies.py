from django.conf import settings
from django.middleware.csrf import get_token
from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied


def _seconds(value) -> int:
    return max(1, int(value.total_seconds()))


def expose_csrf_cookie(request) -> None:
    """Ensure browser clients can send a CSRF header with cookie-authenticated writes."""

    get_token(request)


def enforce_cookie_csrf(request) -> None:
    check = CSRFCheck(lambda _: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied("安全校验失败，请刷新页面后重试。")


def set_auth_cookies(response, *, access: str, refresh: str, request=None) -> None:
    if not settings.JWT_COOKIE_AUTH_ENABLED:
        return
    trusted_lan = bool(request and getattr(request, "library_trusted_lan_http", False))
    common = {
        "secure": settings.SESSION_COOKIE_SECURE and not trusted_lan,
        "httponly": True,
        "domain": None,
    }
    response.set_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        access,
        max_age=_seconds(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]),
        path="/",
        samesite="Lax",
        **common,
    )
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        refresh,
        max_age=_seconds(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]),
        path="/api/auth/",
        samesite="Strict",
        **common,
    )


def clear_auth_cookies(response) -> None:
    response.delete_cookie(
        settings.JWT_ACCESS_COOKIE_NAME,
        path="/",
        samesite="Lax",
    )
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path="/api/auth/",
        samesite="Strict",
    )
