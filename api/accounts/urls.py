from django.contrib.auth import get_user_model
from django.conf import settings
from django.urls import path
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.response import Response

from .serializers import VersionedTokenRefreshSerializer
from .cookies import enforce_cookie_csrf, expose_csrf_cookie, set_auth_cookies
from .views import (
    AdminSetPasswordView,
    AdminUserDetailView,
    AdminUserListView,
    CurrentUserView,
    CurrentCapabilitiesView,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    RegisterView,
)


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_scope = "token_refresh"
    serializer_class = VersionedTokenRefreshSerializer

    def post(self, request, *args, **kwargs):
        try:
            payload = request.data.copy()
            cookie_refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, "")
            if not payload.get("refresh") and cookie_refresh:
                enforce_cookie_csrf(request)
                payload["refresh"] = cookie_refresh
            serializer = self.get_serializer(data=payload)
            serializer.is_valid(raise_exception=True)
            tokens = serializer.validated_data
            response_payload = tokens if settings.JWT_RETURN_TOKENS_IN_BODY else {"detail": "登录状态已续期。"}
            response = Response(response_payload)
            access = tokens.get("access")
            refresh = tokens.get("refresh") or payload.get("refresh")
            if access and refresh:
                set_auth_cookies(response, access=access, refresh=refresh, request=request)
                expose_csrf_cookie(request)
            return response
        except get_user_model().DoesNotExist as exc:
            request.library_auth_failure_reason = "refresh_failed"
            raise InvalidToken("刷新令牌对应的账户已不存在。") from exc
        except APIException:
            request.library_auth_failure_reason = "refresh_failed"
            raise


urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", ThrottledTokenRefreshView.as_view(), name="token-refresh"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("capabilities/", CurrentCapabilitiesView.as_view(), name="current-capabilities"),
    path("users/", AdminUserListView.as_view(), name="admin-user-list"),
    path("users/<int:user_id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("password/request/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("password/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("users/<int:user_id>/set-password/", AdminSetPasswordView.as_view(), name="admin-set-password"),
]
