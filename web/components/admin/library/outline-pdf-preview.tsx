"use client";

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Minus, Plus } from "lucide-react";
import { apiBlob, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { PdfCanvas } from "@/components/pdf-canvas";
import type { OutlineAsset } from "@/lib/api/curation-workspace.client";
import styles from "./document-outline.module.css";

export function OutlinePdfPreview({ asset, ownerId, page, setPage, navigationTarget, onFileReady }: {
  asset: OutlineAsset; ownerId: string; page: number; setPage: (page: number) => void; navigationTarget?: [number, number];
  onFileReady?: (url: string) => void;
}) {
  const [file, setFile] = useState<{ key: string; url: string } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [actualPages, setActualPages] = useState(0);
  const [pageInput, setPageInput] = useState<string | null>(null);
  const key = `${ownerId}:${asset.id}:${asset.sha256}`;
  const url = file?.key === key ? file.url : "";
  const total = actualPages || asset.page_count;
  const jump = (next: number) => {
    setPageInput(null);
    if (Number.isInteger(next) && next > 0 && next <= total) setPage(next);
  };
  const onLoad = useCallback((count: number) => setActualPages(count), []);
  useEffect(() => {
    let alive = true, objectUrl = "";
    const clear = () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); setFile(null); onFileReady?.(""); };
    const unsubscribe = subscribeToSessionChanges(clear);
    void withPrivateOwner(ownerId, () => apiBlob(asset.preview_url, getServerSessionCredential())).then(blob => {
      if (!alive) return;
      objectUrl = URL.createObjectURL(blob); setFile({ key, url: objectUrl }); setError(""); onFileReady?.(objectUrl);
    }).catch((reason: unknown) => { if (alive) setError(reason instanceof Error ? reason.message : "阅读文件暂时无法预览。"); });
    return () => { alive = false; unsubscribe(); if (objectUrl) URL.revokeObjectURL(objectUrl); onFileReady?.(""); };
  }, [ownerId, asset.preview_url, key, attempt, onFileReady]);
  return <section className={styles.preview} aria-label="对应页面预览">
    <header><h2>对应页面预览</h2><span>PDF 第 {page} 页 / 共 {total || "—"} 页</span></header>
    <div className={styles.pdfToolbar}>
      <button type="button" aria-label="上一页" disabled={page <= 1} onClick={() => jump(page - 1)}><ChevronLeft size={15} /></button>
      <form onSubmit={event => { event.preventDefault(); jump(Number(pageInput ?? page)); }}>
        <input aria-label="预览 PDF 页码" type="number" min={1} max={total || undefined} value={pageInput ?? page} onChange={event => setPageInput(event.target.value)} onBlur={() => jump(Number(pageInput ?? page))} /><span> / {total || "—"}</span>
      </form>
      <button type="button" aria-label="下一页" disabled={!total || page >= total} onClick={() => jump(page + 1)}><ChevronRight size={15} /></button>
      <button type="button" aria-label="缩小页面" disabled={zoom <= 60} onClick={() => setZoom(value => value - 20)}><Minus size={14} /></button>
      <button type="button" aria-label="恢复页面缩放" onClick={() => setZoom(100)}>{zoom}%</button>
      <button type="button" aria-label="放大页面" disabled={zoom >= 200} onClick={() => setZoom(value => value + 20)}><Plus size={14} /></button>
    </div>
    {error ? <div className={styles.notice} role="alert"><p>{error}</p><button type="button" onClick={() => { setError(""); setAttempt(value => value + 1); }}>重新读取 PDF</button></div> : !url ? <p role="status" className={styles.notice}>正在读取当前文件……</p> :
      page > total && total > 0 ? <p role="alert" className={styles.notice}>所选页超出实际 PDF 页数，请校准节点。</p> :
        <div className={styles.canvas}><PdfCanvas key={url} url={url} page={page} zoom={zoom} sourceWidth={0} sourceHeight={0} canonicalBlocks={[]} highlights={[]} onDocumentLoad={onLoad} navigationTarget={navigationTarget} /></div>}
    <p className={styles.caption}>请对照正文确认印刷页码和跳转位置。这里读取当前文件的原始页面。</p>
  </section>;
}
