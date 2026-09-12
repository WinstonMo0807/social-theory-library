"use client";

import { useEffect, useState, type Dispatch, type SetStateAction } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useActionGuard } from "@/lib/use-action-guard";
import type { ActionState } from "../action-feedback";
import type {
  AnnotationDraft,
  PagePayload,
  ReaderAnnotation,
  ReaderBookmark,
  SelectionSnapshot,
  SidebarTab,
} from "./types";

type ReaderRecordsOptions = {
  assetId: string;
  initialFocus: string;
  readerAuthenticated: boolean;
  page: number;
  pagePayloads: Record<number, PagePayload>;
  captureSelection: (clientX?: number, clientY?: number) => SelectionSnapshot | null;
  setSelectionTools: Dispatch<SetStateAction<SelectionSnapshot | null>>;
  setPage: Dispatch<SetStateAction<number>>;
  jumpToPage: (target: number, behavior?: ScrollBehavior) => void;
  setLeftPanel: (open: boolean) => void;
  setSidebarTab: Dispatch<SetStateAction<SidebarTab>>;
  setGate: Dispatch<SetStateAction<string | null>>;
  setCopyStatus: Dispatch<SetStateAction<string>>;
  setCopyStatusState: Dispatch<SetStateAction<ActionState>>;
};

/** Private per-reader records retain the existing API, selectors and mutation guard. */
export function useReaderRecords({
  assetId, initialFocus, readerAuthenticated, page, pagePayloads, captureSelection,
  setSelectionTools, setPage, jumpToPage, setLeftPanel, setSidebarTab, setGate,
  setCopyStatus, setCopyStatusState,
}: ReaderRecordsOptions) {
  const [annotations, setAnnotations] = useState<ReaderAnnotation[]>([]);
  const [bookmarks, setBookmarks] = useState<ReaderBookmark[]>([]);
  const [annotationDraft, setAnnotationDraft] = useState<AnnotationDraft | null>(null);
  const [focusedAnnotationId, setFocusedAnnotationId] = useState(initialFocus);
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const currentPagePayload = pagePayloads[page] ?? null;
  const bookmarkedPage = Boolean(
    currentPagePayload &&
    bookmarks.some((bookmark) => bookmark.page === currentPagePayload.page_id),
  );

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
        `/reading/annotations/?asset=${encodeURIComponent(assetId)}`,
        {},
        token,
      ),
      apiRequest<{ results: ReaderBookmark[] }>(
        `/reading/bookmarks/?asset=${encodeURIComponent(assetId)}`,
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
  }, [initialFocus, jumpToPage, readerAuthenticated, setLeftPanel, setSidebarTab, assetId]);

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
      setCopyStatusState("idle");
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
    const actionKey = "save-annotation";
    if (!startAction(actionKey)) return;
    setCopyStatus(draft.kind === "note" ? "正在保存笔记……" : draft.kind === "underline" ? "正在保存划线……" : "正在保存高亮……");
    setCopyStatusState("pending");
    try {
      const created = await apiRequest<ReaderAnnotation>(
        "/reading/annotations/",
        {
          method: "POST",
          body: JSON.stringify({
            asset: assetId,
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
      setCopyStatusState("success");
      window.getSelection()?.removeAllRanges();
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "批注保存失败");
      setCopyStatusState("error");
    } finally {
      finishAction(actionKey);
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
    const actionKey = `delete-annotation:${annotationId}`;
    if (!startAction(actionKey)) return;
    setCopyStatus("正在删除个人阅读记录……");
    setCopyStatusState("pending");
    try {
      await apiRequest(`/reading/annotations/${annotationId}/`, { method: "DELETE" }, token);
      setAnnotations((items) => items.filter((item) => item.id !== annotationId));
      if (focusedAnnotationId === annotationId) setFocusedAnnotationId("");
      setCopyStatus("个人阅读记录已删除");
      setCopyStatusState("success");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "删除失败");
      setCopyStatusState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function deleteBookmark(bookmarkId: string) {
    if (!readerAuthenticated) return;
    if (!window.confirm("确定删除这个书签吗？")) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `delete-bookmark:${bookmarkId}`;
    if (!startAction(actionKey)) return;
    setCopyStatus("正在删除书签……");
    setCopyStatusState("pending");
    try {
      await apiRequest(`/reading/bookmarks/${bookmarkId}/`, { method: "DELETE" }, token);
      setBookmarks((items) => items.filter((item) => item.id !== bookmarkId));
      setCopyStatus("书签已删除");
      setCopyStatusState("success");
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "书签删除失败");
      setCopyStatusState("error");
    } finally {
      finishAction(actionKey);
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
      setCopyStatusState("idle");
      return;
    }
    const existing = bookmarks.find((bookmark) => bookmark.page === targetPagePayload.page_id);
    const actionKey = `toggle-bookmark:${targetPagePayload.page_id}`;
    if (!startAction(actionKey)) return;
    setCopyStatus(existing ? "正在移除书签……" : "正在保存书签……");
    setCopyStatusState("pending");
    try {
      if (existing) {
        await apiRequest(
          `/reading/bookmarks/${existing.id}/`,
          { method: "DELETE" },
          token,
        );
        setBookmarks((items) => items.filter((bookmark) => bookmark.id !== existing.id));
        setCopyStatus("书签已移除");
        setCopyStatusState("success");
      } else {
        const created = await apiRequest<ReaderBookmark>(
          "/reading/bookmarks/",
          {
            method: "POST",
            body: JSON.stringify({
              asset: assetId,
              page: targetPagePayload.page_id,
              label: targetPagePayload.chapter_title || `PDF 第 ${targetPageIndex} 页`,
            }),
          },
          token,
        );
        setBookmarks((items) => [created, ...items]);
        setCopyStatus("书签已保存");
        setCopyStatusState("success");
      }
      setSelectionTools(null);
    } catch (error) {
      setCopyStatus(error instanceof Error ? error.message : "书签操作失败");
      setCopyStatusState("error");
    } finally {
      finishAction(actionKey);
    }
  }

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

  return {
    annotations,
    bookmarks,
    annotationDraft,
    setAnnotationDraft,
    focusedAnnotationId,
    setFocusedAnnotationId,
    bookmarkedPage,
    pendingAction,
    beginAnnotation,
    saveAnnotation,
    deleteAnnotation,
    deleteBookmark,
    toggleBookmark,
    protectedAction,
    showSidebarTab,
  };
}
