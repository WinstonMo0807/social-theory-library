from dataclasses import dataclass
import json

import httpx
from django.conf import settings


@dataclass(frozen=True)
class ExternalPassageSearch:
    ids: list[str]
    estimated_total: int


def _headers():
    if not settings.MEILISEARCH_MASTER_KEY:
        return {}
    return {"Authorization": f"Bearer {settings.MEILISEARCH_MASTER_KEY}"}


def external_passage_ids(
    query: str,
    limit: int = 50,
    asset_id: str | None = None,
) -> ExternalPassageSearch | None:
    if not settings.USE_EXTERNAL_SEARCH:
        return None
    from catalog.services.publication_eligibility import public_editions

    editions = public_editions(require_fulltext=True)
    if asset_id:
        editions = editions.filter(active_catalog_revision__reader_asset_id=asset_id)
    revision_ids = []
    legacy_assets = []
    for edition in editions:
        revision = edition.active_catalog_revision
        provenance = revision.provenance or {}
        index_id = provenance.get("fulltext_index_revision_id")
        if index_id == "legacy" or (not index_id and provenance.get("source") == "v304_safe_backfill"):
            legacy_assets.append(str(revision.reader_asset_id))
        else:
            revision_ids.append(str(index_id or revision.pk))
    if not revision_ids and not legacy_assets:
        return ExternalPassageSearch([], 0)
    clauses = []
    if revision_ids:
        clauses.append(f"catalog_revision_id IN {json.dumps(sorted(set(revision_ids)))}")
    if legacy_assets:
        clauses.append(f"(catalog_revision_id NOT EXISTS AND asset_id IN {json.dumps(sorted(set(legacy_assets)))})")
    active_filter = "is_public = true AND (" + " OR ".join(clauses) + ")"
    try:
        payload = {
            "q": query,
            "limit": limit,
            "attributesToRetrieve": ["id", "passage_id"],
            "showRankingScore": True,
            "filter": active_filter,
        }
        if asset_id:
            payload["filter"] = f'{active_filter} AND asset_id = "{asset_id}"'
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/passages/search",
            headers=_headers(),
            json=payload,
            timeout=2,
        )
        if response.status_code == 400 and not revision_ids and legacy_assets:
            # Before the additive index-settings upgrade has completed, an
            # old index cannot filter on the newly introduced attribute.
            # Legacy-only fallback remains restricted to the exact active
            # published asset whitelist; never use it for modern revisions.
            error = response.json()
            message = str(error.get("message") or "")
            if error.get("code") == "invalid_search_filter" and "catalog_revision_id" in message:
                payload["filter"] = (
                    "is_public = true AND asset_id IN "
                    + json.dumps(sorted(set(legacy_assets)))
                )
                response = httpx.post(
                    f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/passages/search",
                    headers=_headers(), json=payload, timeout=2,
                )
        if response.status_code == 404:
            return ExternalPassageSearch([], 0)
        response.raise_for_status()
        data = response.json()
        ids = list(dict.fromkeys(str(hit.get("passage_id") or hit["id"]) for hit in data.get("hits", []) if hit.get("id")))
        return ExternalPassageSearch(
            ids=ids,
            estimated_total=int(data.get("estimatedTotalHits", len(ids))),
        )
    except (httpx.HTTPError, KeyError, ValueError):
        if settings.REQUIRE_EXTERNAL_SEARCH:
            raise
        return None
