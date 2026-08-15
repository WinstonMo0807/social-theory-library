"use client";

import { useEffect, useRef } from "react";
import { apiRequest } from "@/lib/api";

type UsageEvent = "reader_open" | "search_submit" | "search_result_click" | "download";

export function UsageTracker({
  eventType,
  workId,
  assetId,
  query = "",
  resultCount,
  source = "public",
  scope = "",
}: {
  eventType: UsageEvent;
  workId?: string;
  assetId?: string;
  query?: string;
  resultCount?: number;
  source?: string;
  scope?: string;
}) {
  const recorded = useRef(false);

  useEffect(() => {
    if (recorded.current || (eventType === "search_submit" && !query.trim())) return;
    recorded.current = true;
    void apiRequest("/catalog/usage-events/", {
      method: "POST",
      body: JSON.stringify({
        event_type: eventType,
        work_id: workId,
        asset_id: assetId,
        query,
        result_count: resultCount,
        source,
        scope,
      }),
    }).catch(() => undefined);
  }, [assetId, eventType, query, resultCount, scope, source, workId]);

  return null;
}


export function SearchClickTracker({ query, source }: { query: string; source: string }) {
  useEffect(() => {
    if (!query.trim()) return;
    const listener = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest("a") : null;
      if (!target || !target.closest(".explore-page")) return;
      const href = target.getAttribute("href") || "";
      if (!href || href.startsWith("/explore?") || href === "/explore") return;
      void apiRequest("/catalog/usage-events/", {
        method: "POST",
        body: JSON.stringify({
          event_type: "search_result_click",
          query,
          source,
          scope: href.slice(0, 80),
        }),
      }).catch(() => undefined);
    };
    document.addEventListener("click", listener, { capture: true });
    return () => document.removeEventListener("click", listener, { capture: true });
  }, [query, source]);
  return null;
}
