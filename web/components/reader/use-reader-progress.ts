"use client";

import { useEffect } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export function useReaderProgress({ assetId, page, totalPages, readerAuthenticated }: {
  assetId: string;
  page: number;
  totalPages: number;
  readerAuthenticated: boolean;
}) {
  useEffect(() => {
    if (!readerAuthenticated) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const timer = window.setTimeout(() => {
      void (async () => {
        // Both writes are best-effort, but they target the same reader and asset.
        // Keep them sequential so single-writer stores do not race each other.
        await apiRequest(
          "/reading/progress/",
          {
            method: "POST",
            body: JSON.stringify({
              asset: assetId,
              current_page: page,
              progress_ratio: page / totalPages,
              last_position: { page },
            }),
          },
          token,
        ).catch(() => undefined);
        await apiRequest(
          "/reading/history/",
          {
            method: "POST",
            body: JSON.stringify({
              asset: assetId,
              page_index: page,
              session_seconds: 0,
            }),
          },
          token,
        ).catch(() => undefined);
      })();
    }, 650);
    return () => window.clearTimeout(timer);
  }, [page, readerAuthenticated, totalPages, assetId]);

}
