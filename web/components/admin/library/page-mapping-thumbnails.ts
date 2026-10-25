"use client";

import { useEffect, useState } from "react";
import type { PDFDocumentLoadingTask, RenderTask } from "pdfjs-dist/types/src/display/api";

/** Eight visible pages share one bounded thumbnail document; no library files are uploaded. */
export function useMappingThumbnails(url: string, indexes: string, withCredentials = false): { images: Record<number, string>; error: string } {
  const [result, setResult] = useState<{ key: string; images: Record<number, string>; error: string } | null>(null);
  const key = `${url}:${indexes}:${withCredentials}`;
  useEffect(() => {
    if (!url || !indexes) return;
    let alive = true, loading: PDFDocumentLoadingTask | null = null, rendering: RenderTask | null = null;
    async function load() {
      const pdfjs = await import("pdfjs-dist");
      if (!alive) return;
      pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.js";
      loading = pdfjs.getDocument({ url, withCredentials, disableStream: true, disableAutoFetch: true, cMapUrl: "/pdfjs/cmaps/", cMapPacked: true, standardFontDataUrl: "/pdfjs/standard_fonts/", wasmUrl: "/pdfjs/wasm/" });
      const document = await loading.promise;
      const images: Record<number, string> = {};
      for (const index of indexes.split(",").map(Number).slice(0, 8)) {
        if (!alive) return;
        if (index < 1 || index > document.numPages) continue;
        const page = await document.getPage(index);
        if (!alive) return;
        const base = page.getViewport({ scale: 1 }), viewport = page.getViewport({ scale: Math.min(160 / base.width, 200 / base.height) });
        const canvas = window.document.createElement("canvas");
        canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
        rendering = page.render({ canvas, viewport });
        await rendering.promise;
        images[index] = canvas.toDataURL("image/png");
        page.cleanup();
      }
      if (alive) setResult({ key, images, error: "" });
      await loading.destroy(); loading = null;
    }
    void load().catch((reason: unknown) => { if (alive) setResult({ key, images: {}, error: reason instanceof Error ? reason.message : "缩略图暂时不可用，请查看右侧原稿。" }); });
    return () => { alive = false; rendering?.cancel(); void loading?.destroy(); };
  }, [url, indexes, key, withCredentials]);
  return result?.key === key && url ? result : { images: {}, error: "" };
}
