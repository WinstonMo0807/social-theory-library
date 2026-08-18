from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .cookies import enforce_cookie_csrf


class VersionedJWTAuthentication(JWTAuthentication):
    """Reject tokens issued before an administrator or reader changed the password."""

    def authenticate(self, request):
        header = self.get_header(request)
        if header is not None:
            try:
                return super().authenticate(request)
            except InvalidToken as exc:
                self._record_failure(request, self._token_failure_reason(exc))
                raise
            except AuthenticationFailed as exc:
                self._record_failure(request, self._user_failure_reason(exc))
                raise
        if not settings.JWT_COOKIE_AUTH_ENABLED:
            return None
        raw_token = request.COOKIES.get(settings.JWT_ACCESS_COOKIE_NAME)
        if not raw_token:
            self._record_failure(request, "no_cookie")
            return None
        try:
            validated_token = self.get_validated_token(raw_token.encode())
            user = self.get_user(validated_token)
        except InvalidToken as exc:
            self._record_failure(request, self._token_failure_reason(exc))
            raise
        except AuthenticationFailed as exc:
            self._record_failure(request, self._user_failure_reason(exc))
            raise
        if request.method not in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            enforce_cookie_csrf(request)
        return user, validated_token

    @staticmethod
    def _record_failure(request, reason: str) -> None:
        request.library_auth_failure_reason = reason

    @staticmethod
    def _token_failure_reason(exc: InvalidToken) -> str:
        return "expired_session" if "expired" in str(exc.detail).casefold() else "invalid_session"

    @staticmethod
    def _user_failure_reason(exc: AuthenticationFailed) -> str:
        detail = f"{exc.get_codes()} {exc.detail}".casefold()
        return "user_not_found" if "user_not_found" in detail or "user not found" in detail else "invalid_session"

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        try:
            token_version = int(validated_token.get("token_version", 0))
        except (TypeError, ValueError) as exc:
            raise AuthenticationFailed("登录令牌无效，请重新登录。") from exc
        if token_version != user.token_version:
            raise AuthenticationFailed("密码已变更，请重新登录。")
        return user
