"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, ChevronDown, LoaderCircle } from "lucide-react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "./ui/dialog";
import { AccountAvatar, readAccountAvatar } from "./account-avatar";
import styles from "./account-avatar.module.css";

type Snapshot = components["schemas"]["AvatarState"];
type Receipt = components["schemas"]["AvatarReceipt"];
const key = (owner: string) => `stl-avatar-command:${owner}`;

export function ProfileAvatarEditor({ owner, name }: { owner: string; name: string }) {
  const [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return <AvatarEditor key={`${owner}:${epoch}`} owner={owner} name={name} />;
}

function AvatarEditor({ owner, name }: { owner: string; name: string }) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null), [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false), [ready, setReady] = useState(false), [storageFailed, setStorageFailed] = useState(false);
  const [file, setFile] = useState<File | null>(null), [preview, setPreview] = useState(""), [recovery, setRecovery] = useState("");
  const [confirmation, setConfirmation] = useState<"remove" | "stop" | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const pending = useRef<{ id: string; body: FormData } | null>(null), controller = useRef<AbortController | null>(null), sending = useRef(false);
  const fileInput = useRef<HTMLInputElement | null>(null);
  useUnsavedForm(Boolean(file || recovery), false);
  const request = useCallback(async function avatarRequest<T extends Snapshot>(path = "", options: RequestInit = {}) {
    const signal = AbortSignal.any([controller.current!.signal, AbortSignal.timeout(30000)]);
    return withPrivateOwner(owner, async () => {
      const value = await apiRequest<T>(`/auth/me/avatar/${path}`, { ...options, signal, cache: "no-store", headers: { "X-Reader-Owner": owner } }, getServerSessionCredential(), false);
      if (value.owner_id !== owner) throw Error("头像所属账户已变化，请重新读取。");
      return value;
    }, signal);
  }, [owner]);
  useEffect(() => {
    const current = new AbortController(); controller.current = current;
    const off = subscribeToSessionChanges(() => current.abort());
    queueMicrotask(async () => {
      if (current.signal.aborted) return;
      try { const id = sessionStorage.getItem(key(owner)) || ""; if (id && !/^[\da-f-]{36}$/i.test(id)) throw Error("原头像请求编号无法读取。"); setRecovery(id); }
      catch { setStorageFailed(true); setMessage("无法读取原请求记录，请恢复会话存储后重新打开本页。"); }
      setReady(true);
      try { const value = await request<Snapshot>(); if (!current.signal.aborted) setSnapshot(value); }
      catch (reason) { if (!current.signal.aborted) setMessage(reason instanceof Error ? reason.message : "无法读取头像资料。"); }
    });
    return () => { current.abort(); off(); };
  }, [owner, request]);
  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    queueMicrotask(() => setPreview(url));
    return () => URL.revokeObjectURL(url);
  }, [file]);
  async function run(action: () => Promise<void>) {
    if (sending.current || !controller.current || controller.current.signal.aborted) return;
    sending.current = true; setBusy(true); setMessage("");
    try { await action(); }
    catch (reason) { if (!controller.current.signal.aborted) setMessage(reason instanceof Error ? reason.message : "操作结果尚未确认，请查询原请求。"); }
    finally { sending.current = false; if (!controller.current?.signal.aborted) setBusy(false); }
  }
  function accept(value: Receipt, id: string) {
    if (value.request_id !== id || !["applied", "cancelled"].includes(value.state)) throw Error("头像操作结果与原请求不一致。");
    sessionStorage.removeItem(key(owner)); setRecovery(""); pending.current = null; setCanRetry(false); setFile(null); setPreview(""); setSnapshot(value); setConfirmation(null);
    if (fileInput.current) fileInput.current.value = "";
    setMessage(value.state === "cancelled" ? "已取消待处理的头像操作。" : value.has_avatar ? "头像已更新。" : "已恢复默认头像。");
  }
  async function submit(action: "set" | "remove") {
    if (!snapshot || storageFailed || !ready || recovery && !pending.current) return;
    await run(async () => {
      let original = pending.current;
      if (!original) {
        const id = createRequestKey(), body = new FormData();
        body.set("action", action); body.set("request_id", id); body.set("expected_version", snapshot.expected_version); body.set("confirmed", "true");
        if (action === "set") { if (!file) throw Error("请先选择图片。"); body.set("image", file); }
        sessionStorage.setItem(key(owner), id); setRecovery(id); original = { id, body }; pending.current = original; setCanRetry(true);
      }
      try { accept(await request<Receipt>("", { method: "POST", body: original.body }), original.id); }
      catch (reason) {
        if (reason instanceof ApiRequestError && !(reason instanceof PrivateOwnerVerificationError) && [400, 409].includes(reason.status)) {
          sessionStorage.removeItem(key(owner)); setRecovery(""); pending.current = null; setCanRetry(false); setConfirmation(null);
        }
        throw reason;
      }
    });
  }
  function recover(stop = false) {
    if (!recovery) return;
    void run(async () => accept(await request<Receipt>(`commands/${recovery}/`, stop ? { method: "POST", body: JSON.stringify({ action: "cancel_pending" }) } : {}), recovery));
  }
  function download() {
    void run(async () => {
      const blob = await readAccountAvatar(owner, owner, controller.current!.signal);
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = "profile-avatar.png"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage("已准备本人头像下载。");
    });
  }
  const blocked = busy || !ready || storageFailed || Boolean(recovery);
  function cancelSelection() {
    setFile(null); setPreview(""); setMessage("");
    if (fileInput.current) fileInput.current.value = "";
  }
  return <section className={styles.editor} aria-label="头像设置">
    <input ref={fileInput} hidden type="file" aria-label="选择头像图片" accept="image/jpeg,image/png,image/webp" disabled={blocked || !snapshot} onChange={event => {
      const chosen = event.target.files?.[0] || null;
      if (chosen && (chosen.size > 2 * 1024 * 1024 || !["image/jpeg", "image/png", "image/webp"].includes(chosen.type))) { setFile(null); setPreview(""); setMessage("请选择2 MB以内的JPEG、PNG或WebP。"); event.target.value = ""; return; }
      setFile(chosen); setMessage(""); setPreview("");
    }} />
    <div className={styles.row}>
      <button type="button" className={styles.avatarButton} aria-label="点击更换头像" disabled={blocked || !snapshot} onClick={() => fileInput.current?.click()}>
        {file && preview ? <img className={styles.preview} src={preview} alt="新头像预览" /> : <AccountAvatar owner={owner} target={owner} revision={snapshot?.has_avatar ? snapshot.revision : null} name={name} />}
        <span className={styles.camera}><Camera size={16} aria-hidden="true" /></span>
      </button>
      <div className={styles.content}>
        <h3>{file ? "新头像预览" : "头像"}</h3>
        <p className={styles.privacy}>仅你和获准管理账号的管理员可见。</p>
        <div className={styles.actions}>
          {file ? <>
            <button type="button" className={styles.primary} disabled={blocked || !snapshot} onClick={() => void submit("set")}>{busy ? <><LoaderCircle size={16} className={styles.spinner} aria-hidden="true" />正在保存…</> : "保存头像"}</button>
            <button type="button" disabled={blocked} onClick={cancelSelection}>取消</button>
            <button type="button" className={styles.textButton} disabled={blocked} onClick={() => fileInput.current?.click()}>重新选择</button>
          </> : <button type="button" className={styles.primary} disabled={blocked || !snapshot} onClick={() => fileInput.current?.click()}><Camera size={16} aria-hidden="true" />更换头像</button>}
        </div>
        <p className={styles.hint}>{file ? "已居中裁切，保存后生效。" : "JPG、PNG 或 WebP，不超过 2 MB。"}</p>
        {!file ? <details className={styles.more}><summary>更多<ChevronDown size={14} aria-hidden="true" /></summary><div className={styles.moreActions}>
          {snapshot?.has_avatar ? <><button type="button" disabled={busy} onClick={download}>下载头像</button><button type="button" disabled={blocked} onClick={() => setConfirmation("remove")}>恢复默认头像</button></> : null}
          <button type="button" disabled={busy} onClick={() => void run(async () => setSnapshot(await request<Snapshot>()))}>刷新头像</button>
        </div></details> : null}
      </div>
    </div>
    {!snapshot && !message ? <p role="status">正在读取头像…</p> : null}
    {recovery && !busy ? <div className={styles.feedback}><p>尚未确认头像是否保存，请先查看结果。</p><div className={styles.actions}><button type="button" onClick={() => recover()}>查看结果</button><button type="button" onClick={() => setConfirmation("stop")}>取消未完成操作</button>{canRetry ? <button type="button" onClick={() => void submit(pending.current!.body.get("action") === "set" ? "set" : "remove")}>重试保存</button> : null}</div></div> : null}
    {message ? <p className={styles.feedback} role="status">{message}</p> : null}
    <Dialog open={confirmation !== null} onRequestClose={() => { if (!busy) setConfirmation(null); }} className={styles.dialog} aria-label="确认头像操作"><h3>{confirmation === "stop" ? "取消未完成的操作？" : "恢复默认头像？"}</h3><p>{confirmation === "stop" ? "尚未完成的操作将被取消。如果已经保存，会保留保存结果。" : "当前图片将被移除，改用姓名首字作为头像。"}</p><div className={styles.actions}><button type="button" disabled={busy} onClick={() => setConfirmation(null)}>取消</button><button type="button" className={styles.primary} disabled={busy} onClick={() => { if (confirmation === "stop") recover(true); else if (confirmation) void submit(confirmation); }}>{busy ? "正在处理…" : confirmation === "stop" ? "确认取消" : "恢复默认"}</button></div>{message ? <p role="status">{message}</p> : null}</Dialog>
  </section>;
}
