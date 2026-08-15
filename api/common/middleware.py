import hmac

from django.conf import settings


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
