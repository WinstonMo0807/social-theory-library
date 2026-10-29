"use client";

import { useEffect, useRef, useState } from "react";
import { Archive, ArchiveRestore, Pencil, X } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { ReaderMaterial } from "./reader-materials";
import styles from "./reader-overview.module.css";

type Action = "rename" | "archive" | "restore";
type Target = { kind: string; id: string; revision: string; title?: string };
type Command = { request_id: string; action: Action; targets: Target[] };
type Receipt = { owner_id: string; request_id: string; state: "applied" | "cancelled"; action: string; applied: Array<{ id: string; kind: string; revision: string }> };
const labels = { rename: "重命名", archive: "归档资料", restore: "恢复资料" };
const uuid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

export function ReaderMaterialActions({ ownerId, selection, blocked, onApplied, onLocked }: { ownerId: string; selection: ReaderMaterial[]; blocked: boolean; onApplied: () => void; onLocked: (locked: boolean) => void }) {
  const [editor, setEditor] = useState<{ action: Action; rows: ReaderMaterial[]; titles: string[] } | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [ready, setReady] = useState(false), [broken, setBroken] = useState(false), [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(""), [stopping, setStopping] = useState(false);
  const controller = useRef<AbortController | null>(null), sending = useRef(false);
  const [original, setOriginal] = useState<Command | null>(null);
  const storageKey = `stl-reader-material-command:${ownerId}`;
  useEffect(() => {
    const active = new AbortController(); controller.current = active;
    const unsubscribe = subscribeToSessionChanges(() => active.abort());
    queueMicrotask(() => {
      if (active.signal.aborted) return;
      try {
        const key = sessionStorage.getItem(storageKey);
        if (key && !uuid.test(key)) throw Error("原操作编号无法核对，请保留记录并重新读取本人资料。");
        setPending(key); if (key) setMessage("上次操作结果尚未核实，请查询原请求。重命名内容仅保存在提交时的内存中。");
      } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "无法读取原操作编号。"); }
      finally { setReady(true); }
    });
    return () => { active.abort(); unsubscribe(); };
  }, [storageKey]);
  const locked = !ready || broken || busy || Boolean(pending) || Boolean(editor);
  useEffect(() => { onLocked(locked); }, [locked, onLocked]);
  useUnsavedForm(Boolean(editor) || Boolean(pending), false);
  const canRename = selection.length > 0 && selection.length <= 20;
  const canArchive = selection.length > 0 && selection.length <= 100;
  function open(action: Action) { setMessage(""); setEditor({ action, rows: selection, titles: selection.map(row => row.editable_title) }); }
  function close() {
    if (busy) return;
    if (editor?.action === "rename" && !pending && editor.titles.some((title, i) => title !== editor.rows[i].editable_title) && !window.confirm("名称尚未保存，确定放弃修改吗？")) return;
    setEditor(null);
  }
  async function dispatch(mode: "submit" | "read" | "stop", next?: Command) {
    const active = controller.current;
    if (!ready || broken || sending.current || !active || active.signal.aborted) return;
    const command = next ?? original, id = pending ?? command?.request_id;
    if (!id || (mode === "submit" && !command)) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      sessionStorage.setItem(storageKey, id); setPending(id);
      if (command) setOriginal(command);
      const result = await withPrivateOwner(ownerId, async () => {
        const result = await apiRequest<Receipt>(`/reading/reader-center/commands/${mode === "submit" ? "" : `${id}/`}`, {
          method: mode === "read" ? "GET" : "POST", cache: "no-store", headers: { "X-Reader-Owner": ownerId },
          signal: AbortSignal.any([active.signal, AbortSignal.timeout(30000)]),
          ...(mode === "read" ? {} : { body: JSON.stringify(mode === "stop" ? { action: "cancel_pending" } : command) }),
        }, getServerSessionCredential(), false);
        if (result.owner_id !== ownerId || result.request_id !== id || !["applied", "cancelled"].includes(result.state)) throw new PrivateOwnerVerificationError("原操作归属或编号不匹配，请保留恢复记录。", 403);
        return result;
      }, active.signal);
      if (active.signal.aborted) return;
      sessionStorage.removeItem(storageKey); setPending(null); setOriginal(null); setEditor(null);
      setMessage(result.state === "applied" ? `已${labels[result.action as Action] || "处理"} ${result.applied.length} 项资料，原请求不会重复执行。` : "尚未执行的原请求已停止。已经完成的更改不会被撤销。");
      onApplied();
    } catch (reason) { if (!active.signal.aborted) setMessage(reason instanceof Error ? reason.message : "尚未取得结果，请查询或重试原操作。"); }
    finally { sending.current = false; if (!active.signal.aborted) { setBusy(false); setStopping(false); } }
  }
  function submit() {
    if (!editor) return;
    const targets = editor.rows.flatMap((row, i) => editor.action === "rename" && editor.titles[i] === row.editable_title ? [] : [{ kind: row.kind, id: row.id, revision: row.revision, ...(editor.action === "rename" ? { title: editor.titles[i].trim() } : {}) }]);
    if (!targets.length) { setMessage("名称没有变化。"); return; }
    void dispatch("submit", { request_id: createRequestKey(), action: editor.action, targets });
  }
  const feedback = <>{message ? <p role="status">{message}</p> : null}{pending ? <div><button type="button" disabled={busy} onClick={() => void dispatch("read")}>查询原请求</button>{original ? <button type="button" disabled={busy} onClick={() => void dispatch("submit")}>重试原操作</button> : null}<button type="button" disabled={busy} onClick={() => setStopping(true)}>停止尚未执行的请求</button></div> : null}</>;
  return <>
    <button type="button" disabled={blocked || locked || !canRename} onClick={() => open("rename")}><Pencil size={14} />重命名</button>
    <button type="button" disabled={blocked || locked || !canArchive || selection.every(row => row.status === "archived")} onClick={() => open("archive")}><Archive size={14} />归档</button>
    {canArchive && selection.some(row => row.status === "archived") ? <button type="button" disabled={blocked || locked} onClick={() => open("restore")}><ArchiveRestore size={14} />恢复资料</button> : null}
    {message || pending ? <div className={styles.materialCommandNotice}>{feedback}</div> : null}
    {editor ? <Dialog open className={`${styles.transferDialog} ${styles.materialEditor}`} aria-labelledby="reader-material-editor-title" onRequestClose={close}><header><h2 id="reader-material-editor-title">{labels[editor.action]}</h2><button type="button" disabled={busy} onClick={close} aria-label="关闭资料编辑"><X size={17} /></button></header><p>{editor.action === "rename" ? "研究、书单与书签修改原名称；笔记、计划、体检和选材设置本人资料列表的显示名称，正文、原题名和目标不变。任何一项版本变化都会停止本次全部修改。" : "归档用于整理本人的资料列表，可在“已归档”筛选中恢复；保留原文、笔记确认与授权、阅读进度及任务记录。不会归档未选择的资料。"}</p>
      <form onSubmit={event => { event.preventDefault(); submit(); }}><ul>{editor.rows.map((row, i) => <li key={row.key}><label><span>{row.kind_label} · {row.title}</span>{editor.action === "rename" ? <input aria-label={`新的名称：${row.title}`} value={editor.titles[i]} maxLength={240} required disabled={busy || Boolean(pending)} onChange={event => setEditor(current => current ? { ...current, titles: current.titles.map((title, index) => index === i ? event.target.value : title) } : current)} /> : <small>{row.status === "archived" ? "已归档" : "已保存"}</small>}</label></li>)}</ul>
        {feedback}<footer><button type="button" disabled={busy} onClick={close}>{pending ? "稍后核对" : "取消"}</button><button type="submit" disabled={busy || Boolean(pending) || (editor.action === "rename" && editor.titles.some(title => !title.trim()))}>{busy ? "正在保存…" : "确认并保存"}</button></footer>
      </form></Dialog> : null}
    <ConfirmDialog open={stopping} title="核对并停止原操作？" description="已经完成的操作返回原操作结果，不重复执行或撤销；尚未执行的原请求将被停止，迟到请求也不会更改资料。" confirmLabel={busy ? "正在核对…" : "核对并停止"} pending={busy} onCancel={() => setStopping(false)} onConfirm={() => dispatch("stop")} />
  </>;
}
