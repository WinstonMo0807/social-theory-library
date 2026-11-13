"""Unified recall; Discovery sessions provide durable presentation."""
def retrieve_channel(query, channel, filters, access_statuses, *, limit=100,
                               expanded=False, aliases=(), request_context=None, is_current=None):
    """One recall/fusion/source-check/order path for sessions and the legacy Ask adapter.

    ``filters`` here is a server-resolved scope, not unvalidated HTTP input. This
    preserves large curated paths and the internal exact-file restriction.
    """
    from catalog.services.discovery_sessions import _warning, _rrf, _deduplicate, _rerank, _diverse_prefix, MAX_MATERIALIZED
    from catalog.services.discovery_projection import discovery_candidates, validate_discovery_results
    request_context = request_context if request_context is not None else {}
    result = discovery_candidates(query, channel, filters, access_statuses, limit=limit,
                                  expanded=expanded, request_context=request_context)
    branches = [(result.get("sparse", []), 1.0), (result.get("dense", []), 1.0),
                (result.get("contextual", []), 0.6)]
    warnings = list(result.get("warnings", []))
    if channel == "passages" and filters.get("search_scope") == "terms":
        from catalog.models import QueryLexiconState
        from catalog.services.query_lexicon.search import resolve_search_query
        from catalog.services.query_lexicon.sync import QueryLexiconInvariantError
        try:
            resolution = resolve_search_query(query)
            translations = list(dict.fromkeys(row["query"] for row in resolution["expansion_branches"]
                if row.get("branch_type") == "verified_translation" and row.get("displayable")
                and row.get("language", "").split("-")[0] in {"zh", "en"} and not row.get("ambiguous")))[:4]
            for translated in translations:
                if is_current and not is_current():
                    return {"rows": [], "warnings": warnings, "canceled": True, "version": str(result.get("version") or "")}
                branch = discovery_candidates(translated, channel, filters, access_statuses, limit=limit, request_context=request_context)
                branches.append((branch.get("sparse", []), 1.0 / max(len(translations), 1)))
                warnings.extend(branch.get("warnings", []))
        except (QueryLexiconState.DoesNotExist, QueryLexiconInvariantError):
            warnings.append(_warning("terms_pending", "已确认的中英文术语索引尚未就绪，本次保留输入词的原文匹配。", channel))
    if channel == "passages" and expanded and aliases and not filters.get("search_scope"):
        for alias in aliases[:4]:
            if is_current and not is_current():
                return {"rows": [], "warnings": warnings, "canceled": True, "version": str(result.get("version") or "")}
            branch = discovery_candidates(alias, channel, filters, access_statuses, limit=40,
                                          expanded=True, request_context=request_context)
            branches.extend([(branch.get("sparse", []), 0.2 / len(aliases[:4])),
                             (branch.get("dense", []), 0.2 / len(aliases[:4]))])
            warnings.extend(branch.get("warnings", []))
    rows = validate_discovery_results(channel, _rrf(branches)[:MAX_MATERIALIZED], access_statuses, filters=filters)
    if channel == "passages":
        rows = _deduplicate(rows)
        if is_current and not is_current():
            return {"rows": [], "warnings": warnings, "canceled": True, "version": str(result.get("version") or "")}
        rerank_count = 40 if expanded else 20
        rows, rerank_warnings = (rows, []) if filters.get("_keyword_only") else _rerank(query, rows, rerank_count, str(result.get("reranker_artifact") or ""))
        warnings.extend(rerank_warnings)
        # Only the scored pool is eligible for promotion. The unscored fusion
        # tail remains available, but work diversity is not evidence relevance.
        if not any(warning.get("code") == "reranker_unavailable" for warning in rerank_warnings):
            rows = _diverse_prefix(rows, eligible_count=rerank_count)
    # Model calls may outlive a publication change. Recheck after them as well.
    rows = validate_discovery_results(channel, rows, access_statuses, filters=filters)
    if channel == "passages":
        from .locators import attach_locators
        rows = attach_locators(rows)
    coverage = result.get("coverage") or {}
    if channel == "passages" and (coverage.get("index_pending_editions") or coverage.get("text_pending_editions")):
        warnings.append(_warning("coverage_pending", "所选来源仍有原文或关键词索引待完成。当前结果仅覆盖已就绪的片段，零条结果不代表原文中不存在。", channel))
    return {"rows": rows, "warnings": warnings, "version": str(result.get("version") or ""),
            "coverage": coverage,
            "retrieval": {"algorithm": "hybrid_context_rrf_v1", "rrf_k": 60,
                "candidates": {name:len(result.get(name, [])) for name in ("sparse", "dense", "contextual")},
                "context_source": "bibliography_and_document_structure", "baseline": bool(filters.get("_baseline"))},
            "index_uid": str(result.get("index_uid") or getattr(request_context.get("generation"), "uid", "")),
            "embedding_artifact": str(result.get("embedding_artifact") or ""),
            "embedding_dimensions": result.get("embedding_dimensions"),
            "reranker_artifact": str(result.get("reranker_artifact") or ""),
            "canceled": False}
