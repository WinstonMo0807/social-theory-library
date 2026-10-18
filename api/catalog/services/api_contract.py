"""Small, shared helpers for the STL 4.0 public API contract.

The application still serves a few pre-4.0 URLs because existing bookmarks and
the current client use them.  Keeping the successor metadata in one place lets
those compatibility responses point at the same canonical workflow without
creating another search implementation.
"""

from django.conf import settings

CANONICAL_DISCOVERY_ENDPOINT = "/api/catalog/discovery-search/"
CANONICAL_SEMANTIC_ENDPOINT = "/api/catalog/discovery-search/"


def api_version():
    return str(getattr(settings, "API_CONTRACT_VERSION", "4.0")).strip() or "4.0"


def annotate_response(response, *, canonical_endpoint: str | None = None, deprecated: bool = False):
    """Attach machine-readable contract metadata to a DRF response."""

    response["X-STL-API-Version"] = api_version()
    if isinstance(getattr(response, "data", None), dict):
        response.data["api_version"] = api_version()
        if canonical_endpoint:
            response.data["canonical_endpoint"] = canonical_endpoint
        if deprecated:
            response.data["deprecated"] = True
    if canonical_endpoint:
        response["X-STL-Canonical-Endpoint"] = canonical_endpoint
    if deprecated:
        response["Deprecation"] = "true"
        if canonical_endpoint:
            response["Link"] = f'<{canonical_endpoint}>; rel="successor-version"'
    return response
