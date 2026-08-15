from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from .cookies import enforce_cookie_csrf


class VersionedJWTAuthentication(JWTAuthentication):
    """Reject tokens issued before an administrator or reader changed the password."""

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)
        if not settings.JWT_COOKIE_AUTH_ENABLED:
            return None
        raw_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
        if not raw_token:
            return None
        validated_token = self.get_validated_token(raw_token.encode())
        if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            enforce_cookie_csrf(request)
        return self.get_user(validated_token), validated_token

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        try:
            token_version = int(validated_token.get("token_version", 0))
        except (TypeError, ValueError) as exc:
            raise AuthenticationFailed("登录令牌无效，请重新登录。") from exc
        if token_version != user.token_version:
            raise AuthenticationFailed("密码已变更，请重新登录。")
        return user
