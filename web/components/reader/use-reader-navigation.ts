"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { PdfScrollRequest } from "../pdf-continuous-viewer";

export function clampReaderPage(target: number, totalPages: number) {
  return Math.min(totalPages, Math.max(1, Math.round(target) || 1));
}

export function readerThumbnailPages(page: number, totalPages: number) {
  if (totalPages <= 400) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const start = Math.max(1, Math.min(page - 120, totalPages - 239));
  return Array.from({ length: 240 }, (_, index) => start + index);
}

/** Owns PDF page/zoom position and the existing URL page parameter. */
export function useReaderNavigation({ initialPage, initialPageCount, accessPageCount = 0 }: {
  initialPage: number;
  initialPageCount: number;
  accessPageCount?: number;
}) {
  const [page, setPage] = useState(Math.min(Math.max(initialPage, 1), Math.max(initialPageCount, 1)));
  const [zoom, setZoom] = useState(100);
  const [documentPages, setDocumentPages] = useState(0);
  const [scrollRequest, setScrollRequest] = useState<PdfScrollRequest>({
    page: Math.min(Math.max(initialPage, 1), Math.max(initialPageCount, 1)),
    sequence: 0,
    behavior: "auto",
  });
  const totalPages = Math.max(documentPages, accessPageCount, initialPageCount, 1);
  const jumpToPage = useCallback((target: number, behavior: ScrollBehavior = "smooth") => {
    const nextPage = clampReaderPage(target, totalPages);
    setPage(nextPage);
    setScrollRequest((current) => ({
      page: nextPage,
      sequence: current.sequence + 1,
      behavior,
    }));
  }, [totalPages]);
  const changeZoom = useCallback((delta: number) => {
    setZoom((value) => Math.min(180, Math.max(60, value + delta)));
    setScrollRequest((current) => ({
      page,
      sequence: current.sequence + 1,
      behavior: "auto",
    }));
  }, [page]);
  const progress = Math.round((page / totalPages) * 100);
  const thumbnailPages = useMemo(() => readerThumbnailPages(page, totalPages), [page, totalPages]);
  const onDocumentLoad = useCallback((pages: number) => {
    setDocumentPages(pages);
  }, []);
  const onVisiblePageChange = useCallback((visiblePage: number) => {
    setPage((current) => current === visiblePage ? current : visiblePage);
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("page", String(page));
    window.history.replaceState(window.history.state, "", url);
  }, [page]);

  return {
    page,
    setPage,
    zoom,
    totalPages,
    progress,
    thumbnailPages,
    scrollRequest,
    jumpToPage,
    changeZoom,
    onDocumentLoad,
    onVisiblePageChange,
  };
}
