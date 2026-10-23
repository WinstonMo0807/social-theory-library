"use client";

import Link from "next/link";
import { safeAdminHref } from "@/lib/admin-route-context";
import { useId, useState } from "react";
import type { components } from "@/lib/api/generated/schema";
import styles from "./processing-workspace.module.css";

type Followup = components["schemas"]["ProcessingFollowup"];
const labels: Record<Followup["state"], string> = {
  waiting: "等待识别完成", running: "正在生成待审候选", completed: "候选处理已完成",
  skipped: "已按任务设置跳过", disabled: "馆内候选服务未启用", failed: "概念对齐未完成", unrecorded: "历史任务未记录对齐结果",
};
const retryLabels: Record<string, string> = {pending:"等待处理",running:"正在处理",succeeded:"已完成",failed:"未完成，可核对后重试",canceled:"已取消",paused:"已暂停"};
const counts: Record<string, string> = { created: "新增关系候选", updated: "更新待审候选", new_node_tasks: "新增术语候选", protected_nodes: "保留人工决定" };

export function ProcessingFollowup({ value, disabled, onSave }: { value: Followup; disabled: boolean; onSave: (enabled: boolean) => Promise<void> }) {
  const [enabled, setEnabled] = useState(value.enabled), helpId = useId();
  return <section className={styles.followup} aria-label="识别完成后的操作">
    <h3>后续操作</h3>
    <label><input type="checkbox" checked={enabled} disabled={disabled || !value.can_configure} aria-describedby={helpId} onChange={event => setEnabled(event.target.checked)}/><span>完成后自动开始概念对齐（基于馆内术语表）</span></label>
    <p id={helpId} className={styles.note}>依据馆内已有术语和原文生成待审核的关系与证据。人工审核决定继续保留，候选需审核后采用。</p>
    <div className={styles.actions}><span role="status">{labels[value.state]}</span>{value.can_configure ? <button type="button" disabled={disabled || enabled === value.enabled} onClick={() => void onSave(enabled)}>保存后续操作</button> : null}</div>
    {enabled !== value.enabled && value.can_configure ? <p className={styles.note}>设置尚未保存。保存后用于本任务尚未开始的概念对齐阶段。</p> : null}
    {value.state === "completed" ? <dl className={styles.facts}>{Object.entries(value.counts).map(([key, count]) => <div key={key}><dt>{counts[key] || key}</dt><dd>{count}</dd></div>)}</dl> : null}
    {value.state === "failed" ? <p className={styles.notice}>已保存的识别结果保留。请前往关系核对查看已有候选与原文证据。可通过“只重试概念对齐”单独处理此阶段，识别文字继续保留。</p> : null}
    {value.retry_url ? <p><Link href={safeAdminHref(value.retry_url)}>查看接续概念任务 →</Link>{value.retry_status ? <span> · {retryLabels[value.retry_status] || "状态待核对"}</span> : null}</p> : null}
    {value.result_url && (value.state === "completed" || value.state === "failed") ? <Link href={safeAdminHref(value.result_url)}>查看关系与原文证据 →</Link> : null}
  </section>;
}
