from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ReaderProfile, RecoveryCode, User


@admin.register(User)
class LibraryUserAdmin(UserAdmin):
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
