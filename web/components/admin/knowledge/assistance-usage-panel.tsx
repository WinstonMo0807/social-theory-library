"use client";

import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export type AssistanceUsage = {
  scope: string; target_type: string; target_id: string; generated_at: string;
  period_start: string | null; period_end: string | null; total: number;
  counts: Record<string, number>; reviewed: number;
  acceptance: { numerator: number; denominator: number; is_accuracy: false };
  unknown_reason: string; event_count: number; event_limit: number;
  modified_adoptions?: number; removed_prefills?: number; unclassified_prefill_changes?: number;
  events: Array<{ id: string; candidate_id: string; action: string; created_at: string; record_url: string }>;
  candidate_records: Array<{ id: string; field: string; status: string; source: string; reviewed_at: string | null; reason: string; record_url: string }>;
};

const statusLabels: Record<string, string> = { pending: "待复核", accepted: "已采用", rejected: "未采用", superseded: "已取代" };
export function AssistanceUsagePanel({ usage }: { usage: AssistanceUsage }) {
  const [opened, setOpened] = useState("");
  const [record, setRecord] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function inspect(id: string, url: string) {
    if (busy) return;
    setBusy(true); setOpened(id); setRecord(null); setError("");
    try { setRecord(await apiRequest<Record<string, unknown>>(url, {}, getServerSessionCredential())); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "原始记录暂时不可读取，请重试。"); }
    finally { setBusy(false); }
  }
  return <details className="admin-panel assistance-history" aria-label="建议处理记录">
    <summary>建议处理记录 · {usage.total} 条</summary>
    <p>统计范围：{usage.period_start ? new Date(usage.period_start).toLocaleString("zh-CN") : "尚无数据"} 至 {usage.period_end ? new Date(usage.period_end).toLocaleString("zh-CN") : "尚无数据"}；读取于 {new Date(usage.generated_at).toLocaleString("zh-CN")}。</p>
    <p>待复核 {usage.counts.pending ?? 0} · 已采用 {usage.counts.accepted ?? 0} · 未采用 {usage.counts.rejected ?? 0} · 已取代 {usage.counts.superseded ?? 0}</p>
    <p>{usage.acceptance.denominator ? `处理过的 ${usage.acceptance.denominator} 条建议中，采用了 ${usage.acceptance.numerator} 条。` : "还没有处理过建议。"}这只是操作记录，不表示建议内容一定正确。</p>
    <p>明确修改后采用 {usage.modified_adoptions ?? 0} 条 · 填入后不再使用 {usage.removed_prefills ?? 0} 条 · 未区分的历史调整 {usage.unclassified_prefill_changes ?? 0} 条。</p>
    <details><summary>统计范围与限制</summary><p>{usage.scope}</p><p>{usage.unknown_reason}</p></details>
    {!usage.total ? <p>尚无字段候选记录。不表示检索失败或服务未配置；需要时请从具体字段明确发起查找。</p> : null}
    <details><summary>追溯候选与人工复核记录</summary>{usage.candidate_records.map((row) => <article key={row.id}><strong>{row.field} · {statusLabels[row.status] || row.status}</strong><p>来源：{row.source}；复核时间：{row.reviewed_at ? new Date(row.reviewed_at).toLocaleString("zh-CN") : "尚未复核"}</p>{row.reason ? <p>理由：{row.reason}</p> : null}<small>候选编号 {row.id}</small><button className="button secondary" type="button" disabled={busy} onClick={() => void inspect(row.id, row.record_url)}>读取原始候选</button></article>)}
      <p>相关操作事件 {usage.event_count} 条，下列最多 {usage.event_limit} 条，计数来自完整查询。</p>
      {usage.events.map((row) => <p key={row.id}>{{accept_field_enrichment_candidate: "采用", reject_field_enrichment_candidate: "未采用", field_prefill_modified_adoption: "修改后采用", field_prefill_removed: "填入后不再使用", field_prefill_removed_or_edited: "填写有调整，未判定是否采用"}[row.action] || "建议处理"} · {new Date(row.created_at).toLocaleString("zh-CN")} · 事件 {row.id} · 候选 {row.candidate_id}</p>)}
      {opened ? <div aria-live="polite"><h4>原始候选 {opened}</h4>{busy ? <p>读取中…</p> : null}{error ? <p role="alert">{error}</p> : null}{record ? <dl>{["field_name", "proposed_value", "source_class", "status", "review_reason", "evidence"].filter((key) => record[key] !== undefined).map((key) => <div key={key}><dt>{key}</dt><dd style={{ overflowWrap: "anywhere" }}>{typeof record[key] === "object" ? JSON.stringify(record[key]) : String(record[key])}</dd></div>)}</dl> : null}</div> : null}
    </details>
  </details>;
}
