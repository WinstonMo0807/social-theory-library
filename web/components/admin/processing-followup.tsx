"use client";
import Link from "next/link";
import { safeAdminHref } from "@/lib/admin-route-context";
import type { components } from "@/lib/api/generated/schema";
import styles from "./processing-workspace.module.css";

type Followup = components["schemas"]["ProcessingFollowup"];
export function ProcessingFollowup({ value }: { value: Followup; disabled: boolean; onSave: (enabled: boolean) => Promise<void> }) {
  return <section className={styles.followup} aria-label="识别后的知识编纂"><h3>知识编纂</h3>
    <p className={styles.note}>正文识别与检索更新完成后，可在 Intelligence 选择章节，核验原文并审核陈述。已有人工决定保留。</p>
    {value.result_url && <Link href={safeAdminHref(value.result_url)}>打开此书的 Intelligence 工作台</Link>}
    {Object.values(value.counts).some(v => v > 0) && <details><summary>旧候选处理记录</summary><dl className={styles.facts}>{Object.entries(value.counts).map(([key, count]) => <div key={key}><dt>{{ created: "原新增候选", updated: "原更新候选", new_node_tasks: "原术语候选", protected_nodes: "保留人工决定" }[key] || key}</dt><dd>{count}</dd></div>)}</dl></details>}
  </section>;
}
