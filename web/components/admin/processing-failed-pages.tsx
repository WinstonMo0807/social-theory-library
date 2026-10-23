"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { X } from "lucide-react";
import type { components } from "@/lib/api/generated/schema";
import { safeAdminHref } from "@/lib/admin-route-context";
import { Dialog } from "@/components/ui/dialog";
import { ocrPageRanges } from "./workflow/edition-ocr-control";
import styles from "./processing-workspace.module.css";

type Job = components["schemas"]["ProcessingWorkspaceTask"];

export function ProcessingFailedPages({ job, disabled, onRetry }: {
  job: Job; disabled: boolean; onRetry: (pages: number[]) => Promise<void>;
}) {
  const [selected, setSelected] = useState<number[]>([]), [confirmation, setConfirmation] = useState<number[] | null>(null);
  const titleId = useId(), pages = job.failure_pages, canRetry = job.actions.includes("retry");
  const chosen = pages.filter(page => selected.includes(page));
  function pageUrl(page: number) { return `${safeAdminHref(job.result_urls.ocr)}?view=issues&status=failed&pdf_page=${page}`; }
  return <section className={styles.failedPages} aria-label="选择中断页重试">
    <p>以下页面在本任务中断时尚未确认保存。已完成页继续保留在原检查点。</p>
    <div className={styles.failureTableScroll}><table className={styles.failureTable}>
      <thead><tr><th><input type="checkbox" aria-label="选择当前列出的全部中断页" disabled={disabled || !canRetry} checked={Boolean(pages.length) && chosen.length === pages.length} onChange={event => setSelected(event.target.checked ? [...pages] : [])}/></th><th>所在位置</th><th>记录状态</th><th>操作</th></tr></thead>
      <tbody>{pages.map(page => <tr key={page}><td><input type="checkbox" aria-label={`选择 PDF 第 ${page} 页`} checked={chosen.includes(page)} disabled={disabled || !canRetry} onChange={event => setSelected(current => event.target.checked ? [...current, page] : current.filter(value => value !== page))}/></td><td>PDF 第 {page} 页</td><td>中断，尚未确认保存</td><td>{job.result_urls.ocr ? <Link href={pageUrl(page)}>对照原页</Link> : null}</td></tr>)}</tbody>
    </table></div>
    {job.failure_page_count > pages.length ? <p className={styles.note}>本处列出前 {pages.length} 页，共记录 {job.failure_page_count} 页；可以先处理所选页，其他页面继续保留。</p> : null}
    <div className={styles.actions}><span>已选 {chosen.length} 页</span><button type="button" className={styles.primary} disabled={disabled || !canRetry || !chosen.length} onClick={() => setConfirmation(chosen)}>重试所选中断页</button><button type="button" disabled={!chosen.length || disabled} onClick={() => setSelected([])}>清除选择</button></div>
    <p className={styles.note}>沿原任务、文件和识别设置重试。所选页处理结束后，其他未完成页会暂停等待继续；不会重做已保存页，也不将局部完成记为整份文件完成。</p>
    <Dialog open={Boolean(confirmation)} onRequestClose={() => setConfirmation(null)} className={`${styles.dialog} ${styles.recoveryDialog}`} aria-labelledby={titleId}>
      <header><h2 id={titleId}>核对本次重试范围</h2><button type="button" aria-label="关闭重试确认" onClick={() => setConfirmation(null)}><X size={18}/></button></header>
      <p className={styles.recoveryTitle}>{job.title}</p><p>仅处理 PDF 第 {ocrPageRanges(confirmation || [])} 页，保持原识别设置与人工文字保护。</p>
      <p>提交时重新核对原任务、来源与页面状态。其余未完成页暂停等待继续；已保存结果保留。</p>
      <div className={styles.actions}><button type="button" onClick={() => setConfirmation(null)}>返回选择</button><button type="button" className={styles.primary} disabled={disabled || !canRetry} onClick={() => { const values = confirmation; setConfirmation(null); if (values?.length) void onRetry(values); }}>确认重试这些页</button></div>
    </Dialog>
  </section>;
}
