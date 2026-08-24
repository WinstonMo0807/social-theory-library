from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import ReaderProfile, RecoveryCode, User
from .ownership import (
    configured_library_owner_email,
    is_library_owner_email,
    is_library_owner_identity,
    normalize_email_identity,
)


def _assignable_role_choices():
    return [choice for choice in User.Role.choices if choice[0] != User.Role.REVIEWER]


class LibraryUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = _assignable_role_choices()
        if self.instance and self.instance.role == User.Role.REVIEWER:
            self.initial["role"] = User.Role.EDITOR

    def clean_email(self):
        email = normalize_email_identity(self.cleaned_data.get("email"))
        if is_library_owner_identity(self.instance) and email != configured_library_owner_email():
            raise forms.ValidationError("System Owner 的身份邮箱不能修改。")
        if is_library_owner_email(email) and not is_library_owner_identity(self.instance):
            raise forms.ValidationError("该邮箱保留给 System Owner。")
        duplicate = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("该邮箱已被其他账户使用。")
        return email

    def clean(self):
        cleaned = super().clean()
        if is_library_owner_identity(self.instance):
            if cleaned.get("role") != User.Role.ADMIN or not cleaned.get("is_active", True):
                raise forms.ValidationError("System Owner 账户不能被停用或降级。")
        return cleaned


class LibraryUserCreationForm(UserCreationForm):
    role = forms.ChoiceField(label="角色", choices=_assignable_role_choices())

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "display_name", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = _assignable_role_choices()

    def clean_email(self):
        email = normalize_email_identity(self.cleaned_data.get("email"))
        if is_library_owner_email(email):
            raise forms.ValidationError("System Owner 邮箱不能通过管理端创建。")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("该邮箱已被其他账户使用。")
        return email


@admin.register(User)
class LibraryUserAdmin(UserAdmin):
    form = LibraryUserChangeForm
    add_form = LibraryUserCreationForm
    list_display = ("email", "display_name", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active", "is_staff")
    search_fields = ("email", "display_name", "username")
    fieldsets = UserAdmin.fieldsets + (
        ("书库权限", {"fields": ("display_name", "role", "email_verified_at", "locale")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("书库权限", {"fields": ("email", "display_name", "role")}),
    )


@admin.register(ReaderProfile)
class ReaderProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "newsletter_enabled", "updated_at")
    search_fields = ("user__email", "user__display_name")


@admin.register(RecoveryCode)
class RecoveryCodeAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "used_at", "created_at")
    readonly_fields = ("code_hash",)
