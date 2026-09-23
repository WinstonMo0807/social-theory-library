"""Current-publication boundary for the versioned Meilisearch projection.

Only identifiers and bounded candidate sets are loaded here. Canonical originals,
manual decisions and the earlier semantic index are never rewritten.
"""
from __future__ import annotations

import json
from uuid import UUID

import httpx
from django.conf import settings
from django.db.models import Count, Q

from catalog.discovery_index_models import DiscoveryDocument, DiscoverySourceState
from catalog.models import EvidenceSpan, Page, SemanticIndexVersion
from catalog.services.discovery_inference import DiscoveryInferenceError, embed_texts, normalize_texts
from catalog.services.discovery_sources import edition_scope_records, iter_source_headers, source_queryset, fingerprint


class DiscoveryIndexError(RuntimeError):
    def __init__(self, code, message="检索索引暂不可用，请稍后重试。"):
        self.code = code
        super().__init__(message)


def meili(method, path, payload=None, *, timeout=30):
    headers = {"Authorization": f"Bearer {settings.MEILISEARCH_MASTER_KEY}"} if settings.MEILISEARCH_MASTER_KEY else {}
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(timeout, connect=3)) as client:
            response = client.request(method, settings.MEILISEARCH_URL.rstrip("/") + path, headers=headers, json=payload)
            if response.status_code == 404:
                raise DiscoveryIndexError("index_missing")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Never propagate a backend URL, key or document body into a public error.
        raise DiscoveryIndexError("index_unavailable") from exc


def active_generation():
    return SemanticIndexVersion.discovery_objects.filter(status="active").first()


def kinds_for(channel):
    return (("edition",) if channel == "passages" else
            ("reading_path", "recommendation_issue", "evidence_curation") if channel == "curation" else
            ("scholar", "node", "topic", "discipline", "subdiscipline", "concept", "timeline"))


def _matches(header, filters):
    """Metadata facets constrain passages, matching the existing Explore filters."""
    if header["channel"] != "passages":
        return True
    from catalog.services.semantic_search import YEAR_FILTERS
    filters = dict(filters)
    if filters.get("document_types"):
        filters["document_types"] = ["journal_article" if value == "article" else value for value in filters["document_types"]]
    simple = {"work_ids": [header.get("work_id")], "authors": header.get("author_ids", []),
              "document_types": [header.get("document_type")], "access": [header.get("access_status")]}
    for key, values in simple.items():
        if filters.get(key) and not set(map(str, filters[key])).intersection(map(str, values)):
            return False
    for key, field, attr in (("theory_node_ids", "theories", "id"), ("theories", "theories", "slug"),
                              ("topic_ids", "topics", "id"), ("topics", "topics", "slug")):
        values = [str(item.get(attr)) for item in header.get(field, []) if isinstance(item, dict)]
        if filters.get(key) and not set(map(str, filters[key])).intersection(values):
            return False
    year = header.get("publication_year")
    if filters.get("years"):
        ranges = [YEAR_FILTERS.get(str(value), (int(value), int(value)) if str(value).lstrip("-").isdigit() else (None, None))
                  for value in filters["years"]]
        if not any(year is not None and (low is not None or high is not None)
                   and (low is None or year >= low) and (high is None or year <= high) for low, high in ranges):
            return False
    if (filters.get("year_min") is not None and (year is None or year < int(filters["year_min"]))) or (
            filters.get("year_max") is not None and (year is None or year > int(filters["year_max"]))):
        return False
    if filters.get("concepts"):
        # The activated snapshot is authoritative, not newer draft relations.
        concepts = [item for item in header.get("theories", []) if item.get("type") == "concept"]
        values = {str(item.get(field)) for item in concepts for field in ("id", "slug")}
        if not set(map(str, filters["concepts"])).intersection(values):
            return False
    return True


def current_scopes(channel, access_statuses, filters=None):
    filters = filters or {}
    scopes = []
    if channel == "passages" and not any(value for key, value in filters.items() if key != "languages"):
        for _, _, token in edition_scope_records(access_statuses):
            scopes.append(token)
            if len(scopes) > 20000:
                raise DiscoveryIndexError("scope_limit", "当前可检索来源过多，请缩小馆藏筛选范围。")
        return scopes
    for kind in kinds_for(channel):
        for row, header in iter_source_headers(kind, access_statuses):
            if _matches(header, filters):
                scopes.append(header["scope_token"])
            if len(scopes) > 20000:
                raise DiscoveryIndexError("scope_limit", "当前可检索来源过多，请缩小馆藏筛选范围。")
    return scopes


def validate_discovery_results(channel, rows, access_statuses):
    """Hydrate by identity, then recheck source version AND the exact text slice."""
    if channel not in {"passages", "entities", "curation"}:
        return []
    refs = {}
    for row in rows[:1200]:
        try:
            refs[str(UUID(str(row.get("id") or row.get("document_id"))))] = row
        except (AttributeError, TypeError, ValueError):
            continue
    documents = list(DiscoveryDocument.objects.filter(pk__in=refs, channel=channel, keyword_ready=True,
                                                  access_status__in=access_statuses))
    # Sessions can retain a retired generation; it is safe only while the same
    # source remains public at the same revision. Its index is not consulted.
    headers, output = {}, {}
    source_ids = {}
    for doc in documents:
        source_ids.setdefault(doc.source_type, set()).add(doc.source_id)
    for kind, ids in source_ids.items():
        if kind not in kinds_for(channel):
            continue
        for row, header in iter_source_headers(kind, access_statuses,
                queryset=source_queryset(kind, access_statuses).filter(pk__in=ids)):
            headers[(kind, str(row.pk))] = header
    span_ids = [doc.payload.get("evidence_span_id") for doc in documents if doc.payload.get("evidence_span_id")]
    page_ids = [doc.payload.get("page_id") for doc in documents if not doc.payload.get("evidence_span_id") and doc.payload.get("page_id")]
    spans = {str(row["id"]): row for row in EvidenceSpan.objects.filter(pk__in=span_ids, is_stale=False).values(
        "id", "document_revision_id", "page__asset_id", "original_text")}
    pages = {str(row["id"]): row for row in Page.objects.filter(pk__in=page_ids).values("id", "asset_id", "text")}
    for doc in documents:
        ref = refs[str(doc.pk)]
        if ref.get("source_revision") and ref["source_revision"] != doc.source_revision:
            continue
        key = (doc.source_type, str(doc.source_id))
        header = headers.get(key)
        if not header or header["source_revision"] != doc.source_revision or header["scope_token"] != doc.scope_token:
            continue
        payload = dict(doc.payload)
        if channel == "passages":
            span_id, page_id = payload.get("evidence_span_id"), payload.get("page_id")
            if span_id:
                unit = spans.get(span_id)
                original = unit["original_text"] if unit and str(unit["document_revision_id"]) == str(doc.document_revision_id) and str(unit["page__asset_id"]) == header["asset_id"] else None
            else:
                unit = pages.get(page_id)
                original = unit["text"] if unit and str(unit["asset_id"]) == header["asset_id"] else None
            if original is None or fingerprint(original) != payload.get("unit_hash") or original[doc.start_offset:doc.end_offset] != doc.text:
                continue
        # Do not overwrite the passage's OCR/language/locator metadata with its
        # bibliographic header or expose the full knowledge source on one card.
        payload.update({key: value for key, value in header.items() if key not in {"text", "source_kind", "language"}})
        payload.pop("text", None)
        source_start = int(payload.get("source_start_offset") or 0)
        payload.update(id=str(doc.pk), document_id=str(doc.pk), source_revision=doc.source_revision,
                       text=doc.text, excerpt=doc.text, start_offset=source_start + doc.start_offset, end_offset=source_start + doc.end_offset,
                       unit_start_offset=doc.start_offset, unit_end_offset=doc.end_offset,
                       token_count=doc.token_count)
        # Display metadata is fresh; no vectors or internal source text leak.
        output[str(doc.pk)] = payload
    return [output[key] for key in refs if key in output]


def discovery_coverage(access_statuses, filters=None):
    generation = active_generation()
    # Stream snapshot metadata in batches. Coverage uses grouped SQL counts,
    # not one source-state query and two COUNTs for every book on every poll.
    current = {}
    filters = filters or {}
    if not any(value for key, value in filters.items() if key != "languages"):
        records = edition_scope_records(access_statuses)
    else:
        records = ((str(row.pk), header["source_revision"], header["scope_token"])
                   for row, header in iter_source_headers("edition", access_statuses) if _matches(header, filters))
    for key, revision, token in records:
        current[key] = (revision, token)
        if len(current) > 20000:
            raise DiscoveryIndexError("scope_limit", "当前可检索来源过多，请缩小馆藏筛选范围。")
    total = len(current)
    if not generation:
        return {"eligible_editions": total, "indexed_editions": 0, "vector_editions": 0,
                "passage_count": 0, "pending_editions": total, "partial": bool(total), "generation": None}
    # A source is ready only when its completed fingerprint is still current.
    ready, vector, text_count = 0, 0, 0
    counts = {(str(row["source_id"]), row["source_revision"]): row for row in
        DiscoveryDocument.objects.filter(generation=generation, source_type="edition", source_id__in=current,
            access_status__in=access_statuses).values("source_id", "source_revision").annotate(
                keywords=Count("pk", filter=Q(keyword_ready=True)), vectors=Count("pk", filter=Q(keyword_ready=True, vector_ready=True)))}
    states = DiscoverySourceState.objects.filter(generation=generation, source_type="edition", source_id__in=current,
        indexed_at__isnull=False, error="").values("source_id", "source_revision", "completed_count", "expected_count")
    for state in states:
        key = (str(state["source_id"]), state["source_revision"])
        if current[key[0]][0] != key[1] or state["completed_count"] != state["expected_count"]:
            continue
        count = counts.get(key, {})
        n = count.get("keywords", 0)
        if n and n == state["expected_count"]:
            ready += 1
            text_count += n
            vector += int(count.get("vectors", 0) == n)
    return {"eligible_editions": total, "indexed_editions": ready, "vector_editions": vector,
            "passage_count": text_count, "pending_editions": max(0, total - ready),
            "partial": ready < total or vector < ready, "generation": str(generation.pk)}


def discovery_candidates(query, channel, filters, access_statuses, limit=120, expanded=False, request_context=None):
    # This dictionary lives only for one Celery query task. Pin its index/model
    # generation across channels and reuse query encoding without shared caches.
    context = request_context if request_context is not None else {}
    if "generation" not in context:
        context["generation"] = active_generation()
    generation = context["generation"]
    filters = filters or {}
    coverage = discovery_coverage(access_statuses, filters) if channel == "passages" else {}
    warnings = []
    empty = {"sparse": [], "dense": [], "version": str(generation.pk) if generation else "",
             "reranker_artifact": generation.config_snapshot.get("reranker_artifact", "") if generation else "",
             "warnings": warnings, "coverage": coverage}
    if not generation:
        warnings.append({"code": "index_pending", "message": "检索索引尚未建立，管理员可在处理中心查看进度。"})
        return empty
    scopes = current_scopes(channel, access_statuses, filters)
    if not scopes:
        return empty
    if channel != "passages" and filters:
        warnings.append({"code": "passage_facets", "message": "馆藏筛选作用于原文；知识入口与策展按问题检索。"})
    limit = min(300, max(1, int(limit)))
    normalized = query
    try:
        normalized_cache = context.setdefault("normalized", {})
        normalization_key = (str(generation.pk), query)
        if normalization_key not in normalized_cache:
            normalized_cache[normalization_key] = normalize_texts([query])["texts"][0]
        normalized = normalized_cache[normalization_key]
    except DiscoveryInferenceError:
        warnings.append({"code": "normalization_unavailable", "message": "文字规范化服务暂不可用，当前保留输入文字检索。"})
    base = {"limit": limit, "filter": [f"channel = {json.dumps(channel)}",
            f"scope_token IN {json.dumps(scopes)}", f"access_status IN {json.dumps(list(access_statuses))}"],
            "attributesToRetrieve": ["id", "source_revision"]}
    if channel == "passages" and filters.get("languages"):
        from catalog.services.semantic_search import _language_filter_values
        base["filter"].append(f"language IN {json.dumps(_language_filter_values(filters['languages']))}")
    try:
        sparse = meili("POST", f"/indexes/{generation.uid}/search", {**base, "q": normalized})
        empty["sparse"] = sparse.get("hits", [])
        from .discovery_query import keyword_question
        keywords = keyword_question(normalized)
        if channel == "passages" and keywords != normalized:
            extra = meili("POST", f"/indexes/{generation.uid}/search", {**base, "q": keywords, "attributesToSearchOn": ["normalized_text"]})
            # Fuse before hydration so each source/text slice is loaded once.
            scores, refs = {}, {}
            for hits, weight in ((empty["sparse"], 1.0), (extra.get("hits", []), 0.85)):
                for rank, row in enumerate(hits, 1):
                    key = row.get("id")
                    if key:
                        scores[key] = scores.get(key, 0) + weight / (60 + rank)
                        refs[key] = row
            empty["sparse"] = [refs[key] for key in sorted(scores, key=lambda key: (-scores[key], key))][:limit]
    except DiscoveryIndexError:
        warnings.append({"code": "keyword_unavailable", "message": "关键词索引暂不可用。"})
    try:
        vector_cache = context.setdefault("vectors", {})
        vector_key = (generation.config_snapshot["embedding_artifact"], query)
        if vector_key not in vector_cache:
            vector_cache[vector_key] = embed_texts([query], kind="query", expected_artifact=vector_key[0])["vectors"][0]
        vector = vector_cache[vector_key]
        dense = meili("POST", f"/indexes/{generation.uid}/search", {**base, "q": "", "vector": vector,
            "hybrid": {"embedder": "discovery", "semanticRatio": 1.0}})
        empty["dense"] = dense.get("hits", [])
    except (DiscoveryIndexError, DiscoveryInferenceError, KeyError):
        warnings.append({"code": "dense_unavailable", "message": "向量检索暂不可用，当前只显示关键词召回的材料。"})
    hydrated = {row["id"]: row for row in validate_discovery_results(channel, [*empty["sparse"], *empty["dense"]], access_statuses)}
    for branch in ("sparse", "dense"):
        empty[branch] = [hydrated[row["id"]] for row in empty[branch] if row.get("id") in hydrated]
    return empty
