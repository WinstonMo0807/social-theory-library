"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { ChevronLeft, ChevronRight, ExternalLink, Minus, Plus } from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";
import { apiRequest } from "@/lib/api";
import type { ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey, researchReaderHref } from "@/lib/api/research-evidence";
import { PdfCanvas } from "@/components/pdf-canvas";
import type { AccessPayload, PagePayload } from "@/components/reader/types";
import { useReaderDocument, validateReaderPage } from "@/components/reader/use-reader-document";
import { readerResearchAnchors } from "@/components/reader/use-reader-research";
import { buildReaderPageOverlays } from "@/components/reader/use-reader-page-overlays";

type SourceTab = "original" | "context" | "page" | "book";
const sourceTabs: Array<{ id: SourceTab; label: string }> = [
  { id: "original", label: "原文查看" }, { id: "context", label: "前后文对照" },
  { id: "page", label: "页面信息" }, { id: "book", label: "书目信息" },
];

function SourceText({ reference }: { reference: ResolvedEvidence }) {
  const text = reference.source_status === "available" ? reference.quote || reference.text : "";
  const href = researchReaderHref(reference);
  return <div className="stl4-citation-source-text">
    {text ? <blockquote>{text}</blockquote> : <p>这条材料尚无可显示的原文片段。</p>}
    <p>{reference.source_status === "available" ? "尚无完整页定位，以上为当前可用的原文片段。" : "来源当前不可用，请返回报告重新核对。"}</p>
    {href ? <a href={href} target="_blank" rel="noopener noreferrer">在新窗口打开原文 <ExternalLink size={13} /></a> : null}
  </div>;
}

function SourceDocument({ reference, assetId, revisionId, initialPage }: {
  reference: ResolvedEvidence; assetId: string; revisionId: string; initialPage: number;
}) {
  const [tab, setTab] = useState<SourceTab>("original");
  const [page, setPage] = useState(initialPage);
  const [pageInput, setPageInput] = useState<string | null>(null);
  const [zoom, setZoom] = useState(100);
  const [documentPages, setDocumentPages] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const panelId = useId();
  const { access, accessError, pagePayloads, pageErrors, requestPagePayload, retryPagePayload, retryAccess } = useReaderDocument({
    assetId, workId: reference.work_id, documentRevisionId: revisionId,
  });
  const [verified, setVerified] = useState<{ access: AccessPayload; page: number; payload?: PagePayload; error?: string } | null>(null);

  // Access signatures contain no revision. Recheck the canonical page after every
  // signature refresh, and never combine the previous verification with a new URL.
  useEffect(() => {
    if (!access) return;
    const request = new AbortController();
    void apiRequest<PagePayload>(`/catalog/assets/${encodeURIComponent(assetId)}/pages/${page}/`, {
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(30000)]), cache: "no-store",
    }).then(payload => {
      validateReaderPage(payload, assetId, revisionId, page);
      if (!request.signal.aborted) setVerified({ access, page, payload });
    }).catch((reason: unknown) => {
      if (!request.signal.aborted) setVerified({ access, page, error: reason instanceof Error ? reason.message : "原文记录核对失败，请重试。" });
    });
    return () => request.abort();
  }, [access, assetId, revisionId, page, attempt]);

  const current = verified?.access === access && verified.page === page ? verified : null;
  const payload = current?.payload;
  const totalPages = documentPages || access?.page_count || 0;
  const pageOutsideDocument = totalPages > 0 && page > totalPages;
  const onDocumentLoad = useCallback((count: number) => setDocumentPages(count), []);
  const neighbors = [page - 1, page + 1].filter(value => value > 0 && totalPages > 0 && value <= totalPages);
  useEffect(() => {
    if (tab !== "context" || !payload || !access) return;
    if (page > 1) requestPagePayload(page - 1);
    if (totalPages > page) requestPagePayload(page + 1);
  }, [tab, payload, access, page, totalPages, requestPagePayload]);

  const overlay = payload ? buildReaderPageOverlays({ annotations: [], focusedAnnotationId: "", passageFocus: null,
    pagePayloads: { [page]: payload }, researchAnchors: readerResearchAnchors(reference, assetId, revisionId), query: "", searchMatches: [],
  })[page] : null;
  const jumpToPage = (value: number) => {
    if (Number.isInteger(value) && value >= 1 && (!totalPages || value <= totalPages)) setPage(value);
    setPageInput(null);
  };
  const retry = () => { setVerified(null); setAttempt(value => value + 1); retryAccess(); };
  const readerParams = new URLSearchParams({ page: String(page), revision: revisionId });
  if (reference.evidence_span_id && page === initialPage) readerParams.set("evidence", reference.evidence_span_id);
  const href = `/reader/${encodeURIComponent(assetId)}?${readerParams}`;
  const failure = accessError || current?.error || (pageOutsideDocument ? "这条原文定位超出文件页数，请返回报告重新核对来源。" : "");

  return <div className="stl4-citation-source">
    <div className="stl4-citation-source-tabs" role="tablist" aria-label="原文与上下文" onKeyDown={event => {
      const index = sourceTabs.findIndex(item => item.id === tab);
      const next = event.key === "ArrowRight" ? (index + 1) % sourceTabs.length : event.key === "ArrowLeft" ?
        (index + sourceTabs.length - 1) % sourceTabs.length : event.key === "Home" ? 0 : event.key === "End" ? sourceTabs.length - 1 : -1;
      if (next < 0) return;
      event.preventDefault();
      setTab(sourceTabs[next].id);
      event.currentTarget.querySelectorAll("button")[next]?.focus();
    }}>
      {sourceTabs.map(item => <button key={item.id} type="button" role="tab" aria-selected={tab === item.id}
        tabIndex={tab === item.id ? 0 : -1} id={`${panelId}-${item.id}`} aria-controls={`${panelId}-panel`} onClick={() => setTab(item.id)}>{item.label}</button>)}
    </div>
    <div className="stl4-citation-source-toolbar">
      <button type="button" aria-label="上一页原文" disabled={page <= 1} onClick={() => jumpToPage(page - 1)}><ChevronLeft size={14} /></button>
      <form onSubmit={event => { event.preventDefault(); jumpToPage(Number(pageInput ?? page)); }}>
        <input aria-label="原文 PDF 页码" type="number" inputMode="numeric" min={1} max={totalPages || undefined}
          value={pageInput ?? page} onChange={event => setPageInput(event.target.value)} onBlur={() => jumpToPage(Number(pageInput ?? page))} />
        <span>/ {totalPages || "—"}</span>
      </form>
      <button type="button" aria-label="下一页原文" disabled={!totalPages || page >= totalPages} onClick={() => jumpToPage(page + 1)}><ChevronRight size={14} /></button>
      <span className="stl4-citation-source-divider" />
      <button type="button" aria-label="缩小原文" disabled={zoom <= 60} onClick={() => setZoom(value => Math.max(60, value - 20))}><Minus size={14} /></button>
      <select aria-label="原文缩放" value={zoom} onChange={event => setZoom(Number(event.target.value))}>
        {[60, 80, 100, 120, 140, 160, 180].map(value => <option key={value} value={value}>{value}%</option>)}
      </select>
      <button type="button" aria-label="放大原文" disabled={zoom >= 180} onClick={() => setZoom(value => Math.min(180, value + 20))}><Plus size={14} /></button>
      <a href={href} target="_blank" rel="noopener noreferrer" aria-label="在新窗口打开原文"><ExternalLink size={14} /></a>
    </div>
    <div id={`${panelId}-panel`} role="tabpanel" aria-labelledby={`${panelId}-${tab}`} className="stl4-citation-source-panel">
      {failure ? <div className="stl4-citation-source-notice" role="alert"><strong>暂时无法核对原文</strong><p>{failure}</p><button type="button" onClick={retry}>重新读取</button></div> :
        !access || !payload ? <LoadingState className="stl4-citation-source-notice" role="status">正在读取并核对原文版本……</LoadingState> : <>
          {tab === "original" && overlay ? <div className="stl4-citation-source-canvas">
            <PdfCanvas key={`${access.served_asset_id}:${access.sha256}`} url={access.url} page={page} zoom={zoom}
              sourceWidth={overlay.sourceWidth} sourceHeight={overlay.sourceHeight} canonicalBlocks={overlay.canonicalBlocks}
              highlights={overlay.highlights} onDocumentLoad={onDocumentLoad} />
          </div> : null}
          {tab === "context" ? <div className="stl4-citation-source-context">
            {[...neighbors, page].sort((a, b) => a - b).map(index => {
              const row = index === page ? payload : pagePayloads[index];
              const error = pageErrors[index];
              return <section key={index} aria-label={`原文第${index}页上下文`}>
                <h4>PDF 第 {index} 页{row?.printed_label ? ` · 书内页码 ${row.printed_label}` : ""}{index === page ? " · 当前页" : ""}</h4>
                {row?.chapter_title ? <p className="stl4-citation-source-caption">{row.chapter_title}</p> : null}
                {error ? <p role="alert">{error} <button type="button" onClick={() => retryPagePayload(index)}>重试</button></p> :
                  row ? <p className="stl4-citation-source-prose">{row.text || "这一页尚无可提取的文字，请查看 PDF 原文。"}</p> : <LoadingState role="status">正在读取这一页的上下文……</LoadingState>}
              </section>;
            })}
          </div> : null}
          {tab === "page" ? <dl className="stl4-citation-source-facts">
            <dt>文件页码</dt><dd>第 {page} 页{totalPages ? ` / 共 ${totalPages} 页` : ""}</dd>
            <dt>书内页码</dt><dd>{payload.printed_label || "尚未确认"}</dd>
            <dt>所属章节</dt><dd>{payload.chapter_title || "尚未确认"}</dd>
            <dt>页面文字</dt><dd>{payload.text_source === "none" ? "暂无可提取文字" : payload.text_source === "ocr" ? "文字识别结果" : payload.text_source === "hybrid" ? "文件文字与识别结果" : "文件文字"}</dd>
            <dt>引文定位</dt><dd>{page === initialPage && overlay?.highlights.length ? "已定位到原文区域" : page === initialPage ? "已定位到页，暂无已核对的区域坐标" : "正在查看相邻原文"}</dd>
          </dl> : null}
          {tab === "book" ? <div className="stl4-citation-source-book"><h4>{reference.title || "书目题名尚未确认"}</h4>
            <p>{reference.authors?.join("、") || "作者信息尚未确认"}</p>
            {reference.citation ? <blockquote>{reference.citation}</blockquote> : <p>这条原文尚无完整书目引文。</p>}
          </div> : null}
        </>}
    </div>
    <footer><span>{reference.title || "原文材料"}{payload?.printed_label ? ` · 书内页码 ${payload.printed_label}` : ""}</span>
      {page !== initialPage ? <button type="button" onClick={() => jumpToPage(initialPage)}>回到引文页</button> : null}</footer>
  </div>;
}

export function CitationSourcePreview({ reference }: { reference: ResolvedEvidence | null }) {
  if (!reference) return <div className="stl4-citation-source-notice">选择一条候选材料后查看原文与上下文。</div>;
  const anchor = reference.anchors?.[0] || reference;
  const valid = reference.source_status === "available" && anchor.source_status === "available" && anchor.asset_id && anchor.document_revision_id &&
    Number.isInteger(anchor.pdf_page) && (anchor.pdf_page || 0) > 0;
  if (!valid) return <SourceText reference={reference} />;
  return <SourceDocument key={`${researchEvidenceKey(reference)}:${anchor.asset_id}:${anchor.document_revision_id}:${anchor.pdf_page}`}
    reference={reference} assetId={anchor.asset_id!} revisionId={anchor.document_revision_id!} initialPage={anchor.pdf_page!} />;
}
