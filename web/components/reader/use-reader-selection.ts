"use client";

import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
  type ClipboardEvent as ReactClipboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { apiRequest } from "@/lib/api";
import { readerSelectionSourceBox, type ReaderRotation } from "@/lib/reader-coordinates";
import type { ActionState } from "../action-feedback";
import type { PagePayload, SelectionSnapshot } from "./types";

const editableSelector = "input,textarea,select,[role='textbox'],[contenteditable]:not([contenteditable='false'])";

function pdfTextElement(node: Node | null | undefined): Element | null {
  const element = node instanceof Element ? node : node?.parentElement;
  return element && !element.closest(editableSelector)
    && element.closest(".pdf-native-text-layer,.canonical-text-layer") ? element : null;
}

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
  const mouseUpTimer = useRef<number | undefined>(undefined);
  const [selectionTools, setSelectionTools] = useState<SelectionSnapshot | null>(null);

  function captureSelection(clientX?: number, clientY?: number): SelectionSnapshot | null {
    const selection = window.getSelection();
    const quote = selection?.toString().trim() ?? "";
    if (!quote || !selection?.rangeCount || document.activeElement?.matches(editableSelector)) return null;
    const anchorElement = pdfTextElement(selection.anchorNode);
    if (!anchorElement || !readerDocumentRef.current?.contains(anchorElement)) return null;
    const selectedStage = anchorElement?.closest<HTMLElement>(
      ".pdf-canvas-stage[data-page-number]",
    );
    const stage = selectedStage;
    if (!stage) return null;
    const targetPage = Number(stage?.dataset.pageNumber) || page;
    const targetPagePayload = pagePayloads[targetPage];
    if (!targetPagePayload) {
      requestPagePayload(targetPage);
      setCopyStatus("该页规范文字层尚未就绪，请稍后再试");
      setCopyStatusState("idle");
      return null;
    }
    const range = selection.getRangeAt(0);
    const endElement = pdfTextElement(range.endContainer);
    const startElement = pdfTextElement(range.startContainer);
    if (startElement?.closest(".pdf-canvas-stage") !== stage || endElement?.closest(".pdf-canvas-stage") !== stage) {
      setCopyStatus("跨页文字仍可直接复制；引用与笔记请逐页选择，避免页码与选文错配。");
      setCopyStatusState("idle");
      return null;
    }
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
    const stageRotation = Number(stage.dataset.readerRotation || 0);
    if (![0, 90, 180, 270].includes(stageRotation)) return null;
    const bboxes = rangeRects.flatMap((rect) => {
      const box = readerSelectionSourceBox([
        rect.left - stageRect.left, rect.top - stageRect.top,
        rect.right - stageRect.left, rect.bottom - stageRect.top,
      ], stageRect.width, stageRect.height, targetPagePayload.width, targetPagePayload.height, stageRotation as ReaderRotation);
      return box ? [box] : [];
    });
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

  const updateTouchSelection = useEffectEvent(() => {
    const snapshot = captureSelection();
    // Only the floating menu follows the live DOM selection. The source-panel
    // retained selection and any unfinished note draft belong to ReaderShell.
    setSelectionTools(current => {
      if (current && snapshot && current.pageId === snapshot.pageId
        && current.quote === snapshot.quote && JSON.stringify(current.bboxes) === JSON.stringify(snapshot.bboxes)) return current;
      return snapshot;
    });
  });

  useEffect(() => {
    let timer: number | undefined;
    const changed = () => {
      if (timer !== undefined) window.clearTimeout(timer);
      const selection = window.getSelection();
      if (!selection || selection.isCollapsed || !selection.toString().trim()) {
        updateTouchSelection();
      } else {
        // Long-press handles produce selectionchange without mouseup on touch
        // browsers. Read the latest page payload only after the handles settle.
        timer = window.setTimeout(() => updateTouchSelection(), 100);
      }
    };
    document.addEventListener("selectionchange", changed);
    return () => {
      document.removeEventListener("selectionchange", changed);
      if (timer !== undefined) window.clearTimeout(timer);
      if (mouseUpTimer.current !== undefined) window.clearTimeout(mouseUpTimer.current);
    };
  }, []);

  function showSelectionTools(event: ReactMouseEvent<HTMLElement>) {
    if (mouseUpTimer.current !== undefined) window.clearTimeout(mouseUpTimer.current);
    mouseUpTimer.current = window.setTimeout(() => {
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
    const anchorElement = pdfTextElement(selection?.anchorNode);
    const focusElement = pdfTextElement(selection?.focusNode);
    if (!selected.trim() || document.activeElement?.matches(editableSelector)
      || !anchorElement || !focusElement || !readerDocumentRef.current?.contains(anchorElement)
      || !readerDocumentRef.current?.contains(focusElement)) return;
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
      try {
        await navigator.clipboard.writeText(cleanTextLocally(selected));
        setCopyStatus("已在浏览器中清理并复制");
        setCopyStatusState("success");
      } catch {
        setCopyStatus("浏览器未允许复制，选文已保留，请使用系统复制操作。");
        setCopyStatusState("error");
        return;
      }
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
