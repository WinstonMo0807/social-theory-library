"""Verified contract surface. Legacy endpoints remain in the coverage audit.

No routing duplication: select the existing URLPattern instances by name and
preserve their real /api/catalog prefix and original permission-protected view.
"""
from django.urls import include, path
from catalog.urls import urlpatterns as catalog_patterns
from distribution.urls import urlpatterns as distribution_patterns


VERIFIED_NAMES = {
    "admin-curation-sources", "admin-evidence-curation", "admin-evidence-curation-publish", "public-evidence-curation",
    "admin-scholar-relation-list", "admin-scholar-relation-detail", "admin-scholar-relation-publish", "admin-scholar-relation-archive", "public-scholar-relation-list",
    "admin-curation-drafts",
    "work-list", "work-detail", "asset-manifest", "asset-page-content",
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
}
urlpatterns = [
    path("api/catalog/", include([pattern for pattern in catalog_patterns if pattern.name in VERIFIED_NAMES])),
    path("api/distribution/", include([pattern for pattern in distribution_patterns if pattern.name == "asset-access"])),
]
