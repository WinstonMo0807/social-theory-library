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
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ClipboardEvent as ReactClipboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import type { Work } from "@/lib/data";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import type { CanonicalBlock } from "./pdf-canvas";
import {
  PdfContinuousViewer,
  type PdfPageOverlay,
  type PdfScrollRequest,
} from "./pdf-continuous-viewer";
import { BookCover } from "./ui";
import { UsageTracker } from "./usage-tracker";
import { AskLibraryLink } from "./ask-library-link";

type AccessPayload = {
  url: string;
  download_url: string;
  original_download_url?: string;
  download_rendition?: "normalized" | "ocr_pdf" | "web_derivative";
  source: string;
  expires_in: number | null;
  download_filename: string;
  edition_id: string;
  page_count: number;
  requested_asset_id: string;
  served_asset_id: string;
  source_artifact_id: string | null;
  rendition: "normalized" | "ocr_pdf" | "web_derivative";
  reader_rendition_policy: "auto" | "original" | "ocr";
  reader_fallback_reason: string;
  sha256: string;
  ocr_status: "not_required" | "pending" | "running" | "succeeded" | "failed" | "disabled";
  ocr_text_available: boolean;
  page_label_status: "pending" | "ready" | "needs_review";
  semantic_index_status: "not_indexed" | "pending" | "running" | "ready" | "failed";
};

type PagePayload = {
  page_id: string;
  page_index: number;
  printed_label: string;
  chapter_title: string;
  text_source: "none" | "embedded" | "ocr" | "hybrid";
  width: number;
  height: number;
  text: string;
  blocks: CanonicalBlock[];
};

type ReaderAnnotation = {
  id: string;
  page: string;
  kind: "highlight" | "underline" | "note";
  selector: {
    page_index?: number;
    exact?: string;
    bboxes?: number[][];
  };
  quote: string;
  body_text: string;
  created_at: string;
  updated_at: string;
};

type ReaderBookmark = {
  id: string;
  page: string;
  page_index: number;
  label: string;
  created_at?: string;
};

type AnnotationDraft = {
  kind: "highlight" | "underline" | "note";
  pageIndex: number;
  pageId: string;
  quote: string;
  bboxes: number[][];
  body: string;
};

type SelectionSnapshot = Omit<AnnotationDraft, "kind" | "body"> & {
  x: number;
  y: number;
};

type SearchMatch = {
  rank: number;
  occurrence_count: number;
  page_id: string;
  page_index: number;
  printed_label: string;
  snippet: string;
  width: number;
  height: number;
  blocks: { bbox: number[]; text: string; order: number }[];
  highlights?: { bbox: number[]; text: string; source: "pdf-text" | "ocr-estimate" }[];
};

type PassageFocus = {
  id: string;
  asset_id: string;
  title: string;
  page_index: number;
  printed_label: string;
  width: number;
  height: number;
  bbox: number[];
  text: string;
};

type CitationStyle = "gbt7714-2025" | "apa" | "chicago" | "mla" | "harvard";
type CitationBundle = Record<CitationStyle, string> & {
  page?: {
    pdf_page: number;
    printed_label: string;
    citation_label: string;
    source: "pdf-label" | "pdf-index" | "legacy" | "none";
  };
};
type SidebarTab = "outline" | "thumbnails" | "highlights" | "bookmarks" | "notes";

function formatReaderTimestamp(value?: string) {
  if (!value) return "保存时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "保存时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

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
  const [page, setPage] = useState(Math.min(Math.max(initialPage, 1), Math.max(work.pages, 1)));
  const [zoom, setZoom] = useState(100);
  const [query, setQuery] = useState(initialQuery);
  const [dark, setDark] = useState(false);
  const [leftOpen, setLeftOpen] = useState(true);
  const [rightOpen, setRightOpen] = useState(true);
  const [mobileLeftOpen, setMobileLeftOpen] = useState(false);
  const [compactRightOpen, setCompactRightOpen] = useState(false);
  const isMobile = useMediaQuery("(max-width: 760px)");
  const isCompact = useMediaQuery("(max-width: 1050px)");
  const effectiveLeftOpen = isMobile ? mobileLeftOpen : leftOpen;
  const effectiveRightOpen = isCompact ? compactRightOpen : rightOpen;
  const [access, setAccess] = useState<AccessPayload | null>(null);
  const [accessError, setAccessError] = useState("");
  const [documentPages, setDocumentPages] = useState(0);
  const [pagePayloads, setPagePayloads] = useState<Record<number, PagePayload>>({});
  const pagePayloadsRef = useRef<Record<number, PagePayload>>({});
  const pendingPageRequests = useRef<Set<number>>(new Set());
  const [searchMatches, setSearchMatches] = useState<SearchMatch[]>([]);
  const [activeSearchMatch, setActiveSearchMatch] = useState(0);
  const [searchCandidatesOpen, setSearchCandidatesOpen] = useState(false);
  const [passageFocus, setPassageFocus] = useState<PassageFocus | null>(null);
  const [citationStyle, setCitationStyle] = useState<CitationStyle>("gbt7714-2025");
  const [citations, setCitations] = useState<CitationBundle | null>(null);
  const [annotations, setAnnotations] = useState<ReaderAnnotation[]>([]);
  const [bookmarks, setBookmarks] = useState<ReaderBookmark[]>([]);
  const [annotationDraft, setAnnotationDraft] = useState<AnnotationDraft | null>(null);
  const [focusedAnnotationId, setFocusedAnnotationId] = useState(initialFocus);
  const [sidebarTab, setSidebarTab] = useState<SidebarTab>("outline");
  const [gate, setGate] = useState<string | null>(null);
  const [copyStatus, setCopyStatus] = useState("");
  const [selectionTools, setSelectionTools] = useState<SelectionSnapshot | null>(null);
  const [scrollRequest, setScrollRequest] = useState<PdfScrollRequest>({
    page: Math.min(Math.max(initialPage, 1), Math.max(work.pages, 1)),
    sequence: 0,
    behavior: "auto",
  });
  const readerDocumentRef = useRef<HTMLElement>(null);
  const totalPages = Math.max(documentPages, access?.page_count ?? 0, work.pages, 1);
  const currentPagePayload = pagePayloads[page] ?? null;
  const jumpToPage = useCallback((target: number, behavior: ScrollBehavior = "smooth") => {
    const nextPage = Math.min(totalPages, Math.max(1, Math.round(target) || 1));
    setPage(nextPage);
    setScrollRequest((current) => ({
      page: nextPage,
      sequence: current.sequence + 1,
      behavior,
    }));
  }, [totalPages]);
  const changeZoom = useCallback((delta: number) => {
    setZoom((value) => Math.min(180, Math.max(60, value + delta)));
    setScrollRequest((current) => ({
      page,
      sequence: current.sequence + 1,
      behavior: "auto",
    }));
  }, [page]);
  const setLeftPanel = useCallback((open: boolean) => {
    if (isMobile) setMobileLeftOpen(open);
    else setLeftOpen(open);
  }, [isMobile]);

  useEffect(() => {
    pagePayloadsRef.current = pagePayloads;
  }, [pagePayloads]);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: number | undefined;

    async function loadAccess() {
      try {
        const payload = await apiRequest<AccessPayload>(`/distribution/assets/${work.id}/access/`);
        if (cancelled) return;
        const nextAccess = {
          ...payload,
          url: normalizePublicResourceUrl(payload.url),
          download_url: normalizePublicResourceUrl(payload.download_url || payload.url),
          original_download_url: payload.original_download_url
            ? normalizePublicResourceUrl(payload.original_download_url)
            : undefined,
        };
        setAccess((current) => {
          if (current && current.ocr_status !== nextAccess.ocr_status) {
            pagePayloadsRef.current = {};
            pendingPageRequests.current.clear();
            setPagePayloads({});
          }
          return nextAccess;
        });
        setAccessError("");
        const statusRefreshSeconds = ["pending", "running"].includes(payload.ocr_status)
          ? 20
          : Number.POSITIVE_INFINITY;
        const addressRefreshSeconds = payload.expires_in
          ? Math.max(60, payload.expires_in - 120)
          : Number.POSITIVE_INFINITY;
        const refreshSeconds = Math.min(statusRefreshSeconds, addressRefreshSeconds);
        if (Number.isFinite(refreshSeconds)) {
          refreshTimer = window.setTimeout(
            loadAccess,
            refreshSeconds * 1000,
          );
        }
      } catch (error: unknown) {
        if (!cancelled) {
          const message = error instanceof Error ? error.message : "";
          setAccess(null);
          setAccessError(
            /failed to fetch|networkerror/i.test(message)
              ? "暂时无法连接阅读文件服务，请稍后重试。"
              : message || "公开阅读副本尚未就绪。",
          );
        }
      }
    }

    void loadAccess();
    return () => {
      cancelled = true;
      if (refreshTimer) window.clearTimeout(refreshTimer);
    };
  }, [work.id]);

  useEffect(() => {
    if (!readerAuthenticated) {
      queueMicrotask(() => {
        setAnnotations([]);
        setBookmarks([]);
      });
      return;
    }
    const token = getServerSessionCredential();
    if (!token) return;
    let cancelled = false;
    Promise.all([
      apiRequest<{ results: ReaderAnnotation[] }>(
        `/reading/annotations/?asset=${encodeURIComponent(work.id)}`,
        {},
        token,
      ),
      apiRequest<{ results: ReaderBookmark[] }>(
        `/reading/bookmarks/?asset=${encodeURIComponent(work.id)}`,
        {},
        token,
      ),
    ])
      .then(([annotationPayload, bookmarkPayload]) => {
        if (cancelled) return;
        setAnnotations(annotationPayload.results);
        setBookmarks(bookmarkPayload.results);
        if (initialFocus) {
          const focused = annotationPayload.results.find((item) => item.id === initialFocus);
          if (focused) {
            jumpToPage(focused.selector.page_index || 1, "auto");
            setSidebarTab(focused.kind === "note" ? "notes" : "highlights");
            setLeftPanel(true);
            setFocusedAnnotationId(focused.id);
          }
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [initialFocus, jumpToPage, readerAuthenticated, setLeftPanel, work.id]);

  const requestPagePayload = useCallback((targetPage: number) => {
    if (
      targetPage < 1
      || pagePayloadsRef.current[targetPage]
      || pendingPageRequests.current.has(targetPage)
    ) return;
    pendingPageRequests.current.add(targetPage);
    void apiRequest<PagePayload>(`/catalog/assets/${work.id}/pages/${targetPage}/`)
      .then((payload) => {
        pagePayloadsRef.current = {
          ...pagePayloadsRef.current,
          [payload.page_index]: payload,
        };
        setPagePayloads(pagePayloadsRef.current);
      })
      .catch(() => undefined)
      .finally(() => {
        pendingPageRequests.current.delete(targetPage);
      });
  }, [work.id]);

  useEffect(() => {
    requestPagePayload(page);
  }, [access?.ocr_status, page, requestPagePayload]);

  useEffect(() => {
    if (!initialPassage) return;
    let cancelled = false;
    apiRequest<PassageFocus>(
      `/catalog/passages/${encodeURIComponent(initialPassage)}/focus/`,
    )
      .then((payload) => {
        if (cancelled || payload.asset_id !== work.id) return;
        setPassageFocus(payload);
        requestPagePayload(payload.page_index);
        jumpToPage(payload.page_index, "auto");
      })
      .catch(() => {
        if (!cancelled) setPassageFocus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [initialPassage, jumpToPage, requestPagePayload, work.id]);

  useEffect(() => {
    if (!initialEvidence) return;
    let cancelled = false;
    apiRequest<PassageFocus>(
      `/catalog/theory-system/evidence/${encodeURIComponent(initialEvidence)}/focus/`,
    )
      .then((payload) => {
        if (cancelled || payload.asset_id !== work.id) return;
        setPassageFocus(payload);
        requestPagePayload(payload.page_index);
        jumpToPage(payload.page_index, "auto");
      })
      .catch(() => {
        if (!cancelled) setPassageFocus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [initialEvidence, jumpToPage, requestPagePayload, work.id]);

  useEffect(() => {
    if (!query.trim()) {
      return;
    }
    let cancelled = false;
    const timer = window.setTimeout(() => {
      apiRequest<{ matches: SearchMatch[] }>(
        `/catalog/assets/${work.id}/search/?q=${encodeURIComponent(query.trim())}`,
      )
        .then((payload) => {
          if (!cancelled) {
            setSearchMatches(payload.matches);
            setActiveSearchMatch(0);
            setSearchCandidatesOpen(payload.matches.length > 0);
          }
        })
        .catch(() => {
          if (!cancelled) setSearchMatches([]);
        });
    }, 260);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, work.id]);

  const editionId = work.editionId ?? access?.edition_id;
  useEffect(() => {
    if (!editionId) {
      return;
    }
    let cancelled = false;
    apiRequest<CitationBundle>(
      `/catalog/editions/${editionId}/citations/?pdf_page=${page}`,
    )
      .then((payload) => {
        if (!cancelled) setCitations(payload);
      })
      .catch(() => {
        if (!cancelled) setCitations(null);
      });
    return () => {
      cancelled = true;
    };
  }, [editionId, page]);

  useEffect(() => {
    if (!readerAuthenticated) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const timer = window.setTimeout(() => {
      void (async () => {
        // Both writes are best-effort, but they target the same reader and asset.
        // Keep them sequential so single-writer stores do not race each other.
        await apiRequest(
          "/reading/progress/",
          {
            method: "POST",
            body: JSON.stringify({
              asset: work.id,
              current_page: page,
              progress_ratio: page / totalPages,
              last_position: { page },
            }),
          },
          token,
        ).catch(() => undefined);
        await apiRequest(
          "/reading/history/",
          {
            method: "POST",
            body: JSON.stringify({
              asset: work.id,
              page_index: page,
              session_seconds: 0,
            }),
          },
          token,
        ).catch(() => undefined);
      })();
    }, 650);
    return () => window.clearTimeout(timer);
  }, [page, readerAuthenticated, totalPages, work.id]);

  const progress = Math.round((page / totalPages) * 100);
  const pageOverlays = useMemo(() => {
    const result: Record<number, PdfPageOverlay> = {};
    const pageIndexes = new Set<number>([
      ...Object.keys(pagePayloads).map(Number),
      ...(query.trim() ? searchMatches.map((match) => match.page_index) : []),
      ...(passageFocus ? [passageFocus.page_index] : []),
      ...annotations
        .map((annotation) => annotation.selector.page_index)
        .filter((index): index is number => Boolean(index)),
    ]);
    pageIndexes.forEach((pageIndex) => {
      const payload = pagePayloads[pageIndex];
      const match = query.trim()
        ? searchMatches.find((item) => item.page_index === pageIndex)
        : undefined;
      const focusedPassage = passageFocus?.page_index === pageIndex
        ? passageFocus
        : undefined;
      result[pageIndex] = {
        sourceWidth: payload?.width || match?.width || focusedPassage?.width || 0,
        sourceHeight: payload?.height || match?.height || focusedPassage?.height || 0,
        canonicalBlocks: payload?.blocks ?? [],
        highlights: [
          ...(focusedPassage?.bbox?.length === 4
            ? [{
                bbox: focusedPassage.bbox,
                kind: "search" as const,
              }]
            : []),
          ...(match?.highlights ?? []).map((highlight) => ({
            bbox: highlight.bbox,
            kind: "search" as const,
          })),
          ...annotations
            .filter((annotation) => annotation.selector.page_index === pageIndex)
            .flatMap((annotation) =>
              (annotation.selector.bboxes ?? []).map((bbox) => ({
                bbox,
                kind: annotation.kind,
              })),
            ),
        ],
        notes: annotations
          .filter(
            (annotation) =>
              annotation.kind === "note"
              && annotation.selector.page_index === pageIndex,
          )
          .map((annotation) => ({
            id: annotation.id,
            bbox: annotation.selector.bboxes?.[0] ?? null,
            body: annotation.body_text,
            quote: annotation.quote,
            createdAt: formatReaderTimestamp(annotation.created_at),
            focused: annotation.id === focusedAnnotationId,
          })),
      };
    });
    return result;
  }, [annotations, focusedAnnotationId, pagePayloads, passageFocus, query, searchMatches]);
  const readerOutline = outline.map((item) => [item.chapter_title, item.index] as const);
  const currentOutline = [...outline]
    .reverse()
    .find((item) => item.index <= page);
  const thumbnailPages = useMemo(() => {
    if (totalPages <= 400) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }
    const start = Math.max(1, Math.min(page - 120, totalPages - 239));
    return Array.from({ length: 240 }, (_, index) => start + index);
  }, [page, totalPages]);
  const bookmarkedPage = Boolean(
    currentPagePayload &&
    bookmarks.some((bookmark) => bookmark.page === currentPagePayload.page_id),
  );
  const onDocumentLoad = useCallback((pages: number) => {
    setDocumentPages(pages);
  }, []);
  const onVisiblePageChange = useCallback((visiblePage: number) => {
    setPage((current) => current === visiblePage ? current : visiblePage);
  }, []);

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("page", String(page));
    window.history.replaceState(window.history.state, "", url);
  }, [page]);

  function protectedAction(label: string) {
    if (!readerAuthenticated) {
      setGate(label);
      return;
    }
    setGate(null);
    if (label === "书签") {
      void toggleBookmark();
      return;
    }
    if (label === "笔记") {
      beginAnnotation("note");
      return;
    }
    beginAnnotation("highlight");
  }

  function captureSelection(clientX?: number, clientY?: number): SelectionSnapshot | null {
    const selection = window.getSelection();
    const quote = selection?.toString().trim() ?? "";
    if (!quote || !selection?.rangeCount) return null;
    const anchorElement = selection?.anchorNode instanceof Element
      ? selection.anchorNode
      : selection?.anchorNode?.parentElement;
    if (!anchorElement || !readerDocumentRef.current?.contains(anchorElement)) return null;
    const selectedStage = anchorElement?.closest<HTMLElement>(
      ".pdf-canvas-stage[data-page-number]",
    );
    const stage = selectedStage;
    const targetPage = Number(stage?.dataset.pageNumber) || page;
    const targetPagePayload = pagePayloads[targetPage];
    if (!stage || !targetPagePayload) {
      requestPagePayload(targetPage);
      setCopyStatus("该页规范文字层尚未就绪，请稍后再试");
      return null;
    }
    const range = selection.getRangeAt(0);
    const stageRect = stage.getBoundingClientRect();
    const rangeRects = Array.from(range.getClientRects())
      .filter((rect) => (
        rect.width > 1
        && rect.height > 1
        && rect.right > stageRect.left
        && rect.left < stageRect.right
        && rect.bottom > stageRect.top
        && rect.top < stageRect.bottom
      ));
    const bboxes =
      rangeRects.map((rect) => [
        Math.max(0, ((rect.left - stageRect.left) / stageRect.width) * targetPagePayload.width),
        Math.max(0, ((rect.top - stageRect.top) / stageRect.height) * targetPagePayload.height),
        Math.min(targetPagePayload.width, ((rect.right - stageRect.left) / stageRect.width) * targetPagePayload.width),
        Math.min(targetPagePayload.height, ((rect.bottom - stageRect.top) / stageRect.height) * targetPagePayload.height),
      ]);
    if (!bboxes.length) return null;
    const lastRect = rangeRects.at(-1);
    return {
      pageIndex: targetPage,
      pageId: targetPagePayload.page_id,
      quote,
      bboxes,
      x: Math.min(
        Math.max(clientX ?? lastRect?.left ?? stageRect.left, 12),
        Math.max(window.innerWidth - 330, 12),
      ),
      y: Math.min(
        Math.max(clientY ?? (lastRect?.bottom ?? stageRect.top) + 10, 12),
        Math.max(window.innerHeight - 70, 12),
      ),
    };
  }

  function showSelectionTools(event: ReactMouseEvent<HTMLElement>) {
    window.setTimeout(() => {
      const snapshot = captureSelection(event.clientX, event.clientY + 8);
      setSelectionTools(snapshot);
    }, 0);
  }

  function showSelectionContextMenu(event: ReactMouseEvent<HTMLElement>) {
    const snapshot = captureSelection(event.clientX, event.clientY);
    if (!snapshot) return;
    event.preventDefault();
    setSelectionTools(snapshot);
  }

  function beginAnnotation(
    kind: AnnotationDraft["kind"],
    snapshot: SelectionSnapshot | null = captureSelection(),
  ) {
    if (!readerAuthenticated) {
      setGate(kind === "note" ? "笔记" : kind === "underline" ? "划线" : "高亮");
      return;
    }
    if (!snapshot) {
      setCopyStatus("请先在 PDF 页面选择文字");
      return;
    }
    setPage(snapshot.pageIndex);
    const draft: AnnotationDraft = {
      kind,
      pageIndex: snapshot.pageIndex,
      pageId: snapshot.pageId,
      quote: snapshot.quote,
      bboxes: snapshot.bboxes,
      body: "",
    };
    setSelectionTools(null);
    if (kind === "note") {
      setAnnotationDraft(draft);
      return;
    }
    void persistAnnotation(draft);
  }

  async function persistAnnotation(draft: AnnotationDraft) {
    if (!readerAuthenticated) {
      setGate(draft.kind === "note" ? "笔记" : draft.kind === "underline" ? "划线" : "高亮");
      return;
    }
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const created = await apiRequest<ReaderAnnotation>(
        "/reading/annotations/",
        {
          method: "POST",
          body: JSON.stringify({
            asset: work.id,
            page: draft.pageId,
            kind: draft.kind,
            quote: draft.quote,
            body: draft.body,
            color: "yellow",
            selector: {
              type: "TextQuoteSelector",
              exact: draft.quote,
              page_index: draft.pageIndex,
              bboxes: draft.bboxes,
            },
          }),
        },
        token,
      );
      setAnnotations((items) => [created, ...items]);
      setAnnotationDraft(null);
      setFocusedAnnotationId(created.id);
      setCopyStatus(draft.kind === "note" ? "笔记已保存" : draft.kind === "underline" ? "划线已保存" : "高亮已保存");
      window.getSelection()?.removeAllRanges();
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "批注保存失败");
    }
  }

  async function saveAnnotation() {
    if (annotationDraft) await persistAnnotation(annotationDraft);
  }

  async function deleteAnnotation(annotationId: string) {
    if (!readerAuthenticated) return;
    const annotation = annotations.find((item) => item.id === annotationId);
    if (!annotation || !window.confirm(`确定删除这条${annotation.kind === "note" ? "笔记" : annotation.kind === "underline" ? "划线" : "高亮"}吗？`)) {
      return;
    }
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      await apiRequest(`/reading/annotations/${annotationId}/`, { method: "DELETE" }, token);
      setAnnotations((items) => items.filter((item) => item.id !== annotationId));
      if (focusedAnnotationId === annotationId) setFocusedAnnotationId("");
      setCopyStatus("个人阅读记录已删除");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "删除失败");
    }
  }

  async function deleteBookmark(bookmarkId: string) {
    if (!readerAuthenticated) return;
    if (!window.confirm("确定删除这个书签吗？")) return;
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      await apiRequest(`/reading/bookmarks/${bookmarkId}/`, { method: "DELETE" }, token);
      setBookmarks((items) => items.filter((item) => item.id !== bookmarkId));
      setCopyStatus("书签已删除");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "书签删除失败");
    }
  }

  async function toggleBookmark(snapshot?: SelectionSnapshot | null) {
    if (!readerAuthenticated) {
      setGate("书签");
      return;
    }
    const token = getServerSessionCredential();
    if (!token) {
      setGate("书签");
      return;
    }
    const targetPagePayload = snapshot
      ? pagePayloads[snapshot.pageIndex]
      : currentPagePayload;
    const targetPageIndex = snapshot?.pageIndex ?? page;
    if (!targetPagePayload) {
      setCopyStatus("页面信息尚未就绪");
      return;
    }
    const existing = bookmarks.find((bookmark) => bookmark.page === targetPagePayload.page_id);
    try {
      if (existing) {
        await apiRequest(
          `/reading/bookmarks/${existing.id}/`,
          { method: "DELETE" },
          token,
        );
        setBookmarks((items) => items.filter((bookmark) => bookmark.id !== existing.id));
        setCopyStatus("书签已移除");
      } else {
        const created = await apiRequest<ReaderBookmark>(
          "/reading/bookmarks/",
          {
            method: "POST",
            body: JSON.stringify({
              asset: work.id,
              page: targetPagePayload.page_id,
              label: targetPagePayload.chapter_title || `PDF 第 ${targetPageIndex} 页`,
            }),
          },
          token,
        );
        setBookmarks((items) => [created, ...items]);
        setCopyStatus("书签已保存");
      }
      setSelectionTools(null);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "书签操作失败");
    }
  }

  function cleanTextLocally(value: string) {
    return value
      .replace(/\u00ad/g, "")
      .replace(/(\p{L})-\s*\n\s*(\p{L})/gu, "$1$2")
      .replace(/[ \t]*\n[ \t]*\n+[ \t]*/g, "\n\n")
      .replace(/[ \t]*\n[ \t]*/g, " ")
      .replace(/[ \t]{2,}/g, " ")
      .replace(/\s+([,.;:!?，。；：！？])/g, "$1")
      .trim();
  }

  function handleDocumentCopy(event: ReactClipboardEvent<HTMLElement>) {
    const selection = window.getSelection();
    const selected = selection?.toString() ?? "";
    const anchorElement = selection?.anchorNode instanceof Element
      ? selection.anchorNode
      : selection?.anchorNode?.parentElement;
    if (!selected.trim() || !anchorElement || !readerDocumentRef.current?.contains(anchorElement)) return;
    event.preventDefault();
    event.clipboardData.setData("text/plain", cleanTextLocally(selected));
    setCopyStatus("已自动清理复制格式");
  }

  async function cleanCopy(selectedText?: string) {
    const selected = selectedText?.trim() || window.getSelection()?.toString().trim();
    if (!selected) {
      setCopyStatus("请先选择正文");
      return;
    }
    try {
      const payload = await apiRequest<{ text: string; html: string }>("/catalog/clean-copy/", {
        method: "POST",
        body: JSON.stringify({ text: selected }),
      });
      if ("ClipboardItem" in window && navigator.clipboard.write) {
        await navigator.clipboard.write([
          new ClipboardItem({
            "text/plain": new Blob([payload.text], { type: "text/plain" }),
            "text/html": new Blob([payload.html], { type: "text/html" }),
          }),
        ]);
      } else {
        await navigator.clipboard.writeText(payload.text);
      }
      setCopyStatus("已清理并复制");
    } catch {
      await navigator.clipboard.writeText(cleanTextLocally(selected));
      setCopyStatus("已在浏览器中清理并复制");
    }
    setSelectionTools(null);
    window.getSelection()?.removeAllRanges();
  }

  async function copyCitation() {
    const text = citations?.[citationStyle];
    if (!text) {
      setCopyStatus("引用数据尚未就绪");
      return;
    }
    await navigator.clipboard.writeText(text);
    setCopyStatus("引用已复制");
  }

  function jumpToFirstSearchMatch() {
    if (searchMatches[0]) {
      jumpToSearchMatch(0);
    }
  }

  function jumpToSearchMatch(index: number) {
    const match = searchMatches[index];
    if (!match) return;
    setActiveSearchMatch(index);
    setSearchCandidatesOpen(false);
    setPassageFocus(null);
    requestPagePayload(match.page_index);
    jumpToPage(match.page_index);
  }

  function setRightPanel(open: boolean) {
    if (isCompact) setCompactRightOpen(open);
    else setRightOpen(open);
  }

  function showSidebarTab(tab: SidebarTab, label?: string) {
    if (
      label
      && !readerAuthenticated
      && ["highlights", "bookmarks", "notes"].includes(tab)
    ) {
      setGate(label);
      return;
    }
    setSidebarTab(tab);
    setLeftPanel(true);
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
          {access ? <a href={access.download_url || access.url} download={access.download_filename} title={access.download_rendition === "ocr_pdf" ? "下载可搜索 OCR 版" : "下载原始 PDF"} onClick={() => { void apiRequest("/catalog/usage-events/", { method: "POST", body: JSON.stringify({ event_type: "download", asset_id: work.id, work_id: work.workId, source: "reader" }) }).catch(() => undefined); }}><Download size={18} /><span>{access.download_rendition === "ocr_pdf" ? "下载 OCR 版" : "下载"}</span></a> : <button type="button" disabled><Download size={18} /><span>下载</span></button>}
          <button type="button" onClick={() => protectedAction("批注")}><Highlighter size={18} /><span>批注</span></button>
          <button className={bookmarkedPage ? "active" : ""} type="button" onClick={() => protectedAction("书签")}><Bookmark size={18} fill={bookmarkedPage ? "currentColor" : "none"} /><span>书签</span></button>
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
                <button className="reader-library-delete" type="button" aria-label={`删除第 ${annotation.selector.page_index || 1} 页${annotation.kind === "underline" ? "划线" : "高亮"}`} onClick={() => void deleteAnnotation(annotation.id)}><Trash2 size={14} /></button>
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
                <button className="reader-library-delete" type="button" aria-label={`删除第 ${bookmark.page_index || 1} 页书签`} onClick={() => void deleteBookmark(bookmark.id)}><Trash2 size={14} /></button>
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
                <button className="reader-library-delete" type="button" aria-label={`删除第 ${annotation.selector.page_index || 1} 页笔记`} onClick={() => void deleteAnnotation(annotation.id)}><Trash2 size={14} /></button>
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
        <span className="reader-copy-status" aria-live="polite">{copyStatus}</span>
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
          <button type="button" onClick={() => void toggleBookmark(selectionTools)}><Bookmark size={15} />书签</button>
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
            <button className="button" type="submit">保存笔记</button>
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
