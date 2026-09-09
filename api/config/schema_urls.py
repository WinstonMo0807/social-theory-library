"""Verified contract surface. Legacy endpoints remain in the coverage audit.

No routing duplication: select the existing URLPattern instances by name and
preserve their real /api/catalog prefix and original permission-protected view.
"""
from django.urls import include, path
from catalog.urls import urlpatterns as catalog_patterns


VERIFIED_NAMES = {
    "cataloging-session-list", "cataloging-session-detail", "cataloging-session-abandon",
    "cataloging-candidate-decision", "cataloging-metadata-import", "cataloging-metadata-decision",
    "catalog-field-contracts",
    "publication-prepare", "publication-rollback",
    "publication-history",
    "media-list", "media-detail", "media-rendition",
    "work-cover-media-selection",
    "public-cover-metadata",
}
urlpatterns = [path("api/catalog/", include([pattern for pattern in catalog_patterns if pattern.name in VERIFIED_NAMES]))]
