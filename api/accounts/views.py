from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework import generics
from common.private_responses import PrivateAccountResponses
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from drf_spectacular.utils import extend_schema

from common.permissions import CanManageUsers
from common.capabilities import capability_snapshot

from .cookies import clear_auth_cookies, enforce_cookie_csrf, expose_csrf_cookie, set_auth_cookies
from .models import User
from .ownership import is_library_owner, is_library_owner_identity
from .serializers import (
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)


class AuthEntryView(PrivateAccountResponses, APIView):
    # Credentials are verified by the operation, so an expired access cookie
    # cannot prevent login/recovery. Anonymous browser writes still require CSRF.
    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if settings.JWT_COOKIE_AUTH_ENABLED and request.method not in {"GET", "HEAD", "OPTIONS"}:
            enforce_cookie_csrf(request)


class AuthNoticeOutput(serializers.Serializer):
    detail = serializers.CharField()


class LoginOutput(serializers.Serializer):
    user = UserSerializer()
    session = serializers.ChoiceField(choices=["cookie", "token"])
    access = serializers.CharField(required=False)
    refresh = serializers.CharField(required=False)


class AuthEntryOutput(serializers.Serializer):
    csrf_ready = serializers.BooleanField()
    password_login = serializers.BooleanField()
    remember_days = serializers.IntegerField()
    recovery_mode = serializers.CharField()
    recovery_minutes = serializers.IntegerField()


class RegisterView(AuthEntryView):
    throttle_scope = "register"

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(AuthEntryView):
    throttle_scope = "login"

    @extend_schema(responses=AuthEntryOutput)
    def get(self, request):
        expose_csrf_cookie(request)
        return Response({"csrf_ready": True, "password_login": True,
            "remember_days": settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].days,
            "recovery_mode": "email_code", "recovery_minutes": 20})

    @extend_schema(request=LoginSerializer, responses=LoginOutput)
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        response_payload = {
            "user": payload["user"],
            "session": "cookie" if settings.JWT_COOKIE_AUTH_ENABLED else "token",
        }
        if settings.JWT_RETURN_TOKENS_IN_BODY:
            response_payload.update({"access": payload["access"], "refresh": payload["refresh"]})
        response = Response(response_payload)
        set_auth_cookies(
            response,
            access=payload["access"],
            refresh=payload["refresh"],
            request=request,
            remember=payload["remember_session"],
        )
        from django.middleware.csrf import rotate_token
        rotate_token(request)
        expose_csrf_cookie(request)
        return response


class LogoutView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "token_refresh"

    def post(self, request):
        payload = request.data.copy()
        if not payload.get("refresh"):
            payload["refresh"] = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, "")
        serializer = LogoutSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        return response


class CurrentUserView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CurrentCapabilitiesView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(capability_snapshot(request.user).as_dict())


class PasswordResetRequestView(AuthEntryView):
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetRequestSerializer, responses=AuthNoticeOutput)
    def post(self, request):
        serializer = PasswordResetRequestSerializer(
            data=request.data,
            context={"request_ip": request.META.get("REMOTE_ADDR")},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "如果邮箱存在，验证码已发送。"})


class PasswordResetConfirmView(AuthEntryView):
    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetConfirmSerializer, responses=AuthNoticeOutput)
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response = Response({"detail": "密码已重置，请重新登录。"})
        clear_auth_cookies(response)
        return response


class AdminSetPasswordView(PrivateAccountResponses, APIView):
    permission_classes = [CanManageUsers]

    def post(self, request, user_id):
        from .user_management_views import legacy_command
        return legacy_command(request, user_id, "password")


class AdminUserListView(PrivateAccountResponses, generics.ListAPIView):
    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer
    search_fields = ("username", "email", "display_name")
    ordering_fields = ("date_joined", "last_login", "email")
    queryset = User.objects.all().order_by("-date_joined", "-pk")


class AdminUserDetailView(PrivateAccountResponses, generics.RetrieveUpdateAPIView):
    permission_classes = [CanManageUsers]
    serializer_class = AdminUserUpdateSerializer
    queryset = User.objects.all()
    lookup_url_kwarg = "user_id"

    def update(self, request, *args, **kwargs):
        from .user_management_views import legacy_command
        return legacy_command(request, kwargs["user_id"], "update")
