from django.contrib import admin

from .models import (
    Annotation,
    Bookmark,
    ReadingHistory,
    ReadingList,
    ReadingListItem,
    ReadingProgress,
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
