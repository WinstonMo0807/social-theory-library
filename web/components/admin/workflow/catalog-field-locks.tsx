"use client";

import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { LockKeyhole, LockKeyholeOpen, X } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import styles from "./catalog-field-locks.module.css";

type Field = { name: string; label: string; scope: "work" | "edition"; value: unknown; display_value: unknown; can_edit: boolean; locks: Array<{ id: string; edition_id: string; version_label: string; value: unknown; display_value: unknown; actor: string; reason: string; updated_at: string }> };
type Context = { fields: Field[]; disabled: boolean; open: (name?: string) => void };
type Receipt = { owner_id: string; work_id: string; edition_id: string; request_id: string; state: "applied" | "cancelled" };
type Command = { edition_id: string; request_id: string; edit_version: string; sections: Record<string, never>; field_locks: Array<{ field: string; action: "lock" | "unlock"; reason: string }> };
const LockContext = createContext<Context | null>(null);
const display = (value: unknown): string => value == null || value === "" ? "未填写" : Array.isArray(value) ? value.map(display).join("、") : typeof value === "object" ? "confirmed_null" in value ? "明确留空" : JSON.stringify(value) : String(value);
const uuid = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

export function CatalogFieldLocksProvider({ owner, workId, editionId, version, fields, disabled, onChanged, onGuard, children }: {
  owner: string; workId: string; editionId: string; version: string; fields: Field[]; disabled: boolean;
  onChanged: () => Promise<unknown>; onGuard: (value: boolean) => void; children: ReactNode;
}) {
  const [editor, setEditor] = useState<{ name: string; version: string } | null>(null), [reason, setReason] = useState("");
  const [ready, setReady] = useState(false), [broken, setBroken] = useState(false), [pending, setPending] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(""), [stopping, setStopping] = useState(false);
  const [original, setOriginal] = useState<Command | null>(null);
  const controller = useRef<AbortController | null>(null), sending = useRef(false);
  const storageKey = `stl-field-lock:${owner}:${workId}:${editionId}`;
  useEffect(() => {
    const active = new AbortController(); controller.current = active;
    const unsubscribe = subscribeToSessionChanges(() => active.abort());
    queueMicrotask(() => {
      if (active.signal.aborted) return;
      try { const value = sessionStorage.getItem(storageKey); if (value && !uuid.test(value)) throw Error("原人工锁操作编号无法核对，请保留记录并重新打开编辑页。"); setPending(value); }
      catch (error) { setBroken(true); setMessage(error instanceof Error ? error.message : "无法读取原请求编号。"); }
      finally { setReady(true); }
    });
    return () => { active.abort(); unsubscribe(); };
  }, [storageKey]);
  const blocked = !ready || broken || busy || Boolean(pending);
  useEffect(() => { onGuard(blocked || Boolean(editor)); }, [blocked, editor, onGuard]);
  useUnsavedForm(Boolean(reason) || Boolean(pending), false);
  const field = fields.find(row => row.name === editor?.name);
  function open(name?: string) { if (disabled || blocked) return; setReason(""); setMessage(""); setEditor({ name: name || fields[0]?.name || "", version }); }
  function close() { if (busy || reason && !pending && !window.confirm("人工锁说明尚未提交，确定放弃吗？")) return; setEditor(null); setReason(""); }
  async function dispatch(mode: "submit" | "read" | "stop", value?: Command) {
    const active = controller.current, command = value || original, id = mode === "submit" ? command?.request_id : pending;
    if (!active || active.signal.aborted || sending.current || !id || !ready || broken) return;
    if (mode === "submit" && (disabled || !command)) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      if (mode === "submit") { sessionStorage.setItem(storageKey, id); setPending(id); setOriginal(command); }
      const root = `/catalog/admin/library/works/${workId}/edits/`;
      const credential = getServerSessionCredential();
      const result = await withPrivateOwner(owner, async () => {
        const options = { cache: "no-store" as const, headers: { "X-Editor-Owner": owner }, signal: AbortSignal.any([active.signal, AbortSignal.timeout(30000)]) };
        if (mode === "submit") await apiRequest(root, { ...options, method: "POST", body: JSON.stringify(command) }, credential, false);
        const receipt = await apiRequest<Receipt>(`${root}commands/${id}/`, { ...options, ...(mode === "stop" ? { method: "POST", body: JSON.stringify({ action: "cancel_pending", edition_id: editionId }) } : {}) }, credential, false);
        if (receipt.owner_id !== owner || receipt.work_id !== workId || receipt.edition_id !== editionId || receipt.request_id !== id || !["applied", "cancelled"].includes(receipt.state)) throw Error("原请求回执不匹配，请保留编号继续核对。");
        return receipt;
      }, active.signal);
      if (active.signal.aborted) return;
      sessionStorage.removeItem(storageKey); setPending(null); setOriginal(null); setEditor(null); setReason("");
      setMessage(result.state === "applied" ? "人工锁决定已保存，字段内容和公开状态没有改变。" : "尚未执行的原决定已停止，已完成操作不会撤销。");
      await onChanged();
    } catch (error) { if (!active.signal.aborted) setMessage(error instanceof Error ? error.message : "结果尚未确认，请查回原请求。"); }
    finally { sending.current = false; if (!active.signal.aborted) { setBusy(false); setStopping(false); } }
  }
  const feedback = <>{message ? <p role="status">{message}</p> : null}{pending ? <div className={styles.actions}><p>上次人工锁决定尚未核对，请先查回原请求。</p><button type="button" disabled={busy} onClick={() => void dispatch("read")}>查回原决定</button>{original ? <button type="button" disabled={busy || disabled} onClick={() => void dispatch("submit")}>重试原决定</button> : null}<button type="button" disabled={busy} onClick={() => setStopping(true)}>停止尚未执行的请求</button></div> : null}</>;
  return <LockContext value={{ fields, disabled: disabled || blocked, open }}>{children}
    {message || pending ? <aside className={styles.notice}>{feedback}</aside> : null}
    {editor ? <Dialog open className={styles.dialog} aria-label="字段人工锁" onRequestClose={close}><header><h2>字段人工锁</h2><button type="button" disabled={busy} aria-label="关闭人工锁" onClick={close}><X size={18} /></button></header>
      <label>核对字段<select value={editor.name} disabled={busy || Boolean(pending) || Boolean(reason)} onChange={event => setEditor({ name: event.target.value, version })}>{fields.map(row => <option key={row.name} value={row.name}>{row.label}{row.locks.length ? " · 已锁定" : ""}</option>)}</select></label>
      {field ? <><p>{field.scope === "work" ? "这是作品共有字段。此处显示各版本已有的人工锁，解除后会解除整部作品对此字段的候选保护。" : "此决定只影响当前出版版本的字段保护。"} 候选仍须明确采用，公开内容仍须独立发布。</p><strong>当前已保存值</strong><blockquote>{display(field.display_value)}</blockquote>
        {field.locks.map(lock => <article key={lock.id}><strong>{lock.version_label || "未命名版本"} · {lock.actor}</strong><p>{display(lock.display_value)}</p><small>{lock.reason || "未填写说明"} · {new Date(lock.updated_at).toLocaleString("zh-CN")}</small></article>)}
        <label>{field.locks.length ? "解除保护的原因" : "确认当前值的说明"}<textarea rows={3} maxLength={400} disabled={busy || Boolean(pending)} value={reason} onChange={event => setReason(event.target.value)} /></label>
        <p>{field.locks.length ? "解除人工锁不会修改字段或自动采用新候选；可核对后重新锁定当前保存值。" : "锁定后，新候选可以查看但不能直接采用。手工修改仍走原保存流程。"}</p>
        {editor.version !== version ? <p role="alert">当前书目已变化，请关闭此窗口后重新核对。</p> : null}{feedback}
        {!field.can_edit ? <p>当前账户可以核对记录，但没有修改此类字段人工锁的权限。</p> : null}
        <footer><button type="button" disabled={busy} onClick={close}>返回编辑</button><button type="button" disabled={disabled || blocked || !field.can_edit || !reason.trim() || editor.version !== version} onClick={() => void dispatch("submit", { request_id: createRequestKey(), edition_id: editionId, edit_version: editor.version, sections: {}, field_locks: [{ field: field.name, action: field.locks.length ? "unlock" : "lock", reason: reason.trim() }] })}>{busy ? "正在保存…" : field.locks.length ? "确认解除保护" : "锁定当前保存值"}</button></footer>
      </> : <p>此字段暂不可管理，请重新读取书目。</p>}
    </Dialog> : null}
    <ConfirmDialog open={stopping} title="核对并停止原决定？" description="已保存决定返回原回执；尚未执行的请求会被停止，迟到提交不能再更改人工锁。" confirmLabel="核对并停止" pending={busy} onCancel={() => setStopping(false)} onConfirm={() => dispatch("stop")} />
  </LockContext>;
}

export function CatalogFieldLockButton({ name }: { name?: string }) {
  const context = useContext(LockContext), field = context?.fields.find(row => row.name === name);
  if (!context || name && !field) return null;
  const locked = Boolean(field?.locks.length);
  return <button className={styles.trigger} type="button" disabled={context.disabled} aria-label={name ? `${field?.label}：${locked ? "查看人工锁" : "设置人工锁"}` : "查看字段人工锁"} onClick={() => context.open(name)}>{locked ? <LockKeyhole size={13} /> : <LockKeyholeOpen size={13} />}{name ? locked ? "人工锁定" : "保护此字段" : "字段人工锁"}</button>;
}

export type CatalogLockFields = Field[];
