from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AnnotationViewSet,
    BookmarkViewSet,
    ReaderDataExportView,
    ReaderSubmissionView,
    ReadingHistoryViewSet,
    ReadingListViewSet,
    ReadingProgressViewSet,
    SavedItemViewSet,
    SavedTopicViewSet,
)
from .library_views import (
    LibraryAssistantStatusView,
    LibraryConversationMessagesView,
    LibraryConversationStreamView,
    LibraryConversationViewSet,
    LibraryMessageCancelView,
    LibraryMessageSourceDetailView,
    LibraryMessageSourcesView,
)
from .runtime_views import AdminAIRuntimeProfilesView, AdminAIRuntimeProfileTestView

router = DefaultRouter()
router.register("progress", ReadingProgressViewSet, basename="progress")
router.register("annotations", AnnotationViewSet, basename="annotations")
router.register("bookmarks", BookmarkViewSet, basename="bookmarks")
router.register("saved", SavedItemViewSet, basename="saved")
router.register("saved-topics", SavedTopicViewSet, basename="saved-topics")
router.register("lists", ReadingListViewSet, basename="reading-lists")
router.register("history", ReadingHistoryViewSet, basename="reading-history")
router.register(
    "library-conversations",
    LibraryConversationViewSet,
    basename="library-conversations",
)

urlpatterns = [
    path("", include(router.urls)),
    path("export/", ReaderDataExportView.as_view(), name="reader-data-export"),
    path("submit/", ReaderSubmissionView.as_view(), name="reader-submission"),
    path(
        "library-conversations/<uuid:conversation_id>/messages/",
        LibraryConversationMessagesView.as_view(),
        name="library-conversation-messages",
    ),
    path(
        "library-conversations/<uuid:conversation_id>/messages/stream/",
        LibraryConversationStreamView.as_view(),
        name="library-conversation-stream",
    ),
    path(
        "library-messages/<uuid:message_id>/sources/",
        LibraryMessageSourcesView.as_view(),
        name="library-message-sources",
    ),
    path(
        "library-messages/<uuid:message_id>/sources/<uuid:source_id>/",
        LibraryMessageSourceDetailView.as_view(),
        name="library-message-source-detail",
    ),
    path(
        "library-messages/<uuid:message_id>/cancel/",
        LibraryMessageCancelView.as_view(),
        name="library-message-cancel",
    ),
    path(
        "library-assistant/status/",
        LibraryAssistantStatusView.as_view(),
        name="library-assistant-status",
    ),
    path(
        "admin/ai-runtime-profiles/",
        AdminAIRuntimeProfilesView.as_view(),
        name="admin-ai-runtime-profiles",
    ),
    path(
        "admin/ai-runtime-profiles/test/",
        AdminAIRuntimeProfileTestView.as_view(),
        name="admin-ai-runtime-profile-test",
    ),
]
