"""One typed query entry for source recall and published editorial objects.

Original text uses the existing Meilisearch lifecycle. Bibliography, identity
and Wiki text use the authoritative published PostgreSQL projection; they are
never promoted to verbatim source evidence. No model calls for object matching.
"""
from time import monotonic
from django.db.models import Q
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError
from catalog import models as m
from catalog.services.knowledge_core import entity_data
from catalog.services.knowledge_public import public_entities, page_data
from catalog.services.publication_eligibility import public_editions
from catalog.services.knowledge_workspace import public_page_url

TYPES = ("original_text", "bibliography", "knowledge_object", "knowledge_page", "curated_content")


def _excerpt(text, query):
    at = text.casefold().find(query.casefold())
    start = max(0, at - 80)
    return ("…" if start else "") + text[start:start + 400] + ("…" if len(text) > start + 400 else "")


def _objects(query, kind, actor, limit, work_id):
    """Bounded candidates; final matching uses only visible published content."""
    if kind == "bibliography":
        rows = public_editions().select_related("work", "active_catalog_revision").filter(
            Q(active_catalog_revision__snapshot__work__title__icontains=query))
        if work_id:
            rows = rows.filter(work_id=work_id)
        rows = rows.order_by("work_id", "-is_primary", "pk")
    elif kind == "knowledge_object":
        from catalog.services.knowledge_entity_queries import entity_query
        rows = entity_query(public_entities(), query=query, public=True, definitions=True)
        if work_id:
            rows = rows.filter(assertion_participations__assertion__sources__work_id=work_id,
                assertion_participations__assertion__status="published").distinct()
    else:
        rows = m.KnowledgePage.objects.filter(status="published").filter(
            Q(title__icontains=query) | Q(scope__icontains=query) | Q(body_blocks__icontains=query)).select_related("entity", "work").order_by("title", "pk")
        if work_id:
            rows = rows.filter(work_id=work_id)
    results, seen = [], set()
    scan_limit = max(100, limit * 5)
    candidates = list(rows[:scan_limit + 1])
    for row in candidates[:scan_limit]:
        if kind == "bibliography":
            if row.work_id in seen:
                continue
            snapshot = row.active_catalog_revision.snapshot
            title = (snapshot.get("work") or {}).get("title", "")
            if query.casefold() not in title.casefold():
                continue
            seen.add(row.work_id)
            results.append({"id": str(row.work_id), "source_type": kind, "work_id": str(row.work_id),
                "edition_id": str(row.pk), "title": title, "excerpt": (snapshot.get("edition") or {}).get("version_label", ""),
                "url": f"/works/{row.public_slug}", "coverage": "published_bibliography"})
        elif kind == "knowledge_object":
            value = entity_data(row, public=True)
            text = "\n".join([value["label"], value["definition"], *[v["text"] for v in value["aliases"]]])
            if query.casefold() not in text.casefold():
                continue
            page = m.KnowledgePage.objects.filter(entity=row, status="published").first()
            results.append({"id": str(row.pk), "source_type": kind, "title": value["label"], "excerpt": _excerpt(value["definition"], query),
                "entity": value, "page_id": str(page.pk) if page else None,
                "url": public_page_url(page) if page else "", "coverage": "published_identity"})
        else:
            try:
                value = page_data(row, actor)
            except Http404:
                continue
            body = "\n".join([value.get("scope", ""), *[v.get("text", "") for v in value["blocks"]]]).strip()
            text = value["title"] + "\n" + body
            if query.casefold() not in text.casefold():
                continue  # A withdrawn reference cannot match via its hidden block.
            results.append({"id": str(row.pk), "source_type": kind, "title": value["title"], "excerpt": _excerpt(body, query),
                "page_id": str(row.pk), "revision_id": value["revision_id"], "work_id": str(row.work_id) if row.work_id else None,
                "url": public_page_url(row), "coverage": "published_compilation"})
        if len(results) > limit:
            break
    return {"status": "ready", "results": results[:limit], "has_more": len(results) > limit or len(candidates) > scan_limit,
        "coverage": "bounded_candidates", "warnings": []}


def search(query, actor, *, source_types=None, work_id=None, limit=20, mode="keyword"):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("请登录后检索书库。")
    if not isinstance(query, str) or not 2 <= len(query.strip()) <= 1200:
        raise ValidationError("检索词须为2至1200字符。")
    kinds = source_types if source_types is not None else TYPES
    if not isinstance(kinds, (list, tuple)) or not kinds or any(v not in TYPES for v in kinds):
        raise ValidationError("请选择原文、作品、实体或知识页。")
    if mode not in {"keyword", "hybrid"} or not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise ValidationError("检索模式或条数无效。")
    if work_id:
        from catalog.services.intelligence_changes import uuid_value
        work_id = uuid_value(work_id)
        if not public_editions().filter(work_id=work_id).exists():
            raise Http404("作品当前尚未公开。")
    query = query.strip()
    started, groups = monotonic(), {}
    for kind in dict.fromkeys(kinds):
        if kind not in {"original_text", "curated_content"}:
            groups[kind] = _objects(query, kind, actor, limit, work_id)
            continue
        from .search import retrieve_channel
        from catalog.services.discovery_projection import DiscoveryIndexError
        from catalog.services.semantic_search import viewer_access_statuses
        try:
            filters = {"_keyword_only": mode == "keyword"}
            if work_id:
                filters["work_ids"] = [str(work_id)]
            result = retrieve_channel(query, "passages" if kind == "original_text" else "curation", filters, viewer_access_statuses(authenticated=True), limit=limit)
            codes = {w["code"] for w in result["warnings"]}
            if "keyword_unavailable" in codes and (mode == "keyword" or "dense_unavailable" in codes):
                raise DiscoveryIndexError("search_unavailable", "原文检索请求失败，请重试；查询条件已保留。")
            groups[kind] = {"status": "waiting_index" if codes & {"index_pending", "scope_index_pending", "coverage_pending"} else "ready",
                "results": [{**v, "source_type": kind} for v in result["rows"][:limit]], "warnings": result["warnings"],
                "coverage": "returned_results_only", "has_more": len(result["rows"]) >= limit}
        except DiscoveryIndexError as exc:
            groups[kind] = {"status": "failed", "code": exc.code, "detail": str(exc), "results": [], "warnings": []}
    failed = sum(v["status"] == "failed" for v in groups.values())
    return {"query": query, "groups": groups, "status": "failed" if failed == len(groups) else "partial" if failed else "ready",
        "elapsed_ms": round((monotonic() - started) * 1000), "mode": mode}
