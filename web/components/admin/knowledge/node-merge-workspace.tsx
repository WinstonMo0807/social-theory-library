"use client";

import Link from "next/link";
import { createPortal } from "react-dom";
import { useEffect, useId, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import type { components } from "@/lib/api/generated/schema";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { EntityPicker } from "../forms/workflow-fields";
import { useScholarSave } from "./use-scholar-save";
import styles from "./timeline-editor.module.css";

type Preview = components["schemas"]["NodeMergePreview"];
type Result = components["schemas"]["NodeMergeResult"];
type History = components["schemas"]["NodeMergeRows"];
const labels: Record<string, string> = { aliases: "别名", discipline_links: "学科", subdiscipline_links: "子学科", topic_links: "主题", work_relations: "文献关系", person_relations: "人物关系", knowledge_relations: "知识关系", evidence: "证据", timeline_events: "时间线关联", reading_path_items: "阅读路径", review_tasks: "审核任务", legacy_mappings: "历史映射" };
const statuses: Record<string, string> = { published: "已公开", draft: "草稿", pending: "待审核", rejected: "不采用", archived: "已下线" };

export function NodeMergeWorkspace({ owner, nodeId, disabled, onChanged }: {
  owner: string; nodeId: string; disabled: boolean; onChanged: () => Promise<void>;
}) {
  const user = useAdminSession(), permitted = hasAdminCapability(user, "can_merge_authority"), canRollback = hasAdminCapability(user, "can_run_system_recovery");
  const command = useScholarSave(owner, "node_merge"), life = useRef<AbortController | null>(null), acting = useRef(false), composing = useRef(false), titleId = useId();
  const [target, setTarget] = useState<{ id: string; name: string } | null>(null), [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null), [record, setRecord] = useState<Result | null>(null), [knownId, setKnownId] = useState("");
  const [history, setHistory] = useState<History | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState(""), [confirmed, setConfirmed] = useState(false), [notice, setNotice] = useState("");
  const visible = preview?.source.id === nodeId && preview.target.id === target?.id ? preview : null;
  const pending = busy || Boolean(command.recovery);
  useUnsavedForm(pending, false);
  useEffect(() => { const controller = new AbortController(); life.current = controller; return () => controller.abort(); }, [owner, nodeId]);
  async function request<T>(path: string, init: RequestInit = {}) {
    if (!owner || !life.current || life.current.signal.aborted) throw Error("请重新核对当前账户。");
    const signal = AbortSignal.any([life.current.signal, AbortSignal.timeout(60000)]);
    return withPrivateOwner(owner, () => apiRequest<T>(path, { ...init, cache: "no-store", signal, headers: { ...init.headers, "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal);
  }
  async function act(work: () => Promise<void>) {
    if (acting.current || composing.current) return;
    acting.current = true; setBusy(true); setError("");
    try { await work(); } catch (reason) { if (!life.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "操作结果尚未确认，请查回原记录。"); }
    finally { acting.current = false; if (!life.current?.signal.aborted) setBusy(false); }
  }
  function close() { if (!pending && !composing.current) { setOpen(false); setConfirmed(false); } }
  async function readPreview() {
    if (disabled || !target || command.recovery) return;
    setConfirmed(false); setPreview(null);
    await act(async () => {
      const data = await request<Preview>(`/catalog/admin/theory-system/nodes/${nodeId}/merge-preview/?target_node=${encodeURIComponent(target.id)}`);
      if (data.source.id !== nodeId || data.target.id !== target.id) throw Error("预览与原合并对象不一致，请重新读取。");
      setPreview(data); setRecord(null); setKnownId("");
    });
  }
  async function readRecord(id: string) {
    setConfirmed(false); setRecord(null); setKnownId(id);
    const data = await request<Result>(`/catalog/admin/theory-system/merges/${encodeURIComponent(id)}/rollback/`);
    if (data.id !== id) throw Error("合并记录与请求不一致。");
    setRecord(data); setKnownId(""); setTarget(null); setPreview(null);
  }
  async function merge() {
    if (!visible || !confirmed || !visible.can_merge || disabled || !permitted || !command.ready || command.recovery) return;
    await act(async () => {
      const data = await command.save<Result>(`/catalog/admin/theory-system/nodes/${nodeId}/merge/`, JSON.stringify({ target_node: visible.target.id, fingerprint: visible.fingerprint, confirmed: true, change_note: "后台人工核对重复条目及影响后合并" }), {}, "POST");
      setRecord(data); setTarget(null); setPreview(null); setConfirmed(false); setNotice("合并记录已保存，来源条目和历史保留。");
      await onChanged();
    });
  }
  async function recover(cancel = false) {
    setOpen(true);
    await act(async () => {
      const receipt = await command.lookup(cancel);
      if (receipt?.exists && receipt.node_merge_id) { await readRecord(receipt.node_merge_id); await onChanged(); }
      else if (receipt) { setConfirmed(false); setPreview(null); setNotice(receipt.state === "cancelled" ? "尚未执行的原请求已停止。" : "原请求已执行，但记录目前不可读取；请核对操作历史，不要重复提交。"); }
    });
  }
  async function readHistory(page = 1) {
    setConfirmed(false);
    await act(async () => { setHistory(await request<History>(`/catalog/admin/theory-system/nodes/${nodeId}/merges/?page=${page}`)); });
  }
  async function rollback() {
    if (!record?.rollback.can_rollback || !confirmed || !canRollback || disabled || command.recovery) return;
    await act(async () => {
      const data = await request<Result>(`/catalog/admin/theory-system/merges/${record.id}/rollback/`, { method: "POST", body: JSON.stringify({ fingerprint: record.rollback.fingerprint, confirmed: true }) });
      if (data.id !== record.id) throw Error("回退结果与原记录不一致，请重新读取。");
      setRecord(data); setConfirmed(false); setNotice("原合并已回退，后续恢复记录保留。"); await onChanged();
    });
  }
  const modal = <Dialog open={open || Boolean(command.recovery)} onRequestClose={close} aria-labelledby={titleId} className={`${styles.mergeDialog} ${styles.mergeWorkspace}`} onCompositionStartCapture={() => { composing.current = true; }} onCompositionEndCapture={() => { composing.current = false; }}>
    <header><h2 id={titleId}>重复理论或概念的合并与恢复</h2><button type="button" disabled={pending} onClick={close}>关闭</button></header>
    {notice ? <p role="status">{notice}</p> : null}{error || command.error ? <p role="alert">{error || command.error}</p> : null}
    {command.recovery ? <div><p>上次合并结果尚未核对，先查回原请求，再继续编辑。</p><button type="button" disabled={busy} onClick={() => void recover()}>查回原合并请求</button><button type="button" disabled={busy} onClick={() => void recover(true)}>停止尚未执行的请求</button></div> : null}
    {knownId ? <p role="status">已保留原记录编号。<button type="button" disabled={pending} onClick={() => void act(async () => { await readRecord(knownId); await onChanged(); })}>重新读取原合并记录</button></p> : null}
    <fieldset disabled={pending || Boolean(knownId) || !command.ready} style={{ border: 0, padding: 0 }}>
      <button type="button" onClick={() => void readHistory()}>读取合并历史</button>
      {history ? <details open><summary>合并历史 · {history.count} 条</summary><ul>{history.results.map(row => <li key={row.id}>{row.source_name} → {row.target_name} · {row.rolled_back_at ? "已回退" : "已合并"}<button type="button" onClick={() => void act(() => readRecord(row.id))}>查看记录</button></li>)}</ul><button type="button" disabled={history.page <= 1} onClick={() => void readHistory(history.page - 1)}>上一页</button><span> {history.page} / {history.pages} </span><button type="button" disabled={history.page >= history.pages} onClick={() => void readHistory(history.page + 1)}>下一页</button></details> : null}
      {record ? <><h3>{record.source_name} → {record.target_name}</h3><p><Link href={`/admin/theories?node=${record.source_node}`} target="_blank">打开来源条目 ↗</Link> · <Link href={`/admin/theories?node=${record.target_node}`} target="_blank">打开保留条目 ↗</Link></p>{record.rolled_back_at ? <p>这次合并已回退。</p> : <><p>回退恢复来源状态、原关系和本次迁移的关联；合并后已有修改时会阻止覆盖。</p><ul>{record.rollback.blockers.map((text, index) => <li key={index}>{text}</li>)}</ul><label><input type="checkbox" checked={confirmed} disabled={disabled || !canRollback || !record.rollback.can_rollback} onChange={event => setConfirmed(event.target.checked)}/>我已核对这次回退的影响</label><button type="button" disabled={disabled || !canRollback || !confirmed || !record.rollback.can_rollback} onClick={() => void rollback()}>确认回退这次合并</button></>}<button type="button" onClick={() => void act(() => readRecord(record.id))}>重新读取记录</button><button type="button" onClick={() => { setRecord(null); setConfirmed(false); }}>返回对象选择</button></> : <>
        {disabled ? <p>请先保存主体输入，并核对原保存或发布操作，再合并。</p> : null}
        <EntityPicker owner={owner} label="选择保留的理论或概念" endpoint="/catalog/admin/theory-system/nodes/" nameField="canonical_name_zh" queryParam="q" values={target ? [target] : []} onChange={values => { const row = values.at(-1); if (row?.id === nodeId) { setError("不能合并到当前条目自身。"); return; } setTarget(row?.id ? { id: row.id, name: row.name } : null); setConfirmed(false); setPreview(null); }}/>
        <button type="button" disabled={disabled || !target} onClick={() => void readPreview()}>读取合并影响</button>
        {visible ? <><div className={styles.mergeCompare}>{[visible.source, visible.target].map((row, index) => <article key={`${index}:${row.id}`}><h3>{index ? "保留条目" : "来源条目"}</h3><strong>{row.name}</strong><p>{row.name_en}</p><p>{statuses[row.status] || row.status}</p><Link href={row.editor_url} target="_blank">查看完整资料 ↗</Link></article>)}</div><p>{visible.rule}</p><ul>{Object.entries(visible.affected).map(([key, count]) => <li key={key}>{labels[key] || key}：{count} 项</li>)}</ul><ul>{visible.blockers.map((text, index) => <li key={index}>{text}</li>)}</ul><label><input type="checkbox" checked={confirmed} disabled={disabled || !visible.can_merge || !permitted} onChange={event => setConfirmed(event.target.checked)}/>确认是重复条目，已核对保留内容及公开影响</label><button type="button" disabled={disabled || !visible.can_merge || !permitted || !confirmed} onClick={() => void merge()}>合并到保留条目</button></> : null}
      </>}
    </fieldset>
  </Dialog>;
  return <section className={styles.mergeWorkspace} aria-label="理论概念合并与恢复"><h3>重复条目与原合并记录</h3><p>核对两项条目和当前影响，合并会更新公开关联并保留原记录。</p><button type="button" disabled={!permitted || !command.ready} onClick={() => setOpen(true)}>核对合并与恢复</button>{!permitted ? <p>执行合并需系统所有者权限。</p> : null}{typeof document !== "undefined" ? createPortal(modal, document.body) : null}</section>;
}
