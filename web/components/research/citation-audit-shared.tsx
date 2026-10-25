"use client";

import Link from "next/link";
import { LockKeyhole } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { isTaskRunning } from "@/lib/api/task-polling";
import type { AuditData, AuditLocation, AuditOccurrence, ResearchRecord } from "@/lib/api/research.client";

export const auditStatuses: Record<string, string> = { queued: "排队中", running: "处理中", completed: "检查已完成", partial: "部分结果待核对", failed: "处理未完成", canceled: "已取消", cancelled: "已取消" };
export const auditDecisions = { accepted: "已核对", ignored: "暂时忽略", corrected: "已记录修正", needs_review: "仍待核对" };
export const auditFindingNames: Record<string, string> = { identity: "书目身份", fulltext: "原文可用性", support: "论断关系", direct_quote: "引文文字", private_quote: "本人来源文字", page: "页码" };
export const auditCategories = { all: "全部", text_match: "文字已匹配", unverified: "待核对", unavailable: "原文不可用", corrected: "本人已修正", accepted: "本人已核对", ignored: "暂时忽略" };
export type AuditCategory = keyof typeof auditCategories;

export function auditEvidenceChanged(row: AuditOccurrence) {
  const unavailable = (reference: { source_status: string; anchors?: { source_status: string }[] }) => reference.source_status !== "available" || reference.anchors?.some(anchor => anchor.source_status !== "available");
  return row.findings.some(finding => finding.status === "source_unavailable" || finding.source_status === "source_unavailable"
    || finding.references?.some(unavailable) || finding.private_references?.some(unavailable))
    || Boolean(row.support_analysis?.reference && unavailable(row.support_analysis.reference));
}
export function AuditEvidenceNotice({ row }: { row: AuditOccurrence }) {
  return row.decision && auditEvidenceChanged(row) ? <p className="stl4-audit-caption" role="alert">核对依据已变化或不可用，需重新核对。前次人工决定与校正文案保留。</p> : null;
}
export function auditCategory(row: AuditOccurrence): AuditCategory {
  if (row.decision) {
    if (row.decision.value === "needs_review" || auditEvidenceChanged(row)) return "unverified";
    return row.decision.value;
  }
  if (auditEvidenceChanged(row) || row.findings.some(finding => finding.kind === "fulltext")) return "unavailable";
  if (row.findings.length && row.findings.every(finding => finding.status === "text_match" && finding.page_status !== "needs_review")) return "text_match";
  return "unverified";
}

export function auditLocation(location?: AuditLocation) {
  if (!location) return "位置待核对";
  const parts = [location.pdf_page ? `稿件 PDF 第 ${location.pdf_page} 页` : location.part?.includes("footnote") ? "脚注" : location.part?.includes("endnote") ? "尾注" : "正文"];
  if (location.note_id != null) parts.push(`编号 ${location.note_id}`);
  if (location.paragraph != null) parts.push(`第 ${location.paragraph + 1} 段`);
  if (location.start !== undefined) parts.push(`字符 ${location.start + 1}–${location.end ?? location.start + 1}`);
  return parts.join(" · ");
}

export function AuditFrame({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`stl4-research-page stl4-audit-page ${className}`.trim()}><div className="stl4-research-detail-shell">{children}</div></div>;
}
export function AuditGate({ next, children }: { next: string; children: (ownerId: string, retrySession: () => void) => ReactNode }) {
  const { state, retry } = useSessionBootstrap();
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(next)}`); }, [state.status, next]);
  if (state.status === "forbidden" || state.status === "temporary_error") return <AuditFrame><div className="stl4-research-state" role="alert"><h2>暂时无法读取引文体检</h2><p>{state.message}</p><button onClick={retry}>重新验证登录</button></div></AuditFrame>;
  if (state.status !== "authenticated" || !state.user) return <AuditFrame><div className="stl4-research-state" role="status">正在核对登录状态…</div></AuditFrame>;
  return <div key={state.user.id}>{children(String(state.user.id), retry)}</div>;
}
export function AuditBreadcrumb({ id, issue, parse }: { id?: string; issue?: boolean; parse?: boolean }) {
  return <nav className="stl4-research-breadcrumb" aria-label="面包屑"><Link href="/account">读者中心</Link><span>/</span><Link href="/account/citation-audits">引文体检</Link>{id ? <><span>/</span>{issue ? <Link href={`/account/citation-audits/${id}`}>体检报告</Link> : <span>{parse ? "解析与核对" : "体检报告"}</span>}</> : null}{issue ? <><span>/</span><span>原文核验</span></> : null}<span className="stl4-audit-private"><LockKeyhole size={12} />仅本人可见</span></nav>;
}
export function AuditProgress({ record }: { record: ResearchRecord<AuditData> }) {
  const active = isTaskRunning(record.status);
  const stages = [{ id: "queued", label: "等待处理" }, { id: "parsing", label: "解析稿件" }, { id: "ocr", label: "文字识别" }, { id: "matching", label: "馆藏匹配" }, { id: "checking", label: "引文核对" }, { id: "report", label: "生成报告" }];
  const stage = record.status === "queued" ? "queued" : record.data.stage || "parsing";
  const index = stages.findIndex(item => item.id === stage);
  return <div className="stl4-audit-progress" aria-live="polite"><div><strong>{auditStatuses[record.status || ""] || "任务已保存"}</strong><span>{active ? "本地服务处理，可以离开后再回来。" : "已保存的结果与人工记录可继续查看。"}</span></div><ol>{stages.filter(item => item.id !== "ocr" || record.data.ocr_progress?.total || stage === "ocr").map(item => <li key={item.id} aria-current={item.id === stage ? "step" : undefined} data-passed={stages.indexOf(item) < index || undefined}>{item.label}</li>)}</ol>{typeof record.total_units === "number" && record.total_units > 0 ? <><progress max={record.total_units} value={record.completed_units || 0} aria-label="当前阶段进度" /><small>当前阶段已处理 {record.completed_units || 0} / {record.total_units} 项</small></> : active ? <small>当前阶段尚未提供可计算的进度。</small> : null}{record.error_code ? <p role="alert">任务未能全部完成。已保存内容保留，可重试或查看已解析结果。</p> : null}</div>;
}
