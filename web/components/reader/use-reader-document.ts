"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { isTaskRunning, pollBudgetExpired } from "@/lib/api/task-polling";
import type { Work } from "@/lib/data";
import type { AccessPayload, PagePayload } from "./types";

export function validateReaderPage(payload: PagePayload, assetId: string, revisionId: string, page: number) {
  if (payload.page_index !== page || (payload.asset_id && payload.asset_id !== assetId)) {
    throw new ApiRequestError("页内容身份与当前文献或页码不一致，请重新加载文献。", 409);
  }
  if ((revisionId || payload.document_revision_id !== undefined) && (payload.document_revision_id || "") !== revisionId) {
    throw new ApiRequestError("正式原文修订已变化，请重新加载当前页面以核对新的原文和定位。", 409);
  }
  return payload;
}

/** Signed access refresh and canonical page payloads share the same asset scope. */
export function useReaderDocument({ assetId, workId, documentRevisionId = "" }: { assetId: string; workId: Work["workId"]; documentRevisionId?: string }) {
  const [access, setAccess] = useState<AccessPayload | null>(null);
  const [accessError, setAccessError] = useState("");
  const [accessRequest, setAccessRequest] = useState(0);
  const sourceChanged = useRef(false);
  const retryAccess = useCallback(() => { if (sourceChanged.current) window.location.reload(); else setAccessRequest(value => value + 1); }, []);
  const [pagePayloads, setPagePayloads] = useState<Record<number, PagePayload>>({});
  const [pageErrors, setPageErrors] = useState<Record<number, string>>({});
  const failedPageRequests = useRef(new Set<number>());
  const [statusPollPaused, setStatusPollPaused] = useState(false);
  const pagePayloadsRef = useRef<Record<number, PagePayload>>({});
  const pendingPageRequests = useRef<Set<number>>(new Set());
  const pageGeneration = useRef(0);
  const lastAccess = useRef<AccessPayload | null>(null);

  useEffect(() => {
    pagePayloadsRef.current = pagePayloads;
  }, [pagePayloads]);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: number | undefined;
    const lifetime = new AbortController();
    const startedAt = Date.now();
    let loading = false;

    async function loadAccess() {
      if (cancelled || sourceChanged.current || loading) return;
      loading = true;
      if (refreshTimer) window.clearTimeout(refreshTimer);
      try {
        const payload = await apiRequest<AccessPayload>(`/distribution/assets/${assetId}/access/`, { signal: AbortSignal.any([lifetime.signal, AbortSignal.timeout(30000)]), cache: "no-store" }, getServerSessionCredential());
        if (cancelled || sourceChanged.current) return;
        if (payload.requested_asset_id !== assetId) throw new ApiRequestError("阅读文件身份已变化，请重新打开文献。", 409);
        const nextAccess = {
          ...payload,
          url: normalizePublicResourceUrl(payload.url),
          download_url: normalizePublicResourceUrl(payload.download_url || payload.url),
          original_download_url: payload.original_download_url
            ? normalizePublicResourceUrl(payload.original_download_url)
            : undefined,
        };
        const current = lastAccess.current;
        if (current && (current.ocr_status !== nextAccess.ocr_status || current.sha256 !== nextAccess.sha256 ||
            current.served_asset_id !== nextAccess.served_asset_id || current.requested_asset_id !== nextAccess.requested_asset_id)) {
            pageGeneration.current += 1;
            pagePayloadsRef.current = {};
            pendingPageRequests.current.clear();
            failedPageRequests.current.clear();
            setPagePayloads({});
            setPageErrors({});
        }
        lastAccess.current = nextAccess;
        setAccess(nextAccess);
        setAccessError("");
        const paused = isTaskRunning(payload.ocr_status) && pollBudgetExpired(startedAt);
        setStatusPollPaused(paused);
        const statusRefreshSeconds = isTaskRunning(payload.ocr_status) && !paused
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
          if (error instanceof ApiRequestError && [401, 403, 404, 409, 410].includes(error.status)) {
            pageGeneration.current += 1;
            pagePayloadsRef.current = {};
            pendingPageRequests.current.clear();
            failedPageRequests.current.clear();
            setPagePayloads({});
            setPageErrors({});
          }
          setAccessError(
            /failed to fetch|networkerror/i.test(message)
              ? "暂时无法连接阅读文件服务，请稍后重试。"
              : message || "公开阅读副本尚未就绪。",
          );
        }
      } finally { loading = false; }
    }

    void loadAccess();
    const revalidate = () => { if (document.visibilityState === "visible") void loadAccess(); };
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => {
      cancelled = true;
      lifetime.abort();
      if (refreshTimer) window.clearTimeout(refreshTimer);
      window.removeEventListener("focus", revalidate);
      document.removeEventListener("visibilitychange", revalidate);
    };
  }, [assetId, accessRequest]);

  const requestPagePayload = useCallback((targetPage: number) => {
    if (
      targetPage < 1
      || sourceChanged.current
      || pagePayloadsRef.current[targetPage]
      || pendingPageRequests.current.has(targetPage)
      || failedPageRequests.current.has(targetPage)
    ) return;
    pendingPageRequests.current.add(targetPage);
    const generation = pageGeneration.current;
    void apiRequest<PagePayload>(`/catalog/assets/${assetId}/pages/${targetPage}/`, { signal: AbortSignal.timeout(30000), cache: "no-store" }, getServerSessionCredential())
      .then((payload) => {
        if (generation !== pageGeneration.current) return;
        validateReaderPage(payload, assetId, documentRevisionId, targetPage);
        pagePayloadsRef.current = {
          ...pagePayloadsRef.current,
          [payload.page_index]: payload,
        };
        setPagePayloads(pagePayloadsRef.current);
        setPageErrors(previous => { const next = { ...previous }; delete next[targetPage]; return next; });
      })
      .catch((reason: unknown) => {
        if (generation !== pageGeneration.current) return;
        const message = reason instanceof Error ? reason.message : "页内容暂时读取失败，请重试。";
        failedPageRequests.current.add(targetPage);
        setPageErrors(previous => ({ ...previous, [targetPage]: message }));
        if (reason instanceof ApiRequestError && [401, 403, 404, 409, 410].includes(reason.status)) {
          sourceChanged.current = true;
          pageGeneration.current += 1;
          pagePayloadsRef.current = {};
          pendingPageRequests.current.clear();
          setPagePayloads({});
          setAccess(null);
          setAccessError(message);
        }
      })
      .finally(() => {
        if (generation === pageGeneration.current) pendingPageRequests.current.delete(targetPage);
      });
  }, [assetId, documentRevisionId]);

  const retryPagePayload = useCallback((page: number) => {
    if (sourceChanged.current) { window.location.reload(); return; }
    failedPageRequests.current.delete(page);
    requestPagePayload(page);
  }, [requestPagePayload]);

  const trackDownload = useCallback(() => { void apiRequest("/catalog/usage-events/", { method: "POST", body: JSON.stringify({ event_type: "download", asset_id: assetId, work_id: workId, source: "reader" }) }).catch(() => undefined); }, [assetId, workId]);

  return { access, accessError, pagePayloads, pageErrors, requestPagePayload, retryPagePayload, statusPollPaused, trackDownload, retryAccess };
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
