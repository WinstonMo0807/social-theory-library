"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Bookmark, Check, Copy, RefreshCw, X } from "lucide-react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { findPathFollowReceipt, loadPathFollow, loadPathPlan, previewPathUpgrade, writePathFollow } from "@/lib/api/reading-paths.client";
import { readingPathHref, type PathFollowCommand, type PathFollowRecord, type PathFollowResponse, type PathUpgradePreview, type PublicReadingPath } from "@/lib/api/reading-paths.types";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePublicSession } from "@/components/public-session-provider";
import { Dialog } from "@/components/ui/dialog";
import styles from "./reading-path.module.css";

type Pending = { owner: string; command: PathFollowCommand; dispatched: boolean };
export function usePathPersonal(path: PublicReadingPath, preview = false, initialPlanId = "") {
  const { state: session } = usePublicSession(), owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  const [record, setRecord] = useState<PathFollowRecord | null>(null), [busy, setBusy] = useState(false), [loading, setLoading] = useState(false);
  const [recordOwner, setRecordOwner] = useState<string | null>(null), [loadedFor, setLoadedFor] = useState("");
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [planId, setPlanId] = useState("");
  const [pending, setPending] = useState<Pending | null>(null), [upgrade, setUpgrade] = useState<PathUpgradePreview | null>(null);
  const memory = useRef<Pending | null>(null), operation = useRef<AbortController | null>(null), readOperation = useRef<AbortController | null>(null), epoch = useRef(0), live = useRef(true), lock = useRef(false);
  useUnsavedForm({ pending: !!pending && (!owner || pending.owner === owner) }, { pending: false });
  useEffect(() => {
    live.current = true;
    const unsubscribe = subscribeToSessionChanges(() => {
      epoch.current += 1; operation.current?.abort(); readOperation.current?.abort(); lock.current = false;
      setRecord(null); setRecordOwner(null); setLoadedFor(""); setUpgrade(null); setPlanId(""); setBusy(false); setLoading(false); setNotice("");
      setPending(memory.current); setError("登录状态已变化，请重新核对当前账户。原操作标识仍保留在本页。");
    });
    return () => { live.current = false; epoch.current += 1; operation.current?.abort(); readOperation.current?.abort(); unsubscribe(); };
  }, []);
  const reload = useCallback(() => {
    if (!owner || preview) return Promise.resolve();
    readOperation.current?.abort(); const controller = new AbortController(), version = epoch.current; readOperation.current = controller;
    const response = initialPlanId ? loadPathPlan(initialPlanId, owner, controller.signal) : loadPathFollow(path.id, owner, controller.signal);
    return response.then(value => {
      if (!live.current || controller.signal.aborted || version !== epoch.current) return;
      if (value.record && value.record.path_id !== path.id || initialPlanId && (!value.record || value.record.id !== initialPlanId || value.record.type !== "personal_plan")) throw new Error("此私人计划与当前路径不匹配，已停止恢复。请从本人计划列表重新进入。");
      setRecord(value.record); setRecordOwner(owner); setError("");
    }).catch(failure => {
      if (!live.current || controller.signal.aborted || version !== epoch.current) return;
      if (!initialPlanId && failure instanceof ApiRequestError && failure.status === 404) { setRecord(null); setRecordOwner(owner); setError(""); }
      else setError(failure instanceof Error ? failure.message : "跟读记录暂时无法读取。");
    }).finally(() => {
      if (live.current && !controller.signal.aborted && version === epoch.current) { setLoading(false); setLoadedFor(`${owner}:${initialPlanId || path.id}`); }
    });
  }, [initialPlanId, owner, path.id, preview]);
  useEffect(() => {
    if (owner && memory.current?.owner !== owner) memory.current = null;
    if (owner && !preview) void reload();
    return () => readOperation.current?.abort();
  }, [owner, preview, reload]);
  function accept(value: PathFollowResponse, command: PathFollowCommand) {
    if (value.receipt?.request_id !== command.request_id || value.receipt.deleted !== (value.record === null)) throw new Error("未能核对原操作结果。");
    if (command.action === "copy-plan" && value.record && value.record.type !== "personal_plan") throw new Error("私人计划操作结果不匹配。");
    if (command.action !== "create" && command.action !== "copy-plan" && value.record && value.record.id !== command.id) throw new Error("跟读记录操作结果不匹配。");
    if (command.action === "delete" && !value.receipt.deleted) throw new Error("未能确认删除结果。");
    memory.current = null; setPending(null); setUpgrade(null); setRecordOwner(owner);
    if (command.action === "copy-plan") {
      setPlanId(value.record?.id || ""); setNotice(value.record ? "已另存为私人阅读计划。公共路径与当前跟读进度仍保留。" : "原操作对应的计划已删除，不会通过重试重建。");
    } else { setRecord(value.record); setNotice(value.receipt.deleted ? "原跟读记录已删除。旧请求不会重新创建它。" : command.action === "upgrade" ? "已升级到所选公开版本，原进度和笔记保留。" : command.action === "note" ? "本人笔记已保存。" : command.action === "progress" ? "阅读进度已保存。" : "路径收藏状态已保存。"); }
    return value;
  }
  async function mutate(command: PathFollowCommand, recover = false): Promise<PathFollowResponse | null> {
    if (!owner || preview || lock.current || memory.current && (memory.current.owner !== owner || memory.current.command.request_id !== command.request_id)) return null;
    memory.current ||= { owner, command, dispatched: false }; setPending(memory.current);
    lock.current = true; operation.current?.abort(); const controller = new AbortController(), version = epoch.current; operation.current = controller;
    setBusy(true); setError(""); setNotice("");
    let checked = !recover;
    try {
      if (recover) {
        let prior: PathFollowResponse | null = null;
        try { prior = await findPathFollowReceipt(command.request_id, owner, controller.signal); }
        catch (failure) { if (!(failure instanceof ApiRequestError && failure.status === 404)) throw failure; }
        if (!live.current || controller.signal.aborted || version !== epoch.current) return null;
        checked = true; if (prior?.receipt) return accept(prior, command);
      }
      const result = await writePathFollow(command, owner, controller.signal, () => { if (memory.current?.command.request_id === command.request_id) memory.current.dispatched = true; });
      if (!live.current || controller.signal.aborted || version !== epoch.current) return null;
      return accept(result, command);
    } catch (failure) {
      if (!live.current || version !== epoch.current || controller.signal.aborted) return null;
      const definite = checked && !(failure instanceof PrivateOwnerVerificationError) && failure instanceof ApiRequestError && [400, 401, 403, 404, 409, 422].includes(failure.status);
      if (definite) { memory.current = null; setPending(null); }
      setError(definite ? failure instanceof Error ? failure.message : "操作未完成，请重新读取记录。" : memory.current?.dispatched ? "原操作结果尚未确认。请核对原请求后再继续，离开本页将失去查询入口。" : "当前账户尚未核对，写入请求还未发出。原请求标识已保留。");
      return null;
    } finally { if (operation.current === controller) { operation.current = null; lock.current = false; if (live.current) setBusy(false); } }
  }
  async function loadUpgrade() {
    const target = record?.latest_source_revision;
    if (!owner || preview || !record || !target || lock.current || memory.current) return;
    operation.current?.abort(); const controller = new AbortController(), version = epoch.current; operation.current = controller; lock.current = true; setBusy(true); setError("");
    try { const value = await previewPathUpgrade(record.id, target.token, owner, controller.signal); if (live.current && !controller.signal.aborted && version === epoch.current) setUpgrade(value); }
    catch (failure) { if (live.current && !controller.signal.aborted && version === epoch.current) setError(failure instanceof Error ? failure.message : "版本差异暂时无法读取。"); }
    finally { if (operation.current === controller) { operation.current = null; lock.current = false; if (live.current) setBusy(false); } }
  }
  async function copyPlan() {
    let current = record;
    if (!current) { const result = await mutate({ action: "create", request_id: createRequestKey(), path_id: path.id, expected_source_revision: path.revision.token, bookmarked: false }); current = result?.record || null; }
    if (current) await mutate({ action: "copy-plan", request_id: createRequestKey(), id: current.id, expected_revision: current.revision });
  }
  return { owner, initialPlanId, sessionReady: ["authenticated", "unauthenticated"].includes(session.status), record: recordOwner === owner ? record : null,
    busy, loading: loading || !!owner && !preview && loadedFor !== `${owner}:${initialPlanId || path.id}`, error, notice: recordOwner === owner ? notice : "", planId: recordOwner === owner ? planId : "", pending: pending?.owner === owner ? pending : null, upgrade: recordOwner === owner ? upgrade : null,
    reload: () => { setLoading(true); setError(""); return reload(); }, mutate, copyPlan, loadUpgrade, closeUpgrade: () => setUpgrade(null) };
}
export type PathPersonal = ReturnType<typeof usePathPersonal>;

export function ReadingPathActions({ path, personal, preview, initialCopy = false }: { path: PublicReadingPath; personal: PathPersonal; preview: boolean; initialCopy?: boolean }) {
  const [copyOpen, setCopyOpen] = useState(initialCopy), [deleteOpen, setDeleteOpen] = useState(false);
  const blocked = personal.busy || personal.loading || !!personal.pending || !personal.sessionReady || !!personal.error;
  const nextPath = `${readingPathHref(path)}${personal.initialPlanId ? `?copy=${encodeURIComponent(personal.initialPlanId)}` : copyOpen ? "?action=copy-plan" : ""}`;
  const login = `/login?${new URLSearchParams({ next: nextPath })}`;
  return <>
    <div className={styles.personalActions}>{preview ? <p className={styles.muted}>管理预览 · 私人收藏和进度不可操作</p> : personal.initialPlanId ? personal.record ? <><span>当前私人计划副本</span><Link className={styles.outlineButton} href={`/account/plans/${personal.record.id}`}>返回私人计划</Link></> : personal.owner ? <span className={styles.muted}>正在核对指定的本人副本</span> : <Link className={styles.primaryButton} href={login}>登录后读取本人副本</Link> : !personal.owner ? <><Link className={styles.primaryButton} href={login}><Bookmark size={16} />登录后收藏路径</Link><Link className={styles.outlineButton} href={`/login?${new URLSearchParams({ next: `${readingPathHref(path)}?action=copy-plan` })}`}><Copy size={15} />另存为私人计划</Link></> : <>
      <button type="button" className={styles.primaryButton} disabled={blocked} onClick={() => void personal.mutate(personal.record ? { action: "bookmark", request_id: createRequestKey(), id: personal.record.id, expected_revision: personal.record.revision, bookmarked: !personal.record.bookmarked } : { action: "create", request_id: createRequestKey(), path_id: path.id, expected_source_revision: path.revision.token })}>{personal.record?.bookmarked ? <Check size={16} /> : <Bookmark size={16} />}{personal.record?.bookmarked ? "已收藏路径" : "收藏路径"}</button>
      <button type="button" className={styles.outlineButton} disabled={blocked} onClick={() => setCopyOpen(true)}><Copy size={15} />另存为私人计划</button>
    </>}</div>
    {!preview && personal.loading ? <p role="status" className={styles.status}>正在核对本人跟读记录…</p> : null}
    {!preview && personal.error ? <div role="alert" className={styles.error}><p>{personal.error}</p>{!personal.pending ? <button type="button" disabled={personal.busy} onClick={() => void personal.reload()}>重新读取本人记录</button> : null}</div> : null}
    {!preview && personal.notice ? <p role="status" className={styles.status}>{personal.notice}</p> : null}
    {!preview && personal.pending ? <div className={styles.status} role="status"><p>{personal.busy ? "正在保存，请稍候。" : "原操作尚待核对，本页保留原请求标识。"}</p><button type="button" disabled={personal.busy} onClick={() => { if (personal.pending) void personal.mutate(personal.pending.command, true); }}><RefreshCw size={14} />核对原操作</button></div> : null}
    {!preview && personal.planId ? <p className={styles.status}><Link href={`/account/plans/${personal.planId}`}>打开另存的私人计划<ArrowIcon /></Link></p> : null}
    {!preview && personal.record?.type === "path_follow" ? <section data-content-section className={styles.personalSettings}><header data-section-heading>本人跟读记录</header><p>取消收藏会保留阅读进度和笔记。删除跟读记录会删除这份跟读中的本人进度与笔记，不删除另存的私人计划。</p><button type="button" disabled={blocked} onClick={() => setDeleteOpen(true)}>删除本人跟读记录</button></section> : null}
    <Dialog className={styles.dialog} open={!preview && copyOpen} aria-labelledby="path-copy-heading" onRequestClose={() => { if (!personal.busy) setCopyOpen(false); }}><header><h2 id="path-copy-heading">另存为私人阅读计划</h2><button type="button" disabled={personal.busy} aria-label="关闭另存计划" onClick={() => setCopyOpen(false)}><X size={19} /></button></header><p>复制所选路径与当前本人进度，之后在私人计划中独立安排阅读。公共路径更新不会自动改写私人计划。</p>{!personal.owner ? <Link className={styles.primaryButton} href={login}>登录后另存</Link> : personal.planId ? <Link className={styles.primaryButton} href={`/account/plans/${personal.planId}`}>打开私人计划</Link> : <button type="button" className={styles.primaryButton} disabled={blocked} onClick={() => void personal.copyPlan()}>{personal.busy ? "正在保存…" : "确认另存为私人计划"}</button>}{personal.error ? <p role="alert">{personal.error}</p> : null}{personal.pending && !personal.busy ? <button type="button" onClick={() => { if (personal.pending) void personal.mutate(personal.pending.command, true); }}>核对原操作</button> : null}</Dialog>
    <Dialog className={styles.dialog} open={!preview && deleteOpen} aria-labelledby="path-delete-heading" onRequestClose={() => { if (!personal.busy) setDeleteOpen(false); }}><header><h2 id="path-delete-heading">删除本人跟读记录</h2><button type="button" disabled={personal.busy} aria-label="关闭删除跟读记录" onClick={() => setDeleteOpen(false)}><X size={19} /></button></header><p>将删除此跟读记录的收藏、进度和本人笔记。公共路径和已经另存的私人计划不受影响。</p><button type="button" disabled={blocked} onClick={() => void (async () => { if (!personal.record) return; const result = await personal.mutate({ action: "delete", id: personal.record.id, expected_revision: personal.record.revision, request_id: createRequestKey() }); if (result?.receipt?.deleted) setDeleteOpen(false); })()}>确认删除跟读记录</button></Dialog>
  </>;
}
function ArrowIcon() { return <span aria-hidden="true"> →</span>; }
