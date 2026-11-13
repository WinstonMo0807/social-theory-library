"use client";

import { LoadingState } from "@/components/ui/loading-state";

import { useEffect, useEffectEvent, useRef, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, ExternalLink, RefreshCw, Search, X } from "lucide-react";
import type { ParallelSegment, ParallelSegments, ParallelVersion } from "@/lib/api/parallel-reader.client";
import { parallelFocusMatches } from "@/lib/api/parallel-navigation";
import { sameParallelSegment } from "@/lib/api/parallel-reader.client";
import type { ResolvedEvidence } from "@/lib/api/research.client";
import { useParallelResource } from "./use-parallel-resource";
import { useReaderSearch } from "./use-reader-search";
import { normalizePublicResourceUrl } from "@/lib/api";

const ignorePagePrefetch = () => {};

export function ParallelColumn({ side, version, page, segmentId, selectedReference, focusId, onPage, onSelect, onReady, onScrollSegment, versionControl }: {
  side: "left" | "right"; version: ParallelVersion | undefined; page: number; segmentId: string;
  selectedReference?: ResolvedEvidence;
  focusId?: string;
  onPage: (page: number) => void; onSelect: (segment: ParallelSegment) => void;
  onReady: (ready: boolean) => void;
  onScrollSegment?: (segment: ParallelSegment) => void;
  versionControl?: ReactNode;
}) {
  const [typedPage, setTypedPage] = useState({ page, value: String(page) });
  const pageInput = typedPage.page === page ? typedPage.value : String(page);
  const [fontSize, setFontSize] = useState(17);
  const [searchOpen, setSearchOpen] = useState(false);
  const search = useReaderSearch({
    assetId: version?.asset_id || "", documentRevisionId: version?.document_revision_id || "",
    initialQuery: "", initialPassage: "", initialEvidence: "",
    requestPagePayload: ignorePagePrefetch, jumpToPage: onPage,
  });
  const identity = `${version?.asset_id}:${version?.document_revision_id}:${page}`;
  const windowKey = `${identity}:${focusId || ""}`;
  const [requestedWindow, setRequestedWindow] = useState<{ key: string; offset: number } | null>(null);
  const requestedOffset = requestedWindow?.key === windowKey ? requestedWindow.offset : null;
  const path = version?.asset_id
    ? `/catalog/parallel/segments/?${new URLSearchParams({ asset_id: version.asset_id, ...(version.document_revision_id ? { document_revision_id: version.document_revision_id } : {}), page: String(page), offset: String(requestedOffset ?? 0), ...(focusId && requestedOffset === null ? { focus: focusId } : {}) })}` : "";
  const resource = useParallelResource<ParallelSegments>(path);
  const panel = useRef<HTMLDivElement>(null);
  const select = useEffectEvent(onSelect);
  const reportReady = useEffectEvent(onReady);
  const ready = Boolean(resource.data?.document_revision_id && resource.data.document_revision_id === version?.document_revision_id && resource.data.segments.length);
  useEffect(() => { reportReady(ready); }, [ready]);
  const actualOffset = resource.data?.offset ?? requestedOffset ?? 0;
  const activeSegment = resource.data?.segments.find(row => row.id === segmentId || sameParallelSegment(row.reference, selectedReference));
  const focusedSegment = resource.data?.segments.find(row => parallelFocusMatches(row, focusId || ""));
  const activeId = activeSegment?.id;
  useEffect(() => {
    if (!resource.data?.segments.length || activeSegment || focusId && !focusedSegment) return;
    select(focusedSegment || resource.data.segments[0]);
  }, [resource.data, activeSegment, focusedSegment, focusId]);
  useEffect(() => {
    if (!activeId || !panel.current) return;
    const row = Array.from(panel.current.querySelectorAll<HTMLElement>("[data-segment]"))
      .find(node => node.dataset.segment === activeId);
    if (row) panel.current.scrollTo({ top: row.offsetTop - panel.current.offsetTop - 14,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [activeId]);

  function go(target: number) {
    if (Number.isInteger(target) && target >= 1 && target <= (version?.total_pages || resource.data?.total_pages || 1)) onPage(target);
  }
  return <section className="parallel-column" aria-label={`${side === "left" ? "左" : "右"}侧正文`}>
    {versionControl ? <header className="parallel-manual-version">{version?.cover_url ? <img src={normalizePublicResourceUrl(version.cover_url)} alt={`${version.title}封面`} width={58} height={82} /> : null}<div><strong>{side === "left" ? "左侧版本" : "右侧版本"}：{version?.language || "尚未选择"}</strong><p>{version?.version_label || version?.title}</p></div><details data-disclosure="collection"><summary>更换版本</summary>{versionControl}</details></header> : null}
    <div className="parallel-column-heading"><strong>{side === "left" ? "左侧" : "右侧"} · {version?.language || "语言待补"}</strong><span>{version?.version_label || "出版版本"}</span></div>
    <div className="parallel-page-controls">
      <button type="button" aria-label={`${side === "left" ? "左" : "右"}侧上一页`} disabled={!version?.asset_id || page <= 1} onClick={() => go(page - 1)}><ChevronLeft size={16} /></button>
      <form onSubmit={event => { event.preventDefault(); go(Number(pageInput)); }}><label><span className="sr-only">{side === "left" ? "左" : "右"}侧PDF页码</span><input inputMode="numeric" value={pageInput} onChange={event => setTypedPage({ page, value: event.target.value })} disabled={!version?.asset_id} /></label><span> / {version?.total_pages || "—"} 页</span><button type="submit" disabled={!version?.asset_id}>前往</button></form>
      <button type="button" aria-label={`${side === "left" ? "左" : "右"}侧下一页`} disabled={!version?.asset_id || page >= (version.total_pages || 1)} onClick={() => go(page + 1)}><ChevronRight size={16} /></button>
      <label className="parallel-text-size"><span className="sr-only">正文大小</span><select data-stl-select value={fontSize} onChange={event => setFontSize(Number(event.target.value))}><option value={15}>小</option><option value={17}>标准</option><option value={20}>大</option><option value={23}>更大</option></select></label>
      <button type="button" disabled={!version?.document_revision_id} aria-expanded={searchOpen} aria-label={`在${side === "left" ? "左" : "右"}侧版本中搜索`} onClick={() => setSearchOpen(value => !value)}><Search size={14} /></button>
      {version?.asset_id ? <a href={`/reader/${encodeURIComponent(version.asset_id)}?${new URLSearchParams({ page: String(page), ...(version.document_revision_id ? { revision: version.document_revision_id } : {}) })}`} target="_blank" rel="noreferrer" aria-label={`在新标签页打开${side === "left" ? "左" : "右"}侧PDF原文`}><ExternalLink size={15} /></a> : null}
    </div>
    {searchOpen ? <div className="parallel-column-search"><form onSubmit={event => { event.preventDefault(); search.jumpToFirstSearchMatch(); }}><label><span className="sr-only">书内关键词</span><input autoFocus value={search.query} onChange={event => search.setQuery(event.target.value)} placeholder="在此版本中搜索" maxLength={200} /></label><button type="submit" disabled={!search.searchMatches.length}>定位</button><button type="button" aria-label="关闭版本搜索" onClick={() => { search.setQuery(""); setSearchOpen(false); }}><X size={15} /></button></form>{search.searchLoading ? <LoadingState variant="compact" role="status">正在查找…</LoadingState> : search.searchError ? <p role="alert">{search.searchError}<button type="button" onClick={search.retrySearch}>重试</button></p> : search.query.trim() ? <><p>{search.searchMatches.length ? `当前返回 ${search.searchMatches.length} 个匹配页（最多 100 页）` : "没有找到匹配页。"}</p><ul>{search.searchMatches.map((match, index) => <li key={match.page_id}><button type="button" onClick={() => search.jumpToSearchMatch(index)}><strong>PDF 第 {match.page_index} 页</strong><span>{match.snippet}</span></button></li>)}</ul></> : null}</div> : null}
    {resource.data?.segments.length ? <label className="parallel-segment-select"><span className="sr-only">当前页段落定位</span><select data-stl-select value={activeSegment?.id || ""} onChange={event => { const row = resource.data?.segments.find(item => item.id === event.target.value); if (row) onSelect(row); }}><option value="">选择当前页段落</option>{resource.data.segments.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label> : null}
    <div className="parallel-text-pane" ref={panel} style={{ fontSize }} onScroll={() => {
      const el = panel.current;
      if (!el || !onScrollSegment || !resource.data) return;
      const top = el.getBoundingClientRect().top;
      const nodes = Array.from(el.querySelectorAll<HTMLElement>("[data-segment]"));
      const node = nodes.find(row => row.getBoundingClientRect().bottom > top + 50);
      const match = resource.data.segments.find(row => row.id === node?.dataset.segment);
      if (match) onScrollSegment(match);
    }}>
      {!version ? <p className="parallel-empty">选择一个版本开始比较。</p> : !version.asset_id ? <div className="parallel-empty"><strong>这个版本暂未提供可用正文</strong><p>{version.notice || "可以先使用其他已收录版本，或提交版本建议。"}</p><a href="/feedback?category=content">提交版本建议</a></div>
        : resource.loading ? <div role="status" className="parallel-empty"><LoadingState variant="page">正在读取 PDF 第 {page} 页…</LoadingState><button type="button" onClick={resource.stop}>停止读取</button></div>
          : resource.error || resource.stopped ? <div role="alert" className="parallel-empty"><p>{resource.error || "已停止读取，原文位置保留。"}</p><button type="button" onClick={resource.reload}><RefreshCw size={14} />重新读取</button></div>
            : resource.data ? <>
              {focusId && !focusedSegment && !activeSegment ? <p className="parallel-source-notice" role="status">原定位没有对应到当前返回的段落。请核对本页并明确选择，不会自动改用第一段。</p> : null}
              {resource.data.notice ? <p className="parallel-source-notice">{resource.data.notice}</p> : null}
              {!resource.data.segments.length ? <div className="parallel-empty"><strong>{resource.data.state === "text_unavailable" ? "此页尚无可用文字" : "此页没有可选正文"}</strong><p>可以打开原 PDF 阅读，或定位到其他页面。</p></div> : resource.data.segments.map(segment => <button type="button" key={segment.id} data-segment={segment.id} className={`parallel-segment ${activeSegment?.id === segment.id ? "is-selected" : ""}`} aria-pressed={activeSegment?.id === segment.id} onClick={() => onSelect(segment)}>
                <span className="parallel-segment-number">{segment.label}</span><span lang={version.language || undefined}>{segment.text}{segment.text_truncated ? <small className="parallel-source-notice">此处显示部分正文，完整段落请打开原 PDF。</small> : null}</span>
              </button>)}
              {actualOffset > 0 || resource.data.has_more ? <div className="parallel-segment-pages"><button type="button" disabled={actualOffset === 0} onClick={() => setRequestedWindow({ key: windowKey, offset: Math.max(0, actualOffset - 20) })}>上一组正文</button><button type="button" disabled={!resource.data.has_more || resource.data.next_offset === null} onClick={() => setRequestedWindow({ key: windowKey, offset: resource.data?.next_offset ?? 0 })}>更多正文</button></div> : null}
            </> : null}
    </div>
  </section>;
}
