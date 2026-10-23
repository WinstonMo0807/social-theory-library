"use client";

import Link from "next/link";
import { ArrowRight, Download, FileText, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import type { PrivacyTarget } from "@/lib/api/privacy.client";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { PrivacyRequestRecovery, usePrivacyPreparation } from "./privacy-request-recovery";
import { OperationDialog } from "./privacy-workspace";
import styles from "./reader-overview.module.css";

export type ReaderMaterial = { id: string; key: string; kind: string; kind_label: string; title: string; question: string; status: string; href: string; updated_at: string; revision: string };
const leaves: Record<string, PrivacyTarget["category"]> = { research: "research", notes: "annotations", bookmarks: "bookmarks", plans: "plans", lists: "reading_lists", audits: "audits", confirmed: "memories", saved: "saved_items" };
const erasable = new Set(["notes", "bookmarks", "plans", "lists", "confirmed", "saved"]);
const statuses: Record<string, string> = { saved: "已保存", archived: "已归档", confirmed: "已确认", reading: "进行中", pending: "待开始", queued: "待处理", running: "处理中", completed: "已完成", complete: "已完成", partial: "部分完成", failed: "处理失败", cancelled: "已取消", canceled: "已取消", source_unavailable: "来源待核对" };

export function ReaderMaterials({ rows, ownerId, cards, onChanged, onGuardChange }: { rows: ReaderMaterial[]; ownerId: string; cards: boolean; onChanged: () => void; onGuardChange: (guarded: boolean) => void }) {
  const [selected, setSelected] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [operation, setOperation] = useState<string | null>(null);
  const preparation = usePrivacyPreparation(ownerId, `stl-reader-material-request:${ownerId}`);
  const chosen = rows.filter(row => selected.includes(row.key));
  const canErase = chosen.length > 0 && chosen.every(row => erasable.has(row.kind));
  useUnsavedForm(chosen.length > 0 && !preparation.pending, false);
  const guarded = chosen.length > 0 || preparation.pending || preparation.busy;
  useEffect(() => { onGuardChange(guarded); }, [guarded, onGuardChange]);
  function openOperation(id: string) { setSelected([]); setOperation(id); onChanged(); }
  async function submit(kind: "export" | "erase") {
    if (!chosen.length) return;
    const id = await preparation.prepare({ kind, targets: chosen.map(row => ({ category: leaves[row.kind], id: row.id, revision: row.revision })) });
    if (id) openOperation(id);
  }
  const locked = preparation.locked;
  return <>
    <div className={styles.bulk}>
      <label><input type="checkbox" aria-label="选择当前页全部资料" disabled={locked || !rows.length} checked={rows.length > 0 && chosen.length === rows.length} onChange={event => setSelected(event.target.checked ? rows.map(row => row.key) : [])} />已选择 {chosen.length} 项</label>
      <button type="button" disabled={locked || !chosen.length} onClick={() => void submit("export")}><Download size={14} />导出所选</button>
      <button type="button" disabled={locked || !canErase} onClick={() => void submit("erase")}><Trash2 size={14} />删除预览</button>
      {chosen.length && !canErase ? <small>研究与体检请打开原工作台管理。</small> : <small>选择仅限当前页；删除前须核对影响。</small>}
      <Link href="/account/settings/privacy">资料任务</Link>
    </div>
    <PrivacyRequestRecovery preparation={preparation} onOpen={openOperation} className={styles.bulkNotice} />
    {message ? <div className={styles.bulkNotice} role="alert"><p>{message}</p></div> : null}
    {rows.length ? <div className={`${styles.materials} ${cards ? styles.cards : ""}`}>
      <div className={styles.tableHead}><span>标题</span><span>类型</span><span>关联问题</span><span>最近更新</span><span>状态</span><span>操作</span></div>
      {rows.map(row => <article key={row.key} data-selected={selected.includes(row.key)}><div className={styles.materialTitle}><input type="checkbox" aria-label={`选择${row.title}`} checked={selected.includes(row.key)} disabled={locked} onChange={event => setSelected(previous => event.target.checked ? [...previous, row.key] : previous.filter(key => key !== row.key))} /><FileText size={18} /><Link href={row.href}><strong>{row.title}</strong></Link></div><span className={styles.kind}>{row.kind_label}</span><p className={styles.question}>{row.question || "—"}</p><time dateTime={row.updated_at}>{new Date(row.updated_at).toLocaleDateString("zh-CN")}</time><span className={styles.status} data-state={row.status}>{statuses[row.status] || "待核对"}</span><Link className={styles.open} href={row.href} aria-label={`打开${row.title}`}>打开 <ArrowRight size={14} /></Link></article>)}
    </div> : null}
    {operation ? <OperationDialog id={operation} ownerId={ownerId} titles={Object.fromEntries(rows.map(row => [row.id, row.title]))} onClose={() => { setOperation(null); onChanged(); }} onChanged={onChanged} onInvalid={reason => setMessage(reason instanceof Error ? reason.message : "任务暂不可用，请重新读取。")} /> : null}
  </>;
}
