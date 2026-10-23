"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./processing-workspace.module.css";

type Job = components["schemas"]["ProcessingWorkspaceTask"];
const activityLabels = { none: "活动记录", heartbeat: "最近心跳", checkpoint: "最近检查点", started: "开始处理", queue: "最近派发记录" };
const time = (value: string | null) => value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚无记录";

export function ProcessingTaskRecovery({ job, disabled, onRecover, onRefresh }: {
  job: Job; disabled: boolean; onRecover: () => Promise<void>; onRefresh: () => void;
}) {
  const [confirm, setConfirm] = useState(false), titleId = useId();
  const recovery = job.recovery;
  if (recovery.state === "inactive") return null;
  const delayed = recovery.state === "recoverable" || recovery.state === "delayed";
  const canRecover = recovery.can_recover && job.actions.includes("recover");
  return <section className={styles.recovery} data-delayed={delayed} aria-label="任务活动与恢复">
    <h3>{delayed ? "任务活动待核对" : recovery.state === "waiting_sources" ? "等待来源任务汇总" : "任务活动记录"}</h3>
    <p>{recovery.notice}</p>
    <dl className={styles.facts}>
      <div><dt>{activityLabels[recovery.activity_kind]}</dt><dd>{time(recovery.last_activity_at)}</dd></div>
      {recovery.eligible_at ? <div><dt>恢复保护期至</dt><dd>{time(recovery.eligible_at)}</dd></div> : null}
    </dl>
    <div className={styles.actions}>
      <button type="button" onClick={onRefresh}>继续等待并刷新</button>
      {canRecover ? <button type="button" className={styles.primary} disabled={disabled} onClick={() => setConfirm(true)}>核对并恢复任务</button> : null}
      <Link href={recovery.state === "waiting_sources" ? "/admin/processing/semantic-index" : "/admin/processing/status"}>{recovery.state === "waiting_sources" ? "查看来源进度" : "查看服务状态"}</Link>
    </div>
    <Dialog open={confirm && canRecover} onRequestClose={() => setConfirm(false)} className={`${styles.dialog} ${styles.recoveryDialog}`} aria-labelledby={titleId}>
      <header><h2 id={titleId}>恢复此处理任务</h2><button type="button" aria-label="关闭恢复确认" onClick={() => setConfirm(false)}><X size={18}/></button></header>
      <p className={styles.recoveryTitle}>{job.title}</p>
      <p>恢复前会再次核对任务活动、原材料与操作权限。已保存的页、片段和任务记录保留。</p>
      <p>{job.pause_requested ? "本任务已经请求暂停，恢复时优先保存为暂停状态。" : job.status === "pending" ? "排队任务将沿原执行编号重新通知处理队列。" : "仍符合恢复条件时，将从已保存的检查点重新派发；原执行轮次不能再提交结果。"}</p>
      <p className={styles.note}>本操作保留当前服务选择。需要更换 OCR 服务时，请使用任务中的“迁移到其他节点”。提交后请依据最新进度确认实际状态。</p>
      <div className={styles.actions}><button type="button" onClick={() => { setConfirm(false); onRefresh(); }}>继续等待</button><button type="button" className={styles.primary} disabled={disabled} onClick={() => { setConfirm(false); void onRecover(); }}>确认核对并恢复</button></div>
    </Dialog>
  </section>;
}
