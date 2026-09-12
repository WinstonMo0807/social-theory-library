"use client";

import {
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
  type ClipboardEvent as ReactClipboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { apiRequest } from "@/lib/api";
import type { ActionState } from "../action-feedback";
import type { PagePayload, SelectionSnapshot } from "./types";

export function cleanTextLocally(value: string) {
  return value
    .replace(/\u00ad/g, "")
    .replace(/(\p{L})-\s*\n\s*(\p{L})/gu, "$1$2")
    .replace(/[ \t]*\n[ \t]*\n+[ \t]*/g, "\n\n")
    .replace(/[ \t]*\n[ \t]*/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/\s+([,.;:!?，。；：！？])/g, "$1")
    .trim();
}

/** Owns the document selection, text coordinate mapping and copy interactions. */
export function useReaderSelection({ page, pagePayloads, requestPagePayload, setCopyStatus, setCopyStatusState }: {
  page: number;
  pagePayloads: Record<number, PagePayload>;
  requestPagePayload: (page: number) => void;
  setCopyStatus: Dispatch<SetStateAction<string>>;
  setCopyStatusState: Dispatch<SetStateAction<ActionState>>;
}) {
  const readerDocumentRef = useRef<HTMLElement>(null);
  const [selectionTools, setSelectionTools] = useState<SelectionSnapshot | null>(null);

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
      setCopyStatusState("idle");
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
    setCopyStatusState("success");
  }

  async function cleanCopy(selectedText?: string) {
    const selected = selectedText?.trim() || window.getSelection()?.toString().trim();
    if (!selected) {
      setCopyStatus("请先选择正文");
      setCopyStatusState("idle");
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
      setCopyStatusState("success");
    } catch {
      await navigator.clipboard.writeText(cleanTextLocally(selected));
      setCopyStatus("已在浏览器中清理并复制");
      setCopyStatusState("success");
    }
    setSelectionTools(null);
    window.getSelection()?.removeAllRanges();
  }

  return {
    readerDocumentRef,
    selectionTools,
    setSelectionTools,
    captureSelection,
    showSelectionTools,
    showSelectionContextMenu,
    handleDocumentCopy,
    cleanCopy,
  };
}
