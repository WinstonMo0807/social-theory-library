"use client";

import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  RenderTask,
} from "pdfjs-dist/types/src/display/api";
import type { TextLayer } from "pdfjs-dist/types/src/display/text_layer";
import { LoadingState } from "./ui/loading-state";
import { Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import type { CanonicalBlock, PageHighlight } from "./pdf-canvas";
import {
  displayedHighlightBox, displayedReaderBox, rotateReaderBox, rotateReaderPoint,
  type ReaderRotation,
} from "@/lib/reader-coordinates";

const pdfWorkerUrl = "/pdfjs/pdf.worker.min.js";

export type PdfPageOverlay = {
  sourceWidth: number;
  sourceHeight: number;
  canonicalBlocks: CanonicalBlock[];
  highlights: PageHighlight[];
  notes: {
    id: string;
    bbox: number[] | null;
    body: string;
    quote: string;
    createdAt: string;
    focused: boolean;
  }[];
};

export type PdfScrollRequest = {
  page: number;
  sequence: number;
  behavior: ScrollBehavior;
  position?: [number, number];
};

type PageSize = {
  width: number;
  height: number;
};

function fittedSize(source: PageSize, availableWidth: number, zoom: number, rotation: ReaderRotation): PageSize {
  const safeWidth = Math.max(availableWidth, 280);
  const rotatedWidth = rotation === 90 || rotation === 270 ? source.height : source.width;
  const baseScale = Math.min(1.25, safeWidth / Math.max(rotatedWidth, 1));
  const scale = Math.max(baseScale, 0.1) * (zoom / 100);
  return {
    width: source.width * scale,
    height: source.height * scale,
  };
}

function isPdfRenderingCancellation(reason: unknown): reason is { name: string } {
  return (
    typeof reason === "object"
    && reason !== null
    && "name" in reason
    && reason.name === "RenderingCancelledException"
  );
}

function ContinuousPdfPage({
  pdfDocument,
  pageNumber,
  zoom,
  rotation,
  availableWidth,
  fallbackSize,
  active,
  current,
  overlay,
  preferOcrTextLayer,
  onRequestPage,
  onNoteSelect,
  onNoteDelete,
  onRetry,
}: {
  pdfDocument: PDFDocumentProxy;
  pageNumber: number;
  zoom: number;
  rotation: ReaderRotation;
  availableWidth: number;
  fallbackSize: PageSize;
  active: boolean;
  current: boolean;
  overlay?: PdfPageOverlay;
  preferOcrTextLayer: boolean;
  onRequestPage: (page: number) => void;
  onNoteSelect: (annotationId: string) => void;
  onNoteDelete: (annotationId: string) => void;
  onRetry?: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const [naturalSize, setNaturalSize] = useState<PageSize>(fallbackSize);
  const [status, setStatus] = useState("");
  const [failure, setFailure] = useState("");
  const [useOcrTextLayer, setUseOcrTextLayer] = useState(false);

  const targetSize = useMemo(
    () => fittedSize(naturalSize, availableWidth, zoom, rotation),
    [availableWidth, naturalSize, rotation, zoom],
  );

  useEffect(() => {
    if (!active || !canvasRef.current) return;
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    let textLayer: TextLayer | null = null;

    async function renderPage() {
      onRequestPage(pageNumber);
      setStatus(`正在渲染第 ${pageNumber} 页……`);
      setFailure("");
      const pdfPage = await pdfDocument.getPage(pageNumber);
      if (cancelled || !canvasRef.current || !textLayerRef.current) return;
      const naturalViewport = pdfPage.getViewport({ scale: 1 });
      const nextNaturalSize = {
        width: naturalViewport.width,
        height: naturalViewport.height,
      };
      const baseScale = Math.min(
        1.25,
        Math.max(availableWidth, 280) / Math.max(rotation === 90 || rotation === 270 ? naturalViewport.height : naturalViewport.width, 1),
      );
      const viewport = pdfPage.getViewport({
        scale: Math.max(baseScale, 0.1) * (zoom / 100),
      });
      const canvas = canvasRef.current;
      const textContainer = textLayerRef.current;
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("浏览器无法创建 PDF 画布。");
      const outputScale = Math.min(window.devicePixelRatio || 1, 2);

      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      setNaturalSize(nextNaturalSize);
      textContainer.replaceChildren();
      textContainer.style.setProperty("--total-scale-factor", String(viewport.scale));
      setUseOcrTextLayer(false);

      renderTask = pdfPage.render({
        canvas,
        canvasContext: context,
        viewport,
        transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
      });
      let nativeTextPromise: Promise<void> = Promise.resolve();
      if (!preferOcrTextLayer) {
        const pdfjs = await import("pdfjs-dist");
        textLayer = new pdfjs.TextLayer({
          textContentSource: pdfPage.streamTextContent({
            includeMarkedContent: true,
            disableNormalization: false,
          }),
          container: textContainer,
          viewport,
        });
        nativeTextPromise = textLayer.render();
      }
      await Promise.all([renderTask.promise, nativeTextPromise]);
      if (!cancelled) {
        const hasNativeText = Boolean(
          textLayer?.textContentItemsStr.some((text) => text.trim()),
        );
        setUseOcrTextLayer(preferOcrTextLayer || !hasNativeText);
        if (hasNativeText) {
          const end = document.createElement("div");
          end.className = "endOfContent";
          textContainer.append(end);
        }
        setStatus("");
      }
    }

    void renderPage().catch((error: unknown) => {
      if (cancelled || isPdfRenderingCancellation(error)) return;
      setFailure(error instanceof Error ? error.message : "PDF 页面渲染失败");
      setStatus("");
    });

    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [active, availableWidth, onRequestPage, pageNumber, pdfDocument, preferOcrTextLayer, rotation, zoom]);

  // Rendering an offscreen page must not restore the dimensions it had on
  // mount. That shrank earlier pages after a sidebar resize and moved jumps
  // back by a page. The layout footprint always follows the current viewport.
  const displaySize = rotation === 90 || rotation === 270
    ? { width: targetSize.height, height: targetSize.width } : targetSize;
  // Rotate the complete source plane. PDF.js retains its source crop/rotation;
  // native text, OCR and annotations share this additional viewer transform.
  const planeTransform = {
    0: "none",
    90: `matrix(0, 1, -1, 0, ${targetSize.height}, 0)`,
    180: `matrix(-1, 0, 0, -1, ${targetSize.width}, ${targetSize.height})`,
    270: `matrix(0, -1, 1, 0, 0, ${targetSize.width})`,
  }[rotation];

  return (
    <article
      className={`pdf-page-shell ${current ? "current" : ""} ${overlay?.notes.length ? "has-notes" : ""}`}
      data-page-number={pageNumber}
      aria-current={current ? "page" : undefined}
      aria-label={`PDF 第 ${pageNumber} 页`}
    >
      <div
        className={`pdf-canvas-stage continuous ${status ? "is-rendering" : "is-ready"}`}
        data-page-number={pageNumber}
        data-reader-rotation={rotation}
        style={{ width: displaySize.width, height: displaySize.height }}
        aria-busy={Boolean(status)}
      >
        <div className="pdf-source-plane" style={{
          position: "absolute", left: 0, top: 0, width: targetSize.width, height: targetSize.height,
          transform: planeTransform, transformOrigin: "0 0",
        }}>
        {active ? <canvas ref={canvasRef} style={{ width: "100%", height: "100%" }} aria-label={`PDF 第 ${pageNumber} 页画布`} /> : null}
        {active ? (
          <div
            className="textLayer pdf-native-text-layer"
            ref={textLayerRef}
            aria-hidden={preferOcrTextLayer}
            aria-label={`第 ${pageNumber} 页原生文字层`}
          />
        ) : null}
        {active && useOcrTextLayer && overlay ? (
          <div className="canonical-text-layer ocr-fallback" aria-label={`第 ${pageNumber} 页 OCR 可选择文字层`}>
            {overlay.canonicalBlocks.flatMap((block) => {
              const box = displayedReaderBox(block, targetSize.width, targetSize.height);
              if (!box) return null;
              const [x0, y0, x1, y1] = box;
              const lines = block.text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
              const visibleLines = lines.length ? lines : [block.text];
              const lineHeight = Math.max((y1 - y0) / visibleLines.length, 1);
              return visibleLines.map((line, lineIndex) => (
                <span
                  data-block-id={block.id}
                  data-confidence={block.confidence}
                  key={`${block.id}-${lineIndex}`}
                  style={{
                    left: x0,
                    top: y0 + lineIndex * lineHeight,
                    width: Math.max(x1 - x0, 1),
                    height: Math.max(lineHeight, 1),
                    fontSize: Math.max(Math.min(lineHeight * 0.82, 18), 6),
                  }}
                >
                  {line}
                </span>
              ));
            })}
          </div>
        ) : null}
        {active ? (
          <div className="pdf-search-highlights" aria-hidden="true">
            {(overlay?.highlights ?? []).map((highlight, index) => {
              const box = displayedHighlightBox(highlight, targetSize.width, targetSize.height, overlay?.sourceWidth || 0, overlay?.sourceHeight || 0);
              if (!box) return null;
              const [x0, y0, x1, y1] = box;
              return (
                <i
                  className={highlight.kind ?? "search"}
                  data-source={highlight.source}
                  data-reader-annotation-id={highlight.annotationId}
                  key={`${x0}-${y0}-${index}`}
                  style={{
                    left: x0,
                    top: y0,
                    width: Math.max(x1 - x0, 3),
                    height: Math.max(y1 - y0, 3),
                  }}
                />
              );
            })}
          </div>
        ) : null}
        </div>
        {status ? <p className="pdf-render-status">{status}</p> : null}
        {failure ? (
          <div className="pdf-render-error" role="alert">
            <strong>第 {pageNumber} 页暂时无法显示</strong>
            <span>{failure}</span>
            {onRetry ? <button type="button" onClick={onRetry}>重新加载这一页</button> : null}
          </div>
        ) : null}
      </div>
      {active && overlay?.notes.length ? (
        <aside
          className="pdf-note-rail"
          aria-label={`第 ${pageNumber} 页个人笔记`}
          style={{ left: `calc(50% + ${displaySize.width / 2 + 16}px)` }}
        >
        {(overlay?.notes ?? []).map((note, index) => {
          const sourceBox = note.bbox ? displayedHighlightBox({ bbox: note.bbox, kind: "note" },
            1, 1, overlay.sourceWidth, overlay.sourceHeight) : null;
          const top = sourceBox
            ? Math.max(0, rotateReaderBox(sourceBox, rotation)[1] * displaySize.height)
            : 56 + index * 76;
          return (
            <article
              className={`pdf-margin-note ${note.focused ? "focused" : ""}`}
              style={{ top: top + index * 12 }}
              key={note.id}
            >
              <header><strong>笔记</strong><time>{note.createdAt}</time></header>
              <span>{note.body || note.quote || "页面笔记"}</span>
              {note.quote ? <small>原文：{note.quote}</small> : null}
              <div>
                <button type="button" onClick={() => onNoteSelect(note.id)}>定位</button>
                <button type="button" aria-label={`删除第 ${pageNumber} 页笔记`} onClick={() => onNoteDelete(note.id)}><Trash2 size={13} /> 删除</button>
              </div>
            </article>
          );
        })}
        </aside>
      ) : null}
      <span className="pdf-page-label" aria-hidden="true">{pageNumber}</span>
    </article>
  );
}

export function PdfContinuousViewer({
  url,
  pageCount,
  currentPage,
  zoom,
  rotation = 0,
  overlays,
  preferOcrTextLayer = false,
  scrollRequest,
  onDocumentLoad,
  onPageChange,
  onRequestPage,
  onNoteSelect,
  onNoteDelete,
  onRetry,
}: {
  url: string;
  pageCount: number;
  currentPage: number;
  zoom: number;
  rotation?: ReaderRotation;
  overlays: Record<number, PdfPageOverlay>;
  preferOcrTextLayer?: boolean;
  scrollRequest: PdfScrollRequest;
  onDocumentLoad: (pages: number) => void;
  onPageChange: (page: number) => void;
  onRequestPage: (page: number) => void;
  onNoteSelect: (annotationId: string) => void;
  onNoteDelete: (annotationId: string) => void;
  onRetry?: () => void;
}) {
  const viewerRef = useRef<HTMLDivElement>(null);
  const [pdfDocument, setPdfDocument] = useState<PDFDocumentProxy | null>(null);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [availableWidth, setAvailableWidth] = useState(720);
  const [noteRailWidth, setNoteRailWidth] = useState(0);
  const hasMarginNotes = Object.values(overlays).some(overlay => overlay.notes.length > 0);
  const [fallbackSize, setFallbackSize] = useState<PageSize>({ width: 612, height: 792 });
  const [nearPages, setNearPages] = useState<Set<number>>(
    () => new Set([Math.max(1, scrollRequest.page - 1), scrollRequest.page, scrollRequest.page + 1]),
  );
  const [failure, setFailure] = useState("");

  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      if (isPdfRenderingCancellation(event.reason)) event.preventDefault();
    };
    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    return () => window.removeEventListener("unhandledrejection", handleUnhandledRejection);
  }, []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    const updateWidth = () => {
      const noteRail = hasMarginNotes && viewer.clientWidth >= 720 ? 184 : 0;
      setNoteRailWidth(noteRail);
      setAvailableWidth(Math.max(viewer.clientWidth - noteRail, 280));
    };
    const frame = window.requestAnimationFrame(updateWidth);
    const observer = new ResizeObserver(updateWidth);
    observer.observe(viewer);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [hasMarginNotes]);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;

    async function loadDocument() {
      setFailure("");
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
      loadingTask = pdfjs.getDocument({
        url,
        withCredentials: false,
        disableStream: true,
        disableAutoFetch: true,
        // Larger bounded ranges avoid hundreds of 64 KiB requests for scanned books.
        rangeChunkSize: 1024 * 1024,
        enableXfa: true,
        cMapUrl: "/pdfjs/cmaps/",
        cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/",
        wasmUrl: "/pdfjs/wasm/",
      });
      const loadedDocument = await loadingTask.promise;
      const firstPage = await loadedDocument.getPage(1);
      const viewport = firstPage.getViewport({ scale: 1 });
      if (cancelled) return;
      setFallbackSize({ width: viewport.width, height: viewport.height });
      setPdfDocument(loadedDocument);
      onDocumentLoad(loadedDocument.numPages);
    }

    void loadDocument().catch((error: unknown) => {
      if (cancelled) return;
      setPdfDocument(null);
      setFailure(error instanceof Error ? error.message : "PDF 加载失败");
    });

    return () => {
      cancelled = true;
      void loadingTask?.destroy();
    };
  }, [onDocumentLoad, url, loadAttempt]);

  const renderedPageCount = Math.max(pdfDocument?.numPages ?? 0, pageCount, 1);
  const pages = useMemo(
    () => Array.from({ length: renderedPageCount }, (_, index) => index + 1),
    [renderedPageCount],
  );

  useEffect(() => {
    const viewer = viewerRef.current;
    const scrollRoot = viewer?.closest<HTMLElement>(".reader-document");
    if (!viewer || !scrollRoot || !pdfDocument) return;
    const pageElements = Array.from(viewer.querySelectorAll<HTMLElement>(".pdf-page-shell"));
    const visibility = new Map<number, number>();

    const renderObserver = new IntersectionObserver(
      (entries) => {
        setNearPages((current) => {
          const next = new Set(current);
          let changed = false;
          entries.forEach((entry) => {
            const target = entry.target as HTMLElement;
            const page = Number(target.dataset.pageNumber);
            if (!page) return;
            if (entry.isIntersecting) {
              if (!next.has(page)) {
                next.add(page);
                changed = true;
              }
              [page - 1, page, page + 1].forEach((candidate) => {
                if (candidate >= 1 && candidate <= renderedPageCount) {
                  onRequestPage(candidate);
                }
              });
            } else if (next.delete(page)) {
              changed = true;
            }
          });
          return changed ? next : current;
        });
      },
      { root: scrollRoot, rootMargin: "1100px 0px", threshold: 0.01 },
    );

    const currentPageObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const page = Number((entry.target as HTMLElement).dataset.pageNumber);
          if (page) visibility.set(page, entry.isIntersecting ? entry.intersectionRatio : 0);
        });
        let bestPage = currentPage;
        let bestRatio = 0;
        visibility.forEach((ratio, page) => {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            bestPage = page;
          }
        });
        if (bestRatio > 0.02 && bestPage !== currentPage) onPageChange(bestPage);
      },
      { root: scrollRoot, threshold: [0, 0.08, 0.2, 0.4, 0.6, 0.8, 1] },
    );

    pageElements.forEach((element) => {
      renderObserver.observe(element);
      currentPageObserver.observe(element);
    });
    return () => {
      renderObserver.disconnect();
      currentPageObserver.disconnect();
    };
  }, [
    currentPage,
    onPageChange,
    onRequestPage,
    pdfDocument,
    renderedPageCount,
  ]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const scrollRoot = viewer?.closest<HTMLElement>(".reader-document");
    if (!viewer || !scrollRoot || !pdfDocument) return;
    const frame = window.requestAnimationFrame(() => {
      const target = viewer.querySelector<HTMLElement>(
        `.pdf-page-shell[data-page-number="${scrollRequest.page}"]`,
      );
      if (!target) return;
      const stage = target.querySelector<HTMLElement>(".pdf-canvas-stage");
      if (!stage) return;
      const position = scrollRequest.position ? rotateReaderPoint(scrollRequest.position, rotation) : undefined;
      const stageRect = stage.getBoundingClientRect();
      const rootRect = scrollRoot.getBoundingClientRect();
      scrollRoot.scrollTo({
        top: Math.max(scrollRoot.scrollTop + stageRect.top - rootRect.top
          + (position?.[1] ?? 0) * stageRect.height - 22, 0),
        ...(position ? { left: Math.max(scrollRoot.scrollLeft + stageRect.left - rootRect.left
          + position[0] * stageRect.width - 32, 0) } : {}),
        behavior: scrollRequest.behavior,
      });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pdfDocument, rotation, scrollRequest]);

  if (failure) {
    return (
      <div className="reader-unavailable" role="alert">
        <strong>PDF 暂时无法显示</strong>
        <p>{failure}</p>
        <button type="button" className="button secondary" onClick={() => { onRetry?.(); setLoadAttempt(value => value + 1); }}>重试加载 PDF</button>
        <a href={url}>直接打开 PDF</a>
      </div>
    );
  }

  return (
    <div className="continuous-pdf-viewer" ref={viewerRef} aria-label="PDF 连续阅读区" data-note-rail={noteRailWidth > 0} style={{"--pdf-note-rail-width":`${noteRailWidth}px`} as CSSProperties}>
      {!pdfDocument ? <LoadingState variant="page">正在载入 PDF…</LoadingState> : null}
      {pdfDocument ? pages.map((pageNumber) => (
        <ContinuousPdfPage
          pdfDocument={pdfDocument}
          pageNumber={pageNumber}
          zoom={zoom}
          rotation={rotation}
          availableWidth={availableWidth}
          fallbackSize={fallbackSize}
          active={nearPages.has(pageNumber)}
          current={currentPage === pageNumber}
          overlay={overlays[pageNumber]}
          preferOcrTextLayer={preferOcrTextLayer}
          onRequestPage={onRequestPage}
          onNoteSelect={onNoteSelect}
          onNoteDelete={onNoteDelete}
          onRetry={() => { onRetry?.(); setLoadAttempt(value => value + 1); }}
          key={pageNumber}
        />
      )) : null}
    </div>
  );
}
