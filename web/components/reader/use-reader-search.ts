"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import type { PassageFocus, SearchMatch } from "./types";
import { validatedNormalizedBox } from "@/lib/reader-coordinates";

export function validateReaderFocus(payload: PassageFocus, assetId: string, revisionId: string) {
  if (payload.asset_id !== assetId || !Number.isInteger(payload.page_index) || payload.page_index < 1 ||
      (payload.document_revision_id !== undefined && (payload.document_revision_id || "") !== revisionId)) {
    throw new ApiRequestError("这条原文的文件或正式修订已变化，请从原始来源重新打开。", 409);
  }
  // A source label or legacy unit alone cannot prove crop/rotation geometry.
  return payload.document_revision_id && validatedNormalizedBox(payload)
    ? payload : { ...payload, bbox: [], normalized_bbox: [], geometry_status: "unknown" as const };
}

export function validateReaderSearch(payload: { asset_id?: string; document_revision_id?: string | null; matches: SearchMatch[] }, assetId: string, revisionId: string) {
  if ((payload.asset_id && payload.asset_id !== assetId) ||
      (payload.document_revision_id !== undefined && (payload.document_revision_id || "") !== revisionId)) {
    throw new ApiRequestError("书内检索对应的正式文字修订已变化，请重新加载文献。", 409);
  }
  return payload.matches.filter(match => Number.isInteger(match.page_index) && match.page_index > 0)
    .map(match => payload.document_revision_id ? match : { ...match, highlights: [], blocks: [] });
}

export function useReaderSearch({ assetId, documentRevisionId = "", initialQuery, initialPassage, initialEvidence, requestPagePayload, jumpToPage }: {
  assetId: string;
  documentRevisionId?: string;
  initialQuery: string;
  initialPassage: string;
  initialEvidence: string;
  requestPagePayload: (page: number) => void;
  jumpToPage: (page: number, behavior?: ScrollBehavior) => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [searchComposing, setSearchComposing] = useState(false);
  const [searchMatches, setSearchMatches] = useState<SearchMatch[]>([]);
  const [activeSearchMatch, setActiveSearchMatch] = useState(0);
  const [searchCandidatesOpen, setSearchCandidatesOpen] = useState(false);
  const [focusState, setFocusState] = useState<{ key: string; focus: PassageFocus | null; error: string }>({ key: "", focus: null, error: "" });
  const [searchState, setSearchState] = useState<{ key: string; status: "loading" | "ready" | "error"; error: string }>({ key: "", status: "ready", error: "" });
  const [attempt, setAttempt] = useState(0);
  const navigatedFocus = useRef("");
  const suppressedFocus = useRef("");
  const retrySearch = useCallback(() => setAttempt(value => value + 1), []);
  const queryText = query.trim();
  const searchKey = JSON.stringify([assetId, documentRevisionId, queryText, attempt]);
  const focusPath = initialEvidence ? `/catalog/theory-system/evidence/${encodeURIComponent(initialEvidence)}/focus/`
    : initialPassage ? `/catalog/passages/${encodeURIComponent(initialPassage)}/focus/` : "";
  const focusKey = focusPath ? `${assetId}:${documentRevisionId}:${focusPath}` : "";
  const currentMatches = !searchComposing && queryText && searchState.key === searchKey && searchState.status === "ready" ? searchMatches : [];

  useEffect(() => {
    if (!focusPath) return;
    let cancelled = false;
    let loading = false;
    const lifetime = new AbortController();
    const key = focusKey;
    const revalidate = () => {
      if (loading || cancelled || document.visibilityState !== "visible") return;
      loading = true;
      void apiRequest<PassageFocus>(focusPath, { signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(30000)]), cache: "no-store" }, getServerSessionCredential())
        .then(payload => {
          if (cancelled) return;
          const focus = validateReaderFocus(payload, assetId, documentRevisionId);
          setFocusState({ key, focus: suppressedFocus.current !== key ? focus : null, error: "" });
          requestPagePayload(payload.page_index);
          // Revalidation after switching tabs must not undo the reader's current page.
          if (navigatedFocus.current !== key) { navigatedFocus.current = key; jumpToPage(payload.page_index, "auto"); }
        })
        .catch((reason: unknown) => {
          if (!cancelled) setFocusState({ key, focus: null, error: reason instanceof Error ? reason.message : "原文定位读取失败，请重试。" });
        }).finally(() => { loading = false; });
    };
    revalidate();
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => {
      cancelled = true;
      lifetime.abort();
      window.removeEventListener("focus", revalidate);
      document.removeEventListener("visibilitychange", revalidate);
    };
  }, [focusPath, focusKey, jumpToPage, requestPagePayload, assetId, documentRevisionId, attempt]);

  useEffect(() => {
    if (searchComposing) return;
    const request = new AbortController();
    queueMicrotask(() => {
      if (request.signal.aborted) return;
      setSearchMatches([]);
      setActiveSearchMatch(0);
      setSearchCandidatesOpen(false);
      setSearchState({ key: searchKey, status: queryText ? "loading" : "ready", error: "" });
    });
    if (!queryText) return () => { request.abort(); };
    const timer = window.setTimeout(() => {
      const deadline = AbortSignal.timeout(30000);
      apiRequest<{ asset_id?: string; document_revision_id?: string | null; matches: SearchMatch[] }>(
        `/catalog/assets/${encodeURIComponent(assetId)}/search/?q=${encodeURIComponent(queryText)}`,
        { signal: AbortSignal.any([request.signal, deadline]), cache: "no-store" },
        getServerSessionCredential(),
      )
        .then((payload) => {
          if (!request.signal.aborted) {
            const matches = validateReaderSearch(payload, assetId, documentRevisionId);
            setSearchMatches(matches);
            setSearchState({ key: searchKey, status: "ready", error: "" });
            setActiveSearchMatch(0);
            setSearchCandidatesOpen(matches.length > 0);
          }
        })
        .catch((reason: unknown) => {
          if (request.signal.aborted) return;
          setSearchMatches([]);
          setSearchState({
            key: searchKey, status: "error",
            error: deadline.aborted ? "书内检索等待超时，请重试。" : reason instanceof Error ? reason.message : "书内检索读取失败，请重试。",
          });
        });
    }, 260);
    return () => {
      request.abort();
      window.clearTimeout(timer);
    };
  }, [queryText, searchKey, assetId, documentRevisionId, searchComposing]);

  function jumpToFirstSearchMatch() {
    if (currentMatches[0]) {
      jumpToSearchMatch(0);
    }
  }

  function jumpToSearchMatch(index: number) {
    const match = currentMatches[index];
    if (!match) return;
    setActiveSearchMatch(index);
    setSearchCandidatesOpen(false);
    suppressedFocus.current = focusKey;
    navigatedFocus.current = focusKey;
    setFocusState(current => ({ ...current, focus: null }));
    requestPagePayload(match.page_index);
    jumpToPage(match.page_index);
  }

  return {
    query, setQuery, searchComposing, setSearchComposing, searchMatches: currentMatches, setSearchMatches,
    activeSearchMatch: searchState.key === searchKey ? activeSearchMatch : 0,
    searchCandidatesOpen: Boolean(!searchComposing && queryText && searchState.key === searchKey && searchCandidatesOpen),
    setSearchCandidatesOpen, passageFocus: focusState.key === focusKey ? focusState.focus : null,
    sourceError: focusState.key === focusKey ? focusState.error : "",
    searchError: queryText && searchState.key === searchKey ? searchState.error : "",
    searchLoading: Boolean(!searchComposing && queryText && (searchState.key !== searchKey || searchState.status === "loading")), retrySearch,
    jumpToFirstSearchMatch, jumpToSearchMatch,
  };
}
