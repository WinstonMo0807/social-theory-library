"use client";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { PassageFocus } from "./types";

export type KnowledgeSegment = { order: number; page_number: number; start: number; end: number; exact: string; printed_label: string;
  precision: string; geometry: { bbox?: number[]; normalized_bbox?: number[]; width?: number; height?: number; geometry_status?: string } };
type Locator = { schema_version: string; asset_id: string; document_revision_id: string; segments: KnowledgeSegment[]; offset_unit: string };

export function useKnowledgeAnchor(anchorId: string, assetId: string, revisionId: string, preview: boolean) {
  const [state, setState] = useState<{ key: string; locator: Locator | null; error: string } | null>(null);
  const key = `${anchorId}:${assetId}:${revisionId}:${preview}`;
  useEffect(() => {
    if (!anchorId) return;
    const controller = new AbortController();
    void apiRequest<Locator>(`/knowledge/anchors/${anchorId}/?preview=${preview ? "1" : "0"}`, { signal: controller.signal, cache: "no-store" }, getServerSessionCredential()).then(locator => {
      if (locator.asset_id !== assetId || locator.document_revision_id !== revisionId || locator.offset_unit !== "unicode_code_point") throw Error("证据与当前来源修订不一致，请重新打开引用。");
      setState({ key, locator, error: "" });
    }).catch(e => { if (!controller.signal.aborted) setState({ key, locator: null, error: e.message }); });
    return () => controller.abort();
  }, [anchorId, assetId, revisionId, preview, key]);
  const locator = state?.key === key ? state.locator : null;
  const anchors: PassageFocus[] = (locator?.segments || []).map(segment => ({
    id: `${anchorId}:${segment.order}`, asset_id: assetId, document_revision_id: revisionId, title: "原文证据",
    page_index: segment.page_number, printed_label: segment.printed_label, text: segment.exact,
    width: segment.geometry.width || 0, height: segment.geometry.height || 0,
    bbox: segment.geometry.bbox || [], normalized_bbox: segment.geometry.normalized_bbox || [],
    geometry_status: segment.geometry.normalized_bbox?.length === 4 ? "validated" : "unknown", geometry: segment.geometry,
  }));
  return { segments: locator?.segments || [], anchors, error: state?.key === key ? state.error : "" };
}

/** DOM selections use UTF-16; the source contract uses Unicode code points. */
export function codePointRange(text: string, start: number, end: number) {
  const points = Array.from(text);
  if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || end <= start || end > points.length) throw Error("原文范围超出页面。");
  return { start: points.slice(0, start).join("").length, end: points.slice(0, end).join("").length, exact: points.slice(start, end).join("") };
}
