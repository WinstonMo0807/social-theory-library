"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bookmark,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  Copy,
  Download,
  Highlighter,
  List,
  Minus,
  Moon,
  PanelLeftClose,
  PanelRightClose,
  Plus,
  Search,
  StickyNote,
  Sun,
  Trash2,
  Underline,
  X,
} from "lucide-react";
import {
  useCallback,
  useState,
  useSyncExternalStore,
} from "react";
import type { Work } from "@/lib/data";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ActionButton, type ActionState } from "./action-feedback";
import { PdfContinuousViewer } from "./pdf-continuous-viewer";
import { BookCover } from "./ui";
import { UsageTracker } from "./usage-tracker";
import { AskLibraryLink } from "./ask-library-link";
import type { CitationStyle, SidebarTab } from "./reader/types";
import { useReaderNavigation } from "./reader/use-reader-navigation";
import { useReaderSelection } from "./reader/use-reader-selection";
import { useReaderRecords } from "./reader/use-reader-records";
import { useReaderDocument, useReaderPageRequest } from "./reader/use-reader-document";
import { useReaderSearch } from "./reader/use-reader-search";
import { useReaderCitation } from "./reader/use-reader-citation";
import { useReaderProgress } from "./reader/use-reader-progress";
import { formatReaderTimestamp, useReaderPageOverlays } from "./reader/use-reader-page-overlays";

function useMediaQuery(query: string) {
  const subscribe = useCallback((notify: () => void) => {
    const media = window.matchMedia(query);
    media.addEventListener("change", notify);
    return () => media.removeEventListener("change", notify);
  }, [query]);
  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}

export function ReaderShell({
  work,
  initialPage,
  initialQuery,
  initialFocus,
  initialPassage,
  initialEvidence,
  outline = [],
  relatedScholars = [],
  relatedTheories = [],
  relatedTopics = [],
}: {
  work: Work;
  initialPage: number;
  initialQuery: string;
  initialFocus: string;
  initialPassage: string;
  initialEvidence: string;
  outline?: { index: number; printed_label: string; chapter_title: string }[];
  relatedScholars?: { name: string; slug: string; years: string }[];
  relatedTheories?: { name: string; slug: string }[];
  relatedTopics?: { name: string; slug: string }[];
}) {
  const { state: readerSession } = useSessionBootstrap();
  const readerAuthenticated = readerSession.status === "authenticated";
  const [dark, setDark] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [mobileLeftOpen, setMobileLeftOpen] = useState(false);
  const [compactRightOpen, setCompactRightOpen] = useState(false);
  const isMobile = useMediaQuery("(max-width: 760px)");
  const isCompact = useMediaQuery("(max-width: 1050px)");
  const effectiveLeftOpen = isMobile ? mobileLeftOpen : leftOpen;
  const effectiveRightOpen = isCompact ? compactRightOpen : rightOpen;
  const { access, accessError, pagePayloads, requestPagePayload, trackDownload } = useReaderDocument({
    assetId: work.id, workId: work.workId,
  });
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("outline");
  const [gate, setGate] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const [copyStatusState, setCopyStatusState] = useState<ActionState>("idle");
  const {
    page, setPage, zoom, totalPages, progress, thumbnailPages, scrollRequest,
    jumpToPage, changeZoom, onDocumentLoad, onVisiblePageChange,
  } = useReaderNavigation({
    initialPage, initialPageCount: work.pages, accessPageCount: access?.page_count,
  });
  const currentPagePayload = pagePayloads[page] ?? null;
  const setLeftPanel = useCallback((open: boolean) => {
    if (isMobile) setMobileLeftOpen(open);
    else setLeftOpen(open);
  }, [isMobile]);

  const {
    readerDocumentRef, selectionTools, setSelectionTools, captureSelection,
    showSelectionTools, showSelectionContextMenu, handleDocumentCopy, cleanCopy,
  } = useReaderSelection({
    page, pagePayloads, requestPagePayload, setCopyStatus, setCopyStatusState,
  });
  const {
    annotations, bookmarks, annotationDraft, setAnnotationDraft, focusedAnnotationId,
    setFocusedAnnotationId, bookmarkedPage, pendingAction, beginAnnotation,
    saveAnnotation, deleteAnnotation, deleteBookmark, toggleBookmark, protectedAction, showSidebarTab,
  } = useReaderRecords({
    assetId: work.id, initialFocus, readerAuthenticated, page, pagePayloads, captureSelection,
    setSelectionTools, setPage, jumpToPage, setLeftPanel, setSidebarTab, setGate,
    setCopyStatus, setCopyStatusState,
  });

  useReaderPageRequest({ page, ocrStatus: access?.ocr_status, requestPagePayload });

  const {
    query, setQuery, searchMatches, setSearchMatches, activeSearchMatch,
    searchCandidatesOpen, setSearchCandidatesOpen, passageFocus,
    jumpToFirstSearchMatch, jumpToSearchMatch,
  } = useReaderSearch({
    assetId: work.id, initialQuery, initialPassage, initialEvidence, requestPagePayload, jumpToPage,
  });

  const { citationStyle, setCitationStyle, citations, copyCitation } = useReaderCitation({
    editionId: work.editionId ?? access?.edition_id, page, setCopyStatus, setCopyStatusState,
  });

  useReaderProgress({ assetId: work.id, page, totalPages, readerAuthenticated });

  const pageOverlays = useReaderPageOverlays({
    annotations, focusedAnnotationId, pagePayloads, passageFocus, query, searchMatches,
  });
  const readerOutline = outline.map((item) => [item.chapter_title, item.index] as const);
  const currentOutline = [...outline]
    .reverse()
    .find((item) => item.index <= page);
  function setRightPanel(open: boolean) {
    if (isCompact) setCompactRightOpen(open);
    else setRightOpen(open);
  }

  return (
    <div className={`reader ${dark ? "dark" : ""} ${effectiveLeftOpen ? "" : "left-closed"} ${effectiveRightOpen ? "" : "right-closed"}`}>
      <UsageTracker eventType="reader_open" assetId={work.id} workId={work.workId} source="reader" />
      <header className="reader-toolbar">
        <Link className="reader-logo" href="/" aria-label="返回书库"><span>SOCIAL</span><span>THEORY</span><span>LIBRARY</span></Link>
        <div className="toolbar-group page-control">
          <span>PDF 页</span>
          <button type="button" aria-label="上一页" onClick={() => jumpToPage(page - 1)}><ChevronLeft size={17} /></button>
          <input
            aria-label="页码"
            name="reader-page"
            inputMode="numeric"
            autoComplete="off"
            value={page}
            onChange={(event) => setPage(Math.min(totalPages, Math.max(1, Number(event.target.value) || 1)))}
            onBlur={() => jumpToPage(page)}
            onKeyDown={(event) => {
              if (event.key === "Enter") jumpToPage(page);
            }}
          />
          <span>/ {totalPages}</span>
          {currentPagePayload?.printed_label && currentPagePayload.printed_label !== String(page) ? <b className="reader-printed-page">书页 {currentPagePayload.printed_label}</b> : null}
          <button type="button" aria-label="下一页" onClick={() => jumpToPage(page + 1)}><ChevronRight size={17} /></button>
        </div>
        <div className="toolbar-group zoom-control">
          <span>缩放</span>
          <button type="button" aria-label="缩小" onClick={() => changeZoom(-10)}><Minus size={16} /></button>
          <b>{zoom}%</b>
          <button type="button" aria-label="放大" onClick={() => changeZoom(10)}><Plus size={16} /></button>
        </div>
        <div className={`reader-search ${searchCandidatesOpen ? "open" : ""}`}>
          <span>文档内搜索</span>
          <div className="reader-search-field">
            <Search size={16} />
            <input
              value={query}
              name="reader-document-search"
              autoComplete="off"
              onChange={(event) => {
                const value = event.target.value;
                setQuery(value);
                setSearchMatches([]);
                setSearchCandidatesOpen(Boolean(value.trim()));
              }}
              onFocus={() => setSearchCandidatesOpen(searchMatches.length > 0)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  jumpToFirstSearchMatch();
                }
              }}
              placeholder="搜索文档……"
            />
            {query ? (
              <button
                className="reader-search-count"
                type="button"
                aria-label="展开搜索候选"
                onClick={() => setSearchCandidatesOpen((value) => !value)}
              >
                {searchMatches.length} <ChevronsUpDown size={13} />
              </button>
            ) : null}
          </div>
          {query && searchCandidatesOpen ? (
            <div className="reader-search-candidates" role="listbox" aria-label="文档内搜索候选">
              <header><strong>{searchMatches.length} 个页码候选</strong><span>按 PDF 页序排列</span></header>
              {searchMatches.map((match, index) => (
                <button
                  className={activeSearchMatch === index ? "active" : ""}
                  type="button"
                  role="option"
                  aria-selected={activeSearchMatch === index}
                  key={match.page_id}
                  onClick={() => jumpToSearchMatch(index)}
                >
                  <span>{String(match.rank).padStart(2, "0")}</span>
                  <div>
                    <strong>PDF 第 {match.page_index} 页{match.printed_label && match.printed_label !== String(match.page_index) ? ` · 书页 ${match.printed_label}` : ""}</strong>
                    <small>{match.snippet}</small>
                  </div>
                  <em>{match.occurrence_count} 处</em>
                </button>
              ))}
              {!searchMatches.length ? <p>没有找到匹配内容。</p> : null}
            </div>
          ) : null}
        </div>
        <div className="theme-control">
          <span>主题</span>
          <button className={!dark ? "active" : ""} type="button" aria-label="使用浅色主题" onClick={() => setDark(false)}><Sun size={17} /></button>
          <button className={dark ? "active" : ""} type="button" aria-label="使用深色主题" onClick={() => setDark(true)}><Moon size={17} /></button>
        </div>
        <div className="reader-actions">
          <AskLibraryLink
            context="works"
            ids={[work.workId]}
            assetId={work.id}
            label="问这本书"
            className="reader-ask-library"
          />
          {access ? <a href={access.download_url || access.url} download={access.download_filename} title={access.download_rendition === "ocr_pdf" ? "下载可搜索 OCR 版" : "下载原始 PDF"} onClick={trackDownload}><Download size={18} /><span>{access.download_rendition === "ocr_pdf" ? "下载 OCR 版" : "下载"}</span></a> : <button type="button" disabled><Download size={18} /><span>下载</span></button>}
          <button type="button" onClick={() => protectedAction("批注")}><Highlighter size={18} /><span>批注</span></button>
          <ActionButton className={bookmarkedPage ? "active" : ""} type="button" state={pendingAction?.startsWith("toggle-bookmark:") ? "pending" : "idle"} pendingLabel="处理中" disabled={Boolean(pendingAction) && !pendingAction?.startsWith("toggle-bookmark:")} pressed={bookmarkedPage} onClick={() => protectedAction("书签")}><Bookmark size={18} fill={bookmarkedPage ? "currentColor" : "none"} /><span>书签</span></ActionButton>
        </div>
        <div className="reader-progress-top"><span>阅读进度</span><div><i style={{ width: `${progress}%` }} /></div><b>{progress}%</b></div>
      </header>

      <aside className="reader-left">
        <button className="panel-close" type="button" aria-label="关闭目录侧栏" onClick={() => setLeftPanel(false)}><X size={18} /></button>
        <div className="current-book">
          <BookCover work={work} size="small" />
          <div><strong>{work.title}</strong><span>{work.originalTitle}</span><p>{work.author}</p><small>{work.year} · 本馆版本</small></div>
        </div>
        <nav className="reader-tabs">
          <button className={sidebarTab === "outline" ? "active" : ""} type="button" onClick={() => showSidebarTab("outline")}><List size={16} /> 目录</button>
          <button className={sidebarTab === "thumbnails" ? "active" : ""} type="button" onClick={() => showSidebarTab("thumbnails")}><BookOpen size={16} /> 缩略图</button>
          <button className={sidebarTab === "highlights" ? "active" : ""} type="button" onClick={() => showSidebarTab("highlights", "高亮")}><Highlighter size={16} /> 高亮 <b>{annotations.filter((item) => item.kind !== "note").length}</b></button>
          <button className={sidebarTab === "bookmarks" ? "active" : ""} type="button" onClick={() => showSidebarTab("bookmarks", "书签")}><Bookmark size={16} /> 书签 <b>{bookmarks.length}</b></button>
          <button className={sidebarTab === "notes" ? "active" : ""} type="button" onClick={() => showSidebarTab("notes", "笔记")}><StickyNote size={16} /> 笔记 <b>{annotations.filter((item) => item.kind === "note").length}</b></button>
        </nav>
        {sidebarTab === "outline" ? (
          <>
            <label className="outline-search"><Search size={14} /><input aria-label="搜索目录" name="reader-outline-search" autoComplete="off" placeholder="搜索目录……" /></label>
            <div className="outline-list">
              {readerOutline.map(([label, target]) => (
                <button className={Number(target) <= page && page < Number(target) + 20 ? "active" : ""} type="button" key={label} onClick={() => jumpToPage(Number(target))}>
                  <span>{label}</span><small>{target}</small>
                </button>
              ))}
              {!readerOutline.length ? <p className="reader-empty-list">该 PDF 没有可识别的目录书签。</p> : null}
            </div>
          </>
        ) : null}
        {sidebarTab === "thumbnails" ? (
          <div className="reader-thumbnail-grid" aria-label="PDF 页码缩略导航">
            {totalPages > thumbnailPages.length ? (
              <p>显示第 {thumbnailPages[0]}—{thumbnailPages[thumbnailPages.length - 1]} 页，共 {totalPages} 页</p>
            ) : null}
            {thumbnailPages.map((target) => (
              <button className={target === page ? "active" : ""} type="button" key={target} onClick={() => jumpToPage(target)}>
                <span>{target}</span>
              </button>
            ))}
          </div>
        ) : null}
        {sidebarTab === "highlights" ? (
          <div className="reader-library-list">
            {annotations.filter((item) => item.kind !== "note").map((annotation) => (
              <article className={`reader-library-entry ${focusedAnnotationId === annotation.id ? "active" : ""}`} key={annotation.id}>
                <button className="reader-library-open" type="button" onClick={() => { jumpToPage(annotation.selector.page_index || 1); setFocusedAnnotationId(annotation.id); }}>
                  <small>第 {annotation.selector.page_index || 1} 页 · {annotation.kind === "underline" ? "划线" : "高亮"}</small>
                  <span>{annotation.quote || "页面批注"}</span>
                </button>
                <ActionButton className="reader-library-delete" type="button" state={pendingAction === `delete-annotation:${annotation.id}` ? "pending" : "idle"} disabled={Boolean(pendingAction) && pendingAction !== `delete-annotation:${annotation.id}`} aria-label={`删除第 ${annotation.selector.page_index || 1} 页${annotation.kind === "underline" ? "划线" : "高亮"}`} onClick={() => void deleteAnnotation(annotation.id)}><Trash2 size={14} /></ActionButton>
              </article>
            ))}
            {!annotations.some((item) => item.kind !== "note") ? <p className="reader-empty-list">还没有保存高亮或划线。</p> : null}
          </div>
        ) : null}
        {sidebarTab === "bookmarks" ? (
          <div className="reader-library-list">
            {bookmarks.map((bookmark) => (
              <article className="reader-library-entry" key={bookmark.id}>
                <button className="reader-library-open" type="button" onClick={() => jumpToPage(bookmark.page_index || 1)}>
                  <small>第 {bookmark.page_index || 1} 页</small>
                  <span>{bookmark.label}</span>
                </button>
                <ActionButton className="reader-library-delete" type="button" state={pendingAction === `delete-bookmark:${bookmark.id}` ? "pending" : "idle"} disabled={Boolean(pendingAction) && pendingAction !== `delete-bookmark:${bookmark.id}`} aria-label={`删除第 ${bookmark.page_index || 1} 页书签`} onClick={() => void deleteBookmark(bookmark.id)}><Trash2 size={14} /></ActionButton>
              </article>
            ))}
            {!bookmarks.length ? <p className="reader-empty-list">还没有保存书签。</p> : null}
          </div>
        ) : null}
        {sidebarTab === "notes" ? (
          <div className="reader-library-list">
            {annotations.filter((item) => item.kind === "note").map((annotation) => (
              <article className={`reader-library-entry ${focusedAnnotationId === annotation.id ? "active" : ""}`} key={annotation.id}>
                <button className="reader-library-open" type="button" onClick={() => { jumpToPage(annotation.selector.page_index || 1); setFocusedAnnotationId(annotation.id); }}>
                  <small>第 {annotation.selector.page_index || 1} 页 · {formatReaderTimestamp(annotation.created_at)}</small>
                  <span>{annotation.body_text || annotation.quote || "页面笔记"}</span>
                </button>
                <ActionButton className="reader-library-delete" type="button" state={pendingAction === `delete-annotation:${annotation.id}` ? "pending" : "idle"} disabled={Boolean(pendingAction) && pendingAction !== `delete-annotation:${annotation.id}`} aria-label={`删除第 ${annotation.selector.page_index || 1} 页笔记`} onClick={() => void deleteAnnotation(annotation.id)}><Trash2 size={14} /></ActionButton>
              </article>
            ))}
            {!annotations.some((item) => item.kind === "note") ? <p className="reader-empty-list">还没有保存笔记。</p> : null}
          </div>
        ) : null}
      </aside>
      {!effectiveLeftOpen ? <button className="open-panel left" type="button" aria-label="打开目录侧栏" onClick={() => setLeftPanel(true)}><PanelLeftClose size={18} /></button> : null}

      <section
        className="reader-document continuous-scroll-mode"
        data-view-mode="continuous"
        ref={readerDocumentRef}
        onMouseUp={showSelectionTools}
        onContextMenu={showSelectionContextMenu}
        onCopy={handleDocumentCopy}
      >
        {access && access.ocr_status !== "not_required" ? (
          <div className={`reader-processing-status status-${access.ocr_status}`} role="status">
            <strong>{access.ocr_status === "succeeded" ? "OCR 文字层已就绪" : access.ocr_status === "failed" ? "OCR 暂不可用" : access.ocr_status === "disabled" ? "OCR 已停用" : "OCR 正在处理"}</strong>
            <span>{access.ocr_status === "succeeded" ? "页面仍由原始 PDF 渲染，复制与检索使用 OCR 文字层。" : "原始 PDF 可继续阅读；文字复制会在 OCR 成功后自动恢复。"}</span>
            {access.ocr_status === "succeeded" && access.download_rendition === "ocr_pdf" && access.original_download_url ? <a href={access.original_download_url} download={access.download_filename}>需要时下载原始扫描版</a> : null}
          </div>
        ) : null}
        {access?.reader_fallback_reason ? <div className="reader-processing-status status-failed" role="status"><strong>已安全回退</strong><span>{access.reader_fallback_reason}</span></div> : null}
        {access ? (
          <PdfContinuousViewer
            url={access.url}
            pageCount={totalPages}
            currentPage={page}
            zoom={zoom}
            overlays={pageOverlays}
            preferOcrTextLayer={access.ocr_text_available}
            scrollRequest={scrollRequest}
            onDocumentLoad={onDocumentLoad}
            onPageChange={onVisiblePageChange}
            onRequestPage={requestPagePayload}
            onNoteSelect={(annotationId) => {
              setFocusedAnnotationId(annotationId);
              setSidebarTab("notes");
              setLeftPanel(true);
            }}
            onNoteDelete={(annotationId) => void deleteAnnotation(annotationId)}
          />
        ) : (
          <div className="reader-unavailable" role="status">
            <BookOpen size={30} />
            <strong>公开阅读副本尚未就绪</strong>
            <p>{accessError || "正在请求 PDF 的签名阅读地址……"}</p>
            <Link href={`/works/${work.slug}`}>返回文献详情</Link>
          </div>
        )}
        <span className={`reader-copy-status ${copyStatusState}`} role={copyStatusState === "error" ? "alert" : "status"} aria-live={copyStatusState === "error" ? "assertive" : "polite"} aria-busy={copyStatusState === "pending"}>{copyStatus}</span>
      </section>

      {selectionTools ? (
        <div
          className="reader-selection-menu"
          role="toolbar"
          aria-label="所选文字操作"
          style={{ left: selectionTools.x, top: selectionTools.y }}
          onMouseDown={(event) => event.preventDefault()}
        >
          <button type="button" onClick={() => void cleanCopy(selectionTools.quote)}><Copy size={15} />复制</button>
          <button type="button" onClick={() => beginAnnotation("highlight", selectionTools)}><Highlighter size={15} />高亮</button>
          <button type="button" onClick={() => beginAnnotation("underline", selectionTools)}><Underline size={15} />划线</button>
          <button type="button" onClick={() => beginAnnotation("note", selectionTools)}><StickyNote size={15} />笔记</button>
          <ActionButton type="button" state={pendingAction?.startsWith("toggle-bookmark:") ? "pending" : "idle"} pendingLabel="处理中" disabled={Boolean(pendingAction) && !pendingAction?.startsWith("toggle-bookmark:")} onClick={() => void toggleBookmark(selectionTools)}><Bookmark size={15} />书签</ActionButton>
          <button className="close" type="button" aria-label="关闭所选文字菜单" onClick={() => setSelectionTools(null)}><X size={14} /></button>
        </div>
      ) : null}

      <aside className="reader-right">
        <button className="panel-close" type="button" aria-label="关闭信息侧栏" onClick={() => setRightPanel(false)}><X size={18} /></button>
        <section>
          <h2>当前阅读</h2>
          <strong>{currentOutline?.chapter_title || work.title}</strong>
          <p>{currentPagePayload?.chapter_title || `第 ${currentPagePayload?.printed_label || page} 页`}</p>
          <div className="side-progress"><i style={{ width: `${progress}%` }} /></div>
          <p className="progress-label"><span>{page} / {totalPages} 页</span><b>{progress}%</b></p>
        </section>
        <section>
          <h2>引用此页</h2>
          <select
            value={citationStyle}
            onChange={(event) => setCitationStyle(event.target.value as CitationStyle)}
            aria-label="引用格式"
          >
            <option value="gbt7714-2025">GB/T 7714—2025</option>
            <option value="apa">APA</option>
            <option value="chicago">Chicago</option>
            <option value="mla">MLA</option>
            <option value="harvard">Harvard</option>
          </select>
          <p className="citation-page-map">
            PDF 第 {citations?.page?.pdf_page ?? page} 页
            {citations?.page?.printed_label
              && citations.page.printed_label !== String(citations.page.pdf_page)
              ? ` · 书页 ${citations.page.printed_label}`
              : ""}
          </p>
          <p>{citations?.[citationStyle] || "正在根据馆藏元数据生成本页引用……"}</p>
          <button className="button secondary" type="button" onClick={copyCitation}><Copy size={14} /> 复制引用</button>
        </section>
        <section>
          <h2>相关理论流派</h2>
          <div className="tag-list">
            {relatedTheories.map((item) => <Link href={`/theory-schools/${item.slug}`} key={item.slug}>{item.name}</Link>)}
            {!relatedTheories.length ? <span>尚无已确认关系</span> : null}
          </div>
        </section>
        <section>
          <h2>相关学者</h2>
          {relatedScholars.map((scholar) => <Link href={`/scholars/${scholar.slug}`} key={scholar.slug}><span className="tiny-portrait" /><p><strong>{scholar.name}</strong><small>{scholar.years || "查看学者页面"}</small></p></Link>)}
          {!relatedScholars.length ? <p className="reader-empty-list">尚无已确认学者。</p> : null}
        </section>
        <section>
          <h2>相关主题</h2>
          {relatedTopics.map((topic) => <Link href={`/topics/${topic.slug}`} key={topic.slug}>{topic.name}</Link>)}
          {!relatedTopics.length ? <p className="reader-empty-list">尚无已确认主题。</p> : null}
        </section>
      </aside>
      {!effectiveRightOpen ? <button className="open-panel right" type="button" aria-label="打开信息侧栏" onClick={() => setRightPanel(true)}><PanelRightClose size={18} /></button> : null}

      <footer className="reader-bottom">
        <button type="button" onClick={() => jumpToPage(page - 1)}><ChevronLeft size={16} /> 上一页</button>
        <span>{Math.max(1, page - 1)}</span>
        <div>
          <button type="button" aria-label="打开目录导航" onClick={() => showSidebarTab("outline")}><BookOpen size={16} /></button>
          <button type="button" aria-label="打开阅读信息" onClick={() => setRightPanel(true)}><List size={16} /></button>
          <span className="continuous-mode-indicator"><ChevronsUpDown size={16} />连续阅读</span>
        </div>
        <b>{page}</b>
        <button type="button" onClick={() => jumpToPage(page + 1)}>下一页 <ChevronRight size={16} /></button>
      </footer>

      {annotationDraft ? (
        <div className="annotation-composer" role="dialog" aria-modal="false" aria-labelledby="annotation-title">
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void saveAnnotation();
            }}
          >
            <button className="panel-close" type="button" aria-label="关闭批注窗口" onClick={() => setAnnotationDraft(null)}><X size={18} /></button>
            <p className="eyebrow">第 {annotationDraft.pageIndex} 页</p>
            <h2 id="annotation-title">添加笔记</h2>
            {annotationDraft.quote ? <blockquote>{annotationDraft.quote}</blockquote> : <p>本条笔记将锚定到当前页面。</p>}
            <label>
              <span>笔记内容</span>
              <textarea
                rows={4}
                autoFocus
                value={annotationDraft.body}
                onChange={(event) => setAnnotationDraft((draft) => draft ? {
                  ...draft,
                  body: event.target.value,
                } : null)}
                placeholder="可选。正文会加密保存，仅你本人可以通过读者接口读取。"
              />
            </label>
            <ActionButton className="button" type="submit" state={pendingAction === "save-annotation" ? "pending" : "idle"} pendingLabel="正在保存笔记" disabled={Boolean(pendingAction) && pendingAction !== "save-annotation"}>保存笔记</ActionButton>
          </form>
        </div>
      ) : null}

      {gate ? (
        <div className="login-gate" role="dialog" aria-modal="true" aria-labelledby="login-gate-title">
          <div>
            <button className="panel-close" type="button" aria-label="关闭登录提示" onClick={() => setGate(null)}><X size={18} /></button>
            <p className="eyebrow">保存个人阅读资料</p>
            <h2 id="login-gate-title">登录后使用{gate}</h2>
            <p>在线阅读、下载、全文搜索、复制和引用对访客开放。个人批注、笔记、划线、书签和进度需要登录。</p>
            <Link className="button" href={`/login?next=/reader/${work.id}`}>登录 <ArrowRight size={16} /></Link>
            <Link className="button secondary" href="/register">注册读者</Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
