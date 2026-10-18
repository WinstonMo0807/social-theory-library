"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest } from "@/lib/api";
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
  const [searchMatches, setSearchMatches] = useState<SearchMatch[]>([]);
  const [activeSearchMatch, setActiveSearchMatch] = useState(0);
  const [searchCandidatesOpen, setSearchCandidatesOpen] = useState(false);
  const [passageFocus, setPassageFocus] = useState<PassageFocus | null>(null);
  const [sourceError, setSourceError] = useState("");
  const [searchError, setSearchError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const navigatedFocus = useRef("");
  const suppressedFocus = useRef("");
  const retrySearch = useCallback(() => setAttempt(value => value + 1), []);

  useEffect(() => {
    if (!initialPassage && !initialEvidence) return;
    let cancelled = false;
    let loading = false;
    const lifetime = new AbortController();
    const path = initialEvidence ? `/catalog/theory-system/evidence/${encodeURIComponent(initialEvidence)}/focus/`
      : `/catalog/passages/${encodeURIComponent(initialPassage)}/focus/`;
    const key = `${assetId}:${documentRevisionId}:${path}`;
    const revalidate = () => {
      if (loading || cancelled || document.visibilityState !== "visible") return;
      loading = true;
      void apiRequest<PassageFocus>(path, { signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(30000)]), cache: "no-store" })
        .then(payload => {
          if (cancelled) return;
          const focus = validateReaderFocus(payload, assetId, documentRevisionId);
          if (suppressedFocus.current !== key) setPassageFocus(focus);
          setSourceError("");
          requestPagePayload(payload.page_index);
          // Revalidation after switching tabs must not undo the reader's current page.
          if (navigatedFocus.current !== key) { navigatedFocus.current = key; jumpToPage(payload.page_index, "auto"); }
        })
        .catch((reason: unknown) => {
          if (!cancelled) { setPassageFocus(null); setSourceError(reason instanceof Error ? reason.message : "原文定位读取失败，请重试。"); }
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
  }, [initialPassage, initialEvidence, jumpToPage, requestPagePayload, assetId, documentRevisionId, attempt]);

  useEffect(() => {
    if (!query.trim()) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      apiRequest<{ asset_id?: string; document_revision_id?: string | null; matches: SearchMatch[] }>(
        `/catalog/assets/${assetId}/search/?q=${encodeURIComponent(query.trim())}`,
        { signal: AbortSignal.timeout(30000), cache: "no-store" },
      )
        .then((payload) => {
          if (!cancelled) {
            const matches = validateReaderSearch(payload, assetId, documentRevisionId);
            setSearchMatches(matches);
            setSearchError("");
            setActiveSearchMatch(0);
            setSearchCandidatesOpen(matches.length > 0);
          }
        })
        .catch((reason: unknown) => {
          if (!cancelled) { setSearchMatches([]); setSearchError(reason instanceof Error ? reason.message : "书内检索读取失败，请重试。"); }
        });
    }, 260);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, assetId, documentRevisionId, attempt]);

  function jumpToFirstSearchMatch() {
    if (searchMatches[0]) {
      jumpToSearchMatch(0);
    }
  }

  function jumpToSearchMatch(index: number) {
    const match = searchMatches[index];
    if (!match) return;
    setActiveSearchMatch(index);
    setSearchCandidatesOpen(false);
    suppressedFocus.current = navigatedFocus.current;
    setPassageFocus(null);
    requestPagePayload(match.page_index);
    jumpToPage(match.page_index);
  }

  return {
    query, setQuery, searchMatches, setSearchMatches, activeSearchMatch,
    searchCandidatesOpen, setSearchCandidatesOpen, passageFocus,
    sourceError, searchError: query.trim() ? searchError : "", retrySearch,
    jumpToFirstSearchMatch, jumpToSearchMatch,
  };
}
