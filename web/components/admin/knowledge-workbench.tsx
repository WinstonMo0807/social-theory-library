"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowUpRight, ChevronLeft, ChevronRight, BookOpen, X } from "lucide-react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { PdfCanvas } from "@/components/pdf-canvas";
import s from "./knowledge-workbench.module.css";

export const knowledgeCall = <T,>(path: string, body?: unknown, signal?: AbortSignal) => apiRequest<T>(path,
  { cache: "no-store", signal, ...(body === undefined ? {} : { method: "POST", body: JSON.stringify(body) }) }, getServerSessionCredential());
export type SourceSegment = { page_number: number; start: number; end: number; exact: string; node_id?: string; printed_label?: string };
export type SourceLocator = { anchor_id: string; asset_id: string; document_revision_id: string; reader_url: string; segments: SourceSegment[]; chapter_path?: string[] };
export type LibrarySource = { revision_id: string; asset_id: string; edition_id: string; work_id: string; title: string; edition_label?: string; revision_number: number; pages: number;
  readable: boolean; published: boolean; keywords: string; semantic: string; structure_id: string | null; structure_coverage: { structure_status?: string; unmapped_headings?: { title?: string; page?: number }[]; alignment_gaps?: unknown[]; unmatched_ranges?: unknown[] };
  structure_job?: { id: string; status: string; error: string; pages: number[] } | null;
  index_counts: { total?: number; keywords?: number; vectors?: number; expected?: number }; index_error: string; index_job: { id: string; status: string } | null;
  curation: { id: string; status: string } | null; catalog_url: string; outline_url: string; ocr_url: string; work_url?: string; reader_url: string };

export function KnowledgeNavigation({ active, workId, revisionId }: { active: "sources" | "pages" | "intelligence"; workId?: string; revisionId?: string }) {
  const context = new URLSearchParams(); if (workId) context.set("work_id", workId); if (revisionId) context.set("revision", revisionId);
  return <nav className={s.navigation} aria-label="知识工作区">{[
    ["sources", "/admin/sources", "原文与检索"], ["pages", "/admin/knowledge", "知识编纂"], ["intelligence", "/admin/intelligence", "Intelligence"],
  ].map(([key, path, label]) => <Link key={key} href={`${path}${context.size ? `?${context}` : ""}`} aria-current={active === key ? "page" : undefined}>{label}</Link>)}</nav>;
}

export function EvidencePanel({ source, locator, page: incomingPage = 1, open, onClose, onQuote }: {
  source?: Pick<LibrarySource, "asset_id" | "revision_id" | "pages" | "title">; locator?: SourceLocator | null; page?: number;
  open?: boolean; onClose?: () => void; onQuote?: (segment: SourceSegment) => void;
}) {
  const assetId = locator?.asset_id || source?.asset_id, revision = locator?.document_revision_id || source?.revision_id;
  const [page, setPage] = useState(incomingPage), [mode, setMode] = useState<"text" | "pdf">("text"), [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<{ text: string; printed_label: string; content_hash: string } | null>(null);
  const [error, setError] = useState(""), [pdf, setPdf] = useState(""), [pdfError, setPdfError] = useState(""), [pages, setPages] = useState(0);
  const [selected, setSelected] = useState<SourceSegment | null>(null);
  const textRef = useRef<HTMLDivElement>(null);
  useEffect(() => { setPage(locator?.segments[0]?.page_number || incomingPage); setSelected(null); }, [revision, locator?.anchor_id, incomingPage]);
  useEffect(() => {
    setData(null); setError(""); setSelected(null); if (!revision) return;
    const c = new AbortController();
    void knowledgeCall<typeof data>(`/knowledge/revisions/${revision}/pages/${page}/?preview=1`, undefined, c.signal)
      .then(setData).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [revision, page, attempt]);
  useEffect(() => {
    setPdf(""); setPdfError(""); if (mode !== "pdf" || !revision || !assetId) return;
    const c = new AbortController();
    void knowledgeCall<{ url: string; requested_asset_id: string }>(`/distribution/assets/${assetId}/access/?revision=${revision}&preview=1`, undefined, c.signal)
      .then(r => { if (r.requested_asset_id !== assetId) throw new Error("阅读文件身份变化，请重新打开来源。"); setPdf(normalizePublicResourceUrl(r.url)); })
      .catch(e => { if (!c.signal.aborted) setPdfError(e.message); });
    return () => c.abort();
  }, [revision, assetId, mode, attempt]);
  const loaded = useCallback((count: number) => setPages(count), []);
  const total = source?.pages || pages;
  function capture() {
    if (!onQuote || !data || !textRef.current) return;
    const selection = window.getSelection(); if (!selection?.rangeCount || selection.isCollapsed) return;
    const range = selection.getRangeAt(0);
    if (!textRef.current.contains(range.startContainer) || !textRef.current.contains(range.endContainer)) return;
    const prefix = range.cloneRange(); prefix.selectNodeContents(textRef.current); prefix.setEnd(range.startContainer, range.startOffset);
    const start = Array.from(prefix.toString()).length, exact = selection.toString(), end = start + Array.from(exact).length;
    if (Array.from(data.text).slice(start, end).join("") === exact) setSelected({ page_number: page, start, end, exact });
  }
  const citedPages = [...new Set(locator?.segments.map(v => v.page_number) || [])];
  const reader = assetId ? `/reader/${assetId}?revision=${revision}&page=${page}&preview=1${locator?.anchor_id ? `&anchor=${locator.anchor_id}` : ""}` : "";
  return <aside className={`${s.evidence} ${open ? s.evidenceOpen : ""}`} aria-label="来源核验">
    <header className={s.sectionBar}><h2><BookOpen size={17} />来源核验</h2>{onClose && <button className={s.mobileOnly} onClick={onClose} aria-label="返回编辑"><X size={18} /></button>}</header>
    {!revision ? <p className={s.empty}>选择正文或引用，在这里核对对应版本。</p> : <>
      {source?.title && <h3 className={s.sourceTitle}>{source.title}</h3>}
      <div className={s.toolbar}><div className={s.segmented}><button aria-pressed={mode === "text"} onClick={() => setMode("text")}>原文</button><button aria-pressed={mode === "pdf"} onClick={() => setMode("pdf")}>PDF</button></div><Link target="_blank" href={reader}>阅读器 <ArrowUpRight size={14} /></Link></div>
      <div className={s.pageNav}><button disabled={page <= 1} aria-label="上一页" onClick={() => setPage(v => v - 1)}><ChevronLeft size={16} /></button>
        <label>PDF <input aria-label="原文PDF页码" type="number" min={1} max={total || undefined} value={page} onChange={e => { const n = Number(e.target.value); if (Number.isInteger(n) && n > 0 && (!total || n <= total)) setPage(n); }} /></label>
        <span>{total ? `/ ${total}` : ""}{data?.printed_label ? ` · 书页 ${data.printed_label}` : ""}</span><button disabled={!!total && page >= total} aria-label="下一页" onClick={() => setPage(v => v + 1)}><ChevronRight size={16} /></button></div>
      {citedPages.length > 1 && <div className={s.toolbar} aria-label="引用各页">{citedPages.map(p => <button key={p} aria-pressed={page === p} onClick={() => setPage(p)}>PDF {p}</button>)}</div>}
      {mode === "pdf" ? pdfError ? <p role="alert">{pdfError}<button onClick={() => setAttempt(v => v + 1)}>重试PDF</button></p> : pdf ? <div className={s.pdf}><PdfCanvas url={pdf} page={page} zoom={100} sourceWidth={0} sourceHeight={0} canonicalBlocks={[]} highlights={[]} onDocumentLoad={loaded} withCredentials /></div> : <p role="status">正在读取引用版本的 PDF…</p>
      : error ? <p role="alert" className={s.error}>{error}<button onClick={() => setAttempt(v => v + 1)}>重新读取此页</button></p> : !data ? <p role="status">正在读取正文快照…</p> : <>
        {locator?.segments.filter(v => v.page_number === page).map((v, i) => <blockquote key={i} className={s.quote}>{Array.from(data.text).slice(v.start, v.end).join("") === v.exact ? v.exact : <span role="alert">引用与此修订未能匹配，请核对来源。</span>}</blockquote>)}
        {onQuote && <p className={s.muted}>选中下面的原文，可加入引用。跨页文字可分次选取。</p>}
        {selected && onQuote && <button className={s.primary} onClick={() => { onQuote(selected); setSelected(null); }}>将所选文字加入引用</button>}
        <div ref={textRef} className={s.sourceText} onMouseUp={capture} onKeyUp={capture} onTouchEnd={capture} tabIndex={onQuote ? 0 : undefined}>{data.text || "此页尚无可读取文字，请查看 PDF。"}</div>
      </>}
    </>}
  </aside>;
}
