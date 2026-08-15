"use client";

import type {
  PDFDocumentProxy,
  PDFDocumentLoadingTask,
  RenderTask,
} from "pdfjs-dist/types/src/display/api";
import { useEffect, useMemo, useRef, useState } from "react";

const pdfWorkerUrl = "/pdfjs/pdf.worker.min.js";

export type CanonicalBlock = {
  id: string;
  order: number;
  type: string;
  text: string;
  bbox: number[];
  confidence: number;
};

export type PageHighlight = {
  bbox: number[];
  kind?: "search" | "highlight" | "underline" | "note";
};

type PageDimensions = {
  width: number;
  height: number;
};

type AvailableSize = {
  width: number;
  height: number;
};

export function PdfCanvas({
  url,
  page,
  zoom,
  sourceWidth,
  sourceHeight,
  canonicalBlocks,
  highlights,
  onDocumentLoad,
}: {
  url: string;
  page: number;
  zoom: number;
  sourceWidth: number;
  sourceHeight: number;
  canonicalBlocks: CanonicalBlock[];
  highlights: PageHighlight[];
  onDocumentLoad: (pages: number) => void;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [dimensions, setDimensions] = useState<PageDimensions>({ width: 0, height: 0 });
  const [availableSize, setAvailableSize] = useState<AvailableSize>({ width: 0, height: 0 });
  const [status, setStatus] = useState("正在载入 PDF……");
  const [failure, setFailure] = useState("");

  useEffect(() => {
    const container = stageRef.current?.parentElement;
    if (!container) return;
    let frame = 0;
    const updateSize = () => {
      const style = window.getComputedStyle(container);
      const contentWidth = (
        container.clientWidth
        - Number.parseFloat(style.paddingLeft || "0")
        - Number.parseFloat(style.paddingRight || "0")
      );
      const contentHeight = (
        container.clientHeight
        - Number.parseFloat(style.paddingTop || "0")
        - Number.parseFloat(style.paddingBottom || "0")
      );
      setAvailableSize({
        width: Math.max(Math.floor(contentWidth), 0),
        height: Math.max(Math.floor(contentHeight), 0),
      });
    };
    frame = window.requestAnimationFrame(updateSize);
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let loadingTask: PDFDocumentLoadingTask | null = null;
    let loadedDocument: PDFDocumentProxy | null = null;

    async function load() {
      setFailure("");
      setStatus("正在载入 PDF……");
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;
      loadingTask = pdfjs.getDocument({
        url,
        withCredentials: false,
        disableStream: true,
        disableAutoFetch: true,
        enableXfa: true,
        cMapUrl: "/pdfjs/cmaps/",
        cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/",
        wasmUrl: "/pdfjs/wasm/",
      });
      loadedDocument = await loadingTask.promise;
      if (cancelled) return;
      setDocument(loadedDocument);
      onDocumentLoad(loadedDocument.numPages);
    }

    load().catch((error: unknown) => {
      if (cancelled) return;
      setDocument(null);
      setFailure(error instanceof Error ? error.message : "PDF 加载失败");
      setStatus("");
    });

    return () => {
      cancelled = true;
      setDocument(null);
      void loadingTask?.destroy();
      if (loadedDocument && !loadingTask) {
        void loadedDocument.destroy();
      }
    };
  }, [onDocumentLoad, url]);

  useEffect(() => {
    if (!document || !canvasRef.current) return;
    const pdfDocument = document;
    let cancelled = false;
    let renderTask: RenderTask | null = null;

    async function render() {
      const pdfPage = await pdfDocument.getPage(
        Math.min(Math.max(page, 1), pdfDocument.numPages),
      );
      if (cancelled || !canvasRef.current) return;
      const naturalViewport = pdfPage.getViewport({ scale: 1 });
      const fitScale = Math.min(
        1.15,
        availableSize.width
          ? availableSize.width / naturalViewport.width
          : 1.15,
        availableSize.height
          ? availableSize.height / naturalViewport.height
          : 1.15,
      );
      const viewport = pdfPage.getViewport({
        scale: Math.max(fitScale, 0.1) * (zoom / 100),
      });
      const outputScale = Math.min(window.devicePixelRatio || 1, 2);
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("浏览器无法创建 PDF 画布。");

      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      setDimensions({ width: viewport.width, height: viewport.height });

      renderTask = pdfPage.render({
        canvas,
        canvasContext: context,
        viewport,
        transform: outputScale === 1 ? undefined : [outputScale, 0, 0, outputScale, 0, 0],
      });
      await renderTask.promise;
      if (!cancelled) setStatus("");
    }

    setStatus(`正在渲染第 ${page} 页……`);
    setFailure("");
    render().catch((error: unknown) => {
      if (cancelled || error instanceof Error && error.name === "RenderingCancelledException") return;
      setFailure(error instanceof Error ? error.message : "PDF 页面渲染失败");
      setStatus("");
    });

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [availableSize, document, page, zoom]);

  const scale = useMemo(
    () => ({
      x: dimensions.width / Math.max(sourceWidth, 1),
      y: dimensions.height / Math.max(sourceHeight, 1),
    }),
    [dimensions, sourceHeight, sourceWidth],
  );

  return (
    <div
      className={`pdf-canvas-stage ${status ? "is-rendering" : "is-ready"}`}
      ref={stageRef}
      style={{ width: dimensions.width || undefined, minHeight: dimensions.height || 720 }}
      aria-busy={Boolean(status)}
    >
      <canvas ref={canvasRef} aria-label={`PDF 第 ${page} 页`} />
      {dimensions.width && sourceWidth && sourceHeight ? (
        <div className="canonical-text-layer" aria-label="可选择的规范文字层">
          {canonicalBlocks.map((block) => {
            if (block.bbox.length !== 4) return null;
            const [x0, y0, x1, y1] = block.bbox;
            return (
              <span
                data-block-id={block.id}
                data-confidence={block.confidence}
                key={block.id}
                style={{
                  left: x0 * scale.x,
                  top: y0 * scale.y,
                  width: Math.max((x1 - x0) * scale.x, 1),
                  height: Math.max((y1 - y0) * scale.y, 1),
                  fontSize: Math.max(Math.min((y1 - y0) * scale.y * 0.36, 18), 6),
                }}
              >
                {block.text}
              </span>
            );
          })}
        </div>
      ) : null}
      <div className="pdf-search-highlights" aria-hidden>
        {highlights.map((highlight, index) => {
          if (highlight.bbox.length !== 4 || !sourceWidth || !sourceHeight) return null;
          const [x0, y0, x1, y1] = highlight.bbox;
          return (
            <i
              className={highlight.kind ?? "search"}
              key={`${x0}-${y0}-${index}`}
              style={{
                left: x0 * scale.x,
                top: y0 * scale.y,
                width: Math.max((x1 - x0) * scale.x, 3),
                height: Math.max((y1 - y0) * scale.y, 3),
              }}
            />
          );
        })}
      </div>
      {status ? <p className="pdf-render-status">{status}</p> : null}
      {failure ? (
        <div className="pdf-render-error" role="alert">
          <strong>这一页暂时无法显示</strong>
          <span>{failure}</span>
          <a href={url}>直接打开 PDF</a>
        </div>
      ) : null}
    </div>
  );
}
