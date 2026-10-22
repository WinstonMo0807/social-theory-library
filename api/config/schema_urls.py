"""Verified contract surface. Legacy endpoints remain in the coverage audit.

No routing duplication: select the existing URLPattern instances by name and
preserve their real /api/catalog prefix and original permission-protected view.
"""
from django.urls import include, path
from catalog.urls import urlpatterns as catalog_patterns
from distribution.urls import urlpatterns as distribution_patterns
from ingestion.urls import urlpatterns as ingestion_patterns
from reading.urls import router as reading_router, urlpatterns as reading_patterns


VERIFIED_NAMES = {
    "theory-system-directory", "subdiscipline-list", "subdiscipline-detail",
    "topic-list", "topic-detail", "admin-topic-list", "admin-topic-detail",
    "knowledge-entry-citation", "theory-system-overview", "knowledge-node-list", "knowledge-node-detail",
    "normalized-theory-timeline", "normalized-theory-timeline-detail", "reading-path-list", "reading-path-detail",
    "admin-reading-path-list", "admin-reading-path-detail", "admin-knowledge-object-preview",
    "theory-timeline", "admin-theory-timeline-list", "admin-theory-timeline-detail",
    "local-theory-graph",
    "parallel-versions", "parallel-segments", "parallel-candidates",
    "catalog-feedback", "catalog-admin-public-feedback", "catalog-admin-public-feedback-detail",
    "catalog-home", "global-search",
    "admin-discovery-index",
    "discovery-search", "discovery-search-detail", "discovery-search-expand", "discovery-search-cancel", "discovery-search-retry", "discovery-search-context", "discovery-search-remove-document",
    "admin-curation-sources", "admin-evidence-curation", "admin-evidence-curation-publish", "public-evidence-curation",
    "admin-scholar-relation-list", "admin-scholar-relation-detail", "admin-scholar-relation-publish", "admin-scholar-relation-archive", "public-scholar-relation-list",
    "admin-curation-drafts", "admin-today-work",
    "work-list", "work-detail", "asset-manifest", "asset-page-content", "admin-reader-rendition-policy",
    "passage-focus", "theory-evidence-focus", "document-search",
    "knowledge-image-selection",
    "scholar-portrait-selection",
    "person-search", "person-merge-history",
    "person-duplicates", "person-merge-preview",
    "person-merge", "person-merge-record", "person-merge-rollback",
    "cataloging-session-list", "cataloging-session-detail", "cataloging-session-abandon",
    "cataloging-candidate-decision", "cataloging-metadata-import", "cataloging-metadata-decision",
    "catalog-field-contracts",
    "publication-prepare", "publication-rollback",
    "publication-history",
    "media-list", "media-detail", "media-rendition", "media-collection",
    "work-cover-media-selection",
    "public-cover-metadata",
    "work-recommendation-media-selection", "public-recommendation-metadata",
    "recommendation-image-metadata",
    "recommendation-issue-list", "recommendation-issue-detail", "recommendation-issue-save-list",
    "admin-recommendation-issue-list", "admin-recommendation-issue-detail", "admin-recommendation-issue-publish",
    "admin-recommendation-issue-link", "admin-site-content", "admin-site-content-publish", "admin-bibliographic-candidates",
    "asset-outline", "admin-asset-outline", "admin-outline-rebuilds", "admin-outline-job", "admin-page-mapping",
    "content-placement-sources", "admin-content-placements", "content-placement-history", "public-content-placements",
    "editorial-assistance-list", "editorial-assistance-detail",
    "edition-file-submit", "work-files", "work-edition-create", "edition-file-impact-csv",
    "edition-file-request", "edition-generate-reader", "edition-file-adopt", "edition-file-content", "edition-file-rights", "edition-file-prepare-public",
}
urlpatterns = [
    path("api/catalog/", include([pattern for pattern in catalog_patterns if pattern.name in VERIFIED_NAMES])),
    path("api/distribution/", include([pattern for pattern in distribution_patterns if pattern.name in {
        "asset-access", "asset-file", "admin-asset-preview", "backup-job-list", "reader-ocr-status",
    }])),
    path("api/ingestion/", include([pattern for pattern in ingestion_patterns if pattern.name == "ocr-workspace"])),
    path("api/reading/", include([
        pattern for pattern in reading_router.urls
        if getattr(getattr(pattern.callback, "cls", None), "__module__", "") in {"reading.research_views", "reading.privacy_views", "reading.parallel_views", "reading.graph_views", "reading.path_views"}
        or pattern.name in {"annotations-list", "annotations-detail", "bookmarks-list", "bookmarks-detail", "progress-list", "progress-detail", "reading-history-list", "reading-history-detail", "saved-topics-list", "saved-topics-detail", "saved-topics-state", "saved-topics-command"}
    ] + [pattern for pattern in reading_patterns if getattr(pattern, "name", None) in {
        "research-account", "reader-search-records", "reader-privacy", "reader-privacy-items", "citation-preview", "citation-preview-file",
        "citation-source-preview", "citation-source-preview-file",
        "article-comments-public", "article-comments-admin", "article-comments-own", "article-comment-receipt", "article-comment-delete",
        "public-citation-preview", "public-source-status", "source-follows", "source-follow-detail", "source-follow-receipt", "saved-knowledge-node",
    }])),
]
