"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { Bookmark, FolderOpen, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePublicSession } from "@/components/public-session-provider";
import { Dialog } from "@/components/ui/dialog";
import { findGraphViewReceipt, loadGraphView, loadGraphViews, writeGraphView, type GraphViewCommand, type GraphViewPage, type GraphViewResponse } from "@/lib/api/graph-views.client";
import type { GraphViewState } from "@/lib/api/graph.types";
import styles from "./theory-graph.module.css";

type PendingCommand = { owner: string; command: GraphViewCommand; dispatched: boolean };

export function GraphSavedViews(props: { view: GraphViewState | null; title: string; onRestore: (view: GraphViewState) => void; disabled?: boolean; initialSavedView?: string }) {
  const { state: session } = usePublicSession();
  // Keep the nonce through same-owner cookie verification. The command is only
  // held in this page's memory; private titles/layouts never enter Web Storage.
  const memoryRef = useRef<PendingCommand | null>(null);
  const [pending, setPending] = useState<PendingCommand | null>(null);
  const publishPending = useCallback((hasPending: boolean) => setPending(hasPending ? memoryRef.current : null), []);
  useUnsavedForm({ pending: !!pending }, { pending: false });
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  return <SavedViews key={owner || "unverified"} {...props} memoryRef={memoryRef} initialCommand={pending?.owner === owner ? pending.command : null} onPendingChange={publishPending} owner={owner} ready={["authenticated", "unauthenticated"].includes(session.status)} />;
}

function SavedViews({ view, title: defaultTitle, onRestore, disabled, owner, ready, initialSavedView, memoryRef, initialCommand, onPendingChange }: {
  view: GraphViewState | null; title: string; onRestore: (view: GraphViewState) => void; disabled?: boolean; owner: string | null; ready: boolean;
  initialSavedView?: string; memoryRef: RefObject<PendingCommand | null>; initialCommand: GraphViewCommand | null; onPendingChange: (pending: boolean) => void;
}) {
  const [open, setOpen] = useState(!!initialCommand), [title, setTitle] = useState(defaultTitle);
  const [list, setList] = useState<GraphViewPage | null>(null), [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(""), [notice, setNotice] = useState("");
  const [unknown, setUnknown] = useState<GraphViewCommand | null>(initialCommand), [deleteId, setDeleteId] = useState("");
  const request = useRef<AbortController | null>(null), listRequest = useRef<AbortController | null>(null), lock = useRef(false), live = useRef(true);
  const initialLoaded = useRef("");
  useEffect(() => {
    live.current = true;
    if (owner && memoryRef.current?.owner !== owner) { memoryRef.current = null; onPendingChange(false); }
    const unsubscribe = subscribeToSessionChanges(() => {
      request.current?.abort(); listRequest.current?.abort(); request.current = null;
      lock.current = false; setBusy(false); setLoading(false); setList(null);
      if (owner && memoryRef.current?.owner === owner) setUnknown(memoryRef.current.command);
      setError("登录状态已变化。继续操作前将重新核对当前账户；原请求标识仍保留在本页。");
    });
    return () => { live.current = false; request.current?.abort(); listRequest.current?.abort(); unsubscribe(); };
  }, [memoryRef, onPendingChange, owner]);

  async function readPage(nextPage = page) {
    if (!owner) return;
    listRequest.current?.abort();
    const controller = new AbortController(); listRequest.current = controller;
    setLoading(true); setError("");
    try {
      const value = await loadGraphViews(owner, controller.signal, nextPage);
      if (!controller.signal.aborted && live.current) { setList(value); setPage(nextPage); }
    } catch (failure) {
      if (!controller.signal.aborted && live.current) setError(failure instanceof Error ? failure.message : "保存的视图暂时无法读取。");
    } finally { if (!controller.signal.aborted && live.current) setLoading(false); }
  }

  function accept(result: GraphViewResponse, command: GraphViewCommand) {
    if (result.receipt?.request_id !== command.request_id || result.receipt.deleted !== (result.record === null)
        || command.method === "DELETE" && !result.receipt.deleted
        || command.id && result.record && result.record.id !== command.id) throw new Error("未能确认原操作回执。");
    if (memoryRef.current?.owner === owner && memoryRef.current.command.request_id === command.request_id) memoryRef.current = null;
    onPendingChange(false);
    setUnknown(null); setDeleteId("");
    setNotice(result.receipt.deleted ? "原视图已删除，不会通过重试恢复。" : "视图已保存到当前账户。");
    void readPage(1);
  }

  async function mutate(command: GraphViewCommand, recover = false) {
    if (!owner || lock.current) return;
    if (memoryRef.current && (memoryRef.current.owner !== owner || memoryRef.current.command.request_id !== command.request_id)) return;
    memoryRef.current ||= { owner, command, dispatched: false };
    onPendingChange(true);
    lock.current = true; setBusy(true); setError(""); setNotice("");
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    let checked = !recover;
    try {
      if (recover) {
        let prior: GraphViewResponse | null = null;
        try { prior = await findGraphViewReceipt(command.request_id, owner, controller.signal); }
        catch (failure) { if (!(failure instanceof ApiRequestError && failure.status === 404)) throw failure; }
        if (!live.current || controller.signal.aborted) return;
        checked = true;
        if (prior?.receipt) { accept(prior, command); return; }
      }
      const result = await writeGraphView(command, owner, controller.signal, () => {
        if (memoryRef.current?.owner === owner && memoryRef.current.command.request_id === command.request_id) memoryRef.current.dispatched = true;
      });
      if (!live.current || controller.signal.aborted) return;
      accept(result, command);
    } catch (failure) {
      if (!live.current || controller.signal.aborted) return;
      const definite = checked && !(failure instanceof PrivateOwnerVerificationError)
        && failure instanceof ApiRequestError && [400, 401, 403, 404, 409, 422].includes(failure.status);
      const sent = memoryRef.current?.dispatched;
      if (definite) { memoryRef.current = null; onPendingChange(false); }
      setUnknown(definite ? null : command);
      setError(definite ? failure instanceof Error ? failure.message : "操作未能完成，请重新读取视图。"
        : sent ? "尚未确认原操作的结果。服务器可能已保存，请先核对原请求；离开本页会失去查回入口。"
        : "当前账户尚未核对，保存请求还未发送。原请求标识已保留，请重新核对后继续。");
    } finally { if (request.current === controller) { request.current = null; lock.current = false; if (live.current) setBusy(false); } }
  }

  const restore = useCallback(async (identifier: string) => {
    if (!owner || lock.current || memoryRef.current?.owner === owner) return;
    lock.current = true; setBusy(true); setError(""); setNotice("");
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    try {
      const result = await loadGraphView(identifier, owner, controller.signal);
      if (!live.current || controller.signal.aborted) return;
      if (!result.record || result.record.id !== identifier) throw new Error("此视图已不可读取，请刷新列表。");
      onRestore(result.record.data.view); setOpen(false);
    } catch (failure) { if (!controller.signal.aborted && live.current) { setError(failure instanceof Error ? failure.message : "视图暂时无法恢复。"); setOpen(true); } }
    finally { if (request.current === controller) { request.current = null; lock.current = false; if (live.current) setBusy(false); } }
  }, [memoryRef, onRestore, owner]);
  useEffect(() => {
    if (!owner || !initialSavedView || unknown || memoryRef.current || initialLoaded.current === initialSavedView) return;
    initialLoaded.current = initialSavedView;
    void restore(initialSavedView);
  }, [initialSavedView, memoryRef, owner, restore, unknown]);

  return <>
    {!owner && ready ? <Link className={styles.outlineButton} href={`/login?${new URLSearchParams({ next: `/theories/graph${initialSavedView ? `?saved_view=${encodeURIComponent(initialSavedView)}` : ""}` })}`}><Bookmark size={15} />{initialSavedView ? "登录后恢复本人视图" : "保存当前视图"}</Link> : <button className={styles.outlineButton} type="button" disabled={!ready || !owner} onClick={() => { setOpen(true); if (!list) void readPage(1); }}><Bookmark size={15} />{unknown ? "核对未确认的保存" : "保存当前视图"}</button>}
    {unknown && !open ? <p role="alert" className={styles.status}>原操作尚未核对，本页仍保留查回入口；请核对后再离开。</p> : null}
    <Dialog open={open} onRequestClose={() => { if (!busy) setOpen(false); }} className={styles.savedDialog} aria-labelledby="saved-graph-title">
      <header><h2 id="saved-graph-title">我的图谱视图</h2><button type="button" aria-label="关闭保存视图" disabled={busy} onClick={() => setOpen(false)}><X size={19} /></button></header>
      <p>保存当前中心、范围与显示位置。打开时重新读取公开关系与来源。</p>
      <form onSubmit={event => { event.preventDefault(); if (view && title.trim() && !unknown) void mutate({ method: "POST", request_id: createRequestKey(), data: { title: title.trim(), view } }); }}>
        <label>视图名称<input value={title} maxLength={120} required onChange={event => setTitle(event.target.value)} disabled={busy || !!unknown} /></label>
        <button type="submit" className={styles.primaryButton} disabled={busy || disabled || !!unknown || !view || !title.trim()}>保存为新视图</button>
      </form>
      {error ? <p role="alert" className={styles.status}>{error}</p> : null}
      {notice ? <p role="status" className={styles.status}>{notice}</p> : null}
      {unknown ? <button type="button" className={styles.outlineButton} disabled={busy} onClick={() => void mutate(unknown, true)}>{busy ? "正在核对…" : "核对原操作"}</button> : null}
      {initialSavedView && error && !unknown ? <button type="button" className={styles.outlineButton} disabled={busy} onClick={() => void restore(initialSavedView)}>重新读取此视图</button> : null}
      <div className={styles.savedHeading}><h3><FolderOpen size={17} />已保存 {list?.count ?? ""}</h3><button type="button" disabled={busy || loading} onClick={() => void readPage(page)}>刷新列表</button></div>
      {loading ? <p role="status">正在读取我的视图…</p> : list ? <>
        {list.results.length ? <ul className={styles.savedList}>{list.results.map(row => <li key={row.id}><strong>{row.data.title}</strong><small>{new Date(row.updated_at).toLocaleString("zh-CN")}</small><div>
          <button type="button" disabled={busy || !!unknown} onClick={() => void restore(row.id)}>打开视图</button>
          <button type="button" disabled={busy || disabled || !!unknown || !view} onClick={() => { if (view) void mutate({ method: "PATCH", id: row.id, request_id: createRequestKey(), expected_revision: row.revision, data: { title: row.data.title, view } }); }}>更新为当前视图</button>
          {deleteId === row.id ? <><button type="button" disabled={busy || !!unknown} onClick={() => void mutate({ method: "DELETE", id: row.id, request_id: createRequestKey(), expected_revision: row.revision })}>确认删除</button><button type="button" disabled={busy} onClick={() => setDeleteId("")}>取消</button></> : <button type="button" disabled={busy || !!unknown} onClick={() => setDeleteId(row.id)}>删除</button>}
        </div></li>)}</ul> : <p className={styles.empty}>还没有保存的图谱视图。</p>}
        <nav className={styles.pagination} aria-label="已保存图谱分页"><button type="button" disabled={!list.previous || busy || loading} onClick={() => void readPage(page - 1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!list.next || busy || loading} onClick={() => void readPage(page + 1)}>下一页</button></nav>
      </> : null}
    </Dialog>
  </>;
}
