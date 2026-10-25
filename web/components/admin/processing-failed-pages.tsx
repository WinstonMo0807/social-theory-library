"use client";

import Link from "next/link";
import { useCallback, useId, useState } from "react";
import { X } from "lucide-react";
import type { components } from "@/lib/api/generated/schema";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { safeAdminHref } from "@/lib/admin-route-context";
import { Dialog } from "@/components/ui/dialog";
import { ocrPageRanges } from "./workflow/edition-ocr-control";
import styles from "./processing-workspace.module.css";

type Job = components["schemas"]["ProcessingWorkspaceTask"];
type FailedPageList = components["schemas"]["ProcessingFailedPage"];

export function ProcessingFailedPages({ job, owner, disabled, onRetry, onRefresh }: {
  job: Job; owner: string; disabled: boolean; onRetry: (pages: number[]) => Promise<void>; onRefresh: () => void;
}) {
  const [selected, setSelected] = useState<number[]>([]), [confirmation, setConfirmation] = useState<number[] | null>(null);
  const [page, setPage] = useState(1), [notice, setNotice] = useState("");
  const titleId = useId(), canRetry = job.actions.includes("retry");
  const load = useCallback(async (url: string, signal: AbortSignal) => {
    const data = await apiRequest<FailedPageList>(url, { signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false);
    if (data.owner_id !== owner) throw new PrivateOwnerVerificationError("账户已变化，请重新打开任务。", 403);
    if (data.job_id !== job.id || data.version !== job.version || data.page !== page) throw Error("中断页列表与当前任务不一致，请重新读取任务。");
    return data;
  }, [owner, job.id, job.version, page]);
  const resource = usePersistentWorkspace<FailedPageList>(`/ingestion/processing-workspace/failed-pages/${encodeURIComponent(job.id)}/?${new URLSearchParams({ expected_version: job.version, page: String(page) })}`, owner, undefined, load);
  const data = resource.error ? null : resource.data, pages = data?.results || [];
  const locked = disabled || !canRetry || !data || resource.loading;
  function pageUrl(index: number) { return `${safeAdminHref(job.result_urls.ocr)}?view=issues&status=failed&pdf_page=${index}`; }
  function select(values: number[], checked: boolean) {
    const next = checked ? [...new Set([...selected, ...values])].sort((a, b) => a - b) : selected.filter(value => !values.includes(value));
    if (next.length > 20000) { setNotice("一次最多选择20000页，请先处理当前选择。没有截断选择。"); return; }
    setSelected(next); setNotice("");
  }
  return <section className={styles.failedPages} aria-label="选择中断页重试">
    <p>以下页面在本任务中断时尚未确认保存。已完成页继续保留在原检查点。</p>
    {resource.error ? <p role="alert" className={styles.notice}>{resource.error}<button type="button" disabled={disabled} onClick={() => { resource.reload(); onRefresh(); }}>重新读取任务与中断页</button></p> : null}
    {resource.loading ? <p role="status">正在读取中断页…</p> : null}
    {notice ? <p role="status" className={styles.note}>{notice}</p> : null}
    {data ? <><div className={styles.failureTableScroll}><table className={styles.failureTable} aria-label="中断页列表">
      <thead><tr><th><input type="checkbox" aria-label="选择当前列出的全部中断页" disabled={locked} checked={Boolean(pages.length) && pages.every(value => selected.includes(value))} onChange={event => select(pages, event.target.checked)}/></th><th>所在位置</th><th>记录状态</th><th>操作</th></tr></thead>
      <tbody>{pages.map(index => <tr key={index}><td><input type="checkbox" aria-label={`选择 PDF 第 ${index} 页`} checked={selected.includes(index)} disabled={locked} onChange={event => select([index], event.target.checked)}/></td><td>PDF 第 {index} 页</td><td>中断，尚未确认保存</td><td>{job.result_urls.ocr ? <Link href={pageUrl(index)}>对照原页</Link> : null}</td></tr>)}</tbody>
    </table></div>{!pages.length ? <p role="status">当前任务没有可选的中断页，请重新读取任务状态。</p> : null}
    {data.pages > 1 ? <nav className={styles.actions} aria-label="中断页分页"><button type="button" disabled={disabled || page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {data.page} / {data.pages} 页 · 共 {data.count} 个中断页</span><button type="button" disabled={disabled || page >= data.pages} onClick={() => setPage(value => value + 1)}>下一页</button></nav> : null}</> : null}
    <div className={styles.actions}><span>已选 {selected.length} 页（跨页保留）</span><button type="button" className={styles.primary} disabled={locked || !selected.length} onClick={() => setConfirmation([...selected])}>重试所选中断页</button><button type="button" disabled={!selected.length || disabled} onClick={() => setSelected([])}>清除选择</button></div>
    <p className={styles.note}>沿原任务、文件和识别设置重试。任务记录改变后需重新核对选择；其余未完成页暂停等待继续，不重做已保存页，也不将局部完成记为整份文件完成。</p>
    <Dialog open={Boolean(confirmation)} onRequestClose={() => setConfirmation(null)} className={`${styles.dialog} ${styles.recoveryDialog}`} aria-labelledby={titleId}>
      <header><h2 id={titleId}>核对本次重试范围</h2><button type="button" aria-label="关闭重试确认" onClick={() => setConfirmation(null)}><X size={18}/></button></header>
      <p className={styles.recoveryTitle}>{job.title}</p><p>仅处理 PDF 第 {ocrPageRanges(confirmation || [])} 页，保持原识别设置与人工文字保护。</p>
      <p>提交时重新核对原任务、来源与页面状态。其余未完成页暂停等待继续；已保存结果保留。</p>
      <div className={styles.actions}><button type="button" onClick={() => setConfirmation(null)}>返回选择</button><button type="button" className={styles.primary} disabled={locked} onClick={() => { const values = confirmation; setConfirmation(null); if (values?.length) void onRetry(values); }}>确认重试这些页</button></div>
    </Dialog>
  </section>;
}
