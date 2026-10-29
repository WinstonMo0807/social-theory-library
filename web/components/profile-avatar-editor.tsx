"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
  const [confirmation, setConfirmation] = useState<"set" | "remove" | "stop" | null>(null);
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
    setMessage(value.state === "cancelled" ? "原请求已停止，迟到的提交不会更改头像。" : "原头像操作已保存，当前资料已同步。");
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
  return <section className={styles.editor}><div className={styles.row}><AccountAvatar owner={owner} target={owner} revision={snapshot?.has_avatar ? snapshot.revision : null} name={name} /><div><h3>账户头像</h3><p>{snapshot?.notice || "正在读取本人的头像设置…"}</p></div></div>
    <p>支持2 MB以内的静态JPEG、PNG或WebP，居中裁为正方形；保存256像素头像并移除照片元数据，不上传原照片到公开素材库。</p>
    <label>选择图片<input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" disabled={blocked} onChange={event => {
      const chosen = event.target.files?.[0] || null;
      if (chosen && (chosen.size > 2 * 1024 * 1024 || !["image/jpeg", "image/png", "image/webp"].includes(chosen.type))) { setFile(null); setPreview(""); setMessage("请选择2 MB以内的JPEG、PNG或WebP。"); event.target.value = ""; return; }
      setFile(chosen); setMessage(""); setPreview("");
    }} /></label>{file && preview ? <div className={styles.actions}><img className={styles.preview} src={preview} alt="待保存头像的居中裁切预览" /></div> : null}
    <div className={styles.actions}><button disabled={blocked || !file || !snapshot} onClick={() => setConfirmation("set")}>保存头像</button>{file ? <button disabled={blocked} onClick={() => { setFile(null); setPreview(""); if (fileInput.current) fileInput.current.value = ""; }}>取消选择</button> : null}<button disabled={blocked || !snapshot?.has_avatar} onClick={() => setConfirmation("remove")}>移除头像</button><button disabled={busy || !snapshot?.has_avatar} onClick={download}>导出本人头像</button><button disabled={busy || Boolean(file)} onClick={() => void run(async () => setSnapshot(await request<Snapshot>()))}>重新读取</button></div>
    {recovery ? <><p>原头像操作结果尚未确认，原请求编号已保留。查询或停止后再开始其他修改。</p><div className={styles.actions}><button disabled={busy} onClick={() => recover()}>查询原操作</button><button disabled={busy} onClick={() => setConfirmation("stop")}>停止未执行的原操作</button>{canRetry ? <button disabled={busy} onClick={() => void submit(pending.current!.body.get("action") === "set" ? "set" : "remove")}>重试原操作</button> : null}</div></> : null}
    {message ? <p role="status">{message}</p> : null}
    <Dialog open={confirmation !== null} onRequestClose={() => { if (!busy) setConfirmation(null); }} className={styles.dialog} aria-label="确认头像操作"><h3>{confirmation === "stop" ? "核对并停止原操作" : confirmation === "remove" ? "移除本人头像？" : "保存这张头像？"}</h3><p>{confirmation === "stop" ? "已保存的操作返回原结果，尚未执行的请求会被停止。" : confirmation === "remove" ? "移除当前头像并恢复姓名首字，不影响账户、笔记或馆藏。备份按既有保留规则处理。" : "保存处理后的头像，替换当前头像。只有本人和获准管理账户的管理员可查看。"}</p><div className={styles.actions}><button disabled={busy} onClick={() => setConfirmation(null)}>返回</button><button disabled={busy} onClick={() => { if (confirmation === "stop") recover(true); else if (confirmation) void submit(confirmation); }}>{busy ? "正在保存…" : "确认"}</button></div>{message ? <p role="status">{message}</p> : null}</Dialog>
  </section>;
}
