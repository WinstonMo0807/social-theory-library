"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import type { components } from "@/lib/api/generated/schema";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { useScholarSave } from "./use-scholar-save";
import styles from "./timeline-editor.module.css";

type Preview = components["schemas"]["TimelineMergePreview"];
type Result = components["schemas"]["TimelineMergeResult"];
type History = components["schemas"]["MergeRows"];

export function TimelineMergeWorkspace({ owner, eventId, targetId, onTargetChange, disabled, onChanged, onPendingChange }: {
  owner: string; eventId: string; targetId: string; onTargetChange: (id: string) => void; disabled: boolean; onChanged: () => void; onPendingChange: (value: boolean) => void;
}) {
  const user = useAdminSession(), permitted = hasAdminCapability(user, "can_merge_authority");
  const command = useScholarSave(owner, "timeline_merge"), life = useRef<AbortController | null>(null), acting = useRef(false), titleId = useId();
  const [preview, setPreview] = useState<{ key: string; data: Preview } | null>(null), [record, setRecord] = useState<Result | null>(null);
  const [history, setHistory] = useState<History | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [confirmed, setConfirmed] = useState(false), [notice, setNotice] = useState("");
  const key = `${eventId}:${targetId}`, visible = preview?.key === key ? preview.data : null;
  const pending = busy || Boolean(command.recovery);
  useUnsavedForm(pending, false);
  useEffect(() => { onPendingChange(pending); return () => onPendingChange(false); }, [pending, onPendingChange]);
  useEffect(() => { const controller = new AbortController(); life.current = controller; return () => controller.abort(); }, [owner, eventId]);
  async function request<T>(path: string, init: RequestInit = {}) {
    if (!owner || !life.current || life.current.signal.aborted) throw Error("请重新核对当前账户。");
    const signal = AbortSignal.any([life.current.signal, AbortSignal.timeout(60000)]);
    return withPrivateOwner(owner, () => apiRequest<T>(path, { ...init, cache: "no-store", signal, headers: { ...init.headers, "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal);
  }
  async function act(work: () => Promise<void>) {
    if (acting.current) return;
    acting.current = true; setBusy(true); setError("");
    try { await work(); } catch (reason) { if (!life.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "操作结果尚未确认，请查回原记录。"); }
    finally { acting.current = false; if (!life.current?.signal.aborted) setBusy(false); }
  }
  function close() { if (!pending) { onTargetChange(""); setRecord(null); setConfirmed(false); setError(""); } }
  async function readPreview() {
    if (disabled || !targetId || command.recovery) return;
    await act(async () => { const data = await request<Preview>("/catalog/admin/theory-timeline/merge-preview/", { method: "POST", body: JSON.stringify({ source_id: eventId, target_id: targetId }) }); setPreview({ key, data }); setConfirmed(false); });
  }
  async function merge() {
    if (!visible || !confirmed || !visible.can_merge || !permitted || disabled || !command.ready) return;
    await act(async () => {
      const data = await command.save<Result>("/catalog/admin/theory-timeline/merge/", JSON.stringify({ source_id: eventId, target_id: targetId, fingerprint: visible.fingerprint, confirmed: true }), {}, "POST");
      setRecord(data); onTargetChange(""); setConfirmed(false); setNotice("归并已保存，来源事件与历史保留。"); onChanged();
    });
  }
  async function recover(cancel = false) {
    await act(async () => {
      const receipt = await command.lookup(cancel);
      if (receipt?.exists && receipt.timeline_merge_id) { setRecord(await request<Result>(`/catalog/admin/theory-timeline/merges/${receipt.timeline_merge_id}/`)); onTargetChange(""); onChanged(); }
      else if (receipt?.state === "cancelled") { setNotice("尚未执行的归并请求已停止。"); setConfirmed(false); }
    });
  }
  async function readHistory(page = 1) {
    await act(async () => { setHistory(await request<History>(`/catalog/admin/theory-timeline/${eventId}/merges/?page=${page}`)); });
  }
  async function readRecord(id: string) {
    await act(async () => { setRecord(await request<Result>(`/catalog/admin/theory-timeline/merges/${id}/`)); onTargetChange(""); setConfirmed(false); });
  }
  async function rollback() {
    if (!record?.rollback.can_rollback || !confirmed || !permitted || disabled) return;
    await act(async () => { setRecord(await request<Result>(`/catalog/admin/theory-timeline/merges/${record.id}/`, { method: "POST", body: JSON.stringify({ fingerprint: record.rollback.fingerprint, confirmed: true }) })); setConfirmed(false); setNotice("归并已回退，后续修订记录保留。"); onChanged(); });
  }
  return <section className={styles.mergeWorkspace} aria-label="重复事件归并与恢复">
    <button type="button" disabled={pending} onClick={() => void readHistory()}>归并记录与回退</button>
    {notice ? <p role="status">{notice}</p> : null}
    {command.recovery ? <div role="status"><p>上次归并结果尚未核对。请先查回，避免重复提交。</p><button type="button" disabled={busy} onClick={() => void recover()}>查回原请求</button><button type="button" disabled={busy} onClick={() => void recover(true)}>停止尚未执行的请求</button></div> : null}
    {error || command.error ? <p role="alert">{error || command.error}</p> : null}
    {history ? <details open><summary>归并历史 · {history.count} 条</summary><ul>{history.results.map(row => <li key={row.id}><span>{row.source_title} → {row.target_title} · {row.rolled_back_at ? "已回退" : "已归并"}</span><button type="button" disabled={pending} onClick={() => void readRecord(row.id)}>查看记录</button></li>)}</ul><div className={styles.controls}><button type="button" disabled={pending || history.page <= 1} onClick={() => void readHistory(history.page - 1)}>上一页</button><span>{history.page} / {history.pages}</span><button type="button" disabled={pending || history.page >= history.pages} onClick={() => void readHistory(history.page + 1)}>下一页</button></div></details> : null}
    <Dialog open={Boolean(targetId || record)} onRequestClose={close} aria-labelledby={titleId} className={styles.mergeDialog} onKeyDown={event => { if (event.key === "Escape" && event.nativeEvent.isComposing) event.preventDefault(); }}>
      <header><h2 id={titleId}>{record ? "归并记录与回退" : "核对重复事件"}</h2><button type="button" disabled={pending} onClick={close}>关闭</button></header>
      {record ? <><p>{record.source_title} → {record.target_title}</p><p><Link href={`/admin/theories/timeline?event=${record.source}`} target="_blank">打开来源事件</Link> · <Link href={`/admin/theories/timeline?event=${record.target}`} target="_blank">打开保留事件</Link></p>{record.rolled_back_at ? <p>这次归并已回退。原操作与后续恢复修订仍保留。</p> : <><p>回退会恢复两条事件及此次汇入的页面编排。归并后有新修改时会阻止覆盖。</p><ul>{record.rollback.blockers.map((text, index) => <li key={index}>{text}</li>)}</ul><label className={styles.confirmation}><input type="checkbox" checked={confirmed} disabled={busy || disabled || !permitted || !record.rollback.can_rollback} onChange={event => setConfirmed(event.target.checked)}/>我已核对这次回退</label><button type="button" disabled={busy || disabled || !permitted || !confirmed || !record.rollback.can_rollback} onClick={() => void rollback()}>确认回退</button></>}<button type="button" disabled={busy} onClick={() => void readRecord(record.id)}>重新核对记录</button></> : <>
        <p>先保存当前输入。读取并核对两条事件的日期、版本、出处和关联，再决定是否归并。</p>
        <button type="button" disabled={busy || disabled || Boolean(command.recovery)} onClick={() => void readPreview()}>{busy ? "正在读取…" : "读取归并影响"}</button>
        {visible ? <><div className={styles.mergeCompare}>{[visible.source, visible.target].map((row, index) => <article key={`${index}:${row.id}`}><h3>{index ? "保留事件" : "来源事件"}</h3><strong>{row.title}</strong><p>{row.event_type} · {row.start_date || row.date_label || row.start_year || "时间待确认"}{row.end_date || row.end_year ? ` 至 ${row.end_date || row.end_year}` : ""} · {row.date_precision}</p><p>{row.description}</p><p>主要出处：{row.source || "尚未填写"}</p><Link href={row.editor_url} target="_blank">打开原事件</Link></article>)}</div><p>{visible.rule}</p><p>归并后补充出处 {visible.source_count} 条，关联 {visible.relation_count} 条，页面编排 {visible.placement_count} 项。{visible.will_be_public ? "本次确认会更新公开事件。" : "结果保持未公开。"}</p><ul>{visible.blockers.map((text, index) => <li key={index}>{text}</li>)}</ul><label className={styles.confirmation}><input type="checkbox" checked={confirmed} disabled={busy || disabled || !permitted || !visible.can_merge} onChange={event => setConfirmed(event.target.checked)}/>确认是同一事件，并已核对保留内容及影响</label><button type="button" disabled={busy || disabled || !permitted || !confirmed || !visible.can_merge || Boolean(command.recovery)} onClick={() => void merge()}>合并到保留事件</button><button type="button" disabled={pending} onClick={close}>保留独立，返回填写说明</button></> : null}
      </>}
      {!permitted ? <p>当前账户可以核对影响，执行归并与回退需系统所有者权限。</p> : null}
      {error || command.error ? <p role="alert">{error || command.error}</p> : null}
      {command.recovery ? <div className={styles.controls}><button type="button" disabled={busy} onClick={() => void recover()}>查回原请求</button><button type="button" disabled={busy} onClick={() => void recover(true)}>停止尚未执行的请求</button></div> : null}
    </Dialog>
  </section>;
}
