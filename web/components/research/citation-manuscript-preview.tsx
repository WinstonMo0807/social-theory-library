"use client";

import { useEffect, useState } from "react";
import { PdfCanvas } from "@/components/pdf-canvas";
import { subscribeToSessionChanges } from "@/lib/api";
import { downloadAuditOriginal, type AuditData, type ResearchRecord } from "@/lib/api/research.client";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { auditLocation } from "./citation-audit-shared";

/** The encrypted manuscript is fetched only on request; no external document viewer or catalog copy. */
export function CitationManuscriptPreview({ record, ownerId }: { record: ResearchRecord<AuditData>; ownerId: string }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [zoom, setZoom] = useState(100);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (record.data.filetype !== "pdf") return;
    let active = true;
    let objectUrl = "";
    const clear = () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); setUrl(""); };
    const off = subscribeToSessionChanges(clear);
    withPrivateOwner(ownerId, () => downloadAuditOriginal(record.id)).then(result => {
      if (!active) return;
      objectUrl = URL.createObjectURL(result.blob); setUrl(objectUrl); setError("");
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "原稿读取失败。"); });
    return () => { clear(); off(); };
  }, [record.id, record.data.filetype, ownerId, attempt]);
  if (record.data.filetype === "docx") return <section className="stl4-audit-manuscript-preview"><p>以下为实际识别到的引文及附近段落。DOCX 的字体、分页与完整排版请在下载的原稿中查看。</p>{record.data.occurrences.length ? record.data.occurrences.map(row => <article key={row.id}><h3>{auditLocation(row.location)}</h3><p>{row.context}</p></article>) : <p>尚未识别到可预览的引文段落。</p>}</section>;
  return <section className="stl4-audit-manuscript-preview">{error ? <p role="alert">{error}<button onClick={() => setAttempt(attempt + 1)}>重试读取原稿</button></p> : !url ? <p role="status">正在安全读取本人的 PDF 原稿…</p> : <><div className="stl4-audit-toolbar"><button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button><label>稿件 PDF 页码 <input type="number" min={1} max={pages || undefined} value={page} onChange={event => { const value = Number(event.target.value); if (Number.isInteger(value) && value >= 1 && (!pages || value <= pages)) setPage(value); }} /></label><span>/ {pages || "—"}</span><button disabled={!pages || page >= pages} onClick={() => setPage(page + 1)}>下一页</button><label>缩放 <select value={zoom} onChange={event => setZoom(Number(event.target.value))}><option value={75}>75%</option><option value={100}>100%</option><option value={125}>125%</option><option value={150}>150%</option></select></label></div><div className="stl4-audit-manuscript-canvas"><PdfCanvas url={url} page={page} zoom={zoom} sourceWidth={0} sourceHeight={0} canonicalBlocks={[]} highlights={[]} onDocumentLoad={setPages} /></div></>}</section>;
}
