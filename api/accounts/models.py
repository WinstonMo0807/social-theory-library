from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from common.models import UUIDTimeStampedModel


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "管理员"
        EDITOR = "editor", "编辑"
        REVIEWER = "reviewer", "审核者"
        READER = "reader", "读者"

    email = models.EmailField("邮箱", unique=True)
    display_name = models.CharField("显示名称", max_length=120, blank=True)
    role = models.CharField("角色", max_length=16, choices=Role.choices, default=Role.READER)
    email_verified_at = models.DateTimeField("邮箱验证时间", null=True, blank=True)
    locale = models.CharField("界面语言", max_length=16, default="zh-CN")
    data_export_requested_at = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveIntegerField(default=0, editable=False)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMIN
        if not self.display_name:
            self.display_name = self.get_full_name() or self.username
        super().save(*args, **kwargs)


class ReaderProfile(UUIDTimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="reader_profile")
    recommendation_seed = models.CharField(max_length=64, blank=True)
    reading_preferences = models.JSONField(default=dict, blank=True)
    newsletter_enabled = models.BooleanField(default=False)


class AccountAvatar(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True, related_name="account_avatar")
    image_ciphertext = models.BinaryField(default=bytes, blank=True)
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)


class RecoveryCode(UUIDTimeStampedModel):
    class Purpose(models.TextChoices):
        PASSWORD_CODE = "password_code", "旧密码验证码"
        PASSWORD_LINK = "password_link", "密码恢复链接"
        VERIFY_EMAIL = "verify_email", "验证邮箱"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recovery_codes")
    purpose = models.CharField(max_length=20, choices=Purpose.choices, default=Purpose.PASSWORD_CODE)
    account_fingerprint = models.CharField(max_length=64, blank=True, default="")
    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    request_ip = models.GenericIPAddressField(null=True, blank=True)

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()
