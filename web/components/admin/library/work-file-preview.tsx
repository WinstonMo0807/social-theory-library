"use client";

import { ChevronLeft, ChevronRight, Download, Minus, Plus, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { isWorkFileContent, readWorkFileBlob, readWorkFileHead } from "@/lib/api/work-files.client";
import type { WorkFile } from "@/lib/api/work-files.types";
import { PdfCanvas } from "@/components/pdf-canvas";
import { Dialog } from "@/components/ui/dialog";
import styles from "./work-files.module.css";
import { useMappingThumbnails } from "./page-mapping-thumbnails";

export function WorkFilePdf({ url, privateFile = false, initialPage=1, atlasIntake=false }: { url: string; privateFile?: boolean; initialPage?:number; atlasIntake?:boolean }) {
  const [page, setPage] = useState(Number.isSafeInteger(initialPage)&&initialPage>0?initialPage:1), [pages, setPages] = useState(0), [zoom, setZoom] = useState(1);
  const loaded=useCallback((count:number)=>{setPages(count);setPage(value=>Math.max(1,Math.min(value,count)));},[]);
  const firstThumbnail = Math.floor((page-1)/4)*4+1;
  const thumbnailPages = atlasIntake ? Array.from({length:Math.min(4,Math.max(0,pages-firstThumbnail+1))},(_,i)=>firstThumbnail+i) : [];
  const thumbnails = useMappingThumbnails(atlasIntake ? url : "",thumbnailPages.join(","),privateFile);
  return <div className={styles.pdf} data-atlas-intake={atlasIntake}>
    <div className={styles.pdfToolbar}><button aria-label="上一页" disabled={page <= 1} onClick={() => setPage(value => value - 1)}><ChevronLeft size={14} /></button><label>PDF 页<input aria-label="PDF 页码" type="number" min={1} max={pages || 1} value={page} onChange={event => setPage(Math.max(1, Math.min(Math.trunc(Number(event.target.value)) || 1, pages || 1)))} /></label><span>/ {pages || "—"}</span><button aria-label="下一页" disabled={!pages || page >= pages} onClick={() => setPage(value => value + 1)}><ChevronRight size={14} /></button><button aria-label="缩小原稿" disabled={zoom <= .5} onClick={() => setZoom(value => Math.max(.5, value - .25))}><Minus size={14} /></button><span>{Math.round(zoom * 100)}%</span><button aria-label="放大原稿" disabled={zoom >= 2} onClick={() => setZoom(value => Math.min(2, value + .25))}><Plus size={14} /></button></div>
    {pages>0&&initialPage>pages?<p role="alert">来源标记的页码超出此文件范围，已显示末页，请重新核对原文位置。</p>:null}
    <div className={styles.pdfBody}>{atlasIntake ? <nav className={styles.pdfThumbnails} aria-label="原件页面缩略图">{thumbnailPages.map(index=><button key={index} type="button" aria-label={`查看 PDF 第 ${index} 页`} aria-current={page===index?"page":undefined} onClick={()=>setPage(index)}>{thumbnails.images[index]?<img src={thumbnails.images[index]} alt=""/>:<span className={styles.thumbnailPlaceholder}>第 {index} 页</span>}<span>{index}</span></button>)}{thumbnails.error?<p role="status">缩略图未能载入，仍可用页码查看原件。</p>:null}</nav>:null}<div className={styles.pdfStage}><PdfCanvas url={url} page={page} zoom={zoom * 100} sourceWidth={0} sourceHeight={0} canonicalBlocks={[]} highlights={[]} onDocumentLoad={loaded} withCredentials={privateFile} /></div></div>
  </div>;
}

export function WorkFilePreview({ file, ownerId, onClose, initialPage=1, returnLabel="返回文件列表" }: { file: WorkFile; ownerId: string; onClose: () => void; initialPage?:number; returnLabel?:string }) {
  const [verified, setVerified] = useState<{ key: string; url: string } | null>(null), [error, setError] = useState(""), [attempt, setAttempt] = useState(0), [downloading, setDownloading] = useState(false);
  const identity = `${ownerId}:${file.id}:${file.sha256}`, url = verified?.key === identity ? verified.url : "";
  const downloadRequest = useRef<AbortController | null>(null), alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    const clear = () => { alive.current = false; downloadRequest.current?.abort(); };
    const unsubscribe = subscribeToSessionChanges(clear);
    return () => { clear(); unsubscribe(); };
  }, [ownerId]);
  useEffect(() => {
    const controller = new AbortController(); let alive = true;
    const clear = () => { alive = false; controller.abort(); setVerified(null); };
    const unsubscribe = subscribeToSessionChanges(clear);
    if (file.preview_url) void withPrivateOwner(ownerId, () => readWorkFileHead(file.preview_url, controller.signal), controller.signal).then(head => {
      if (!alive) return;
      if (!head.contentType.includes("application/pdf")) throw new Error("此文件不是可直接预览的 PDF，请下载保留的原件。");
      if (head.sha256 !== file.sha256) throw new Error("文件与当前记录不一致，请刷新文件列表后再预览。");
      setVerified({ key: identity, url: head.url }); setError("");
    }).catch(reason => { if (alive) setError(reason instanceof Error ? reason.message : "预览未能读取。"); });
    return () => { clear(); unsubscribe(); };
  }, [identity, file.sha256, file.preview_url, ownerId, attempt]);
  async function download() {
    if (downloadRequest.current || !alive.current || !file.download_url) return;
    const controller = new AbortController(); downloadRequest.current = controller;
    setDownloading(true);
    try { await downloadWorkFile(ownerId, file.download_url, file.filename || "馆藏原件", controller.signal); }
    catch (reason) { if (alive.current) setError(reason instanceof Error ? reason.message : "原件未能下载。"); }
    finally { downloadRequest.current = null; if (alive.current) setDownloading(false); }
  }
  return <Dialog open className={`${styles.dialog} ${styles.previewDialog}`} aria-labelledby="file-preview-title" onRequestClose={onClose}><header><div><h2 id="file-preview-title">{file.filename || "文件预览"}</h2><p>第 {file.version} 份文件 · {file.is_public_reader ? "当前公开阅读文件" : "保留的文件记录"}</p></div><button aria-label="关闭文件预览" onClick={onClose}><X size={18} /></button></header>{error ? <p className={styles.error} role="alert">{error}<button onClick={() => setAttempt(value => value + 1)}>重新读取</button></p> : null}{url ? <WorkFilePdf key={`${url}:${initialPage}`} url={url} privateFile initialPage={initialPage} /> : <p role="status">{file.preview_url ? "正在读取受权限保护的文件…" : "该格式暂无分页预览，可以下载原件。"}</p>}<footer><button onClick={onClose}>{returnLabel}</button><button disabled={!file.download_url || downloading} onClick={() => void download()}><Download size={14} />{downloading ? "正在准备…" : "下载这份原件"}</button></footer></Dialog>;
}

export async function downloadWorkFile(ownerId: string, path: string, name: string, signal?: AbortSignal) {
  const controller = new AbortController(); let url = "";
  const unsubscribe = subscribeToSessionChanges(() => { controller.abort(); if (url) URL.revokeObjectURL(url); });
  const combined = AbortSignal.any([controller.signal, AbortSignal.timeout(60000), ...(signal ? [signal] : [])]);
  try {
    if (isWorkFileContent(path)) {
      const downloadPath = path.includes("?") ? path : `${path}?download=1`;
      const head = await withPrivateOwner(ownerId, () => readWorkFileHead(downloadPath, combined), combined);
      combined.throwIfAborted();
      // Let the authenticated server's attachment header perform the native download.
      // An HTTP error without that header must not be saved under an original filename.
      const link = document.createElement("a"); link.href = head.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.click();
      return;
    }
    const blob = await withPrivateOwner(ownerId, () => readWorkFileBlob(path, combined), combined);
    combined.throwIfAborted();
    url = URL.createObjectURL(blob);
    const link = document.createElement("a"); link.href = url; link.download = name; link.click();
  } finally {
    if (url) window.setTimeout(() => { URL.revokeObjectURL(url); unsubscribe(); }, 1000);
    else unsubscribe();
  }
}
