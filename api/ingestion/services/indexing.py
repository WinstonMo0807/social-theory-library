import time

import httpx
from django.conf import settings

from catalog.models import Asset


def _headers():
    if not settings.MEILISEARCH_MASTER_KEY:
        return {}
    return {"Authorization": f"Bearer {settings.MEILISEARCH_MASTER_KEY}"}


def _wait_task(task_payload: dict, timeout: float = 45) -> dict:
    task_uid = task_payload.get("taskUid")
    if task_uid is None:
        return task_payload
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/tasks/{task_uid}",
            headers=_headers(),
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "succeeded":
            return payload
        if payload.get("status") in {"failed", "canceled"}:
            error = payload.get("error", {})
            raise RuntimeError(error.get("message") or f"Meilisearch 任务 {task_uid} 失败。")
        time.sleep(0.15)
    raise TimeoutError(f"等待 Meilisearch 任务 {task_uid} 超时。")


def ensure_passage_index() -> None:
    base_url = settings.MEILISEARCH_URL.rstrip("/")
    response = httpx.get(
        f"{base_url}/indexes/passages",
        headers=_headers(),
        timeout=5,
    )
    if response.status_code == 404:
        created = httpx.post(
            f"{base_url}/indexes",
            headers=_headers(),
            json={"uid": "passages", "primaryKey": "id"},
            timeout=5,
        )
        created.raise_for_status()
        _wait_task(created.json())
    else:
        response.raise_for_status()

    settings_response = httpx.get(
        f"{base_url}/indexes/passages/settings",
        headers=_headers(),
        timeout=5,
    )
    settings_response.raise_for_status()
    current = settings_response.json()
    desired_searchable = ["title", "authors", "text"]
    desired_filterable = [
        "asset_id",
        "edition_id",
        "work_id",
        "document_type",
        "language",
        "publication_year",
        "theory_slugs",
        "topic_slugs",
        "is_public",
    ]
    if (
        current.get("searchableAttributes") != desired_searchable
        or current.get("filterableAttributes") != desired_filterable
    ):
        updated = httpx.patch(
            f"{base_url}/indexes/passages/settings",
            headers=_headers(),
            json={
                "searchableAttributes": desired_searchable,
                "filterableAttributes": desired_filterable,
                "displayedAttributes": [
                    "id",
                    "asset_id",
                    "edition_id",
                    "edition_slug",
                    "work_id",
                    "title",
                    "authors",
                    "document_type",
                    "language",
                    "publication_year",
                    "theory_slugs",
                    "theory_names",
                    "topic_slugs",
                    "topic_names",
                    "page_index",
                    "printed_label",
                    "text",
                    "bbox",
                    "is_public",
                ],
                "searchCutoffMs": 1200,
            },
            timeout=5,
        )
        updated.raise_for_status()
        _wait_task(updated.json())


def _indexed_asset_document_ids(asset_id: str) -> set[str]:
    base_url = settings.MEILISEARCH_URL.rstrip("/")
    document_ids: set[str] = set()
    offset = 0
    limit = 1000
    while True:
        response = httpx.post(
            f"{base_url}/indexes/passages/documents/fetch",
            headers=_headers(),
            json={
                "filter": f'asset_id = "{asset_id}"',
                "offset": offset,
                "limit": limit,
                "fields": ["id"],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        document_ids.update(str(item["id"]) for item in results if item.get("id"))
        total = int(payload.get("total") or len(document_ids))
        if offset + len(results) >= total:
            return document_ids
        if not results:
            raise RuntimeError("Meilisearch 文档分页提前结束。")
        offset += len(results)


def _remove_stale_asset_documents(asset_id: str, current_ids: set[str]) -> int:
    stale_ids = sorted(_indexed_asset_document_ids(asset_id) - current_ids)
    chunk_size = 1000
    for offset in range(0, len(stale_ids), chunk_size):
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/passages/documents/delete-batch",
            headers=_headers(),
            json=stale_ids[offset : offset + chunk_size],
            timeout=30,
        )
        response.raise_for_status()
        _wait_task(response.json(), timeout=60)
    return len(stale_ids)


def index_asset(asset: Asset, *, is_public: bool | None = None) -> dict:
    work = asset.edition.work
    if is_public is None:
        is_public = asset.edition.state == "published"
    authors = list(
        asset.edition.contributions.filter(approved=True)
        .order_by("order")
        .values_list("person__preferred_name", flat=True)
    )
    approved_relations = work.knowledge_relations.filter(approved=True).select_related(
        "theory_school",
        "topic",
    )
    theories = [
        relation.theory_school
        for relation in approved_relations
        if relation.theory_school_id
    ]
    topics = [
        relation.topic
        for relation in approved_relations
        if relation.topic_id
    ]
    passages = [
        {
            "id": str(passage.id),
            "asset_id": str(asset.id),
            "edition_id": str(asset.edition_id),
            "edition_slug": asset.edition.public_slug,
            "work_id": str(work.id),
            "title": work.title,
            "authors": authors,
            "document_type": work.document_type,
            "language": work.language,
            "publication_year": asset.edition.publication_year,
            "theory_slugs": [item.slug for item in theories],
            "theory_names": [item.name for item in theories],
            "topic_slugs": [item.slug for item in topics],
            "topic_names": [item.name for item in topics],
            "page_index": passage.page.index,
            "printed_label": passage.page.printed_label,
            "text": passage.text,
            "bbox": passage.bbox_union,
            "is_public": is_public,
        }
        for passage in asset.pages.prefetch_related("passages").all()
        for passage in passage.passages.all()
    ]
    try:
        ensure_passage_index()
        if not passages:
            removed = _remove_stale_asset_documents(str(asset.id), set())
            return {
                "backend": "no-passages",
                "documents": 0,
                "removed_stale_documents": removed,
            }
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/passages/documents",
            headers=_headers(),
            json=passages,
            timeout=30,
        )
        response.raise_for_status()
        task = _wait_task(response.json())
        removed = _remove_stale_asset_documents(
            str(asset.id),
            {passage["id"] for passage in passages},
        )
        return {
            "backend": "meilisearch",
            "documents": len(passages),
            "removed_stale_documents": removed,
            "task": task,
        }
    except (httpx.HTTPError, RuntimeError, TimeoutError) as exc:
        if settings.REQUIRE_EXTERNAL_SEARCH:
            raise
        return {
            "backend": "database-fallback",
            "documents": len(passages),
            "warning": str(exc),
        }


def remove_asset_from_index(asset: Asset) -> None:
    filter_expression = f'asset_id = "{asset.id}"'
    try:
        response = httpx.post(
            f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/passages/documents/delete",
            headers=_headers(),
            json={"filter": filter_expression},
            timeout=15,
        )
        response.raise_for_status()
        _wait_task(response.json(), timeout=20)
    except (httpx.HTTPError, RuntimeError, TimeoutError):
        if settings.REQUIRE_EXTERNAL_SEARCH:
            raise
