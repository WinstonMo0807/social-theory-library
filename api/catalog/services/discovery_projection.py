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
from catalog.services.discovery_sources import edition_scope_records, iter_edition_metadata_headers, iter_source_headers, source_queryset, fingerprint
from catalog.services.publication_eligibility import public_editions
from catalog.services.text import page_text_range
from catalog.services.contribution_projection import SnapshotAuthorCandidate, contribution_projection


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


def _matches(header, filters, *, edition=None, contribution_cache=None, access_statuses=None):
    """Metadata facets constrain passages, matching the existing Explore filters."""
    if header["channel"] != "passages":
        return True
    if filters.get("_asset_id") and str(header.get("asset_id")) != str(filters["_asset_id"]):
        return False
    if str(header.get("edition_id")) in filters.get("_excluded_edition_ids", []):
        return False
    if filters.get("availability"):
        available = {"readable": header.get("reader_available", False), "pdf": header.get("pdf_available", False)}
        if "zh_translation" in filters["availability"]:
            cache = contribution_cache if contribution_cache is not None else {}
            key = ("readable_chinese_translations", tuple(sorted(access_statuses or [])))
            if key not in cache:
                # Only activated, accessible Chinese translations count. A Chinese
                # original or a draft translation relation is not a translation.
                rows = public_editions().filter(active_catalog_revision__snapshot__work__language__istartswith="zh",
                    active_catalog_revision__reader_asset__access_status__in=access_statuses or [])
                translated = set()
                for _, candidate in iter_edition_metadata_headers(rows):
                    if candidate["reader_available"] and candidate["chinese_translation"]:
                        translated.add(candidate["work_id"])
                        if candidate["translation_of_id"]:
                            translated.add(candidate["translation_of_id"])
                cache[key] = translated
            available["zh_translation"] = bool({header.get("work_id"), header.get("translation_of_id")} & cache[key])
        if not any(available.get(value, False) for value in filters["availability"]):
            return False
    from catalog.services.semantic_search import YEAR_FILTERS
    filters = dict(filters)
    if filters.get("document_types"):
        filters["document_types"] = ["journal_article" if value == "article" else value for value in filters["document_types"]]
    if filters.get("authors") and edition is not None:
        if contribution_projection(edition, cache=contribution_cache, access_statuses=access_statuses).matching_ranges(filters["authors"]) == []:
            return False
    simple = {"work_ids": [header.get("work_id")],
              "document_types": [header.get("document_type")], "access": [header.get("access_status")]}
    if edition is None:
        simple["authors"] = header.get("author_ids", [])
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


def _edition_scope_queryset(access_statuses, filters):
    rows = source_queryset("edition", access_statuses)
    if filters.get("work_ids"):
        rows = rows.filter(work_id__in=filters["work_ids"])
    if filters.get("_asset_id"):
        rows = rows.filter(active_catalog_revision__reader_asset_id=filters["_asset_id"])
    if filters.get("_primary_only"):
        rows = rows.filter(is_primary=True)
    if filters.get("authors"):
        rows = rows.filter(SnapshotAuthorCandidate(filters["authors"]))
    return rows


def current_scopes(channel, access_statuses, filters=None, *, author_ranges=None, contribution_cache=None):
    filters = filters or {}
    scopes = []
    contribution_cache = contribution_cache if contribution_cache is not None else {}
    if channel == "passages" and not any(value for key, value in filters.items() if key not in {"languages", "_keyword_only"}):
        for _, _, token in edition_scope_records(access_statuses):
            scopes.append(token)
            if len(scopes) > 20000:
                raise DiscoveryIndexError("scope_limit", "当前可检索来源过多，请缩小馆藏筛选范围。")
        return scopes
    for kind in kinds_for(channel):
        queryset = _edition_scope_queryset(access_statuses, filters) if kind == "edition" else None
        for row, header in iter_source_headers(kind, access_statuses, queryset=queryset):
            if _matches(header, filters, edition=row if kind == "edition" else None, contribution_cache=contribution_cache, access_statuses=access_statuses):
                scopes.append(header["scope_token"])
                if kind == "edition" and filters.get("authors") and author_ranges is not None:
                    author_ranges[header["scope_token"]] = contribution_projection(row, cache=contribution_cache, access_statuses=access_statuses).matching_ranges(filters["authors"])
            if len(scopes) > 20000:
                raise DiscoveryIndexError("scope_limit", "当前可检索来源过多，请缩小馆藏筛选范围。")
    return scopes


def validate_discovery_results(channel, rows, access_statuses, *, filters=None, require_keyword=True):
    """Hydrate by identity, then recheck source version AND the exact text slice."""
    if channel not in {"passages", "entities", "curation"}:
        return []
    refs = {}
    for row in rows[:1200]:
        try:
            refs[str(UUID(str(row.get("id") or row.get("document_id"))))] = row
        except (AttributeError, TypeError, ValueError):
            continue
    documents = DiscoveryDocument.objects.filter(pk__in=refs, channel=channel, access_status__in=access_statuses)
    if require_keyword:
        documents = documents.filter(keyword_ready=True)
    documents = list(documents)
    # Sessions can retain a retired generation; it is safe only while the same
    # source remains public at the same revision. Its index is not consulted.
    headers, editions, output = {}, {}, {}
    source_ids = {}
    for doc in documents:
        source_ids.setdefault(doc.source_type, set()).add(doc.source_id)
    for kind, ids in source_ids.items():
        if kind not in kinds_for(channel):
            continue
        for row, header in iter_source_headers(kind, access_statuses,
                queryset=source_queryset(kind, access_statuses).filter(pk__in=ids)):
            headers[(kind, str(row.pk))] = header
            if kind == "edition":
                editions[str(row.pk)] = row
    span_ids = [doc.payload.get("evidence_span_id") for doc in documents if doc.payload.get("evidence_span_id")]
    page_ids = [doc.payload.get("page_id") for doc in documents if not doc.payload.get("evidence_span_id") and doc.payload.get("page_id")]
    spans = {str(row["id"]): row for row in EvidenceSpan.objects.filter(pk__in=span_ids, is_stale=False).values(
        "id", "document_revision_id", "page__asset_id", "page__index", "original_text", "page__text", "start_offset", "end_offset", "section")}
    pages = {str(row["id"]): row for row in Page.objects.filter(pk__in=page_ids).values("id", "asset_id", "index", "text")}
    from catalog.models import DocumentNodeSegment
    from catalog.services.knowledge_sources import digest
    logical_ids = [d.payload.get("node_segment_id") for d in documents if d.payload.get("node_segment_id")]
    logical = {str(s.pk):s for s in DocumentNodeSegment.objects.filter(pk__in=logical_ids).select_related("page","node")}
    contribution_cache = {}
    for doc in documents:
        ref = refs[str(doc.pk)]
        if ref.get("source_revision") and ref["source_revision"] != doc.source_revision:
            continue
        key = (doc.source_type, str(doc.source_id))
        header = headers.get(key)
        if not header or header["source_revision"] != doc.source_revision or header["scope_token"] != doc.scope_token:
            continue
        if (filters or {}).get("availability") and not _matches(header, {"availability": filters["availability"]},
                contribution_cache=contribution_cache, access_statuses=access_statuses):
            continue
        payload = dict(doc.payload)
        if channel == "passages":
            span_id, page_id = payload.get("evidence_span_id"), payload.get("page_id")
            segment_id = payload.get("node_segment_id")
            if segment_id:
                segment = logical.get(segment_id)
                if not segment or segment.page.document_revision_id != doc.document_revision_id or segment.node.document_revision_id != doc.document_revision_id:
                    continue
                if (str(segment.node.structure_id) != payload.get("structure_id") or str(segment.node_id) != payload.get("node_id")
                        or str(segment.page_id) != payload.get("snapshot_id") or segment.start != payload.get("source_start_offset")
                        or digest(segment.page.text) != segment.page.content_hash):
                    continue
                original = segment.page.text[segment.start:segment.end]
                if digest(original) != segment.content_hash:
                    continue
                unit = {"index":segment.page.page_number}
            elif span_id:
                unit = spans.get(span_id)
                original = unit["original_text"] if unit and str(unit["document_revision_id"]) == str(doc.document_revision_id) and str(unit["page__asset_id"]) == header["asset_id"] else None
            else:
                unit = pages.get(page_id)
                original = unit["text"] if unit and str(unit["asset_id"]) == header["asset_id"] else None
            if original is None or fingerprint(original) != payload.get("unit_hash") or original[doc.start_offset:doc.end_offset] != doc.text:
                continue
            if not segment_id:
                payload["section_title"] = str(unit.get("section") or "") if span_id else ""
            # Indexed similarity is not an editorial attribution decision.
            payload["attribution"] = {"status": "unknown", "label": "待人工核对",
                "notice": "请结合上下文区分作者自述、转引与评论；检索相关性不证明观点归属。"}
            if segment_id:
                payload["page_text_range"] = page_text_range(segment.page.text,doc.text,
                    segment.start+doc.start_offset,segment.start+doc.end_offset)
            elif span_id:
                # The saved span and index may predate the corrected extractor.
                # Never certify raw-page offsets solely from cached metadata.
                exact_unit = page_text_range(unit["page__text"], original, unit["start_offset"], unit["end_offset"])
                payload["page_text_range"] = (page_text_range(unit["page__text"], doc.text,
                    unit["start_offset"] + doc.start_offset, unit["start_offset"] + doc.end_offset) if exact_unit else None)
            else:
                payload["page_text_range"] = page_text_range(original, doc.text, doc.start_offset, doc.end_offset)
        # Do not overwrite the passage's OCR/language/locator metadata with its
        # bibliographic header or expose the full knowledge source on one card.
        payload.update({key: value for key, value in header.items() if key not in {"text", "source_kind", "language"}})
        if channel == "passages":
            page_number = unit["page__index"] if span_id else unit["index"]
            authors = contribution_projection(editions[str(doc.source_id)], cache=contribution_cache, access_statuses=access_statuses).for_range(
                header["asset_id"], doc.document_revision_id, page_number)
            if (filters or {}).get("authors") and not set(map(str, filters["authors"])).intersection(authors["author_ids"]):
                continue
            payload.update(authors, pdf_page=page_number, page_index=page_number)
        payload.pop("text", None)
        source_start = int(payload.get("source_start_offset") or 0)
        payload.update(id=str(doc.pk), document_id=str(doc.pk), source_revision=doc.source_revision,
                       text=doc.text, excerpt=doc.text, start_offset=source_start + doc.start_offset, end_offset=source_start + doc.end_offset,
                       unit_start_offset=doc.start_offset, unit_end_offset=doc.end_offset,
                       token_count=doc.token_count)
        # Display metadata is fresh; no vectors or internal source text leak.
        output[str(doc.pk)] = payload
    return [output[key] for key in refs if key in output]


def _published_coverage(access_statuses, filters, eligible_ids, *, contribution_cache=None):
    # Count the actual published metadata scope without admitting unfinished
    # OCR or bibliographic-only records to retrieval. Never inspect draft text.
    rows = public_editions().filter(Q(active_catalog_revision__reader_asset__isnull=True)
        | Q(active_catalog_revision__reader_asset__access_status__in=access_statuses))
    if filters.get("work_ids"):
        rows = rows.filter(work_id__in=filters["work_ids"])
    if filters.get("_asset_id"):
        rows = rows.filter(active_catalog_revision__reader_asset_id=filters["_asset_id"])
    if filters.get("_primary_only"):
        rows = rows.filter(is_primary=True)
    totals = {"published_editions": 0, "bibliographic_editions": 0, "text_pending_editions": 0}
    if filters.get("authors"):
        rows = rows.filter(SnapshotAuthorCandidate(filters["authors"]))
    for edition, header in iter_edition_metadata_headers(rows):
        if not _matches(header, filters, edition=edition, contribution_cache=contribution_cache, access_statuses=access_statuses):
            continue
        totals["published_editions"] += 1
        if totals["published_editions"] > 20000:
            raise DiscoveryIndexError("scope_limit", "当前可检索来源过多，请缩小馆藏筛选范围。")
        if str(edition.pk) in eligible_ids:
            continue
        snapshot_edition = (edition.active_catalog_revision.snapshot or {}).get("edition") or {}
        mode = snapshot_edition.get("publication_mode", edition.publication_mode)
        totals["bibliographic_editions" if mode == "bibliographic" else "text_pending_editions"] += 1
    return totals


def discovery_coverage(access_statuses, filters=None, *, contribution_cache=None):
    contribution_cache = contribution_cache if contribution_cache is not None else {}
    generation = active_generation()
    # Stream snapshot metadata in batches. Coverage uses grouped SQL counts,
    # not one source-state query and two COUNTs for every book on every poll.
    current = {}
    filters = filters or {}
    if not any(value for key, value in filters.items() if key not in {"languages", "_keyword_only"}):
        records = edition_scope_records(access_statuses)
    else:
        queryset = _edition_scope_queryset(access_statuses, filters)
        records = ((str(row.pk), header["source_revision"], header["scope_token"])
                   for row, header in iter_source_headers("edition", access_statuses, queryset=queryset) if _matches(header, filters, edition=row, contribution_cache=contribution_cache, access_statuses=access_statuses))
    for key, revision, token in records:
        current[key] = (revision, token)
        if len(current) > 20000:
            raise DiscoveryIndexError("scope_limit", "当前可检索来源过多，请缩小馆藏筛选范围。")
    total = len(current)
    published = _published_coverage(access_statuses, filters, current, contribution_cache=contribution_cache)
    if not generation:
        return {**published, "eligible_editions": total, "indexed_editions": 0, "vector_editions": 0, "projected_editions": 0,
                "passage_count": 0, "pending_editions": total, "index_pending_editions": total,
                "vector_pending_editions": total, "partial": bool(total or published["text_pending_editions"]), "generation": None}
    # A source is ready only when its completed fingerprint is still current.
    ready, vector, text_count, projected = 0, 0, 0, 0
    counts = {(str(row["source_id"]), row["source_revision"]): row for row in
        DiscoveryDocument.objects.filter(generation=generation, source_type="edition", source_id__in=current,
            access_status__in=access_statuses).values("source_id", "source_revision").annotate(
                keywords=Count("pk", filter=Q(keyword_ready=True)), vectors=Count("pk", filter=Q(keyword_ready=True, vector_ready=True)),
                passages=Count("pk", filter=Q(channel="passages", keyword_ready=True)))}
    states = DiscoverySourceState.objects.filter(generation=generation, source_type="edition", source_id__in=current,
        indexed_at__isnull=False, error="").values("source_id", "source_revision", "completed_count", "expected_count")
    for state in states:
        key = (str(state["source_id"]), state["source_revision"])
        if current[key[0]][0] != key[1] or state["completed_count"] != state["expected_count"]:
            continue
        count = counts.get(key, {})
        n = count.get("keywords", 0)
        # Fully written replacement slices may coexist with valid old vectors.
        if n and n >= state["expected_count"]:
            ready += 1
            text_count += n
            vector += int(count.get("vectors", 0) == n)
            projected += int(count.get("passages", 0) > 0)
    return {**published, "eligible_editions": total, "indexed_editions": ready, "vector_editions": vector, "projected_editions": projected,
            "passage_count": text_count, "pending_editions": max(0, total - ready),
            "index_pending_editions": max(0, total - ready), "vector_pending_editions": max(0, total - vector),
            "partial": bool(published["text_pending_editions"] or ready < total or vector < ready), "generation": str(generation.pk)}


def _author_document_filter(generation, author_ranges, access_statuses):
    """Filter before ranking; a large anthology cannot crowd out its selected chapter."""
    whole = [scope for scope, ranges in author_ranges.items() if ranges is None]
    chapter_condition = Q(pk__in=[])
    branches_count = sum(1 if ranges is None else len(ranges) for ranges in author_ranges.values())
    if branches_count > 400:
        raise DiscoveryIndexError("author_scope_limit", "作者范围超过 400 个版本或章节，请缩小馆藏范围后重试。")
    for scope, ranges in author_ranges.items():
        for chapter in ranges or []:
            chapter_condition |= Q(scope_token=scope, document_revision_id=chapter["document_revision_id"],
                payload__asset_id=chapter["asset_id"], payload__pdf_page__gte=chapter["page_start"],
                payload__pdf_page__lte=chapter["page_end"])
    # ponytail: bound the ID predicate to 5,000 documents; narrower filters are
    # required beyond this instead of silently trimming a chapter's candidates.
    ids = list(DiscoveryDocument.objects.filter(chapter_condition, generation=generation, channel="passages",
        keyword_ready=True, access_status__in=access_statuses).values_list("pk", flat=True)[:5001])
    if len(ids) > 5000:
        raise DiscoveryIndexError("author_scope_limit", "所选章节超过 5,000 个检索片段，请缩小作品或年份范围后重试。")
    branches = ([f"scope_token IN {json.dumps(whole)}"] if whole else [])
    if ids:
        fields = meili("GET", f"/indexes/{generation.uid}/settings/filterable-attributes")
        if "id" not in fields and "*" not in fields:
            raise DiscoveryIndexError("author_scope_index_pending", "当前索引尚未支持准确章节范围，需通过现有索引任务更新后再按章节作者检索。")
        branches.append(f"id IN {json.dumps(list(map(str, ids)))}")
    return " OR ".join(f"({branch})" for branch in branches) or None


def discovery_candidates(query, channel, filters, access_statuses, limit=120, expanded=False, request_context=None):
    # This dictionary lives only for one Celery query task. Pin its index/model
    # generation across channels and reuse query encoding without shared caches.
    context = request_context if request_context is not None else {}
    if "generation" not in context:
        context["generation"] = active_generation()
    generation = context["generation"]
    filters = filters or {}
    contribution_cache = context.setdefault("contribution_projections", {})
    warnings = []
    try:
        coverage = discovery_coverage(access_statuses, filters, contribution_cache=contribution_cache) if channel == "passages" else {}
    except DiscoveryIndexError as error:
        coverage = {}
        warnings.append({"code": error.code, "message": str(error)})
    empty = {"sparse": [], "dense": [], "contextual": [], "version": str(generation.pk) if generation else "",
             "index_uid": str(generation.uid) if generation else "",
             "embedding_artifact": generation.config_snapshot.get("embedding_artifact", "") if generation else "",
             "embedding_dimensions": int(generation.dimensions or generation.config_snapshot.get("dimensions") or 0) if generation else None,
             "reranker_artifact": generation.config_snapshot.get("reranker_artifact", "") if generation else "",
             "warnings": warnings, "coverage": coverage}
    scope = filters.get("search_scope")
    if scope and channel != "passages":
        return empty
    if scope in {"body", "notes", "topics"} and generation and generation.config_snapshot.get("scope_fields_version") != 1:
        warnings.append({"code": "scope_index_pending", "message": "当前索引尚无正文、注释和主题的独立字段。请在索引与任务中更新索引后使用此范围；全部、书名和作者检索仍可使用。"})
        return empty
    if warnings:
        return empty
    author_ranges = {}
    try:
        scopes = current_scopes(channel, access_statuses, filters, author_ranges=author_ranges, contribution_cache=contribution_cache)
    except DiscoveryIndexError as error:
        warnings.append({"code": error.code, "message": str(error)})
        return empty
    # Only the worker installs this in-memory callback. It observes the exact
    # existing scope; no extra retrieval branch or model request is introduced.
    if channel == "passages" and (observe := context.pop("on_passage_scope", None)):
        observe(scopes, generation)
    if not generation:
        warnings.append({"code": "index_pending", "message": "检索索引尚未建立，管理员可在处理中心查看进度。"})
        return empty
    if not scopes:
        return empty
    if channel != "passages" and filters:
        warnings.append({"code": "passage_facets", "message": "馆藏筛选作用于原文；知识入口与策展按问题检索。"})
    limit = min(300, max(1, int(limit)))
    normalized = query
    try:
        normalized_cache = context.setdefault("normalized", {})
        normalization_key = (str(generation.pk), query)
        if normalization_key not in normalized_cache and not filters.get("_keyword_only"):
            normalized_cache[normalization_key] = normalize_texts([query])["texts"][0]
        normalized = normalized_cache.get(normalization_key, query)
    except DiscoveryInferenceError:
        warnings.append({"code": "normalization_unavailable", "message": "文字规范化服务暂不可用，当前保留输入文字检索。"})
    base = {"limit": limit, "filter": [f"channel = {json.dumps(channel)}",
            f"scope_token IN {json.dumps(scopes)}", f"access_status IN {json.dumps(list(access_statuses))}"],
            "attributesToRetrieve": ["id", "source_revision"], "attributesToSearchOn": ["title", "aliases", "authors", "normalized_text"]}
    if scope:
        from catalog.services.discovery_scope import SCOPE_FIELDS
        base["attributesToSearchOn"] = [SCOPE_FIELDS[scope]]
    if author_ranges and any(ranges is not None for ranges in author_ranges.values()):
        try:
            author_filter = _author_document_filter(generation, author_ranges, access_statuses)
        except DiscoveryIndexError as error:
            warnings.append({"code": error.code, "message": str(error)})
            return empty
        if not author_filter:
            return empty
        base["filter"].append(f"({author_filter})")
    if channel == "passages" and filters.get("languages"):
        from catalog.services.semantic_search import _language_filter_values
        base["filter"].append(f"language IN {json.dumps(_language_filter_values(filters['languages']))}")
    try:
        sparse = meili("POST", f"/indexes/{generation.uid}/search", {**base, "q": normalized})
        empty["sparse"] = sparse.get("hits", [])
        from .discovery_query import keyword_question
        keywords = keyword_question(normalized)
        if channel == "passages" and keywords != normalized and not scope:
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
    # Separate, lower-weight recall preserves the exact-text baseline. A context
    # hit may match a chapter title; that title must never replace the quotation.
    if (channel == "passages" and not scope and not filters.get("_baseline")
            and not query.lstrip().startswith(('"', '“'))
            and generation.config_snapshot.get("context_fields_version") == 1):
        try:
            contextual = meili("POST", f"/indexes/{generation.uid}/search", {**base,
                "q": normalized, "attributesToSearchOn": ["normalized_text", "context_text"]})
            empty["contextual"] = contextual.get("hits", [])
        except DiscoveryIndexError:
            warnings.append({"code": "context_unavailable", "message": "章节语境检索暂不可用，保留原文检索结果。"})
    if not scope and not filters.get("_keyword_only"):
        try:
            vector_cache = context.setdefault("vectors", {})
            dimensions = int(generation.dimensions or generation.config_snapshot.get("dimensions") or 384)
            vector_key = (generation.config_snapshot["embedding_artifact"], dimensions, query)
            if vector_key not in vector_cache:
                vector_cache[vector_key] = embed_texts(
                    [query], kind="query", expected_artifact=vector_key[0], expected_dimensions=dimensions,
                )["vectors"][0]
            vector = vector_cache[vector_key]
            dense = meili("POST", f"/indexes/{generation.uid}/search", {**base, "q": "", "vector": vector,
                "hybrid": {"embedder": "discovery", "semanticRatio": 1.0}})
            empty["dense"] = dense.get("hits", [])
        except (DiscoveryIndexError, DiscoveryInferenceError, KeyError):
            warnings.append({"code": "dense_unavailable", "message": "向量检索暂不可用，当前只显示关键词召回的材料。"})
    hydrated = {row["id"]: row for row in validate_discovery_results(channel, [*empty["sparse"], *empty["dense"], *empty["contextual"]], access_statuses, filters=filters)}
    for branch in ("sparse", "dense", "contextual"):
        empty[branch] = [hydrated[row["id"]] for row in empty[branch] if row.get("id") in hydrated]
    return empty
