"use client";

import { LoadingState } from "@/components/ui/loading-state";

import { useEffect, useRef, useState } from "react";
import { useOwnedRead } from "./media-requests";
import styles from "./media-workspace.module.css";

type PagePreview = { owner_id: string; object_type: string; object_id: string; url: string; version: string; fingerprint: string };
type State = { version: string; page_preview?: PagePreview | null };

export function SavedMediaPagePreview({ owner, path, slot, version, objectId, objectType }: {
  owner: string; path: string; slot: string; version: string; objectId: string; objectType: string;
}) {
  const resource = useOwnedRead<State>(owner, `${path}?${new URLSearchParams({ slot, include_preview: "true", expected_version: version })}`);
  if (resource.error) return <section className={styles.feedback} role="alert"><p>{resource.error}</p><p>当前裁切与填写仍保留。若保存版本已变化，请关闭预览并重新读取工作区。</p><button onClick={resource.retry}>重新读取预览</button></section>;
  if (!resource.data) return <LoadingState role="status">正在核对已保存版本并读取完整页面…</LoadingState>;
  const preview = resource.data.page_preview;
  const expectedTypes = objectType === "knowledge_node" ? ["theory", "concept", "debate", "research_problem"] : [objectType === "scholar_profile" ? "scholar" : objectType];
  if (!preview || resource.data.version !== version || preview.owner_id !== owner || preview.object_id !== objectId || !expectedTypes.includes(preview.object_type))
    return <p role="alert">完整预览与当前对象、账户或保存版本不一致，请关闭后重新读取。</p>;
  let url: URL;
  try { url = new URL(preview.url, "https://media-preview.invalid"); }
  catch { return <p role="alert">预览地址无法读取，请从原编辑对象重新进入。</p>; }
  const expectedPath = preview.object_type === "work" ? `/admin/preview/works/${objectId}` : `/admin/preview/knowledge/${preview.object_type}/${objectId}`;
  if (url.origin !== "https://media-preview.invalid" || url.pathname !== expectedPath || url.searchParams.get("frame") !== "1")
    return <p role="alert">预览地址不属于当前受保护页面，请从原编辑对象重新进入。</p>;
  return <PageFrame key={preview.url} preview={preview} onRetry={resource.retry} />;
}

function PageFrame({ preview, onRetry }: { preview: PagePreview; onRetry: () => void }) {
  const ref = useRef<HTMLIFrameElement>(null), [size, setSize] = useState("fit"), [state, setState] = useState("waiting");
  useEffect(() => {
    const listener = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== ref.current?.contentWindow || !event.data || typeof event.data !== "object") return;
      const data = event.data;
      const matches = preview.object_type === "work"
        ? data.type === "stl:publication-preview" && data.editionId === preview.object_id && data.version === preview.version && data.fingerprint === preview.fingerprint
        : data.type === "stl:knowledge-publication-preview" && data.objectType === preview.object_type && data.objectId === preview.object_id && data.owner === preview.owner_id && data.version === preview.version;
      if (matches && data.state !== "loading") setState(data.ok ? "ready" : "error");
    };
    window.addEventListener("message", listener);
    const timer = window.setTimeout(() => setState(current => current === "waiting" ? "unconfirmed" : current), 30000);
    return () => { window.removeEventListener("message", listener); window.clearTimeout(timer); };
  }, [preview]);
  return <section className={styles.fullPagePreview} aria-label="完整页面预览">
    <header><h3>完整页面 · 已保存内容</h3><div role="group" aria-label="页面预览宽度">{[["fit", "适应窗口"], ["desktop", "桌面"], ["mobile", "手机"]].map(([value, label]) => <button key={value} aria-pressed={size === value} onClick={() => setSize(value)}>{label}</button>)}</div></header>
    <p role="status">{state === "ready" ? "已保存页面已显示。此处核对版式，返回工作区后继续编辑。" : state === "error" ? "完整页面暂不可用，原因见下方；当前裁切仍保留。" : state === "unconfirmed" ? "尚未收到当前版本的页面确认，可重新读取；未据此判断内容丢失。" : "正在显示已保存页面…"}{state === "error" || state === "unconfirmed" ? <button onClick={onRetry}>重新读取</button> : null}</p>
    <div className={styles.pageFrameScroll} tabIndex={0} role="region" aria-label="已保存页面版式，可横向滚动"><iframe ref={ref} title="当前对象已保存的完整页面" src={preview.url} referrerPolicy="same-origin" style={{ width: size === "desktop" ? 1280 : size === "mobile" ? 390 : "100%" }} onLoad={() => {
      // This is a layout preview. Preserve scrolling without allowing embedded edits/navigation.
      try { ref.current?.contentDocument?.body.setAttribute("inert", ""); } catch { setState("error"); }
    }} /></div>
  </section>;
}
