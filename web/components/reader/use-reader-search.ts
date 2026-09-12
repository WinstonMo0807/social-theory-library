"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import type { PassageFocus, SearchMatch } from "./types";

export function useReaderSearch({ assetId, initialQuery, initialPassage, initialEvidence, requestPagePayload, jumpToPage }: {
  assetId: string;
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

  useEffect(() => {
    if (!initialPassage) return;
    let cancelled = false;
    apiRequest<PassageFocus>(
      `/catalog/passages/${encodeURIComponent(initialPassage)}/focus/`,
    )
      .then((payload) => {
        if (cancelled || payload.asset_id !== assetId) return;
        setPassageFocus(payload);
        requestPagePayload(payload.page_index);
        jumpToPage(payload.page_index, "auto");
      })
      .catch(() => {
        if (!cancelled) setPassageFocus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [initialPassage, jumpToPage, requestPagePayload, assetId]);

  useEffect(() => {
    if (!initialEvidence) return;
    let cancelled = false;
    apiRequest<PassageFocus>(
      `/catalog/theory-system/evidence/${encodeURIComponent(initialEvidence)}/focus/`,
    )
      .then((payload) => {
        if (cancelled || payload.asset_id !== assetId) return;
        setPassageFocus(payload);
        requestPagePayload(payload.page_index);
        jumpToPage(payload.page_index, "auto");
      })
      .catch(() => {
        if (!cancelled) setPassageFocus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [initialEvidence, jumpToPage, requestPagePayload, assetId]);

  useEffect(() => {
    if (!query.trim()) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      apiRequest<{ matches: SearchMatch[] }>(
        `/catalog/assets/${assetId}/search/?q=${encodeURIComponent(query.trim())}`,
      )
        .then((payload) => {
          if (!cancelled) {
            setSearchMatches(payload.matches);
            setActiveSearchMatch(0);
            setSearchCandidatesOpen(payload.matches.length > 0);
          }
        })
        .catch(() => {
          if (!cancelled) setSearchMatches([]);
        });
    }, 260);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, assetId]);

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
    setPassageFocus(null);
    requestPagePayload(match.page_index);
    jumpToPage(match.page_index);
  }

  return {
    query, setQuery, searchMatches, setSearchMatches, activeSearchMatch,
    searchCandidatesOpen, setSearchCandidatesOpen, passageFocus,
    jumpToFirstSearchMatch, jumpToSearchMatch,
  };
}
