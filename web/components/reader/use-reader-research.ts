"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { readResearchRecord, type ProjectData, type TurnData, type ResolvedEvidence } from "@/lib/api/research.client";
import { availableEvidenceAnchors, evidenceIdentity } from "@/lib/api/research-navigation";
import type { PassageFocus } from "./types";
import { validatedNormalizedBox } from "@/lib/reader-coordinates";

export function readerResearchAnchors(reference: ResolvedEvidence, assetId: string, revisionId: string): PassageFocus[] {
  return availableEvidenceAnchors(reference, assetId, revisionId).map(anchor => {
    const normalized = validatedNormalizedBox(anchor);
    return { id: anchor.evidence_span_id || `${assetId}:${anchor.pdf_page}`,
      asset_id: assetId, title: anchor.title || "", page_index: anchor.pdf_page!, printed_label: anchor.printed_label || "",
      document_revision_id: revisionId,
      width: anchor.coordinate_space?.width || 0, height: anchor.coordinate_space?.height || 0,
      bbox: normalized ? anchor.bbox || [] : [], normalized_bbox: normalized || [],
      geometry_status: normalized ? "validated" : "unknown", geometry: anchor.geometry,
      text: "", text_source: anchor.coordinate_space?.text_source };
  });
}

export function useReaderResearch({ assetId, revisionId, requestedRevisionId, projectId, turnId, referenceId, ownerId, requestPagePayload, jumpToPage }: {
  assetId: string; revisionId: string; projectId: string; turnId: string; referenceId: string; ownerId: string | null;
  requestedRevisionId?: string;
  requestPagePayload: (page: number) => void; jumpToPage: (page: number, behavior?: ScrollBehavior) => void;
}) {
  const key = JSON.stringify([assetId, revisionId, requestedRevisionId, projectId, turnId, referenceId, ownerId]);
  const [result, setResult] = useState<{ key: string; anchors: PassageFocus[]; error: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const navigatedKey = useRef("");
  const retryResearch = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    if (!ownerId || !referenceId || (!projectId && !turnId)) return;
    const request = new AbortController();
    let loading = false;
    const load = async () => {
      if (requestedRevisionId && requestedRevisionId !== revisionId) throw new Error("这个链接对应的正式原文修订已变化，请从研究重新核对原文。");
      let references: ResolvedEvidence[];
      if (turnId) {
        const turn = await readResearchRecord<TurnData>("research-turns", turnId, request.signal);
        if (projectId && turn.project_id !== projectId) throw new Error("这条研究轮次与返回项目不一致，请从研究重新打开原文。");
        references = [...(turn.data.result_refs || []), ...(turn.data.selected_refs || []), ...(turn.data.analysis || []).map(row => row.reference)];
      } else {
        const project = await readResearchRecord<ProjectData>("research-projects", projectId, request.signal);
        references = project.data.selections;
      }
      const identities = await Promise.all(references.map(evidenceIdentity));
      const reference = references[identities.indexOf(referenceId)];
      if (!reference) throw new Error("这条材料已从当前研究移除，请返回研究核对。");
      const anchors = readerResearchAnchors(reference, assetId, revisionId);
      if (!anchors.length) throw new Error("原文文件或正式文字修订已变化，暂不显示旧定位，请返回研究重新选择。");
      if (request.signal.aborted) return;
      setResult({ key, anchors, error: "" });
      for (const anchor of anchors) requestPagePayload(anchor.page_index);
      if (navigatedKey.current !== key) {
        navigatedKey.current = key;
        jumpToPage(anchors[0].page_index, "auto");
      }
    };
    const revalidate = () => {
      if (loading || request.signal.aborted || document.visibilityState !== "visible") return;
      loading = true;
      void load().catch((reason: unknown) => {
        if (!request.signal.aborted) setResult({ key, anchors: [], error: reason instanceof Error ? reason.message : "研究原文定位读取失败。" });
      }).finally(() => { loading = false; });
    };
    revalidate();
    window.addEventListener("focus", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => { request.abort(); window.removeEventListener("focus", revalidate); document.removeEventListener("visibilitychange", revalidate); };
  }, [assetId, revisionId, requestedRevisionId, projectId, turnId, referenceId, ownerId, key, requestPagePayload, jumpToPage, attempt]);
  return { researchAnchors: result?.key === key ? result.anchors : [], researchError: result?.key === key ? result.error : "", retryResearch };
}
