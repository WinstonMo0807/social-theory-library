"use client";

import Link from "next/link";
import { ArrowRight, Download, FileText, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { preparePrivacyOperation, type PrivacyTarget } from "@/lib/api/privacy.client";
import { OperationDialog } from "./privacy-workspace";
import styles from "./reader-overview.module.css";

export type ReaderMaterial = { id: string; key: string; kind: string; kind_label: string; title: string; question: string; status: string; href: string; updated_at: string; revision: string };
type Intent = { requestId: string; kind: "export" | "erase"; targets: PrivacyTarget[] };
const leaves: Record<string, PrivacyTarget["category"]> = { research: "research", notes: "annotations", plans: "plans", lists: "reading_lists", audits: "audits", confirmed: "memories", saved: "saved_items" };
const erasable = new Set(["notes", "plans", "lists", "confirmed", "saved"]);
const statuses: Record<string, string> = { saved: "已保存", archived: "已归档", confirmed: "已确认", reading: "进行中", pending: "待开始", queued: "待处理", running: "处理中", completed: "已完成", complete: "已完成", partial: "部分完成", failed: "处理失败", cancelled: "已取消", canceled: "已取消", source_unavailable: "来源待核对" };

export function ReaderMaterials({ rows, ownerId, cards, onChanged }: { rows: ReaderMaterial[]; ownerId: string; cards: boolean; onChanged: () => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [intent, setIntent] = useState<Intent | null>(null);
  const [busy, setBusy] = useState(false);
  const [brokenRecovery, setBrokenRecovery] = useState(false);
  const [message, setMessage] = useState("");
  const [operation, setOperation] = useState<string | null>(null);
  const requests = useRef<AbortController | null>(null);
  const sending = useRef(false);
  const storageKey = `stl-reader-material-request:${ownerId}`;
  useEffect(() => {
    const controller = new AbortController(); requests.current = controller;
    const unsubscribe = subscribeToSessionChanges(() => controller.abort());
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      try {
        const raw = sessionStorage.getItem(storageKey);
        if (!raw) return;
        const value = JSON.parse(raw) as Intent;
        if (!value || !["export", "erase"].includes(value.kind) || typeof value.requestId !== "string" || !Array.isArray(value.targets) || !value.targets.length || value.targets.length > 20 || value.targets.some(row => !row || !Object.values(leaves).includes(row.category) || typeof row.id !== "string" || typeof row.revision !== "string")) throw new Error("任务恢复信息格式异常，请到隐私与资料核对任务后清除此记录。");
        setIntent(value); setMessage("上次请求尚未取得明确回执。可重试原请求，或先到隐私与资料核对任务。");
      } catch (reason) { setBrokenRecovery(true); setMessage(reason instanceof Error ? reason.message : "无法读取待恢复请求。"); }
    });
    return () => { controller.abort(); unsubscribe(); };
  }, [storageKey]);
  const chosen = rows.filter(row => selected.includes(row.key));
  const canErase = chosen.length > 0 && chosen.every(row => erasable.has(row.kind));
  function clearIntent() {
    sessionStorage.removeItem(storageKey); setIntent(null); setBrokenRecovery(false);
  }
  async function submit(kind?: Intent["kind"]) {
    const controller = requests.current;
    if (!controller || controller.signal.aborted || sending.current) return;
    const command = intent ?? (kind && chosen.length ? { requestId: crypto.randomUUID(), kind, targets: chosen.map(row => ({ category: leaves[row.kind], id: row.id, revision: row.revision })) } : null);
    if (!command) return;
    sending.current = true; setBusy(true); setMessage("");
    try {
      // Persist identity and versions only, before sending; a reload must reuse this request.
      sessionStorage.setItem(storageKey, JSON.stringify(command)); setIntent(command);
      const result = await withPrivateOwner(ownerId, () => preparePrivacyOperation(ownerId, command.requestId, { kind: command.kind, targets: command.targets }, controller.signal), controller.signal);
      if (controller.signal.aborted) return;
      clearIntent(); setSelected([]); setOperation(result.id); onChanged();
    } catch (reason) {
      if (controller.signal.aborted) return;
      if (reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500) {
        clearIntent();
        if (reason.status === 409) { setSelected([]); onChanged(); }
      }
      setMessage(reason instanceof Error ? reason.message : "请求尚未取得回执，请重试原请求。");
    } finally { sending.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  const locked = busy || Boolean(intent) || brokenRecovery;
  return <>
    <div className={styles.bulk}>
      <label><input type="checkbox" aria-label="选择当前页全部资料" disabled={locked || !rows.length} checked={rows.length > 0 && chosen.length === rows.length} onChange={event => setSelected(event.target.checked ? rows.map(row => row.key) : [])} />已选择 {chosen.length} 项</label>
      <button disabled={locked || !chosen.length} onClick={() => void submit("export")}><Download size={14} />导出所选</button>
      <button disabled={locked || !canErase} onClick={() => void submit("erase")}><Trash2 size={14} />删除预览</button>
      {chosen.length && !canErase ? <small>研究与体检请打开原工作台管理。</small> : <small>选择仅限当前页；删除前须核对影响。</small>}
      <Link href="/account/settings/privacy">资料任务</Link>
    </div>
    {message ? <div className={styles.bulkNotice} role="alert"><p>{message}</p>{intent || brokenRecovery ? <>{intent ? <button disabled={busy} onClick={() => void submit()}>{busy ? "正在提交…" : "重试原请求"}</button> : null}<button disabled={busy} onClick={() => { if (window.confirm("请先在隐私与资料中核对任务结果。清除这里只移除本标签页请求信息，不取消服务端任务。确认已核对？")) { try { clearIntent(); setMessage(""); } catch { setMessage("无法清除本机记录，请保留并重试。"); } } }}>已核对任务，清除恢复信息</button></> : null}</div> : null}
    <div className={`${styles.materials} ${cards ? styles.cards : ""}`}>
      <div className={styles.tableHead}><span>标题</span><span>类型</span><span>关联问题</span><span>最近更新</span><span>状态</span><span>操作</span></div>
      {rows.map(row => <article key={row.key} data-selected={selected.includes(row.key)}><div className={styles.materialTitle}><input type="checkbox" aria-label={`选择${row.title}`} checked={selected.includes(row.key)} disabled={locked} onChange={event => setSelected(previous => event.target.checked ? [...previous, row.key] : previous.filter(key => key !== row.key))} /><FileText size={18} /><Link href={row.href}><strong>{row.title}</strong></Link></div><span className={styles.kind}>{row.kind_label}</span><p className={styles.question}>{row.question || "—"}</p><time dateTime={row.updated_at}>{new Date(row.updated_at).toLocaleDateString("zh-CN")}</time><span className={styles.status} data-state={row.status}>{statuses[row.status] || "待核对"}</span><Link className={styles.open} href={row.href} aria-label={`打开${row.title}`}>打开 <ArrowRight size={14} /></Link></article>)}
    </div>
    {operation ? <OperationDialog id={operation} ownerId={ownerId} titles={Object.fromEntries(rows.map(row => [row.id, row.title]))} onClose={() => { setOperation(null); onChanged(); }} onChanged={onChanged} onInvalid={reason => setMessage(reason instanceof Error ? reason.message : "任务暂不可用，请重新读取。")} /> : null}
  </>;
}
