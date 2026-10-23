"use client";

import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { apiRequest } from "@/lib/api";
import type { ActionState } from "../action-feedback";
import type { CitationBundle, CitationStyle } from "./types";

export function useReaderCitation({ editionId, page, setCopyStatus, setCopyStatusState }: {
  editionId: string | undefined;
  page: number;
  setCopyStatus: Dispatch<SetStateAction<string>>;
  setCopyStatusState: Dispatch<SetStateAction<ActionState>>;
}) {
  const [citationStyle, setCitationStyle] = useState<CitationStyle>("gbt7714-2025");
  const [attempt, setAttempt] = useState(0);
  const retryCitation = useCallback(() => setAttempt(value => value + 1), []);
  const key = `${editionId ?? ""}:${page}:${attempt}`;
  const [result, setResult] = useState<{ key: string; data: CitationBundle | null; error: string } | null>(null);
  // A page change invalidates the old citation during render, before effects run.
  const citations = result?.key === key ? result.data : null;
  const citationError = result?.key === key ? result.error : "";
  useEffect(() => {
    if (!editionId) {
      return;
    }
    const request = new AbortController();
    apiRequest<CitationBundle>(
      `/catalog/editions/${editionId}/citations/?pdf_page=${page}`,
      { signal: AbortSignal.any([request.signal, AbortSignal.timeout(30000)]) },
    )
      .then((payload) => {
        if (!request.signal.aborted) setResult({ key, data: payload, error: "" });
      })
      .catch((reason: unknown) => {
        if (!request.signal.aborted) setResult({ key, data: null, error: reason instanceof DOMException && reason.name === "TimeoutError" ? "引用读取超时，请重新读取；当前原文和选文保留。" : reason instanceof Error ? reason.message : "引用读取失败。" });
      });
    return () => {
      request.abort();
    };
  }, [editionId, page, key]);

  async function copyCitation() {
    const text = citations?.[citationStyle];
    if (!text) {
      setCopyStatus(citationError || "当前页引用数据尚未就绪");
      setCopyStatusState(citationError ? "error" : "idle");
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus("引用已复制");
      setCopyStatusState("success");
    } catch {
      setCopyStatus("浏览器未允许复制，请选择引用文字手动复制。");
      setCopyStatusState("error");
    }
  }

  return { citationStyle, setCitationStyle, citations, citationError, citationLoading: Boolean(editionId) && result?.key !== key, copyCitation, retryCitation };
}
