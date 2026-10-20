"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

/** Reuse the already rendered source page; no second PDF download or persisted image. */
export function ReaderPageThumbnail({ sourceRef, page, identity }: {
  sourceRef: RefObject<HTMLElement | null>; page: number; identity: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [readyFor, setReadyFor] = useState("");
  const key = `${identity}:${page}`;
  const ready = readyFor === key;
  useEffect(() => {
    const source = sourceRef.current;
    if (!source) return;
    let frame = 0;
    const paint = () => {
      frame = 0;
      const original = source.querySelector<HTMLCanvasElement>(
        `.pdf-page-shell[data-page-number="${page}"] .pdf-canvas-stage.is-ready canvas`,
      );
      const target = canvasRef.current;
      if (!original?.width || !original.height || !target) { setReadyFor(""); return; }
      const ratio = Math.min(360 / original.width, 480 / original.height, 1);
      target.width = Math.max(1, Math.round(original.width * ratio));
      target.height = Math.max(1, Math.round(original.height * ratio));
      const context = target.getContext("2d", { alpha: false });
      if (!context) { setReadyFor(""); return; }
      context.drawImage(original, 0, 0, target.width, target.height);
      setReadyFor(key);
    };
    const schedule = () => { if (!frame) frame = window.requestAnimationFrame(paint); };
    const observer = new MutationObserver(schedule);
    observer.observe(source, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
    schedule();
    return () => { observer.disconnect(); if (frame) window.cancelAnimationFrame(frame); };
  }, [sourceRef, page, key]);
  return <figure style={{ margin: 0 }}>
    <canvas ref={canvasRef} hidden={!ready} aria-label={`已载入的 PDF 第 ${page} 页缩略图`} style={{ width: "100%", height: "auto" }} />
    {!ready ? <p role="status">当前原页尚未载入，可以继续查看文字处理状态。</p> : null}
    <figcaption>PDF 第 {page} 页 · 当前原页</figcaption>
  </figure>;
}
