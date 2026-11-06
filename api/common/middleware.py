import hmac
import re
from uuid import uuid4

from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils.cache import patch_vary_headers

from accounts.ownership import is_library_owner


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


class ApiContractMiddleware:
    """Attach cross-cutting metadata shared by every 4.0 API response."""

    api_prefix = "/api/"
    api_version = "4.0"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = str(request.META.get("HTTP_X_REQUEST_ID") or "").strip()
        request_id = supplied if _REQUEST_ID_RE.fullmatch(supplied) else uuid4().hex
        request.stl_request_id = request_id
        response = self.get_response(request)
        if getattr(request, "stl_reader_access", False):
            response["Cache-Control"] = "private, no-store, no-transform"
            patch_vary_headers(response, ("Cookie", "Authorization"))
        if request.path.startswith(self.api_prefix):
            response["X-STL-API-Version"] = str(
                getattr(settings, "API_CONTRACT_VERSION", self.api_version)
            )
            response["X-Request-ID"] = request_id
        return response


class TrustedLanHttpMiddleware:
    """Permit cookie authentication only through the explicitly trusted LAN proxy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        marker = request.META.get("HTTP_X_LIBRARY_LAN", "")
        supplied_token = request.META.get("HTTP_X_LIBRARY_LAN_TOKEN", "")
        host = request.get_host().split(":", 1)[0].strip().lower()
        expected_host = settings.LAN_HOST.strip().lower()
        expected_token = settings.LAN_PROXY_TOKEN
        trusted = bool(
            marker == "1"
            and expected_host
            and host == expected_host
            and len(expected_token) >= 32
            and hmac.compare_digest(supplied_token, expected_token)
        )
        request.library_trusted_lan_http = trusted
        response = self.get_response(request)
        if trusted:
            response.headers.pop("Strict-Transport-Security", None)
            for name in (
                settings.JWT_ACCESS_COOKIE_NAME,
                settings.JWT_REFRESH_COOKIE_NAME,
                settings.CSRF_COOKIE_NAME,
                settings.SESSION_COOKIE_NAME,
            ):
                cookie = response.cookies.get(name)
                if cookie is not None:
                    cookie["secure"] = ""
        return response


class OwnerOnlyDjangoAdminMiddleware:
    """Prevent Django superuser flags from bypassing the product capability model."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_django_admin = request.path == "/admin" or request.path.startswith("/admin/")
        user = getattr(request, "user", None)
        if (
            is_django_admin
            and getattr(user, "is_authenticated", False)
            and not is_library_owner(user)
        ):
            return HttpResponseForbidden("Django 管理入口仅供 System Owner 使用。")
        return self.get_response(request)
