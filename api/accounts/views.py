from django.conf import settings
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsLibraryAdmin
from common.capabilities import capability_snapshot

from .cookies import clear_auth_cookies, expose_csrf_cookie, set_auth_cookies
from .models import User
from .ownership import is_library_owner
from .serializers import (
    AdminSetPasswordSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"

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
        )
        expose_csrf_cookie(request)
        return response


class LogoutView(APIView):
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


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CurrentCapabilitiesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(capability_snapshot(request.user).as_dict())


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(
            data=request.data,
            context={"request_ip": request.META.get("REMOTE_ADDR")},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"detail": "如果邮箱存在，验证码已发送。"})


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        response = Response({"detail": "密码已重置，请重新登录。"})
        clear_auth_cookies(response)
        return response


class AdminSetPasswordView(APIView):
    permission_classes = [IsLibraryAdmin]

    def post(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        if target.role == User.Role.ADMIN and target != request.user and not is_library_owner(request.user):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("只有书库最高管理员可以重置其他管理员的密码。")
        serializer = AdminSetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target.set_password(serializer.validated_data["new_password"])
        target.token_version += 1
        target.save(update_fields=["password", "token_version"])
        from ingestion.models import AuditEvent

        AuditEvent.objects.create(
            actor=request.user,
            action="admin_set_password",
            object_type="User",
            object_id=str(target.id),
            after={"password_reset": True},
            request_ip=request.META.get("REMOTE_ADDR"),
        )
        return Response({"detail": "新密码已设置。旧密码从未以可读取形式保存。"})


class AdminUserListView(generics.ListAPIView):
    permission_classes = [IsLibraryAdmin]
    serializer_class = AdminUserSerializer
    search_fields = ("email", "display_name")
    ordering_fields = ("date_joined", "last_login", "email")

    def get_queryset(self):
        return User.objects.annotate(
            annotation_count=Count("annotations", distinct=True),
            bookmark_count=Count("bookmarks", distinct=True),
            saved_count=Count("saved_items", distinct=True),
        ).order_by("-date_joined")


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsLibraryAdmin]
    serializer_class = AdminUserUpdateSerializer
    queryset = User.objects.all()
    lookup_url_kwarg = "user_id"

    def perform_update(self, serializer):
        target = self.get_object()
        requested_role = serializer.validated_data.get("role", target.role)
        requested_active = serializer.validated_data.get("is_active", target.is_active)
        actor_is_owner = is_library_owner(self.request.user)
        target_is_owner = is_library_owner(target)
        if target_is_owner and (requested_role != User.Role.ADMIN or not requested_active):
            from rest_framework.exceptions import ValidationError

            raise ValidationError("最高管理员账户不能被停用或降级。")
        if (
            (requested_role == User.Role.ADMIN or target.role == User.Role.ADMIN)
            and not actor_is_owner
            and target != self.request.user
        ):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("只有最高管理员可以授予或撤销管理员角色。")
        if target == self.request.user and (requested_role != User.Role.ADMIN or not requested_active):
            from rest_framework.exceptions import ValidationError

            raise ValidationError("不能停用当前账户或撤销自己的管理员角色。")
        if (
            target.role == User.Role.ADMIN
            and target.is_active
            and (requested_role != User.Role.ADMIN or not requested_active)
            and User.objects.filter(role=User.Role.ADMIN, is_active=True).count() <= 1
        ):
            from rest_framework.exceptions import ValidationError

            raise ValidationError("系统必须保留至少一个有效管理员账户。")
        before = {
            "display_name": target.display_name,
            "role": target.role,
            "is_active": target.is_active,
        }
        updated = serializer.save()
        from ingestion.models import AuditEvent

        AuditEvent.objects.create(
            actor=self.request.user,
            action="admin_update_user",
            object_type="User",
            object_id=str(updated.id),
            before=before,
            after={
                "display_name": updated.display_name,
                "role": updated.role,
                "is_active": updated.is_active,
            },
            request_ip=self.request.META.get("REMOTE_ADDR"),
        )
