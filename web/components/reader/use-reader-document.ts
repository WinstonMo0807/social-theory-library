"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, normalizePublicResourceUrl } from "@/lib/api";
import type { Work } from "@/lib/data";
import type { AccessPayload, PagePayload } from "./types";

/** Signed access refresh and canonical page payloads share the same asset scope. */
export function useReaderDocument({ assetId, workId }: { assetId: string; workId: Work["workId"] }) {
  const [access, setAccess] = useState<AccessPayload | null>(null);
  const [accessError, setAccessError] = useState("");
  const [pagePayloads, setPagePayloads] = useState<Record<number, PagePayload>>({});
  const pagePayloadsRef = useRef<Record<number, PagePayload>>({});
  const pendingPageRequests = useRef<Set<number>>(new Set());

  useEffect(() => {
    pagePayloadsRef.current = pagePayloads;
  }, [pagePayloads]);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: number | undefined;

    async function loadAccess() {
      try {
        const payload = await apiRequest<AccessPayload>(`/distribution/assets/${assetId}/access/`);
        if (cancelled) return;
        const nextAccess = {
          ...payload,
          url: normalizePublicResourceUrl(payload.url),
          download_url: normalizePublicResourceUrl(payload.download_url || payload.url),
          original_download_url: payload.original_download_url
            ? normalizePublicResourceUrl(payload.original_download_url)
            : undefined,
        };
        setAccess((current) => {
          if (current && current.ocr_status !== nextAccess.ocr_status) {
            pagePayloadsRef.current = {};
            pendingPageRequests.current.clear();
            setPagePayloads({});
          }
          return nextAccess;
        });
        setAccessError("");
        const statusRefreshSeconds = ["pending", "running"].includes(payload.ocr_status)
          ? 20
          : Number.POSITIVE_INFINITY;
        const addressRefreshSeconds = payload.expires_in
          ? Math.max(60, payload.expires_in - 120)
          : Number.POSITIVE_INFINITY;
        const refreshSeconds = Math.min(statusRefreshSeconds, addressRefreshSeconds);
        if (Number.isFinite(refreshSeconds)) {
          refreshTimer = window.setTimeout(
            loadAccess,
            refreshSeconds * 1000,
          );
        }
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "";
          setAccess(null);
          setAccessError(
            /failed to fetch|networkerror/i.test(message)
              ? "暂时无法连接阅读文件服务，请稍后重试。"
              : message || "公开阅读副本尚未就绪。",
          );
        }
      }
    }

    void loadAccess();
    return () => {
      cancelled = true;
      if (refreshTimer) window.clearTimeout(refreshTimer);
    };
  }, [assetId]);

  const requestPagePayload = useCallback((targetPage: number) => {
    if (
      targetPage < 1
      || pagePayloadsRef.current[targetPage]
      || pendingPageRequests.current.has(targetPage)
    ) return;
    pendingPageRequests.current.add(targetPage);
    void apiRequest<PagePayload>(`/catalog/assets/${assetId}/pages/${targetPage}/`)
      .then((payload) => {
        pagePayloadsRef.current = {
          ...pagePayloadsRef.current,
          [payload.page_index]: payload,
        };
        setPagePayloads(pagePayloadsRef.current);
      })
      .catch(() => undefined)
      .finally(() => {
        pendingPageRequests.current.delete(targetPage);
      });
  }, [assetId]);

  const trackDownload = useCallback(() => { void apiRequest("/catalog/usage-events/", { method: "POST", body: JSON.stringify({ event_type: "download", asset_id: assetId, work_id: workId, source: "reader" }) }).catch(() => undefined); }, [assetId, workId]);

  return { access, accessError, pagePayloads, requestPagePayload, trackDownload };
}

/** The page effect follows navigation without coupling access refresh to every scroll. */
export function useReaderPageRequest({ page, ocrStatus, requestPagePayload }: {
  page: number;
  ocrStatus: AccessPayload["ocr_status"] | undefined;
  requestPagePayload: (page: number) => void;
}) {
  useEffect(() => {
    requestPagePayload(page);
  }, [ocrStatus, page, requestPagePayload]);

}
