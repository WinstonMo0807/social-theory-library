"use client";

import { useEffect } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export function useReaderProgress({ assetId, page, totalPages, readerAuthenticated, readerId }: {
  assetId: string;
  page: number;
  totalPages: number;
  readerAuthenticated: boolean;
  readerId?: number;
}) {
  useEffect(() => {
    if (!readerAuthenticated || readerId === undefined) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const request = new AbortController();
    const timer = window.setTimeout(() => {
      void (async () => {
        // Bind both writes to the same owner, including when cookies change
        // between requests. An aborted/failed progress write never starts history.
        const signal = AbortSignal.any([request.signal, AbortSignal.timeout(30000)]);
        const headers = { "X-Reader-Owner": String(readerId) };
        try {
          await apiRequest(
            "/reading/progress/",
            {
              method: "POST", signal, headers,
              body: JSON.stringify({
                asset: assetId,
                current_page: page,
                progress_ratio: page / totalPages,
                last_position: { page },
              }),
            },
            token, false,
          );
          if (signal.aborted) return;
          await apiRequest(
            "/reading/history/",
            {
              method: "POST", signal, headers,
              body: JSON.stringify({
                asset: assetId,
                page_index: page,
                session_seconds: 0,
              }),
            },
            token, false,
          );
        } catch {
          // Position tracking is best-effort and must not interrupt reading.
        }
      })();
    }, 650);
    return () => { request.abort(); window.clearTimeout(timer); };
  }, [page, readerAuthenticated, readerId, totalPages, assetId]);

}
