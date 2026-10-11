import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.models import update_last_login
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .models import RecoveryCode, User
from .ownership import (
    is_library_owner,
    is_library_owner_email,
    is_library_owner_identity,
    library_owner_display_name,
    normalize_email_identity,
)
from common.capabilities import capability_snapshot


ACCOUNT_ROLES = tuple(choice for choice in User.Role.choices if choice[0] != User.Role.REVIEWER)


def validate_display_name(instance, value):
    if instance and is_library_owner_identity(instance) and value != library_owner_display_name():
        raise serializers.ValidationError("系统所有者显示名由部署配置确定，不能在账户页修改。")
    return value


class UserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=ACCOUNT_ROLES, read_only=True)
    reading_preferences = serializers.JSONField(required=False)
    is_library_owner = serializers.SerializerMethodField()
    access_level = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    system_owner_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "role",
            "locale",
            "email_verified_at",
            "reading_preferences",
            "is_library_owner",
            "access_level",
            "capabilities",
            "system_owner_label",
        )
        read_only_fields = ("id", "email", "role", "email_verified_at")

    def validate(self, attrs):
        if self.instance is not None and "email" in self.initial_data:
            supplied = normalize_email_identity(self.initial_data.get("email"))
            current = normalize_email_identity(self.instance.email)
            if supplied != current:
                raise serializers.ValidationError(
                    {"email": "邮箱不能通过个人资料修改，请联系 System Owner。"}
                )
        return attrs

    def validate_display_name(self, value):
        return validate_display_name(self.instance, value)

    def get_is_library_owner(self, instance) -> bool:
        return is_library_owner_identity(instance)

    def get_access_level(self, instance) -> str:
        return capability_snapshot(instance).access_level

    def get_capabilities(self, instance) -> list[str]:
        return list(capability_snapshot(instance).capabilities)

    def get_system_owner_label(self, instance) -> str:
        return library_owner_display_name() if is_library_owner_identity(instance) else ""

    def validate_reading_preferences(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("显示偏好必须是对象。")
        allowed = {"text_size", "font_family"}
        unknown = set(value) - allowed
        if unknown:
            raise serializers.ValidationError("显示偏好包含不支持的设置。")
        if value.get("text_size") not in {None, "standard", "comfortable", "large"}:
            raise serializers.ValidationError("字号设置无效。")
        if value.get("font_family") not in {None, "sans", "serif"}:
            raise serializers.ValidationError("字体设置无效。")
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("role") == User.Role.REVIEWER:
            data["role"] = User.Role.EDITOR
        if is_library_owner_identity(instance):
            data["display_name"] = library_owner_display_name()
        profile = getattr(instance, "reader_profile", None)
        data["reading_preferences"] = (
            profile.reading_preferences
            if profile and isinstance(profile.reading_preferences, dict)
            else {}
        )
        return data

    def update(self, instance, validated_data):
        preferences = validated_data.pop("reading_preferences", None)
        instance = super().update(instance, validated_data)
        if preferences is not None:
            profile = instance.reader_profile
            current = (
                profile.reading_preferences
                if isinstance(profile.reading_preferences, dict)
                else {}
            )
            profile.reading_preferences = {**current, **preferences}
            profile.save(update_fields=["reading_preferences", "updated_at"])
        return instance


class AdminUserSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=ACCOUNT_ROLES, read_only=True)
    annotation_count = serializers.IntegerField(read_only=True)
    bookmark_count = serializers.IntegerField(read_only=True)
    saved_count = serializers.IntegerField(read_only=True)
    is_library_owner = serializers.SerializerMethodField()
    can_manage_admin_role = serializers.SerializerMethodField()
    system_owner_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "role",
            "is_active",
            "date_joined",
            "last_login",
            "annotation_count",
            "bookmark_count",
            "saved_count",
            "is_library_owner",
            "can_manage_admin_role",
            "system_owner_label",
        )
        read_only_fields = fields

    def get_is_library_owner(self, instance) -> bool:
        return is_library_owner_identity(instance)

    def get_can_manage_admin_role(self, instance) -> bool:
        request = self.context.get("request")
        return bool(request and is_library_owner(request.user))

    def get_system_owner_label(self, instance) -> str:
        return library_owner_display_name() if is_library_owner_identity(instance) else ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("role") == User.Role.REVIEWER:
            data["role"] = User.Role.EDITOR
        if is_library_owner_identity(instance):
            data["display_name"] = library_owner_display_name()
        return data


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=ACCOUNT_ROLES, required=False)
    is_library_owner = serializers.SerializerMethodField()
    system_owner_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "role",
            "is_active",
            "is_library_owner",
            "system_owner_label",
        )
        read_only_fields = ("id", "email", "is_library_owner", "system_owner_label")

    def get_is_library_owner(self, instance) -> bool:
        return is_library_owner_identity(instance)

    def get_system_owner_label(self, instance) -> str:
        return library_owner_display_name() if is_library_owner_identity(instance) else ""

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if data.get("role") == User.Role.REVIEWER:
            data["role"] = User.Role.EDITOR
        if is_library_owner_identity(instance):
            data["display_name"] = library_owner_display_name()
        return data

    def validate_role(self, value):
        if value == User.Role.REVIEWER:
            raise serializers.ValidationError("Reviewer 仅用于旧账号兼容，不能再分配。")
        return value

    def validate_display_name(self, value):
        return validate_display_name(self.instance, value)

    def validate(self, attrs):
        if self.instance is not None and "email" in self.initial_data:
            supplied = normalize_email_identity(self.initial_data.get("email"))
            current = normalize_email_identity(self.instance.email)
            if supplied != current:
                raise serializers.ValidationError(
                    {"email": "管理员用户编辑不支持变更登录邮箱。"}
                )
        return attrs


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField(max_length=120)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        value = normalize_email_identity(value)
        if is_library_owner_email(value):
            raise serializers.ValidationError("System Owner 邮箱不能通过公开注册占用。")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("该邮箱已注册。")
        return value

    def validate_password(self, value):
        password_validation.validate_password(value)
        return value

    @transaction.atomic
    def create(self, validated_data):
        email = validated_data["email"]
        username = email
        suffix = 1
        while User.objects.filter(username=username).exists():
            suffix += 1
            username = f"{email}-{suffix}"
        return User.objects.create_user(
            username=username,
            email=email,
            display_name=validated_data["display_name"],
            password=validated_data["password"],
        )


class AdminUserCreateSerializer(RegisterSerializer):
    role = serializers.ChoiceField(choices=ACCOUNT_ROLES, default=User.Role.READER)
    is_active = serializers.BooleanField(default=True)

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("新建账号只接受显示名、邮箱、初始密码、角色和状态。")
        request = self.context.get("request")
        if attrs["role"] != User.Role.READER and not (request and is_library_owner(request.user)):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("只有系统所有者可以为新账号指定后台角色。")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        role = validated_data.pop("role")
        active = validated_data.pop("is_active")
        user = super().create(validated_data)
        if role != user.role or active != user.is_active:
            user.role, user.is_active = role, active
            user.save(update_fields=["role", "is_active"])
        return user


class AdminSetPasswordResultSerializer(serializers.Serializer):
    detail = serializers.CharField()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = User.objects.filter(email__iexact=normalize_email_identity(attrs["email"])).first()
        if user is None:
            raise serializers.ValidationError("邮箱或密码不正确。")
        authenticated = authenticate(
            request=self.context.get("request"),
            username=user.username,
            password=attrs["password"],
        )
        if authenticated is None or not authenticated.is_active:
            raise serializers.ValidationError("邮箱或密码不正确。")
        refresh = RefreshToken.for_user(authenticated)
        refresh["token_version"] = authenticated.token_version
        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, authenticated)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(authenticated).data,
        }


class VersionedTokenRefreshSerializer(TokenRefreshSerializer):
    """Refuse refresh tokens issued before a password reset or account deactivation."""

    def validate(self, attrs):
        try:
            refresh = self.token_class(attrs["refresh"])
        except TokenError as exc:
            raise InvalidToken("刷新令牌无效或已失效。") from exc

        user_id = refresh.get(api_settings.USER_ID_CLAIM)
        user = User.objects.filter(pk=user_id, is_active=True).only("token_version").first()
        if user is None:
            raise InvalidToken("刷新令牌对应的账户已不存在或已停用。")
        try:
            token_version = int(refresh.get("token_version", 0))
        except (TypeError, ValueError) as exc:
            raise InvalidToken("刷新令牌无效。") from exc
        if token_version != user.token_version:
            try:
                refresh.blacklist()
            except TokenError:
                pass
            raise InvalidToken("密码已变更，请重新登录。")
        return super().validate(attrs)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self):
        user = User.objects.filter(
            email__iexact=normalize_email_identity(self.validated_data["email"]),
            is_active=True,
        ).first()
        if user is None:
            return

        code = f"{secrets.randbelow(1_000_000):06d}"
        RecoveryCode.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=timezone.now() + timedelta(minutes=20),
            request_ip=self.context.get("request_ip"),
        )
        send_mail(
            "社科书库密码重置验证码",
            f"您的验证码是 {code}，20 分钟内有效。若非本人操作，请忽略。",
            None,
            [user.email],
            fail_silently=False,
        )


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(min_length=6, max_length=12)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        password_validation.validate_password(value)
        return value

    def save(self):
        user = User.objects.filter(
            email__iexact=normalize_email_identity(self.validated_data["email"]),
            is_active=True,
        ).first()
        if user is None:
            raise serializers.ValidationError({"code": "验证码无效或已过期。"})

        candidates = user.recovery_codes.filter(
            used_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at")[:5]
        matched = next(
            (candidate for candidate in candidates if check_password(self.validated_data["code"], candidate.code_hash)),
            None,
        )
        if matched is None:
            raise serializers.ValidationError({"code": "验证码无效或已过期。"})

        with transaction.atomic():
            user.set_password(self.validated_data["new_password"])
            user.token_version += 1
            user.save(update_fields=["password", "token_version"])
            matched.used_at = timezone.now()
            matched.save(update_fields=["used_at"])
            user.recovery_codes.filter(used_at__isnull=True).exclude(pk=matched.pk).update(used_at=timezone.now())


class AdminSetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value):
        password_validation.validate_password(value)
        return value


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_refresh(self, value):
        try:
            token = RefreshToken(value)
        except TokenError:
            return value
        request = self.context.get("request")
        user_id = token.get(api_settings.USER_ID_CLAIM)
        if request is not None and str(user_id) != str(request.user.pk):
            raise serializers.ValidationError("该刷新令牌不属于当前账户。")
        return value

    def save(self):
        try:
            RefreshToken(self.validated_data["refresh"]).blacklist()
        except TokenError:
            return
