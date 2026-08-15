import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import authenticate, password_validation
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
from .ownership import is_library_owner


class UserSerializer(serializers.ModelSerializer):
    reading_preferences = serializers.JSONField(required=False)
    is_library_owner = serializers.SerializerMethodField()

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
        )
        read_only_fields = ("id", "role", "email_verified_at")

    def get_is_library_owner(self, instance):
        return is_library_owner(instance)

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
    annotation_count = serializers.IntegerField(read_only=True)
    bookmark_count = serializers.IntegerField(read_only=True)
    saved_count = serializers.IntegerField(read_only=True)
    is_library_owner = serializers.SerializerMethodField()
    can_manage_admin_role = serializers.SerializerMethodField()

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
        )
        read_only_fields = fields

    def get_is_library_owner(self, instance):
        return is_library_owner(instance)

    def get_can_manage_admin_role(self, instance):
        request = self.context.get("request")
        return bool(request and is_library_owner(request.user))


class AdminUserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name", "role", "is_active")
        read_only_fields = ("id", "email")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    display_name = serializers.CharField(max_length=120)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
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


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = User.objects.filter(email=attrs["email"].strip().lower()).first()
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
        user = User.objects.filter(email=self.validated_data["email"].strip().lower(), is_active=True).first()
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
        user = User.objects.filter(email=self.validated_data["email"].strip().lower(), is_active=True).first()
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
