"use client";

import Link from "next/link";
import { Clock3, ExternalLink, FileScan, Info, Pause, Play, RefreshCw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { readerOcrContentPath } from "@/lib/api/reader-ocr.client";
import { useReaderOcrStatus } from "./use-reader-ocr-status";
import styles from "./reader-ocr-status.module.css";

export type ReaderOcrStatusProps = {
  assetId: string; documentRevisionId?: string | null; ownerId?: number | null; canManage?: boolean;
  canViewManagement?: boolean;
  onRecoveryLockChange?: (locked: boolean) => void;
  /** A real page thumbnail supplied by the existing Reader; no example scan is substituted. */
  preview?: ReactNode;
};
const statusNames: Record<string, string> = {
  pending: "等待文字识别", queued: "等待文字识别", running: "正在识别文字", pausing: "正在安全暂停",
  paused: "识别已暂停", succeeded: "本次识别已完成", failed: "本次识别未完成",
  canceled: "本次识别已取消", cancelled: "本次识别已取消", disabled: "文字识别已停用", not_required: "当前版本无需文字识别",
};
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0;
function duration(value: number | null) {
  if (!finite(value)) return "暂未记录";
  const seconds = Math.floor(value), minutes = Math.floor(seconds / 60), hours = Math.floor(minutes / 60);
  return `${hours ? `${String(hours).padStart(2, "0")}:` : ""}${String(minutes % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
function checked(value: string) {
  return Number.isNaN(Date.parse(value)) ? "核对时间暂不可用" : new Date(value).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function ReaderOcrStatus({ preview, onRecoveryLockChange, ...props }: ReaderOcrStatusProps) {
  const resource = useReaderOcrStatus(props), data = resource.data, job = data?.job;
  const [confirmAbandon, setConfirmAbandon] = useState(false);
  useEffect(() => {
    onRecoveryLockChange?.(resource.pending || resource.unknown);
    return () => onRecoveryLockChange?.(false);
  }, [onRecoveryLockChange, resource.pending, resource.unknown]);
  const management = Boolean(props.ownerId != null && props.canManage && data?.owner_id === props.ownerId);
  const managementRead = Boolean(props.ownerId != null && props.canViewManagement && data?.owner_id === props.ownerId);
  const processed = data?.processed_content;
  const processedHref = processed && (processed.state === "published" || processed.state === "admin_preview" && managementRead)
    ? readerOcrContentPath(processed.url, managementRead) : "";
  const managementHref = managementRead ? readerOcrContentPath(data?.management_url, true) : "";
  const percent = job && finite(job.percent) && job.percent <= 100 ? job.percent : null;
  const hasCounts = job && finite(job.completed_pages) && finite(job.total_pages) && job.total_pages > 0 && job.completed_pages <= job.total_pages;
  const stateName = data ? statusNames[job?.status || data.ocr_status] || "文字处理状态" : "文字识别状态";
  const blocked = resource.pending || resource.unknown || resource.conflict;
  return <section className={styles.card} aria-label="文字识别进度">
    <header className={styles.heading}><div><span>OCR 文字识别</span><h2>{job?.pause_requested ? "已请求暂停，等待当前页保存" : stateName}</h2></div><button type="button" onClick={resource.refresh} disabled={resource.pending} aria-label="刷新文字识别状态"><RefreshCw size={15} /></button></header>
    {resource.loading ? <p className={styles.empty} role="status">正在读取处理状态…</p> : null}
    {data ? <>
      <div className={styles.body}>
        <div className={styles.preview}>{preview || <div className={styles.noPreview}><FileScan size={32} /><span>当前阅读文件</span></div>}
          <div className={styles.previewCaption}><strong>{job?.phase_label || (job ? "阶段暂未提供" : "当前没有关联的识别任务")}</strong>{job ? <span><Clock3 size={12} />本阶段已用时（含等待） {duration(job.phase_elapsed_seconds)}</span> : null}</div>
        </div>
        <div className={styles.progress}>
          {job ? <>
            {percent !== null ? <><progress value={percent} max={100} aria-label="本次文字识别任务进度" /><strong className={styles.percent}>{new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 }).format(percent)}<small>%</small></strong></> : <p className={styles.noMetric}>尚无可报告的处理百分比</p>}
            <p className={styles.pages}>{hasCounts ? <>本次任务已保存 <strong>{job.completed_pages}</strong> / {job.total_pages} 页</> : finite(job.completed_pages) ? <>本次任务已保存 <strong>{job.completed_pages}</strong> 页，任务总页数尚未确定</> : "本次任务尚无可报告的已处理页数"}</p>
            <p>{["succeeded", "not_required"].includes(job.status) ? "可用文字与原文引用仍以当前正式发布的版本为准。" : "你可以继续阅读扫描原页，或打开已获准查看的处理内容。"}</p>
            {job.stale ? <p className={styles.warning} role="status">任务长时间没有更新，可能已中断。请刷新状态。</p> : null}
          </> : <><p className={styles.noMetric}>当前没有可关联的 OCR 任务</p></>}
          {finite(data.file_page_count) && data.file_page_count > 0 ? <p className={styles.filePages}>整份文件共 {data.file_page_count} 页，可能与本次任务范围不同。</p> : null}
          <p className={styles.checked}>更新于 <time dateTime={data.checked_at}>{checked(data.checked_at)}</time></p>
        </div>
      </div>
      <div className={styles.actions}>
        {processedHref ? <Link className={styles.primary} href={processedHref} target="_blank" rel="noopener noreferrer"><ExternalLink size={15} />{processed?.label || "在新标签页查看已处理内容"}</Link>
          : <span className={styles.unavailable}>已处理内容暂不可打开</span>}
        {management && job ? <>
          {data.can_pause ? <button type="button" disabled={blocked} onClick={() => resource.command("pause")}><Pause size={15} />{resource.pending ? "正在确认…" : "暂停处理"}</button> : null}
          {data.can_resume ? <button type="button" disabled={blocked} onClick={() => resource.command("resume")}><Play size={15} />{resource.pending ? "正在确认…" : job.status === "failed" ? "从已保存页继续" : "继续处理"}</button> : null}
        </> : null}
      </div>
      {processed?.notice ? <p className={styles.explanation}>{processed.notice}</p> : null}
      {management && data.denied_reason && !data.can_pause && !data.can_resume ? <p className={styles.explanation}>{data.denied_reason}</p> : null}
      {managementHref ? <Link className={styles.manage} href={managementHref} target="_blank" rel="noopener noreferrer">查看文字处理详情<ExternalLink size={12} /></Link> : null}
      <aside className={styles.notice}><Info size={16} /><p>识别用时取决于任务范围与图像质量。处理期间可继续使用其他阅读功能，暂停不会清除已保存的页面。</p></aside>
    </> : !resource.loading && !resource.error ? <p className={styles.empty}>当前没有可读取的处理状态。可重新读取，正在阅读的 PDF 会保留。</p> : null}
    {resource.error ? <div className={styles.warning} role="alert"><p>{resource.error}</p>{!resource.unknown ? <button type="button" disabled={resource.pending} onClick={resource.refresh}>{resource.conflict ? "读取并核对当前任务" : "重新读取状态"}</button> : null}</div> : null}
    {resource.unknown ? <div className={styles.warning} role="status"><p>暂停或继续的结果尚未确认。原命令已保留，先查询操作结果；只有任务和原文身份都未变化时才重试原命令。</p>{!props.canManage ? <p>当前账户已无任务操作权限，可在权限恢复后查询，或明确放弃本页核对。</p> : null}<div className={styles.recoveryActions}><button type="button" disabled={resource.pending || !props.canManage} onClick={resource.recover}>{resource.pending ? "正在查询操作结果…" : "查询原处理结果"}</button><button type="button" disabled={resource.pending} onClick={() => setConfirmAbandon(true)}>放弃本页核对</button></div>
      {confirmAbandon ? <div className={styles.abandon} role="group" aria-label="确认放弃本页核对"><p>放弃后可以关闭此面板或重新登录。原命令可能已执行，这不会取消后台处理，也不会发送新命令；再次操作前应核对最新任务状态。</p><div className={styles.recoveryActions}><button type="button" disabled={resource.pending} onClick={() => setConfirmAbandon(false)}>保留并继续核对</button><button type="button" disabled={resource.pending} onClick={() => { resource.abandon(); setConfirmAbandon(false); }}>确认放弃核对</button></div></div> : null}
    </div> : null}
    {resource.pollPaused ? <div className={styles.warning} role="status"><p>状态自动刷新已暂停，后台任务可能仍在继续。</p><button type="button" disabled={resource.pending} onClick={resource.refresh}>继续读取状态</button></div> : null}
    {resource.message ? <p className={styles.message} role="status">{resource.message}</p> : null}
  </section>;
}
