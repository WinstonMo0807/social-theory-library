"use client";

import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
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
  const [citations, setCitations] = useState<CitationBundle | null>(null);
  useEffect(() => {
    if (!editionId) {
      return;
    }
    let cancelled = false;
    apiRequest<CitationBundle>(
      `/catalog/editions/${editionId}/citations/?pdf_page=${page}`,
    )
      .then((payload) => {
        if (!cancelled) setCitations(payload);
      })
      .catch(() => {
        if (!cancelled) setCitations(null);
      });
    return () => {
      cancelled = true;
    };
  }, [editionId, page]);

  async function copyCitation() {
    const text = citations?.[citationStyle];
    if (!text) {
      setCopyStatus("引用数据尚未就绪");
      setCopyStatusState("idle");
      return;
    }
    await navigator.clipboard.writeText(text);
    setCopyStatus("引用已复制");
    setCopyStatusState("success");
  }

  return { citationStyle, setCitationStyle, citations, copyCitation };
}
