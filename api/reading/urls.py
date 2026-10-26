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
from .runtime_views import (
    AdminAIRuntimeProfilesView,
    AdminAIRuntimeProfileTestView,
    ReaderAIConnectionTestView,
    ReaderAIConnectionView,
)
from .research_views import (CitationAuditViewSet, CitationSourceViewSet, PersonalReadingPlanViewSet, ResearchAccountView,
                             ResearchMemoryViewSet, ResearchProjectViewSet, ResearchTurnViewSet)
from .privacy_views import ReaderDataOperationViewSet, ReaderPrivacyItemsView, ReaderPrivacyView, ReaderPrivacyRequestView
from .reader_center_views import ReaderCenterView, ReaderMaterialCommandView, ReaderMaterialReceiptView
from .notebook_views import NotebookView, NotebookChoicesView, NotebookDetailView, NotebookProjectView, NotebookBookmarkNoteView, NotebookExportView
from .document_preview_views import CitationPreviewFileView, CitationPreviewView
from .shared_citation_views import PublicCitationPreviewView
from .source_follow_views import PublicSourceStatusView, SourceFollowsView, SourceFollowDetailView, SourceFollowReceiptView
from .search_record_views import ReaderSearchRecordsView
from .guest_records import GuestRecordsImportView
from .knowledge_save_views import KnowledgeSaveView
from .sharing_views import (ReaderGroupsView, ReaderGroupDetailView, ReaderGroupAcceptView, ReaderGroupReceiptView, ShareSelectionView,
    SharePreviewView, ShareSourcesView, ReaderSharesView, ShareReceiptView, ShareDetailView, ShareNoticesView, PublicShareView)
from .graph_views import SavedGraphViewSet
from .path_views import PathFollowViewSet
from .parallel_views import (AdminParallelCalibrationViewSet, ParallelCalibrationViewSet,
                             ParallelReadingTaskViewSet, PublicParallelCalibrationViewSet)

from .editorial_comment_views import (PublicArticleCommentsView, OwnArticleCommentsView, ArticleCommentReceiptView, ArticleCommentDeleteView, AdminArticleCommentsView)

router = DefaultRouter()
router.register("graph-views", SavedGraphViewSet, basename="graph-views")
router.register("path-follows", PathFollowViewSet, basename="path-follows")
router.register("parallel-tasks", ParallelReadingTaskViewSet, basename="parallel-tasks")
# Specific prefixes precede the owner detail route, so public/admin are not treated as UUIDs.
router.register("parallel-calibrations/public", PublicParallelCalibrationViewSet, basename="public-parallel-calibrations")
router.register("parallel-calibrations/admin", AdminParallelCalibrationViewSet, basename="admin-parallel-calibrations")
router.register("parallel-calibrations", ParallelCalibrationViewSet, basename="parallel-calibrations")
router.register("privacy/operations", ReaderDataOperationViewSet, basename="reader-data-operations")
router.register("research-projects", ResearchProjectViewSet, basename="research-projects")
router.register("research-turns", ResearchTurnViewSet, basename="research-turns")
router.register("citation-audits", CitationAuditViewSet, basename="citation-audits")
router.register("citation-sources", CitationSourceViewSet, basename="citation-sources")
router.register("reading-plans", PersonalReadingPlanViewSet, basename="personal-reading-plans")
router.register("research-memories", ResearchMemoryViewSet, basename="research-memories")
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
    path("guest-records/import/", GuestRecordsImportView.as_view(), name="reader-guest-import"),
    path("groups/", ReaderGroupsView.as_view(), name="reader-groups"),
    path("groups/accept/", ReaderGroupAcceptView.as_view(), name="reader-group-accept"),
    path("groups/receipt/", ReaderGroupReceiptView.as_view(), name="reader-group-receipt"),
    path("groups/<uuid:pk>/", ReaderGroupDetailView.as_view(), name="reader-group-detail"),
    path("shares/selection/", ShareSelectionView.as_view(), name="reader-share-selection"),
    path("shares/sources/", ShareSourcesView.as_view(), name="reader-share-sources"),
    path("shares/preview/", SharePreviewView.as_view(), name="reader-share-preview"),
    path("shares/receipt/", ShareReceiptView.as_view(), name="reader-share-receipt"),
    path("shares/notices/", ShareNoticesView.as_view(), name="reader-share-notices"),
    path("shares/", ReaderSharesView.as_view(), name="reader-shares"),
    path("shares/<uuid:pk>/", ShareDetailView.as_view(), name="reader-share-detail"),
    path("share-links/<uuid:pk>/", PublicShareView.as_view(), name="public-share-link"),
    path("notebook/", NotebookView.as_view(), name="reader-notebook"),
    path("notebook/export/", NotebookExportView.as_view(), name="reader-notebook-export"),
    path("notebook/choices/<str:kind>/", NotebookChoicesView.as_view(), name="reader-notebook-choices"),
    path("notebook/add-to-project/", NotebookProjectView.as_view(), name="reader-notebook-project"),
    path("notebook/bookmarks/<uuid:pk>/note/", NotebookBookmarkNoteView.as_view(), name="reader-bookmark-note"),
    path("notebook/<str:category>/<uuid:pk>/", NotebookDetailView.as_view(), name="reader-notebook-detail"),
    path("reader-center/commands/", ReaderMaterialCommandView.as_view(), name="reader-material-command"),
    path("reader-center/commands/<uuid:request_id>/", ReaderMaterialReceiptView.as_view(), name="reader-material-receipt"),
    path("reader-center/", ReaderCenterView.as_view(), name="reader-center"),
    path("article-comments/public/<uuid:issue_id>/", PublicArticleCommentsView.as_view(), name="article-comments-public"),
    path("article-comments/admin/<uuid:issue_id>/", AdminArticleCommentsView.as_view(), name="article-comments-admin"),
    path("article-comments/<uuid:issue_id>/", OwnArticleCommentsView.as_view(), name="article-comments-own"),
    path("article-comments/<uuid:issue_id>/requests/<uuid:request_id>/", ArticleCommentReceiptView.as_view(), name="article-comment-receipt"),
    path("article-comments/<uuid:issue_id>/<uuid:comment_id>/", ArticleCommentDeleteView.as_view(), name="article-comment-delete"),
    path("saved-knowledge/<uuid:node_id>/", KnowledgeSaveView.as_view(), name="saved-knowledge-node"),
    path("search-records/", ReaderSearchRecordsView.as_view(), name="reader-search-records"),
    path("citation-preview/", PublicCitationPreviewView.as_view(), name="public-citation-preview"),
    path("source-status/", PublicSourceStatusView.as_view(), name="public-source-status"),
    path("source-follows/", SourceFollowsView.as_view(), name="source-follows"),
    path("source-follows/by-request/", SourceFollowReceiptView.as_view(), name="source-follow-receipt"),
    path("source-follows/<uuid:pk>/", SourceFollowDetailView.as_view(), name="source-follow-detail"),
    path("citation-audits/<uuid:pk>/preview/", CitationPreviewView.as_view(), name="citation-preview"),
    path("citation-audits/<uuid:pk>/preview/file/", CitationPreviewFileView.as_view(), name="citation-preview-file"),
    path("citation-sources/<uuid:pk>/preview/", CitationPreviewView.as_view(purpose="private_source"), name="citation-source-preview"),
    path("citation-sources/<uuid:pk>/preview/file/", CitationPreviewFileView.as_view(purpose="private_source"), name="citation-source-preview-file"),
    path("privacy/", ReaderPrivacyView.as_view(), name="reader-privacy"),
    path("privacy/items/", ReaderPrivacyItemsView.as_view(), name="reader-privacy-items"),
    path("privacy/requests/<uuid:request_id>/", ReaderPrivacyRequestView.as_view(), name="reader-privacy-request"),
    path("research-account/", ResearchAccountView.as_view(), name="research-account"),
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
        "library-assistant/connection/",
        ReaderAIConnectionView.as_view(),
        name="reader-ai-connection",
    ),
    path(
        "library-assistant/connection/test/",
        ReaderAIConnectionTestView.as_view(),
        name="reader-ai-connection-test",
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
