"use client";

import { useMemo } from "react";
import type { PdfPageOverlay } from "../pdf-continuous-viewer";
import type { PagePayload, PassageFocus, ReaderAnnotation, SearchMatch } from "./types";

export function formatReaderTimestamp(value?: string) {
  if (!value) return "保存时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "保存时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

type ReaderPageOverlayOptions = {
  annotations: ReaderAnnotation[];
  focusedAnnotationId: string;
  pagePayloads: Record<number, PagePayload>;
  passageFocus: PassageFocus | null;
  query: string;
  searchMatches: SearchMatch[];
};

export function buildReaderPageOverlays({ annotations, focusedAnnotationId, pagePayloads, passageFocus, query, searchMatches }: ReaderPageOverlayOptions) {
  const result: Record<number, PdfPageOverlay> = {};
  const pageIndexes = new Set<number>([
    ...Object.keys(pagePayloads).map(Number),
    ...(query.trim() ? searchMatches.map((match) => match.page_index) : []),
    ...(passageFocus ? [passageFocus.page_index] : []),
    ...annotations
      .map((annotation) => annotation.selector.page_index)
      .filter((index): index is number => Boolean(index)),
  ]);
  pageIndexes.forEach((pageIndex) => {
    const payload = pagePayloads[pageIndex];
    const match = query.trim()
      ? searchMatches.find((item) => item.page_index === pageIndex)
      : undefined;
    const focusedPassage = passageFocus?.page_index === pageIndex
      ? passageFocus
      : undefined;
    result[pageIndex] = {
      sourceWidth: payload?.width || match?.width || focusedPassage?.width || 0,
      sourceHeight: payload?.height || match?.height || focusedPassage?.height || 0,
      canonicalBlocks: payload?.blocks ?? [],
      highlights: [
        ...(focusedPassage?.bbox?.length === 4
          ? [{
              bbox: focusedPassage.bbox,
              kind: "search" as const,
            }]
          : []),
        ...(match?.highlights ?? []).map((highlight) => ({
          bbox: highlight.bbox,
          kind: "search" as const,
        })),
        ...annotations
          .filter((annotation) => annotation.selector.page_index === pageIndex)
          .flatMap((annotation) =>
            (annotation.selector.bboxes ?? []).map((bbox) => ({
              bbox,
              kind: annotation.kind,
            })),
          ),
      ],
      notes: annotations
        .filter(
          (annotation) =>
            annotation.kind === "note"
            && annotation.selector.page_index === pageIndex,
        )
        .map((annotation) => ({
          id: annotation.id,
          bbox: annotation.selector.bboxes?.[0] ?? null,
          body: annotation.body_text,
          quote: annotation.quote,
          createdAt: formatReaderTimestamp(annotation.created_at),
          focused: annotation.id === focusedAnnotationId,
        })),
    };
  });
  return result;
}

export function useReaderPageOverlays({ annotations, focusedAnnotationId, pagePayloads, passageFocus, query, searchMatches }: ReaderPageOverlayOptions) {
  return useMemo(() => buildReaderPageOverlays({
    annotations, focusedAnnotationId, pagePayloads, passageFocus, query, searchMatches,
  }), [annotations, focusedAnnotationId, pagePayloads, passageFocus, query, searchMatches]);
}
