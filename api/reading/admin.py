from django.contrib import admin

from .models import (
    Annotation,
    Bookmark,
    ReadingHistory,
    ReadingList,
    ReadingListItem,
    ReadingProgress,
    ReaderAIConnection,
    SavedItem,
    SavedTopic,
)


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ("user", "asset", "page", "kind", "orphaned", "updated_at")
    list_filter = ("kind", "orphaned")
    search_fields = ("user__email", "asset__edition__work__title")
    exclude = ("body_ciphertext", "quote", "selector")
    readonly_fields = ("asset_sha256",)

    def has_change_permission(self, request, obj=None):
        return False


for model in (
    Bookmark,
    ReadingHistory,
    ReadingList,
    ReadingListItem,
    ReadingProgress,
    SavedItem,
    SavedTopic,
):
    admin.site.register(model)


@admin.register(ReaderAIConnection)
class ReaderAIConnectionAdmin(admin.ModelAdmin):
    list_display = ("user", "provider", "model", "enabled", "status", "last_checked_at")
    list_filter = ("provider", "enabled", "status")
    search_fields = ("user__email", "user__username", "model")
    readonly_fields = (
        "user",
        "provider",
        "base_url",
        "model",
        "api_key_ciphertext",
        "enabled",
        "status",
        "last_checked_at",
        "last_error_code",
        "last_error_message",
        "created_at",
        "updated_at",
    )
    exclude = ("api_key_ciphertext",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
