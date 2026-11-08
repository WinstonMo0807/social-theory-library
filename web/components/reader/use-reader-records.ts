"use client";

import { confirmAction } from "@/lib/ui-dialog";

import { createRequestKey } from "../../lib/request-key";
import { useCallback, useEffect, useEffectEvent, useLayoutEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
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
  readerId?: number;
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

type AnnotationSavePayload = {
  request_id: string; asset: string; page: string; kind: AnnotationDraft["kind"];
  quote: string; body: string; tags: string[]; color: string;
  selector: { type: string; exact: string; page_index: number; bboxes: number[][] };
};
type AnnotationSaveRequest = {
  identity: string; owner: string; payload: AnnotationSavePayload; body: string;
  sourceDraft: AnnotationDraft; unknown: boolean;
};

/** A UUID alone cannot confirm that an unknown write saved this exact note. */
export function annotationReceiptMatches(record: ReaderAnnotation, payload: AnnotationSavePayload) {
  const selector = record.selector;
  return record.id === payload.request_id && record.asset === payload.asset && record.page === payload.page &&
    record.kind === payload.kind && record.quote === payload.quote && record.body_text === payload.body &&
    record.color === payload.color && JSON.stringify(record.tags ?? []) === JSON.stringify(payload.tags) &&
    Boolean(selector) && selector.type === payload.selector.type && selector.exact === payload.selector.exact &&
    selector.page_index === payload.selector.page_index &&
    JSON.stringify(selector.bboxes) === JSON.stringify(payload.selector.bboxes) &&
    JSON.stringify(Object.keys(selector).sort()) === JSON.stringify(Object.keys(payload.selector).sort());
}

/** Private per-reader records retain the existing API, selectors and mutation guard. */
export function useReaderRecords({
  assetId, initialFocus, readerAuthenticated, readerId, page, pagePayloads, captureSelection,
  setSelectionTools, setPage, jumpToPage, setLeftPanel, setSidebarTab, setGate,
  setCopyStatus, setCopyStatusState,
}: ReaderRecordsOptions) {
  const [annotations, setAnnotations] = useState<ReaderAnnotation[]>([]);
  const [bookmarks, setBookmarks] = useState<ReaderBookmark[]>([]);
  const [loadedIdentity, setLoadedIdentity] = useState("");
  const identity = readerAuthenticated && readerId !== undefined ? `${readerId}:${assetId}` : "";
  const [recordsAttempt, setRecordsAttempt] = useState(0);
  const [recordsState, setRecordsState] = useState<{
    identity: string; status: "loading" | "ready" | "error" | "stopped"; error: string;
  }>({ identity: "", status: "loading", error: "" });
  const recordsRequest = useRef<{ identity: string; controller: AbortController } | null>(null);
  const annotationSaveRequest = useRef<AnnotationSaveRequest | null>(null);
  const [annotationSaveState, setAnnotationSaveState] = useState({ identity: "", unknown: false });
  const annotationSaveUnknown = annotationSaveState.identity === identity && annotationSaveState.unknown;
  const activeIdentity = useRef(identity);
  useLayoutEffect(() => {
    activeIdentity.current = identity;
    return () => { activeIdentity.current = ""; };
  }, [identity]);
  const [draftState, setDraftState] = useState<{ identity: string; value: AnnotationDraft | null }>({ identity: "", value: null });
  const annotationDraft = draftState.identity === identity ? draftState.value : null;
  const setAnnotationDraft = useCallback<Dispatch<SetStateAction<AnnotationDraft | null>>>((next) => {
    if (annotationSaveRequest.current?.identity === identity) return;
    setDraftState(current => ({
      identity,
      value: typeof next === "function" ? next(current.identity === identity ? current.value : null) : next,
    }));
  }, [identity]);
  const [focusedAnnotationId, setFocusedAnnotationId] = useState(initialFocus);
  const { pendingAction, startAction, finishAction } = useActionGuard();
  const currentPagePayload = pagePayloads[page] ?? null;
  const recordsReady = Boolean(identity && loadedIdentity === identity && recordsState.identity === identity && recordsState.status === "ready");
  const bookmarkedPage = Boolean(
    recordsReady && currentPagePayload &&
    bookmarks.some((bookmark) => bookmark.page === currentPagePayload.page_id),
  );

  useEffect(() => {
    // A draft belongs to the previous authenticated owner just like saved records.
    let active = true;
    queueMicrotask(() => { if (active) { setAnnotationDraft(null); setFocusedAnnotationId(initialFocus); } });
    return () => { active = false; };
  }, [identity, initialFocus, setAnnotationDraft]);

  const focusLoadedRecord = useEffectEvent(() => {
    if (!initialFocus) return;
    const focused = annotations.find((item) => item.id === initialFocus);
    if (!focused) return;
    jumpToPage(focused.selector.page_index || 1, "auto");
    setSidebarTab(focused.kind === "note" ? "notes" : "highlights");
    setLeftPanel(true);
    setFocusedAnnotationId(focused.id);
  });
  useEffect(() => {
    let active = true;
    if (recordsReady) queueMicrotask(() => { if (active) focusLoadedRecord(); });
    return () => { active = false; };
  }, [initialFocus, recordsReady]);

  const stopRecords = useCallback(() => {
    const current = recordsRequest.current;
    if (!current || current.identity !== identity) return;
    current.controller.abort();
    recordsRequest.current = null;
    setLoadedIdentity("");
    setRecordsState({ identity, status: "stopped", error: "" });
  }, [identity]);

  const retryRecords = useCallback(() => {
    if (!identity) return;
    recordsRequest.current?.controller.abort();
    recordsRequest.current = null;
    setLoadedIdentity("");
    setRecordsState({ identity, status: "loading", error: "" });
    setRecordsAttempt(value => value + 1);
  }, [identity]);

  useEffect(() => {
    if (!identity || readerId === undefined) {
      queueMicrotask(() => {
        setAnnotations([]);
        setBookmarks([]);
        setLoadedIdentity("");
      });
      return;
    }
    const token = getServerSessionCredential();
    const request = new AbortController();
    recordsRequest.current = { identity, controller: request };
    queueMicrotask(() => {
      if (request.signal.aborted || activeIdentity.current !== identity) return;
      setLoadedIdentity("");
      setRecordsState({ identity, status: token ? "loading" : "error", error: token ? "" : "请重新登录后读取个人阅读记录。" });
    });
    if (!token) return () => {
      request.abort();
      if (recordsRequest.current?.controller === request) recordsRequest.current = null;
    };
    // Both collections must finish before publishing a snapshot. A stopped or
    // failed load is explicitly incomplete; a partial array is never an empty library.
    Promise.all([
      readAllPages<ReaderAnnotation>(
        `/reading/annotations/?asset=${encodeURIComponent(assetId)}`,
        token,
        request.signal,
        String(readerId),
      ),
      readAllPages<ReaderBookmark>(
        `/reading/bookmarks/?asset=${encodeURIComponent(assetId)}`,
        token,
        request.signal,
        String(readerId),
      ),
    ])
      .then(([annotationPayload, bookmarkPayload]) => {
        if (request.signal.aborted || activeIdentity.current !== identity) return;
        setAnnotations(annotationPayload);
        setBookmarks(bookmarkPayload);
        setLoadedIdentity(identity);
        setRecordsState({ identity, status: "ready", error: "" });
      })
      .catch((reason: unknown) => {
        if (request.signal.aborted || activeIdentity.current !== identity) return;
        request.abort();
        setLoadedIdentity("");
        setRecordsState({
          identity, status: "error",
          error: reason instanceof Error ? reason.message : "个人阅读记录尚未完整读取，请重试。",
        });
      })
      .finally(() => {
        if (recordsRequest.current?.controller === request) recordsRequest.current = null;
      });
    return () => {
      request.abort();
      if (recordsRequest.current?.controller === request) recordsRequest.current = null;
    };
  }, [readerId, identity, assetId, recordsAttempt]);

  async function beginAnnotation(
    kind: AnnotationDraft["kind"],
    snapshot: SelectionSnapshot | null = captureSelection(),
  ): Promise<boolean> {
    if (!readerAuthenticated) {
      setGate(kind === "note" ? "笔记" : kind === "underline" ? "划线" : "高亮");
      return false;
    }
    if (pendingAction) return false;
    if (annotationSaveRequest.current?.identity === identity) {
      setCopyStatus("上次批注保存状态尚未确认，请先查询原请求。");
      setCopyStatusState("error");
      return false;
    }
    if (!recordsReady) {
      setCopyStatus("个人阅读记录尚未完整读取，请先完成加载或重试。");
      setCopyStatusState("idle");
      return false;
    }
    if (!snapshot) {
      setCopyStatus("请先在 PDF 页面选择文字");
      setCopyStatusState("idle");
      return false;
    }
    if (kind === "note" && annotationDraft) {
      if (annotationDraft.pageId === snapshot.pageId && annotationDraft.quote === snapshot.quote &&
          JSON.stringify(annotationDraft.bboxes) === JSON.stringify(snapshot.bboxes)) return true;
      if ((annotationDraft.body.trim() || annotationDraft.tags?.length) &&
          !(await confirmAction("已有笔记尚未保存，改为记录这段原文会丢失当前输入。仍要继续吗？"))) return false;
    }
    setPage(snapshot.pageIndex);
    const draft: AnnotationDraft = {
      kind,
      pageIndex: snapshot.pageIndex,
      pageId: snapshot.pageId,
      quote: snapshot.quote,
      bboxes: snapshot.bboxes,
      body: "",
      tags: [],
    };
    setSelectionTools(null);
    if (kind === "note") {
      setAnnotationDraft(draft);
      return true;
    }
    void persistAnnotation(draft);
    return true;
  }

  async function persistAnnotation(draft: AnnotationDraft, finalTags?: string[]): Promise<boolean> {
    if (!readerAuthenticated) {
      setGate(draft.kind === "note" ? "笔记" : draft.kind === "underline" ? "划线" : "高亮");
      return false;
    }
    if (!recordsReady) {
      setCopyStatus("个人阅读记录尚未完整读取，请稍后重试。");
      setCopyStatusState("idle");
      return false;
    }
    if (annotationSaveRequest.current?.identity === identity) {
      setCopyStatus("上次批注保存状态尚未确认，请先查询原请求。");
      setCopyStatusState("error");
      return false;
    }
    const payload: AnnotationSavePayload = {
      request_id: createRequestKey(), asset: assetId, page: draft.pageId, kind: draft.kind,
      quote: draft.quote.trim(), body: draft.body.trim(),
      tags: [...new Set((finalTags ?? draft.tags ?? []).map(tag => tag.trim()).filter(Boolean))],
      color: "yellow",
      selector: { type: "TextQuoteSelector", exact: draft.quote, page_index: draft.pageIndex, bboxes: draft.bboxes },
    };
    return sendAnnotationSave({
      identity, owner: String(readerId), payload, body: JSON.stringify(payload), sourceDraft: draft, unknown: false,
    }, false);
  }

  async function sendAnnotationSave(operation: AnnotationSaveRequest, lookup: boolean): Promise<boolean> {
    if (!identity || activeIdentity.current !== operation.identity) return false;
    const token = getServerSessionCredential();
    if (!token) return false;
    const actionKey = "save-annotation";
    if (!startAction(actionKey)) return false;
    annotationSaveRequest.current = operation;
    setCopyStatus(lookup ? "正在核对上次批注保存状态……" : operation.payload.kind === "note" ? "正在保存笔记……" : operation.payload.kind === "underline" ? "正在保存划线……" : "正在保存高亮……");
    setCopyStatusState("pending");
    try {
      const headers = { "X-Reader-Owner": operation.owner };
      let created: ReaderAnnotation | null = null;
      if (lookup) {
        try {
          created = await apiRequest<ReaderAnnotation>(`/reading/annotations/${operation.payload.request_id}/`,
            { headers, cache: "no-store", signal: AbortSignal.timeout(30000) }, token, false);
        } catch (error) {
          if (!(error instanceof ApiRequestError) || error.status !== 404) throw error;
        }
      }
      if (activeIdentity.current !== operation.identity) return false;
      if (!created) created = await apiRequest<ReaderAnnotation>("/reading/annotations/", {
        method: "POST", headers, body: operation.body, signal: AbortSignal.timeout(30000),
      }, token, false);
      if (activeIdentity.current !== operation.identity) return false;
      if (!annotationReceiptMatches(created, operation.payload)) {
        throw new ApiRequestError("保存结果与本次批注不一致，请保留输入并继续核对原请求。", 409);
      }
      annotationSaveRequest.current = null;
      setAnnotationSaveState({ identity, unknown: false });
      const saved = created;
      setAnnotations((items) => [saved, ...items.filter(item => item.id !== saved.id)]);
      // Saving a highlight must not discard an open note. Nor may a delayed
      // save response clear a draft that has been edited since submission.
      setAnnotationDraft(current => current === operation.sourceDraft ? null : current);
      setFocusedAnnotationId(created.id);
      setCopyStatus(operation.payload.kind === "note" ? "笔记已保存" : operation.payload.kind === "underline" ? "划线已保存" : "高亮已保存");
      setCopyStatusState("success");
      window.getSelection()?.removeAllRanges();
      return true;
    } catch (error) {
      if (activeIdentity.current !== operation.identity) return false;
      operation.unknown = operation.unknown || !(error instanceof ApiRequestError) || error.status === 0 || error.status >= 500 || error.status === 409;
      if (!operation.unknown) annotationSaveRequest.current = null;
      setAnnotationSaveState({ identity, unknown: operation.unknown });
      setCopyStatus(`${error instanceof Error ? error.message : "批注保存失败"}${operation.unknown ? " 上次保存尚未确认，原输入与请求已保留，请查询后继续。" : ""}`);
      setCopyStatusState("error");
      return false;
    } finally {
      finishAction(actionKey);
    }
  }

  async function saveAnnotation(finalTags?: string[]): Promise<boolean> {
    return annotationDraft ? persistAnnotation(annotationDraft, finalTags) : false;
  }

  async function retryAnnotationSave(): Promise<boolean> {
    const operation = annotationSaveRequest.current;
    return operation?.unknown && operation.identity === identity ? sendAnnotationSave(operation, true) : false;
  }

  async function deleteAnnotation(annotationId: string) {
    if (!recordsReady) return;
    const annotation = annotations.find((item) => item.id === annotationId);
    if (!annotation || !(await confirmAction(`确定删除这条${annotation.kind === "note" ? "笔记" : annotation.kind === "underline" ? "划线" : "高亮"}吗？`))) {
      return;
    }
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `delete-annotation:${annotationId}`;
    if (!startAction(actionKey)) return;
    setCopyStatus("正在删除个人阅读记录……");
    setCopyStatusState("pending");
    try {
      await apiRequest(`/reading/annotations/${annotationId}/`, { method: "DELETE", headers: { "X-Reader-Owner": String(readerId) } }, token, false);
      if (activeIdentity.current !== identity) return;
      setAnnotations((items) => items.filter((item) => item.id !== annotationId));
      if (focusedAnnotationId === annotationId) setFocusedAnnotationId("");
      setCopyStatus("个人阅读记录已删除");
      setCopyStatusState("success");
    } catch (error) {
      if (activeIdentity.current !== identity) return;
      setCopyStatus(error instanceof Error ? error.message : "删除失败");
      setCopyStatusState("error");
    } finally {
      finishAction(actionKey);
    }
  }

  async function deleteBookmark(bookmarkId: string) {
    if (!recordsReady || !bookmarks.some(item => item.id === bookmarkId)) return;
    if (!(await confirmAction("确定删除这个书签吗？"))) return;
    const token = getServerSessionCredential();
    if (!token) return;
    const actionKey = `delete-bookmark:${bookmarkId}`;
    if (!startAction(actionKey)) return;
    setCopyStatus("正在删除书签……");
    setCopyStatusState("pending");
    try {
      await apiRequest(`/reading/bookmarks/${bookmarkId}/`, { method: "DELETE", headers: { "X-Reader-Owner": String(readerId) } }, token, false);
      if (activeIdentity.current !== identity) return;
      setBookmarks((items) => items.filter((item) => item.id !== bookmarkId));
      setCopyStatus("书签已删除");
      setCopyStatusState("success");
    } catch (error) {
      if (activeIdentity.current !== identity) return;
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
    if (!recordsReady) {
      setCopyStatus("书签尚未完整读取，请稍后重试，避免重复保存。");
      setCopyStatusState("idle");
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
          { method: "DELETE", headers: { "X-Reader-Owner": String(readerId) } },
          token,
          false,
        );
        if (activeIdentity.current !== identity) return;
        setBookmarks((items) => items.filter((bookmark) => bookmark.id !== existing.id));
        setCopyStatus("书签已移除");
        setCopyStatusState("success");
      } else {
        const created = await apiRequest<ReaderBookmark>(
          "/reading/bookmarks/",
          {
            method: "POST",
            headers: { "X-Reader-Owner": String(readerId) },
            body: JSON.stringify({
              asset: assetId,
              page: targetPagePayload.page_id,
              label: targetPagePayload.chapter_title || `PDF 第 ${targetPageIndex} 页`,
            }),
          },
          token,
          false,
        );
        if (activeIdentity.current !== identity) return;
        setBookmarks((items) => [created, ...items]);
        setCopyStatus("书签已保存");
        setCopyStatusState("success");
      }
      setSelectionTools(null);
    } catch (error) {
      if (activeIdentity.current !== identity) return;
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
    annotations: recordsReady ? annotations : [],
    bookmarks: recordsReady ? bookmarks : [],
    annotationDraft: identity ? annotationDraft : null,
    setAnnotationDraft,
    focusedAnnotationId,
    setFocusedAnnotationId,
    bookmarkedPage,
    recordsReady,
    recordsLoading: Boolean(identity && (recordsState.identity !== identity || recordsState.status === "loading")),
    recordsError: recordsState.identity === identity ? recordsState.error : "",
    recordsStopped: Boolean(identity && recordsState.identity === identity && recordsState.status === "stopped"),
    stopRecords,
    retryRecords,
    pendingAction,
    annotationSaveUnknown,
    retryAnnotationSave,
    beginAnnotation,
    saveAnnotation,
    deleteAnnotation,
    deleteBookmark,
    toggleBookmark,
    protectedAction,
    showSidebarTab,
  };
}
