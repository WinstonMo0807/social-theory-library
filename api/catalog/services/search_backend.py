from dataclasses import dataclass

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
    try:
        payload = {
            "q": query,
            "limit": limit,
            "attributesToRetrieve": ["id"],
            "showRankingScore": True,
            "filter": "is_public = true",
        }
        if asset_id:
            payload["filter"] = f'is_public = true AND asset_id = "{asset_id}"'
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/passages/search",
            headers=_headers(),
            json=payload,
            timeout=2,
        )
        if response.status_code == 404:
            return ExternalPassageSearch([], 0)
        response.raise_for_status()
        data = response.json()
        ids = [str(hit["id"]) for hit in data.get("hits", []) if hit.get("id")]
        return ExternalPassageSearch(
            ids=ids,
            estimated_total=int(data.get("estimatedTotalHits", len(ids))),
        )
    except (httpx.HTTPError, KeyError, ValueError):
        if settings.REQUIRE_EXTERNAL_SEARCH:
            raise
        return None
