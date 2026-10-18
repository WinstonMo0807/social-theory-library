"""Verified contract surface. Legacy endpoints remain in the coverage audit.

No routing duplication: select the existing URLPattern instances by name and
preserve their real /api/catalog prefix and original permission-protected view.
"""
from django.urls import include, path
from catalog.urls import urlpatterns as catalog_patterns
from distribution.urls import urlpatterns as distribution_patterns
from reading.urls import router as reading_router, urlpatterns as reading_patterns


VERIFIED_NAMES = {
    "catalog-home",
    "admin-discovery-index",
    "discovery-search", "discovery-search-detail", "discovery-search-expand", "discovery-search-cancel", "discovery-search-retry", "discovery-search-context",
    "admin-curation-sources", "admin-evidence-curation", "admin-evidence-curation-publish", "public-evidence-curation",
    "admin-scholar-relation-list", "admin-scholar-relation-detail", "admin-scholar-relation-publish", "admin-scholar-relation-archive", "public-scholar-relation-list",
    "admin-curation-drafts",
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
}
urlpatterns = [
    path("api/catalog/", include([pattern for pattern in catalog_patterns if pattern.name in VERIFIED_NAMES])),
    path("api/distribution/", include([pattern for pattern in distribution_patterns if pattern.name in {
        "asset-access", "asset-file", "admin-asset-preview", "backup-job-list",
    }])),
    path("api/reading/", include([
        pattern for pattern in reading_router.urls
        if getattr(getattr(pattern.callback, "cls", None), "__module__", "") in {"reading.research_views", "reading.privacy_views"}
    ] + [pattern for pattern in reading_patterns if getattr(pattern, "name", None) in {"research-account", "reader-privacy", "reader-privacy-items"}])),
]
