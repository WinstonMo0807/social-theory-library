"use client";

import { confirmAction, confirmLinkNavigation } from "@/lib/ui-dialog";
import { BrandImage } from "./brand-image";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { SiteConfig } from "@/lib/site-config";
import {
  ArrowRight,
  Bookmark,
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Maximize,
  Minimize,
  MoreHorizontal,
  RotateCw,
  FolderPlus,
  Quote,
  LockKeyhole,
  Copy,
  Download,
  Highlighter,
  List,
  Minus,
  Moon,
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
  useEffect,
  useEffectEvent,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
  type ComponentProps,
} from "react";
import type { ReaderRotation } from "@/lib/reader-coordinates";
import type { Work } from "@/lib/data";
import { filterOutline, outlinePosition, prepareOutline, type OutlineNode } from "@/lib/api/document-outline";
import { safeResearchReturn } from "@/lib/api/research-navigation";
import { authPageHref } from "@/lib/auth-navigation";
import { readerReturnPath } from "@/lib/api/reader-failure";
import { usePublicSession } from "./public-session-provider";
import { useAppearance } from "./appearance-provider";
import { ActionButton, type ActionState } from "./action-feedback";
import { PdfContinuousViewer } from "./pdf-continuous-viewer";
import { SiteHeader } from "./site-header";
import { BookCover } from "./ui";
import { UsageTracker } from "./usage-tracker";
import { AskLibraryLink } from "./ask-library-link";
import { Dialog } from "./ui/dialog";
import { SharedCitationOverlay } from "./shared-citation-overlay";
import type { SharedCitationInput } from "@/lib/api/shared-citation.client";
import type { CitationStyle, SidebarTab, SelectionSnapshot } from "./reader/types";
import { useReaderNavigation } from "./reader/use-reader-navigation";
import { useReaderSelection } from "./reader/use-reader-selection";
import { useReaderRecords } from "./reader/use-reader-records";
import { useReaderDocument, useReaderPageRequest } from "./reader/use-reader-document";
import { useReaderSearch } from "./reader/use-reader-search";
import { useReaderCitation } from "./reader/use-reader-citation";
import { useReaderProgress } from "./reader/use-reader-progress";
import { useReaderResearch } from "./reader/use-reader-research";
import { formatReaderTimestamp, useReaderPageOverlays } from "./reader/use-reader-page-overlays";
import { ReaderOcrStatus } from "./reader/reader-ocr-status";
import { ReaderPageThumbnail } from "./reader/reader-page-thumbnail";
import { ReaderSettings, useReaderPreferences } from "./reader/reader-settings";
import { SaveWorkButton } from "./save-work-button";

function useMediaQuery(query: string) {
  const subscribe = useCallback((notify: () => void) => {
    const media = window.matchMedia(query);
    media.addEventListener("change", notify);
    return () => media.removeEventListener("change", notify);
  }, [query]);
  const getSnapshot = useCallback(() => window.matchMedia(query).matches, [query]);
  return useSyncExternalStore(subscribe, getSnapshot, () => false);
}

export function ReaderShell(props: ComponentProps<typeof ReaderWorkspace>) {
  const { state } = usePublicSession();
  // An explicit account transition invalidates signed files, selections and drafts together.
  return <ReaderWorkspace key={state.status === "authenticated" ? `owner:${state.user?.id}` : "visitor"} {...props} />;
}

function ReaderWorkspace({
  work,
  siteConfig,
  initialPage,
  initialQuery,
  initialFocus,
  initialPassage,
  initialEvidence,
  documentRevisionId = "",
  requestedRevisionId = "",
  researchProjectId = "",
  researchTurnId = "",
  researchReferenceId = "",
  returnTo = "",
  embedded = false,
  outline = [],
  relatedScholars = [],
  relatedTheories = [],
  relatedTopics = [],
}: {
  work: Work;
  siteConfig?: SiteConfig;
  initialPage: number;
  initialQuery: string;
  initialFocus: string;
  initialPassage: string;
  initialEvidence: string;
  documentRevisionId?: string;
  requestedRevisionId?: string;
  researchProjectId?: string;
  researchTurnId?: string;
  researchReferenceId?: string;
  returnTo?: string;
  embedded?: boolean;
  outline?: OutlineNode[];
  relatedScholars?: { name: string; slug: string; years: string; portrait?: string }[];
  relatedTheories?: { name: string; slug: string }[];
  relatedTopics?: { name: string; slug: string }[];
}) {
  const router = useRouter();
  const shellRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [rotation, setRotation] = useState<ReaderRotation>(0);
  const [rightTab, setRightTab] = useState<"source" | "notes" | "citation" | "related">("source");
  const [retainedSelection, setRetainedSelection] = useState<SelectionSnapshot | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [searchOrder, setSearchOrder] = useState("page");
  const { state: readerSession } = usePublicSession();
  const readerAuthenticated = readerSession.status === "authenticated";
  const { dark, update: updateAppearance } = useAppearance();
  const [leftOpen, setLeftOpen] = useState<boolean | null>(null);
  const [rightOpen, setRightOpen] = useState(!embedded);
  const [mobileLeftOpen, setMobileLeftOpen] = useState(false);
  const [compactRightOpen, setCompactRightOpen] = useState(false);
  const [toolbarOpen, setToolbarOpen] = useState(false);
  const {preferences,save:savePreferences}=useReaderPreferences();
  const applyPreferences=(value:typeof preferences)=>{savePreferences(value);setLeftOpen(value.outline);};
  const [ocrOpen, setOcrOpen] = useState(false);
  const [ocrRecoveryLocked, setOcrRecoveryLocked] = useState(false);
  const toolbarSummary = useRef<HTMLButtonElement | null>(null);
  const selectionMenu = useRef<HTMLDivElement | null>(null);
  const [selectionPosition, setSelectionPosition] = useState<{left:number;top:number} | null>(null);
  const isMobile = useMediaQuery("(max-width: 760px)");
  const isCompact = useMediaQuery("(max-width: 1050px)");
  const effectiveLeftOpen = isMobile ? mobileLeftOpen : leftOpen ?? preferences.outline;
  const effectiveRightOpen = isCompact ? compactRightOpen : rightOpen;
  const { access, accessError, pagePayloads, pageErrors, requestPagePayload, retryPagePayload, statusPollPaused, trackDownload, retryAccess } = useReaderDocument({
    assetId: work.id, workId: work.workId, documentRevisionId,
  });
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>(initialQuery ? "search" : "outline");
  const [outlineQuery, setOutlineQuery] = useState("");
  const [collapsedOutline, setCollapsedOutline] = useState<Set<string>>(() => new Set());
  const [selectedOutlineId, setSelectedOutlineId] = useState("");
  const [gate, setGate] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const [copyStatusState, setCopyStatusState] = useState<ActionState>("idle");
  const [sharedCitation, setSharedCitation] = useState<SharedCitationInput | null>(null);
  const [pageInput, setPageInput] = useState<string | null>(null);
  const {
    page, setPage, zoom, totalPages, progress, thumbnailPages, scrollRequest,
    jumpToPage, changeZoom, onDocumentLoad, onVisiblePageChange,
  } = useReaderNavigation({
    initialPage, initialPageCount: work.pages, accessPageCount: access?.page_count, reducedMotion:preferences.motion === "reduced",
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
    recordsLoading, recordsError, recordsStopped, recordsReady, stopRecords, retryRecords,
    annotationSaveUnknown, retryAnnotationSave,
    saveAnnotation, deleteAnnotation, deleteBookmark, protectedAction, showSidebarTab,
  } = useReaderRecords({
    assetId: work.id, initialFocus, readerAuthenticated, readerId: readerSession.user?.id, page, pagePayloads, captureSelection,
    setSelectionTools, setPage, jumpToPage, setLeftPanel, setSidebarTab, setGate,
    setCopyStatus, setCopyStatusState,
  });

  useReaderPageRequest({ page, ocrStatus: access?.ocr_status, requestPagePayload });

  useLayoutEffect(() => {
    if (!selectionTools) return;
    const place = () => {
      const box = selectionMenu.current?.getBoundingClientRect();
      if (!box) return;
      const next = {left:Math.max(8, Math.min(selectionTools.x, window.innerWidth-box.width-8)),top:Math.max(8, Math.min(selectionTools.y, window.innerHeight-box.height-8))};
      setSelectionPosition(current => current?.left===next.left && current.top===next.top ? current : next);
    };
    place();
    window.addEventListener("resize",place);
    return () => window.removeEventListener("resize",place);
  },[selectionTools]);

  const {
    query, setQuery, searchMatches, setSearchMatches, activeSearchMatch,
    passageFocus,
    sourceError, searchError, searchLoading, retrySearch,
    jumpToSearchMatch,
  } = useReaderSearch({
    assetId: work.id, documentRevisionId, initialQuery, initialPassage, initialEvidence, requestPagePayload, jumpToPage,
  });

  const selectedText = access ? annotationDraft ? { ...annotationDraft, x: 0, y: 0 } : selectionTools || retainedSelection : null;
  const citationPage = selectedText?.pageIndex ?? page;
  const { citationStyle, setCitationStyle, citations, citationError, copyCitation, retryCitation } = useReaderCitation({
    editionId: work.editionId ?? access?.edition_id, page: citationPage, setCopyStatus, setCopyStatusState,
  });

  useReaderProgress({ assetId: work.id, page, totalPages, readerAuthenticated:readerAuthenticated && Boolean(access && currentPagePayload), readerId: readerSession.user?.id, guestReady: readerSession.status === "unauthenticated" && Boolean(access && currentPagePayload), revisionId: documentRevisionId });
  const { researchAnchors, researchError, retryResearch } = useReaderResearch({ assetId: work.id, revisionId: documentRevisionId, requestedRevisionId,
    projectId: researchProjectId, turnId: researchTurnId, referenceId: researchReferenceId,
    ownerId: readerSession.status === "authenticated" && readerSession.user ? String(readerSession.user.id) : null, requestPagePayload, jumpToPage });

  const pageOverlays = useReaderPageOverlays({
    annotations, focusedAnnotationId, pagePayloads, passageFocus: access ? passageFocus : null,
    researchAnchors: access ? researchAnchors : [], query, searchMatches: access ? searchMatches : [],
  });
  const allOutline = useMemo(() => prepareOutline(outline), [outline]);
  const readerOutline = useMemo(() => filterOutline(allOutline, outlineQuery, collapsedOutline), [allOutline, outlineQuery, collapsedOutline]);
  const outlineParents = useMemo(() => new Set(allOutline.map(item => item.parent_id).filter(Boolean)), [allOutline]);
  const currentOutline = allOutline.find(item => item.id === selectedOutlineId && item.index === page)
    ?? allOutline.filter(item => item.index <= page).sort((a, b) => b.index - a.index || b.level - a.level)[0];
  const collapseOutline = (id: string, collapse: boolean) => setCollapsedOutline(current => {
    const next = new Set(current); if (collapse) next.add(id); else next.delete(id); return next;
  });
  function setRightPanel(open: boolean) {
    if (isCompact) setCompactRightOpen(open);
    else setRightOpen(open);
  }

  const orderedMatches = searchMatches.map((match, index) => ({ match, index })).sort((a, b) => searchOrder === "reverse" ? b.match.page_index - a.match.page_index : a.match.page_index - b.match.page_index);
  const notes = annotations.filter(item => item.kind === "note");
  const highlights = annotations.filter(item => item.kind !== "note");
  const hasDraft = Boolean(annotationDraft && (annotationDraft.body.trim() || annotationDraft.tags?.length || tagInput.trim()));
  const canLeave = async () => !pendingAction && !ocrRecoveryLocked && ((!hasDraft && !annotationSaveUnknown) || (await confirmAction(annotationSaveUnknown ? "保存结果尚未确认，建议先核对保存结果。仍要离开吗？" : "笔记尚未保存，离开会丢失本次输入。仍要离开吗？")));
  const detailHref = `/works/${encodeURIComponent(work.slug)}`;
  const researchReturn = safeResearchReturn(returnTo);
  const loginReturn = readerReturnPath(work.id, { page: String(page), q: query, focus: initialFocus, passage: initialPassage, evidence: initialEvidence, research_project: researchProjectId, research_turn: researchTurnId, reference: researchReferenceId, revision: requestedRevisionId || documentRevisionId, return_to: researchReturn });
  function openLeft(tab: SidebarTab) {
    showSidebarTab(tab, ["notes", "highlights", "bookmarks"].includes(tab) ? "个人阅读记录" : undefined);
    if (isCompact) setRightPanel(false);
  }
  function openRight(tab: typeof rightTab) {
    setRightTab(tab); setRightPanel(true);
    if (isMobile) setLeftPanel(false);
  }
  async function annotate(snapshot: SelectionSnapshot | null = selectedText || captureSelection()) {
    const changingSource = Boolean(annotationDraft && snapshot &&
      (annotationDraft.pageId !== snapshot.pageId || annotationDraft.quote !== snapshot.quote ||
        JSON.stringify(annotationDraft.bboxes) !== JSON.stringify(snapshot.bboxes)));
    if (changingSource && tagInput.trim() && !annotationDraft?.body.trim() && !annotationDraft?.tags?.length &&
      !(await confirmAction("已有标签尚未保存，改为记录这段原文会丢失当前输入。仍要继续吗？"))) return;
    if ((await beginAnnotation("note", snapshot)) && snapshot) {
      if (changingSource) setTagInput("");
      setRetainedSelection(snapshot);
      openRight("source");
    }
  }
  function sharedSource(snapshot: SelectionSnapshot | null = selectedText) {
    setSharedCitation({ editionId: work.editionId ?? access?.edition_id,
      reference: documentRevisionId ? { asset_id: work.id, document_revision_id: documentRevisionId, pdf_page: snapshot?.pageIndex ?? page } : undefined,
      selectedText: snapshot?.quote });
    if (snapshot) setRetainedSelection(snapshot);
    setSelectionTools(null);
  }
  function visitPage(target: number, position?: [number, number]) {
    jumpToPage(target, "smooth", position);
    if (isMobile) setLeftPanel(false);
  }
  function addTag() {
    const value = tagInput.trim();
    if (!value || !annotationDraft) return;
    if (value.length > 40 || (annotationDraft.tags?.length ?? 0) >= 12) {
      setCopyStatus("每条笔记最多 12 个标签，每个标签最多 40 字。"); setCopyStatusState("error"); return;
    }
    setAnnotationDraft(draft => draft ? { ...draft, tags: [...new Set([...(draft.tags || []), value])] } : null);
    setTagInput("");
  }
  async function commitNote() {
    const tags = [...new Set([...(annotationDraft?.tags || []), tagInput.trim()].filter(Boolean))];
    if (tags.length > 12 || tags.some(tag => tag.length > 40)) {
      setCopyStatus("每条笔记最多 12 个标签，每个标签最多 40 字。"); setCopyStatusState("error"); return;
    }
    if (await saveAnnotation(tags)) setTagInput("");
  }
  async function toggleFullscreen() {
    if (fullscreen) {
      try {
        if (document.fullscreenElement === shellRef.current) await document.exitFullscreen();
        setFullscreen(false);
      } catch { setCopyStatus("暂时无法退出全屏，请按 Esc。"); setCopyStatusState("error"); }
      return;
    }
    setFullscreen(true);
    try {
      await shellRef.current?.requestFullscreen?.();
    } catch {
      // Keep the viewport-filling reader when native fullscreen is unavailable.
    }
  }
  useEffect(() => {
    const update = () => setFullscreen(document.fullscreenElement === shellRef.current);
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented && !document.fullscreenElement && !document.querySelector("dialog[open]")) setFullscreen(false);
    };
    document.addEventListener("fullscreenchange", update);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("fullscreenchange", update);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  useEffect(() => {
    if (!hasDraft && !annotationSaveUnknown && !ocrRecoveryLocked && !pendingAction) return;
    const protect = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [hasDraft, annotationSaveUnknown, ocrRecoveryLocked, pendingAction]);
  const protectOuterNavigation=useEffectEvent((event:MouseEvent)=>{
    if(event.defaultPrevented || event.button!==0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey)return;
    const link=event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
    if(link && !shellRef.current?.contains(link) && link.target!=="_blank" && !link.hasAttribute("download") && (hasDraft || annotationSaveUnknown || ocrRecoveryLocked || pendingAction)){
      void confirmLinkNavigation(event, link, canLeave, href => router.push(href));
    }
  });
  useEffect(()=>{
    if(!embedded)return;
    const protect=(event:MouseEvent)=>protectOuterNavigation(event);
    document.addEventListener("click",protect,true);return()=>document.removeEventListener("click",protect,true);
  },[embedded]);

  const recordStatus = !readerAuthenticated ? <p className="reader-empty-list">登录后查看本人笔记与书签。<button type="button" onClick={() => setGate("个人阅读记录")}>登录</button></p>
    : recordsLoading ? <div className="reader-panel-status" role="status"><p>正在读取个人批注与书签…</p><button type="button" onClick={stopRecords}>停止加载</button></div>
    : recordsError || recordsStopped ? <div className="reader-panel-status" role={recordsError ? "alert" : "status"}><p>{recordsError || "已停止加载，当前记录尚未完整读取。"}</p><button type="button" onClick={retryRecords}>重新加载</button></div> : null;
  const noteList = <div className="reader-library-list">
    {recordStatus}
    {notes.map(annotation => <article className={`reader-library-entry ${focusedAnnotationId === annotation.id ? "active" : ""}`} key={annotation.id}>
      <button className="reader-library-open" type="button" onClick={() => { visitPage(annotation.selector.page_index || 1); setFocusedAnnotationId(annotation.id); if (isCompact) setRightPanel(false); }}>
        <small>第 {annotation.selector.page_index || 1} 页 · {formatReaderTimestamp(annotation.created_at)}</small>
        <span>{annotation.body_text || annotation.quote || "页面笔记"}</span>
        {annotation.tags?.length ? <span className="reader-note-tags">{annotation.tags.map(tag => <em key={tag}># {tag}</em>)}</span> : null}
      </button>
      <ActionButton className="reader-library-delete" type="button" state={pendingAction === `delete-annotation:${annotation.id}` ? "pending" : "idle"} disabled={Boolean(pendingAction)} aria-label={`删除第 ${annotation.selector.page_index || 1} 页笔记`} onClick={() => void deleteAnnotation(annotation.id)}><Trash2 size={14} /></ActionButton>
    </article>)}
    {recordsReady && !notes.length ? <p className="reader-empty-list">还没有保存笔记。选择原文后，可添加仅自己可见的笔记。</p> : null}
  </div>;
  const sourcePage = pagePayloads[citationPage];
  const citationPanel = <section className="reader-citation-panel">
    <h2>引用信息</h2>
    <div className="reader-source-card"><strong>{work.title}</strong><p>{work.author || "作者信息未提供"}</p><small>{[work.version?.publisher, work.version?.publication_year, work.version?.edition_statement].filter(Boolean).join(" · ") || "版本信息未提供"}</small></div>
    <p className="citation-page-map">PDF 第 {citationPage} 页{sourcePage?.printed_label && sourcePage.printed_label !== String(citationPage) ? ` · 书页 ${sourcePage.printed_label}` : ""}</p>
    {sourcePage?.chapter_title ? <p>{sourcePage.chapter_title}</p> : null}
    <label className="reader-format-label">引用格式<select data-stl-select value={citationStyle} onChange={event => setCitationStyle(event.target.value as CitationStyle)} aria-label="引用格式">
      <option value="gbt7714-2025">GB/T 7714—2025</option><option value="apa">APA</option><option value="chicago">Chicago</option><option value="mla">MLA</option><option value="harvard">Harvard</option>
    </select></label>
    <p className="reader-citation-text" role={citationError ? "alert" : "status"}>{citations?.[citationStyle] || citationError || "正在读取本页引用…"}</p>
    {citationError ? <button type="button" onClick={retryCitation}>重试读取引用</button> : null}
    <div className="reader-inline-actions"><button className="button secondary" type="button" disabled={!citations?.[citationStyle]} onClick={copyCitation}><Copy size={14} />复制引用</button><button className="button secondary" type="button" onClick={() => sharedSource()}><Quote size={14} />引用与导出</button></div>
  </section>;
  function recoveryControls(inPanel = false) {
    return annotationSaveUnknown ? <div className={`reader-save-recovery ${inPanel ? "in-panel" : ""}`} role="alert"><strong>保存结果尚待确认</strong><p>{copyStatus || "输入已保留。请先核对这次保存，避免重复创建。"}</p><ActionButton type="button" state={pendingAction === "save-annotation" ? "pending" : "idle"} disabled={Boolean(pendingAction)} onClick={() => { void retryAnnotationSave().then(saved => { if (saved) setTagInput(""); }); }}>核对保存结果</ActionButton></div> : null;
  }
  // Each reference is a state of this same reader; records and PDF identity stay shared.
  const readerView = annotationDraft ? "notes"
    : effectiveLeftOpen && sidebarTab === "search" ? "search"
    : effectiveRightOpen && rightTab === "notes" ? "notes"
    : effectiveLeftOpen && sidebarTab === "outline" && (outlineQuery || isMobile) ? "outline" : "reading";
  const readerReference = readerView === "reading" ? "reader" : `reader-${readerView}` as const;
  const rightTabs: [typeof rightTab, string][] = embedded ? [["source", "原文选取"], ["notes", "我的笔记"], ["citation", "引用信息"], ["related", "相关研究"]] : readerView === "reading"
    ? [["source", "来源"], ["notes", "笔记"], ["related", "相关研究"]]
    : readerView === "search" ? [["source", "来源与引用"], ["notes", `我的笔记${recordsReady ? ` (${notes.length})` : ""}`]]
    : [["source", "原文选取"], ["notes", "我的笔记"], ["citation", "引用信息"]];
  if (!rightTabs.some(([tab]) => tab === rightTab)) rightTabs.push([rightTab, rightTab === "citation" ? "引用信息" : "相关研究"]);
  const outlineMatchCount = allOutline.filter(item => `${item.title} ${item.printed_label} ${item.index}`.toLocaleLowerCase().includes(outlineQuery.trim().toLocaleLowerCase())).length;
  const sourceBook = <section className="reader-source-book"><h2>{readerView === "search" ? "来源信息" : "作品详情"}</h2><Link href={detailHref} className="reader-source-book-summary"><BookCover work={work} size="small" /><span><strong>{work.title}</strong>{work.originalTitle ? <em>{work.originalTitle}</em> : null}<span>{work.author}</span><small>{[work.year, work.version?.publisher].filter(Boolean).join(" · ")}</small><b>查看详情 <ArrowRight size={14} /></b></span></Link></section>;
  const versions = work.versions?.map(row => row.id === work.editionId && work.version ? work.version : row) || (work.version ? [work.version] : []);

  const bookHeading = <div className="reader-book-heading">
          <BookCover work={work} size="small" />
          <div className="reader-title"><h1>{work.title}</h1>{work.originalTitle ? <p>{work.originalTitle}</p> : null}<p>{work.author}</p><small>{[work.year, work.version?.publisher].filter(Boolean).join(" · ")}</small>
            {versions.length ? <label className="reader-version-label"><span className="sr-only">更换版本</span><select data-stl-select aria-label="更换阅读版本" value={work.editionId} onChange={async event => {
              const version = versions.find(row => row.id === event.target.value);
              if (!version || version.id === work.editionId || !(await canLeave())) return;
              const url = version.readable_asset ? `/reader/${encodeURIComponent(version.readable_asset.id)}` : `/works/${encodeURIComponent(version.public_slug || version.id)}`;
              router.push(researchReturn && version.readable_asset ? `${url}?${new URLSearchParams({ return_to: researchReturn })}` : url);
            }}>{versions.map(version => <option value={version.id} key={version.id}>{version.id === work.editionId ? "当前 · " : ""}{[version.edition_statement || version.language, version.publication_year, version.publisher].filter(Boolean).join(" · ") || "未标注版本"}{!version.readable_asset ? "（查看详情）" : ""}</option>)}</select></label> : null}
          </div>
          <div className="reader-heading-actions"><Link className="button secondary reader-return-book" href={detailHref}><ChevronLeft size={15} />返回图书</Link>{researchReturn ? <Link className="button secondary reader-return-research" href={researchReturn}>{researchReturn.startsWith("/recommendations/") ? "返回展项" : researchReturn.startsWith("/explore/") ? "返回候选位置" : researchReturn.startsWith("/topics/") ? "返回主题" : researchReturn.startsWith("/theories/reading-paths/") ? "返回阅读路径" : "返回当前研究"}</Link> : null}<button className="button" type="button" onClick={() => sharedSource()}><FolderPlus size={15} />加入研究</button></div>
        </div>;

  return (
    <div ref={shellRef} data-reader-fullscreen={fullscreen || undefined} data-reader-view={embedded ? undefined : readerView} data-reader-sidebar={sidebarTab} data-reader-motion={preferences.motion} data-reader-highlight={preferences.highlight} className={`reader stl4-reader ${embedded ? "reader-embedded" : ""} ${dark ? "dark" : ""} ${effectiveLeftOpen ? "" : "left-closed"} ${effectiveRightOpen ? "" : "right-closed"}`}
      onClickCapture={event => {
        const link = (event.target as HTMLElement).closest<HTMLAnchorElement>("a[href]");
        if (!event.defaultPrevented && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey && link && link.target !== "_blank" && !link.hasAttribute("download") && (hasDraft || pendingAction || annotationSaveUnknown || ocrRecoveryLocked)) void confirmLinkNavigation(event, link, canLeave, href => router.push(href));
      }}>
      <UsageTracker eventType="reader_open" assetId={work.id} workId={work.workId} source="reader" />
      {!embedded ? <div className="reader-site-header"><SiteHeader config={siteConfig} reader readerReference={readerReference} beforeLogout={canLeave} /></div> : null}
      {embedded ? <div className="reader-heading reader-embedded-heading"><div><strong>{work.title}</strong><small>{work.author}</small></div><div className="reader-embedded-progress"><span>阅读进度 {page} / {totalPages} 页</span><progress value={page} max={totalPages} aria-label="展项阅读位置" /><span>{progress}%</span></div><div className="reader-embedded-actions"><SaveWorkButton workId={work.workId}/>{access ? <a className="button" href={access.download_url || access.url} download={access.download_filename} onClick={trackDownload}><Download size={15}/>下载 PDF</a> : <span>下载暂不可用</span>}<ReaderSettings value={preferences} onSave={applyPreferences}/></div></div> : <div className="reader-heading">
        <nav className="reader-breadcrumb" aria-label="当前位置"><Link href="/home">首页</Link><ChevronRight size={12} /><Link href="/explore">探索</Link><ChevronRight size={12} /><Link href="/explore/original">{work.kind}</Link><ChevronRight size={12} /><Link href={detailHref}>{work.title}</Link><ChevronRight size={12} /><span>PDF 原文阅读器</span></nav>
        <div className="reader-page-intro"><h1>PDF 原文阅读器</h1><p>准确回到原页、读懂上下文，同时保留研究线索。</p></div>
        {readerView !== "search" || !effectiveLeftOpen ? bookHeading : null}
      </div>}

      <header className="reader-toolbar" aria-label="阅读工具栏">
        <button type="button" className="reader-mobile-back" aria-label="返回文献" onClick={async () => { if ((await canLeave())) router.push(detailHref); }}><ChevronLeft size={18} /></button>
        <button type="button" className="reader-outline-toggle" aria-label={effectiveLeftOpen ? "收起目录" : "打开目录"} onClick={() => effectiveLeftOpen ? setLeftPanel(false) : openLeft("outline")}><List size={17} /></button>
        <div className="reader-page-controls"><button type="button" disabled={page <= 1} aria-label="上一页" onClick={() => visitPage(page - 1)}><ChevronLeft size={17} /></button><label><span className="sr-only">PDF 页码</span><input aria-label="PDF 页码" inputMode="numeric" autoComplete="off" value={pageInput ?? String(page)} onChange={event => setPageInput(event.target.value)} onBlur={() => { if (pageInput !== null) { jumpToPage(Number(pageInput), "auto"); setPageInput(null); } }} onKeyDown={event => { if (event.key === "Enter") { jumpToPage(Number(pageInput ?? page), "auto"); setPageInput(null); } }} /></label><span>/ {totalPages}</span><button type="button" disabled={page >= totalPages} aria-label="下一页" onClick={() => visitPage(page + 1)}><ChevronRight size={17} /></button></div>
        <span className="reader-page-label">{currentPagePayload?.printed_label ? `印刷页 ${currentPagePayload.printed_label}` : "PDF 页码"}</span>
        <div className="reader-zoom-controls"><button type="button" aria-label="缩小" disabled={zoom <= 60} onClick={() => changeZoom(-10)}><Minus size={15} /></button><button type="button" title="恢复适应宽度" onClick={() => changeZoom(100 - zoom)}>{zoom}%</button><button type="button" aria-label="放大" disabled={zoom >= 180} onClick={() => changeZoom(10)}><Plus size={15} /></button></div>
        <button className="reader-fullscreen" type="button" aria-label={fullscreen ? "退出全屏" : "全屏阅读"} onClick={() => void toggleFullscreen()}>{fullscreen ? <Minimize size={17} /> : <Maximize size={17} />}</button>
        <button className="reader-search-toggle" type="button" aria-label="书内搜索" onClick={() => openLeft("search")}><Search size={17} /></button>
        <button className="reader-bookmark-toggle" type="button" aria-label={bookmarkedPage ? "移除本页书签" : "保存本页书签"} aria-pressed={bookmarkedPage} disabled={Boolean(pendingAction)} onClick={() => protectedAction("书签")}><Bookmark size={17} fill={bookmarkedPage ? "currentColor" : "none"} /></button>
        <button type="button" ref={toolbarSummary} aria-expanded={toolbarOpen} aria-controls="reader-more" aria-label="更多阅读工具" onClick={() => setToolbarOpen(value => !value)}><MoreHorizontal size={18} /></button>
      </header>

      <ReaderPanel side="left" modal={isMobile && sidebarTab !== "search"} open={effectiveLeftOpen} close={() => setLeftPanel(false)}>
        {isMobile ? recoveryControls(true) : null}
        {readerView === "search" ? <div className="reader-search-book">{bookHeading}</div> : null}
        <div className="reader-outline-heading"><strong>目录</strong><button type="button" aria-label="收起目录" onClick={() => setLeftPanel(false)}><ChevronLeft size={16} /></button></div>
        <div className="reader-panel-heading"><strong>{sidebarTab === "outline" ? "目录" : "目录与书内查找"}</strong><button type="button" aria-label="关闭目录侧栏" onClick={() => setLeftPanel(false)}><X size={18} /></button></div>
        <nav className="reader-panel-tabs" aria-label="阅读导航">{([ ["outline", "目录"], ["search", "搜索"], ["bookmarks", "书签"], ["notes", "笔记"] ] as const).map(([tab, title]) => <button type="button" key={tab} className={sidebarTab === tab ? "active" : ""} aria-pressed={sidebarTab === tab} onClick={() => openLeft(tab)}>{title}</button>)}</nav>
        {sidebarTab === "outline" ? <>
          <label className="reader-panel-search"><Search size={14} /><input aria-label="搜索目录" placeholder="搜索目录…" value={outlineQuery} onChange={event => setOutlineQuery(event.target.value)} />{outlineQuery ? <button type="button" aria-label="清空目录搜索" onClick={() => setOutlineQuery("")}><X size={14} /></button> : null}</label>
          {outlineQuery.trim() ? <div className="reader-outline-matches"><span>找到 {outlineMatchCount} 个匹配结果</span><button type="button" onClick={() => setOutlineQuery("")}>清除</button></div> : null}
          <div className="reader-outline-list">{readerOutline.map(item => <div key={item.id} className={`reader-outline-row ${item.id === currentOutline?.id ? "active" : ""}`} style={{ paddingInlineStart: `${10 + Math.min(item.level - 1, 7) * 13}px` }}>
            {outlineParents.has(item.id) ? <button type="button" className="reader-outline-disclosure" aria-label={`${collapsedOutline.has(item.id) ? "展开" : "折叠"}${item.title}`} aria-expanded={!collapsedOutline.has(item.id) || Boolean(outlineQuery)} onClick={() => collapseOutline(item.id, !collapsedOutline.has(item.id))}><ChevronRight size={13} style={{ transform: collapsedOutline.has(item.id) && !outlineQuery ? undefined : "rotate(90deg)" }} /></button> : <span className="reader-outline-disclosure" />}
            <button type="button" aria-current={item.id === currentOutline?.id ? "location" : undefined} onClick={() => { setSelectedOutlineId(item.id); visitPage(item.index, outlinePosition(item)); }}><span><MatchText text={item.title} query={outlineQuery} /></span><small>{item.printed_label || item.index}</small></button>
          </div>)}</div>
          {!readerOutline.length ? <div className="reader-panel-status"><strong>{outlineQuery ? "没有匹配章节" : "未检测到可靠目录"}</strong><p>{outlineQuery ? "可更换关键词，或在书内查找正文。" : "该文件没有可识别的目录。你可以按页阅读，或在处理完成后再次检查是否可识别目录。"}</p><div className="reader-inline-actions"><button className="button" type="button" onClick={() => setLeftPanel(false)}>按页阅读</button><button className="button secondary" type="button" onClick={() => openLeft("search")}>在书内查找关键词</button></div></div> : null}
          {!allOutline.length ? <form className="reader-quick-jump" onSubmit={event => { event.preventDefault(); const target = Number(new FormData(event.currentTarget).get("page")); visitPage(target); }}><h2>快速跳转</h2><label><span className="sr-only">跳转页码</span><input name="page" type="number" min={1} max={totalPages} required placeholder="输入页码" /></label><button type="submit">跳转</button></form> : null}
          {isMobile ? <button className="button reader-return-document" type="button" onClick={() => setLeftPanel(false)}>返回原文<small>（第 {page} 页）</small></button> : null}
          <button className="reader-panel-link" type="button" onClick={() => openLeft("thumbnails")}>按 PDF 页码快速跳转<ArrowRight size={14} /></button>
        </> : null}
        {sidebarTab === "search" ? <>
          <label className="reader-panel-search"><Search size={15} /><input aria-label="文档内搜索" name="reader-document-search" placeholder="在这本文献中查找" value={query} onChange={event => { setQuery(event.target.value); setSearchMatches([]); }} />{query ? <button type="button" aria-label="清空正文搜索" onClick={() => { setQuery(""); setSearchMatches([]); }}><X size={14} /></button> : null}</label>
          {searchLoading ? <p className="reader-empty-list" role="status">正在查找正文…</p> : searchError ? <div className="reader-panel-status" role="alert"><p>{searchError}</p><button type="button" onClick={retrySearch}>重试查找</button></div> : query.trim() ? <><p className="reader-search-summary">{searchMatches.length ? `找到 ${searchMatches.length} 个匹配页` : "未找到匹配正文"}<label><span className="sr-only">结果排序</span><select data-stl-select aria-label="书内结果排序" value={searchOrder} onChange={event => setSearchOrder(event.target.value)}><option value="page">按页序</option><option value="reverse">按倒序</option></select></label></p><div className="reader-search-results">{orderedMatches.map(({ match, index }) => <button type="button" className={index === activeSearchMatch ? "active" : ""} aria-current={index === activeSearchMatch ? "location" : undefined} key={match.page_id} onClick={() => jumpToSearchMatch(index)}><strong>第 {match.printed_label || match.page_index} 页 <small>PDF {match.page_index}</small></strong><p><MatchText text={match.snippet} query={query} /></p></button>)}</div><p className="reader-empty-list">最多返回 100 个匹配页，范围为本版本已公开的文字；未识别或未发布的文字不在结果中。</p></> : <p className="reader-empty-list">输入词语，查找本版本的公开正文。</p>}
        </> : null}
        {sidebarTab === "thumbnails" ? <><p className="reader-empty-list">PDF 页码导航{totalPages > thumbnailPages.length ? ` · 第 ${thumbnailPages[0]}—${thumbnailPages.at(-1)} 页` : ""}</p><div className="reader-thumbnail-grid">{thumbnailPages.map(target => <button className={target === page ? "active" : ""} type="button" key={target} onClick={() => visitPage(target)}><span>{target}</span></button>)}</div></> : null}
        {sidebarTab === "notes" ? noteList : null}
        {sidebarTab === "highlights" ? <div className="reader-library-list">{recordStatus}{highlights.map(annotation => <article className="reader-library-entry" key={annotation.id}><button className="reader-library-open" type="button" onClick={() => { visitPage(annotation.selector.page_index || 1); setFocusedAnnotationId(annotation.id); }}><small>第 {annotation.selector.page_index || 1} 页 · {annotation.kind === "underline" ? "划线" : "高亮"}</small><span>{annotation.quote}</span></button><ActionButton className="reader-library-delete" type="button" disabled={Boolean(pendingAction)} aria-label="删除批注" onClick={() => void deleteAnnotation(annotation.id)}><Trash2 size={14} /></ActionButton></article>)}{recordsReady && !highlights.length ? <p className="reader-empty-list">还没有保存高亮或划线。</p> : null}</div> : null}
        {sidebarTab === "bookmarks" ? <div className="reader-library-list">{recordStatus}{bookmarks.map(bookmark => <article className="reader-library-entry" key={bookmark.id}><button className="reader-library-open" type="button" onClick={() => visitPage(bookmark.page_index || 1)}><small>第 {bookmark.page_index || 1} 页</small><span>{bookmark.label}</span></button><ActionButton className="reader-library-delete" type="button" disabled={Boolean(pendingAction)} aria-label={`删除第 ${bookmark.page_index || 1} 页书签`} onClick={() => void deleteBookmark(bookmark.id)}><Trash2 size={14} /></ActionButton></article>)}{recordsReady && !bookmarks.length ? <p className="reader-empty-list">还没有保存书签。</p> : null}</div> : null}
      </ReaderPanel>

      <section className="reader-document continuous-scroll-mode" data-view-mode="continuous" ref={readerDocumentRef} onMouseUp={showSelectionTools} onContextMenu={showSelectionContextMenu} onCopy={handleDocumentCopy}>
        {access && access.ocr_status !== "not_required" && (access.ocr_status !== "succeeded" || !documentRevisionId) ? <div className={`reader-processing-status status-${access.ocr_status}`} role="status"><strong>{access.ocr_status === "failed" ? "文字识别暂不可用" : access.ocr_status === "disabled" ? "文字识别已停用" : access.ocr_status === "running" ? "正在识别文字" : access.ocr_status === "succeeded" ? "文字等待发布" : "等待可用文字"}</strong><span>仍可阅读扫描原页。复制、查找与原文引用以当前已获准的文字为准。</span><button type="button" onClick={() => setOcrOpen(true)}>查看文字处理进度</button></div> : null}
        {access?.reader_fallback_reason ? <div className="reader-processing-status status-failed" role="status"><strong>已切换可用阅读副本</strong><span>{access.reader_fallback_reason}</span></div> : null}
        {access && pageErrors[page] ? <div className="reader-processing-status status-failed" role="alert"><strong>当前页文字暂未读出</strong><span>{pageErrors[page]}</span><button type="button" onClick={() => retryPagePayload(page)}>重试页内容</button></div> : null}
        {sourceError || researchError ? <div className="reader-processing-status status-failed" role="alert"><span>{sourceError || researchError}</span><button type="button" onClick={sourceError ? retrySearch : retryResearch}>重新核对原文定位</button></div> : null}
        {(passageFocus && !passageFocus.bbox.length) || researchAnchors.some(anchor => !anchor.bbox.length) ? <p className="reader-processing-status">来源按页定位，请在扫描原页核对具体文字。</p> : null}
        {statusPollPaused ? <div className="reader-processing-status" role="status">阅读状态已停止自动刷新，这不会暂停文字处理任务。<button type="button" onClick={retryAccess}>重新读取</button></div> : null}
        {access ? <PdfContinuousViewer key={`${access.served_asset_id}:${access.sha256}`} url={access.url} pageCount={totalPages} currentPage={page} zoom={zoom} rotation={rotation} overlays={pageOverlays} preferOcrTextLayer={access.ocr_text_available} scrollRequest={scrollRequest} onDocumentLoad={onDocumentLoad} onPageChange={onVisiblePageChange} onRequestPage={requestPagePayload} onNoteSelect={annotationId => { setFocusedAnnotationId(annotationId); openRight("notes"); }} onNoteDelete={annotationId => void deleteAnnotation(annotationId)} onRetry={retryAccess} /> : <div className="reader-unavailable" role="status"><BookOpen size={30} /><strong>{accessError ? "暂时未能加载阅读文件" : "正在连接阅读文件"}</strong><p>{accessError || "正在取得当前版本的阅读文件…"}</p>{accessError ? <><button type="button" className="button" onClick={retryAccess}>重试</button><Link className="button secondary" href={detailHref}>查看其他可用版本</Link><button className="button secondary" type="button" onClick={() => openRight("notes")}>查看我的笔记</button><p>已有个人笔记会保留。</p></> : null}</div>}
      </section>
      {!((isMobile && effectiveLeftOpen) || (isCompact && effectiveRightOpen) || toolbarOpen) ? recoveryControls() : null}
      <span hidden={annotationSaveUnknown} className={`reader-copy-status ${copyStatusState}`} role={copyStatusState === "error" ? "alert" : "status"} aria-live={copyStatusState === "error" ? "assertive" : "polite"}>{copyStatus}</span>

      {selectionTools && access ? <div ref={selectionMenu} className="reader-selection-menu" role="toolbar" aria-label="所选文字操作" style={selectionPosition ?? { left: selectionTools.x, top: selectionTools.y }} onMouseDown={event => event.preventDefault()}>
        <button type="button" onClick={() => { setRetainedSelection(selectionTools); void cleanCopy(selectionTools.quote); }}><Copy size={15} />复制</button><button type="button" onClick={() => sharedSource(selectionTools)}><Quote size={15} />引用</button><button type="button" onClick={() => beginAnnotation("highlight", selectionTools)}><Highlighter size={15} />高亮</button><button type="button" onClick={() => beginAnnotation("underline", selectionTools)}><Underline size={15} />划线</button><button type="button" onClick={() => annotate(selectionTools)}><StickyNote size={15} />记笔记</button><button type="button" onClick={() => { setRetainedSelection(selectionTools); setSelectionTools(null); openRight("source"); }}><FolderPlus size={15} />原文选取</button><button type="button" aria-label="关闭选文菜单" onClick={() => setSelectionTools(null)}><X size={14} /></button>
      </div> : null}
      <ReaderPanel side="right" modal={isCompact} open={effectiveRightOpen} close={() => setRightPanel(false)}>
        {isCompact ? recoveryControls(true) : null}
        <div className="reader-panel-heading"><strong>原文与我的研究</strong><button type="button" aria-label="关闭信息侧栏" onClick={() => setRightPanel(false)}><X size={18} /></button></div>
        <nav className="reader-panel-tabs" aria-label="原文与笔记">{rightTabs.map(([tab, title]) => <button key={tab} type="button" className={rightTab === tab ? "active" : ""} aria-pressed={rightTab === tab} onClick={() => setRightTab(tab)}>{title}</button>)}<button type="button" className="reader-tab-close" aria-label="关闭信息侧栏" onClick={() => setRightPanel(false)}><X size={15} /></button></nav>
        {rightTab === "source" ? <><section className="reader-source-selection">{selectedText ? <><h2>{readerView === "reading" ? "当前引用" : "原文选取"}</h2><blockquote>{selectedText.quote}</blockquote>{readerView === "reading" ? <dl className="reader-source-location"><dt>来源</dt><dd>{work.title}</dd><dt>位置</dt><dd>PDF 第 {selectedText.pageIndex} / {totalPages} 页{sourcePage?.printed_label ? `，印刷页 ${sourcePage.printed_label}` : ""}</dd>{sourcePage?.chapter_title ? <><dt>章节</dt><dd>{sourcePage.chapter_title}</dd></> : null}<dt>版本</dt><dd>{[work.year, work.version?.publisher].filter(Boolean).join(" · ") || "版本信息未提供"}</dd></dl> : null}<p>PDF 第 {selectedText.pageIndex} 页{sourcePage?.chapter_title ? ` · ${sourcePage.chapter_title}` : ""}</p><div className="reader-inline-actions"><button type="button" onClick={() => void cleanCopy(selectedText.quote)}><Copy size={14} />复制原文</button><button className="reader-cite-selection" type="button" onClick={() => sharedSource()}><Quote size={14} />{readerView === "reading" ? "引用此段落" : "引用"}</button><button type="button" onClick={() => annotate()}><StickyNote size={14} />记笔记</button><button type="button" onClick={() => sharedSource()}><FolderPlus size={14} />加入研究</button></div><button className="reader-panel-link" type="button" disabled={Boolean(annotationDraft)} onClick={() => { setRetainedSelection(null); setSelectionTools(null); }}>清除当前选文</button></> : <><h2>当前阅读</h2><strong>{currentPagePayload?.chapter_title || currentOutline?.chapter_title || work.title}</strong><p>PDF 第 {page} 页{currentPagePayload?.printed_label ? ` · 书页 ${currentPagePayload.printed_label}` : ""}</p><p className="reader-empty-list">在原文中选择文字，即可复制、引用、记笔记或加入研究。</p></>}</section>
          {annotationDraft ? <section className="reader-note-editor"><form onSubmit={event => { event.preventDefault(); void commitNote(); }}><fieldset disabled={Boolean(pendingAction) || annotationSaveUnknown}><h2>添加笔记</h2><p>锚定 PDF 第 {annotationDraft.pageIndex} 页</p><label><span className="sr-only">笔记内容</span><textarea autoFocus rows={5} value={annotationDraft.body} onChange={event => setAnnotationDraft(draft => draft ? { ...draft, body: event.target.value } : null)} placeholder="记录你的理解、问题或联想" /></label><div className="reader-note-tags">{(annotationDraft.tags || []).map(tag => <button type="button" key={tag} aria-label={`移除标签${tag}`} onClick={() => setAnnotationDraft(draft => draft ? { ...draft, tags: draft.tags?.filter(value => value !== tag) } : null)}># {tag}<X size={12} /></button>)}</div><div className="reader-tag-entry"><input aria-label="笔记标签" placeholder="添加标签" maxLength={40} value={tagInput} onChange={event => setTagInput(event.target.value)} onKeyDown={event => { if (event.key === "Enter") { event.preventDefault(); addTag(); } }} /><button type="button" onClick={addTag} disabled={!tagInput.trim() || (annotationDraft.tags?.length ?? 0) >= 12}><Plus size={14} /><span className="sr-only">添加标签</span></button></div><div className="reader-note-save"><small><LockKeyhole size={12} />仅自己可见</small><button className="button secondary" type="button" disabled={Boolean(pendingAction)} onClick={async () => { if (!hasDraft || (await confirmAction("放弃这条尚未保存的笔记？"))) { setAnnotationDraft(null); setTagInput(""); } }}>取消</button><ActionButton className="button" type="submit" state={pendingAction === "save-annotation" ? "pending" : "idle"} disabled={!recordsReady || Boolean(pendingAction)} pendingLabel="正在保存">保存笔记</ActionButton></div></fieldset></form>{recordStatus}</section> : null}
          {!annotationDraft ? sourceBook : null}
          {readerView === "search" ? citationPanel : null}
          {annotationDraft || readerView === "notes" ? <section className="reader-related-notes"><h2>我的相关笔记{recordsReady ? `（${notes.length}）` : ""}</h2>{noteList}</section> : null}</> : null}
        {rightTab === "notes" ? <section><h2>我的笔记{recordsReady ? `（${notes.length}）` : ""}</h2>{noteList}<button className="reader-panel-link" type="button" onClick={() => { openLeft("highlights"); if (!isMobile) setRightPanel(false); }}>查看高亮与划线<ArrowRight size={14} /></button></section> : null}
        {rightTab === "citation" ? citationPanel : null}
        {rightTab === "related" ? <><section><h2>相关理论流派</h2><div className="tag-list">{relatedTheories.map(item => <Link href={`/theories/nodes/${encodeURIComponent(item.slug)}`} key={item.slug}>{item.name}</Link>)}{!relatedTheories.length ? <p className="reader-empty-list">尚无已确认的公开关系。</p> : null}</div></section><section><h2>相关学者</h2>{relatedScholars.map(scholar => <Link href={`/scholars/${encodeURIComponent(scholar.slug)}`} key={scholar.slug}>{scholar.portrait ? <img src={scholar.portrait} width={32} height={40} alt={scholar.name} loading="lazy" /> : null}<span><strong>{scholar.name}</strong><small>{scholar.years}</small></span></Link>)}{!relatedScholars.length ? <p className="reader-empty-list">尚无已确认的公开学者。</p> : null}</section><section><h2>相关主题</h2>{relatedTopics.map(topic => <Link href={`/topics/${encodeURIComponent(topic.slug)}`} key={topic.slug}>{topic.name}</Link>)}{!relatedTopics.length ? <p className="reader-empty-list">尚无已确认的公开主题。</p> : null}</section><section><AskLibraryLink context="works" ids={[work.workId]} assetId={work.id} label="围绕本文献开始研究" className="button secondary" /></section></> : null}
      </ReaderPanel>
      <footer className="reader-bottom">{!embedded ? <div className="reader-footer-brand"><BrandImage config={siteConfig ?? undefined} /><span>连接思想 · 开放知识 · 服务研究与大众</span></div> : null}<span className="reader-bottom-work">{work.title}</span><div className="reader-bottom-progress"><span>{page} / {totalPages}</span><progress value={page} max={totalPages} aria-label="阅读位置" /><span>{progress}%</span></div><div className="reader-bottom-actions"><button type="button" onClick={() => effectiveLeftOpen ? setLeftPanel(false) : openLeft("outline")} aria-pressed={effectiveLeftOpen}><List size={17} />目录</button><button type="button" onClick={() => openRight("notes")}><StickyNote size={17} />笔记</button><button type="button" onClick={() => openRight("citation")}><Quote size={17} />引用</button><button type="button" onClick={() => setToolbarOpen(true)}><MoreHorizontal size={17} />更多</button></div></footer>
      <Dialog open={ocrOpen} className="reader-more-dialog reader-ocr-dialog" onRequestClose={() => { if (!ocrRecoveryLocked) setOcrOpen(false); }} aria-labelledby="reader-ocr-heading"><header><h2 id="reader-ocr-heading">文字识别与处理状态</h2><button type="button" disabled={ocrRecoveryLocked} aria-label="关闭文字处理状态" onClick={() => setOcrOpen(false)}><X size={20} /></button></header>{ocrOpen ? <ReaderOcrStatus assetId={work.id} documentRevisionId={documentRevisionId} ownerId={readerSession.user?.id} canViewManagement={Boolean(readerAuthenticated && readerSession.user?.capabilities?.includes("access_back_office"))} canManage={Boolean(readerAuthenticated && readerSession.user?.capabilities?.includes("access_back_office") && readerSession.user.capabilities.includes("can_retry_jobs"))} onRecoveryLockChange={setOcrRecoveryLocked} preview={access ? <ReaderPageThumbnail key={`${access.requested_asset_id}:${access.sha256}:${page}`} sourceRef={readerDocumentRef} page={page} identity={`${access.requested_asset_id}:${access.sha256}`} /> : undefined} /> : null}<Link href={detailHref} target="_blank" rel="noopener noreferrer">在文献详情核对当前版本</Link></Dialog>
      <Dialog open={toolbarOpen} className="reader-more-dialog" id="reader-more" onRequestClose={() => setToolbarOpen(false)} aria-label="阅读工具"><header><h2>阅读工具</h2><button type="button" aria-label="关闭阅读工具" onClick={() => setToolbarOpen(false)}><X size={20} /></button></header>{recoveryControls(true)}<div className="reader-more-actions"><ReaderSettings value={preferences} onSave={applyPreferences}/><button type="button" onClick={() => { setToolbarOpen(false); setOcrOpen(true); }}><BookOpen size={18} />文字识别与处理状态</button><Link href={`/reader/${work.id}?mode=parallel&page=${page}`}><BookOpen size={18} />原文与译本并读</Link><button type="button" onClick={() => { setToolbarOpen(false); openLeft("search"); }}><Search size={18} />书内搜索</button><button type="button" onClick={() => { setToolbarOpen(false); openLeft("bookmarks"); }}><Bookmark size={18} />我的书签</button><button type="button" onClick={() => { setToolbarOpen(false); openRight("citation"); }}><Quote size={18} />引用信息</button><button type="button" onClick={() => { setToolbarOpen(false); openRight("related"); }}><FolderPlus size={18} />相关研究</button><button type="button" onClick={() => { setToolbarOpen(false); protectedAction("书签"); }} aria-pressed={bookmarkedPage}><Bookmark size={18} />{bookmarkedPage ? "移除本页书签" : "保存本页书签"}</button><button type="button" onClick={() => { setToolbarOpen(false); openLeft("highlights"); }}><Highlighter size={18} />我的高亮与划线</button>{access ? <a href={access.download_url || access.url} download={access.download_filename} onClick={trackDownload}><Download size={18} />{access.download_rendition === "ocr_pdf" ? "下载可搜索 PDF" : "下载 PDF"}</a> : <button type="button" disabled><Download size={18} />下载暂不可用</button>}{readerSession.user?.capabilities?.includes("access_back_office") ? <Link href="/admin/processing?tab=ocr"><BookOpen size={18} />查看文字处理任务</Link> : null}<button type="button" onClick={() => { setRotation(value => ((value + 90) % 360) as ReaderRotation); setSelectionTools(null); window.getSelection()?.removeAllRanges(); jumpToPage(page, "auto"); }}><RotateCw size={18} />旋转页面 · {rotation}°</button><button type="button" onClick={() => updateAppearance({ theme: dark ? "light" : "dark" })}>{dark ? <Sun size={18} /> : <Moon size={18} />}{dark ? "浅色阅读界面" : "深色阅读界面"}</button><button type="button" onClick={() => { setToolbarOpen(false); void toggleFullscreen(); }}><Maximize size={18} />{fullscreen ? "退出全屏" : "全屏阅读"}</button></div><div className="reader-more-zoom"><span>页面缩放</span><button type="button" disabled={zoom <= 60} onClick={() => changeZoom(-10)}><Minus size={16} /></button><button type="button" onClick={() => changeZoom(100 - zoom)}>{zoom}%</button><button type="button" disabled={zoom >= 180} onClick={() => changeZoom(10)}><Plus size={16} /></button></div>{access?.original_download_url ? <a href={access.original_download_url} download={access.download_filename}>下载原始扫描版</a> : null}</Dialog>
      {sharedCitation ? <SharedCitationOverlay {...sharedCitation} open onClose={() => setSharedCitation(null)} /> : null}
      {gate ? <Dialog open className="login-gate" onRequestClose={() => setGate(null)} aria-labelledby="login-gate-title"><div><button className="panel-close" type="button" aria-label="关闭登录提示" onClick={() => setGate(null)}><X size={18} /></button><p className="eyebrow">保存个人阅读资料</p><h2 id="login-gate-title">登录后使用{gate}</h2><p>在线阅读、下载、全文搜索、复制和引用对访客开放。个人笔记与书签保存到自己的账户。</p><Link className="button" href={authPageHref("login", loginReturn)}>登录<ArrowRight size={16} /></Link><Link className="button secondary" href={authPageHref("register", loginReturn)}>注册读者</Link></div></Dialog> : null}
    </div>
  );
}

function ReaderPanel({ side, modal, open, close, children }: { side: "left" | "right"; modal: boolean; open: boolean; close: () => void; children: ReactNode }) {
  return modal ? <Dialog open={open} onRequestClose={close} className={`reader-sheet reader-sheet-${side}`} aria-label={side === "left" ? "目录与查找" : "原文、笔记与引用"}>{children}</Dialog>
    : <aside className={`reader-${side}`} inert={!open} aria-hidden={!open}>{children}</aside>;
}

function MatchText({ text, query }: { text: string; query: string }) {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return text;
  const parts: ReactNode[] = [];
  const lower = text.toLocaleLowerCase();
  let start = 0;
  for (let at = lower.indexOf(needle); at >= 0; at = lower.indexOf(needle, start)) {
    parts.push(text.slice(start, at), <mark key={at}>{text.slice(at, at + needle.length)}</mark>);
    start = at + needle.length;
  }
  parts.push(text.slice(start));
  return <>{parts}</>;
}
