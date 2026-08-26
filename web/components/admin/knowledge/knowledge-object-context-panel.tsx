"use client";

import {
  BookOpen,
  ExternalLink,
  FileClock,
  FileText,
  GitFork,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ActionButton, AsyncStatus, type ActionState } from "@/components/action-feedback";
import {
  buildCandidateActionBody,
  type CandidateActionDescriptor,
  type CandidateActionSource,
} from "@/components/admin/research/candidate-action-contract";
import { CandidateDecisionBar } from "@/components/admin/research/candidate-decision-bar";
import { EvidenceEnvelopeCard } from "@/components/admin/research/evidence-envelope-card";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

export type KnowledgeObjectType =
  | "theory"
  | "concept"
  | "debate"
  | "research_problem"
  | "scholar"
  | "discipline"
  | "subdiscipline"
  | "topic"
  | "reading_path"
  | "work";

type CompletenessModule = {
  label: string;
  serializer_fields: string[];
  populated_fields: string[];
  missing_fields: string[];
  complete: boolean;
  available: boolean;
};

type ContentCompleteness = {
  source: string;
  serializer: string;
  perspective: string;
  complete_module_count: number;
  module_count: number;
  unsupported_preview_fields?: string[];
  modules: CompletenessModule[];
};

type PreviewPerspective = {
  available: boolean;
  complete?: boolean;
  serializer: string;
  source?: "editorial_revision" | "canonical_draft" | "published" | string;
  route?: string;
  revision_id?: string | null;
  data?: Record<string, unknown> | null;
  unsupported_preview_fields?: string[];
  reason?: string;
};

type ClaimRow = {
  id: string;
  kind?: string;
  title?: string;
  proposition: string;
  status?: string;
  claim_type?: string;
  evidence?: unknown | unknown[];
};

type RevisionRow = {
  id: string;
  revision: number;
  base_revision: number;
  status: string;
  changed_fields: string[];
  change_note: string;
  has_conflict: boolean;
  publish_url: string;
};

type CandidateRow = CandidateActionSource & {
  id: string;
  candidate_type: string;
  field_name: string;
  proposed_value: unknown;
  confidence: number;
  status: string;
  source: string;
  evidence?: unknown | unknown[];
  knowledge_update_id?: string;
  knowledge_update_kind?: string;
  why_now?: string;
  signal_sources?: string[];
};

type ProjectionState = {
  type: string;
  name: string;
  label: string;
  status: string;
  source_revision: number;
  projected_revision: number;
  lag: number;
  last_error_code: string;
};

type KnowledgeSelection = {
  id: string;
  object_type: KnowledgeObjectType;
  label: string;
  status: string;
  relations?: Array<{
    id: string;
    kind: string;
    label: string;
    target: string;
    status: string;
    description?: string;
  }>;
  evidence?: unknown[];
  claims?: { curated?: ClaimRow[]; derived?: ClaimRow[] };
  ai_candidates?: CandidateRow[];
  knowledge_update_suggestions?: CandidateRow[];
  revisions?: RevisionRow[];
  content_completeness?: ContentCompleteness;
  preview_perspectives?: {
    published?: PreviewPerspective;
    draft?: PreviewPerspective;
  };
  preview_routes?: {
    published?: string;
    draft?: string;
    draft_is_protected?: boolean;
    uses_public_serializer?: boolean;
  };
  frontend_impact?: {
    public_visibility?: boolean;
    modules?: string[];
    projections?: string[];
    projection_types?: string[];
    projection_states?: ProjectionState[];
    targets?: Array<{ label: string; url: string; modules: string[] }>;
  };
  mutation_contract?: {
    published_changes_require_revision?: boolean;
  };
  preview_url?: string;
};

type KnowledgeWorkspacePayload = {
  studio: {
    selection: KnowledgeSelection | null;
    selection_error?: string;
  };
};

const objectLabels: Record<KnowledgeObjectType, string> = {
  theory: "理论",
  concept: "概念",
  debate: "争论",
  research_problem: "研究问题",
  scholar: "学者",
  discipline: "学科",
  subdiscipline: "子学科",
  topic: "主题",
  reading_path: "阅读路径",
  work: "作品",
};

const statusLabels: Record<string, string> = {
  draft: "草稿",
  pending: "待处理",
  published: "已发布",
  verified: "已核验",
  archived: "已下线",
  accepted: "已采用",
  rejected: "已拒绝",
  current: "最新",
  stale: "待更新",
  projecting: "更新中",
  failed: "更新失败",
  not_materialized: "尚未建立",
};

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "尚未填写";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "是" : "否";
  return JSON.stringify(value, null, 2);
}

function evidenceRows(value: unknown | unknown[] | undefined) {
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

function previewLabel(perspective: PreviewPerspective | undefined, fallback: string) {
  if (!perspective?.available) return fallback;
  const fields = Object.keys(perspective.data ?? {}).length;
  return `${fields} 个公开字段`;
}

export function KnowledgeObjectContextPanel({
  objectType,
  objectId,
  refreshKey,
  onChanged,
  onApplyCandidate,
}: {
  objectType: KnowledgeObjectType;
  objectId?: string | null;
  refreshKey?: string | number | null;
  onChanged?: () => void;
  onApplyCandidate?: (candidate: CandidateRow, value: unknown) => Promise<void> | void;
}) {
  const [selection, setSelection] = useState<KnowledgeSelection | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageState, setMessageState] = useState<ActionState>("idle");
  const [busyCandidate, setBusyCandidate] = useState("");
  const [publishingRevision, setPublishingRevision] = useState("");
  const [openCandidate, setOpenCandidate] = useState("");

  const load = useCallback(async () => {
    if (!objectId) {
      setSelection(null);
      setMessage("");
      setMessageState("idle");
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({
        status: "pending",
        object_type: objectType,
        selected_type: objectType,
        selected_id: objectId,
        limit: "1",
      });
      const payload = await apiRequest<KnowledgeWorkspacePayload>(
        `/catalog/admin/knowledge-workspace/?${params.toString()}`,
        {},
        getServerSessionCredential(),
      );
      setSelection(payload.studio.selection);
      if (!payload.studio.selection) {
        setMessage(payload.studio.selection_error
          ? "Knowledge Studio 找不到这个对象，未使用其他对象的数据代替。"
          : "这个对象尚无可用的知识上下文。");
        setMessageState("error");
      } else {
        setMessage("");
        setMessageState("idle");
      }
    } catch (reason) {
      setSelection(null);
      setMessage(reason instanceof Error ? reason.message : "知识对象 Inspector 读取失败。");
      setMessageState("error");
    } finally {
      setLoading(false);
    }
  }, [objectId, objectType]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, refreshKey]);

  async function decideCandidate(
    candidate: CandidateRow,
    descriptor: CandidateActionDescriptor,
    editedValue?: unknown,
  ) {
    if (busyCandidate) return;
    if (descriptor.method === "CLIENT") {
      if (!onApplyCandidate) {
        setMessage("这个操作需要写入当前未保存表单。请在左侧字段研究区采用，Inspector 不会越过编辑草稿直接写入。");
        setMessageState("error");
        return;
      }
      setBusyCandidate(`${candidate.id}:${descriptor.action}`);
      setMessageState("pending");
      try {
        await onApplyCandidate(candidate, editedValue ?? candidate.proposed_value);
        setMessage("候选已经写入当前编辑草稿，尚未发布。");
        setMessageState("success");
      } catch (reason) {
        setMessage(reason instanceof Error ? reason.message : "候选写入草稿失败。");
        setMessageState("error");
      } finally {
        setBusyCandidate("");
      }
      return;
    }
    if (!descriptor.url) {
      setMessage(descriptor.disabledReason || "后端没有为此候选提供安全操作入口。");
      setMessageState("error");
      return;
    }
    setBusyCandidate(`${candidate.id}:${descriptor.action}`);
    setMessageState("pending");
    try {
      await apiRequest(
        descriptor.url,
        {
          method: descriptor.method || "POST",
          body: JSON.stringify(buildCandidateActionBody(descriptor, editedValue)),
        },
        getServerSessionCredential(),
      );
      setMessage(descriptor.action === "reject" ? "已记录不采用。" : "候选决定已保存，正式内容仍遵守现有草稿与发布规则。");
      setMessageState("success");
      await load();
      onChanged?.();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "候选决定失败。");
      setMessageState("error");
    } finally {
      setBusyCandidate("");
    }
  }

  async function publishRevision(revision: RevisionRow) {
    if (!revision.publish_url || publishingRevision) return;
    setPublishingRevision(revision.id);
    setMessageState("pending");
    try {
      await apiRequest(
        revision.publish_url,
        { method: "POST", body: JSON.stringify({}) },
        getServerSessionCredential(),
      );
      setMessage(`Revision ${revision.revision} 已发布，相关投影开始增量更新。`);
      setMessageState("success");
      await load();
      onChanged?.();
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "EditorialRevision 发布失败。");
      setMessageState("error");
    } finally {
      setPublishingRevision("");
    }
  }

  if (!objectId) {
    return (
      <aside className="admin-panel knowledge-object-context-panel is-empty" aria-label="知识对象 Inspector">
        <Sparkles size={18} />
        <div><strong>知识对象 Inspector</strong><p>先保存这个新对象，随后可在这里查看前台完整度、Evidence、Claims、候选与投影状态。</p></div>
      </aside>
    );
  }

  const completeness = selection?.content_completeness;
  const relations = selection?.relations ?? [];
  const evidence = selection?.evidence ?? [];
  const curatedClaims = selection?.claims?.curated ?? [];
  const derivedClaims = selection?.claims?.derived ?? [];
  const candidates = selection?.ai_candidates ?? [];
  const knowledgeUpdates = selection?.knowledge_update_suggestions ?? [];
  const revisions = selection?.revisions ?? [];
  const impact = selection?.frontend_impact;
  const projectionStates = impact?.projection_states ?? [];
  const staleProjections = projectionStates.filter((row) => row.status !== "current" || row.lag > 0);
  const publishedPreview = selection?.preview_perspectives?.published;
  const draftPreview = selection?.preview_perspectives?.draft;
  const previewRoutes = selection?.preview_routes;
  const studioHref = `/admin/knowledge?selected_type=${encodeURIComponent(objectType)}&selected_id=${encodeURIComponent(objectId)}`;

  return (
    <aside className="admin-panel knowledge-object-context-panel" aria-label={`${objectLabels[objectType]}知识对象 Inspector`}>
      <header>
        <div><small>{objectLabels[objectType]} · Knowledge Studio</small><h2>{selection?.label || "知识对象 Inspector"}</h2><span>{selection ? statusLabels[selection.status] || selection.status : "读取中"}</span></div>
        <ActionButton className="secondary" state={loading ? "pending" : "idle"} pendingLabel="读取中" onClick={() => void load()}><RefreshCw size={13} />刷新</ActionButton>
      </header>

      {message ? <AsyncStatus state={messageState} message={message} /> : null}
      {loading && !selection ? <p className="knowledge-object-context-state">正在读取真实知识上下文……</p> : null}

      {selection ? <>
        <section className="knowledge-object-completeness" aria-label="前台内容完整度">
          <header><strong>前台内容完整度</strong><span>{completeness ? `${completeness.complete_module_count}/${completeness.module_count}` : "未接通"}</span></header>
          {completeness ? <div>{completeness.modules.map((module) => <article className={module.complete ? "is-complete" : module.available ? "is-partial" : "is-empty"} key={module.label}><span>{module.label}</span><b>{module.complete ? "完整" : module.available ? "待补" : "缺失"}</b>{module.missing_fields.length ? <small>缺少 {module.missing_fields.join("、")}</small> : null}</article>)}</div> : <p className="knowledge-object-context-state">API 尚未返回基于公开 serializer 的完整度。</p>}
        </section>

        <details open className="knowledge-object-context-section">
          <summary><Sparkles size={14} /><span>AI / Research 候选</span><b>{candidates.length}</b></summary>
          <div className="knowledge-object-context-list">{candidates.map((candidate) => {
            const rows = evidenceRows(candidate.evidence);
            const busyPrefix = `${candidate.id}:`;
            return <article className="knowledge-object-candidate" key={`${candidate.candidate_type}:${candidate.id}`}><header><strong>{candidate.field_name || candidate.candidate_type}</strong><span>{Math.round(Number(candidate.confidence || 0) * 100)}%</span></header><p>{displayValue(candidate.proposed_value)}</p><small>{candidate.source} · {statusLabels[candidate.status] || candidate.status}</small><CandidateDecisionBar candidate={candidate} busyAction={busyCandidate.startsWith(busyPrefix) ? busyCandidate.slice(busyPrefix.length) : ""} disabled={Boolean(busyCandidate)} onInspect={() => setOpenCandidate((current) => current === candidate.id ? "" : candidate.id)} onAction={(descriptor, editedValue) => void decideCandidate(candidate, descriptor, editedValue)} />{openCandidate === candidate.id ? <div className="knowledge-object-candidate-evidence">{rows.map((row, index) => <EvidenceEnvelopeCard compact evidence={row} key={`${candidate.id}:evidence:${index}`} />)}{!rows.length ? <p>当前候选没有达到可展示要求的 Evidence。</p> : null}</div> : null}</article>;
          })}{!candidates.length ? <p className="knowledge-object-context-state">当前没有需要人工处理的高价值候选。</p> : null}</div>
        </details>

        <details open className="knowledge-object-context-section">
          <summary><Sparkles size={14} /><span>Knowledge Growth</span><b>{knowledgeUpdates.length}</b></summary>
          <p className="knowledge-object-context-state">新 Evidence、DerivedClaim 与研究候选经过有界排序后显示在这里，不会自动修改正式知识。</p>
          <div className="knowledge-object-context-list">{knowledgeUpdates.map((candidate) => {
            const rows = evidenceRows(candidate.evidence);
            const busyPrefix = `${candidate.id}:`;
            return <article className="knowledge-object-candidate" key={candidate.knowledge_update_id || `${candidate.candidate_type}:${candidate.id}`}><header><strong>{candidate.field_name || candidate.candidate_type}</strong><span>{Math.round(Number(candidate.confidence || 0) * 100)}%</span></header><p>{displayValue(candidate.proposed_value)}</p>{candidate.why_now ? <small>{candidate.why_now}</small> : null}<CandidateDecisionBar candidate={candidate} busyAction={busyCandidate.startsWith(busyPrefix) ? busyCandidate.slice(busyPrefix.length) : ""} disabled={Boolean(busyCandidate)} onInspect={() => setOpenCandidate((current) => current === candidate.knowledge_update_id ? "" : candidate.knowledge_update_id || candidate.id)} onAction={(descriptor, editedValue) => void decideCandidate(candidate, descriptor, editedValue)} />{openCandidate === (candidate.knowledge_update_id || candidate.id) ? <div className="knowledge-object-candidate-evidence">{rows.map((row, index) => <EvidenceEnvelopeCard compact evidence={row} key={`${candidate.id}:growth-evidence:${index}`} />)}{!rows.length ? <p>当前建议没有独立 Evidence 卡片，请查看其原候选或目标对象。</p> : null}</div> : null}</article>;
          })}{!knowledgeUpdates.length ? <p className="knowledge-object-context-state">当前没有需要主动呈现的知识更新。</p> : null}</div>
        </details>

        <details className="knowledge-object-context-section">
          <summary><FileText size={14} /><span>Evidence</span><b>{evidence.length}</b></summary>
          <div className="knowledge-object-context-list">{evidence.map((row, index) => <EvidenceEnvelopeCard compact evidence={row} key={`${selection.id}:evidence:${index}`} />)}{!evidence.length ? <p className="knowledge-object-context-state">当前对象没有独立 Evidence。Claim 所附依据仍保留在命题中。</p> : null}</div>
        </details>

        <details className="knowledge-object-context-section">
          <summary><BookOpen size={14} /><span>Claims</span><b>{curatedClaims.length + derivedClaims.length}</b></summary>
          <div className="knowledge-object-context-list">{curatedClaims.map((claim) => <article key={`curated:${claim.id}`}><header><strong>{claim.title || claim.kind || "CuratedClaim"}</strong><span>人工策展</span></header><p>{claim.proposition}</p></article>)}{derivedClaims.map((claim) => <article className="is-derived" key={`derived:${claim.id}`}><header><strong>{claim.title || claim.claim_type || "DerivedClaim"}</strong><span>Shadow</span></header><p>{claim.proposition}</p></article>)}{!curatedClaims.length && !derivedClaims.length ? <p className="knowledge-object-context-state">当前没有有效 Claim。</p> : null}</div>
        </details>

        <details className="knowledge-object-context-section">
          <summary><GitFork size={14} /><span>关系</span><b>{relations.length}</b></summary>
          <div className="knowledge-object-context-list">{relations.map((relation) => <article key={relation.id}><header><strong>{relation.label}</strong><span>{statusLabels[relation.status] || relation.status}</span></header><p>{relation.target}</p>{relation.description ? <small>{relation.description}</small> : null}</article>)}{!relations.length ? <p className="knowledge-object-context-state">尚未建立正式关系。</p> : null}</div>
        </details>

        <details open className="knowledge-object-context-section">
          <summary><FileClock size={14} /><span>Revision 与 Preview</span><b>{revisions.length}</b></summary>
          <div className="knowledge-object-preview-status"><p><strong>正式预览</strong><span>{previewLabel(publishedPreview, "对象尚未公开")}</span></p><p><strong>草稿预览</strong><span>{previewLabel(draftPreview, "当前没有 EditorialRevision")}</span></p>{draftPreview?.unsupported_preview_fields?.length ? <small>以下特殊关系字段只能部分预览 {draftPreview.unsupported_preview_fields.join("、")}</small> : null}</div>
          <div className="knowledge-object-context-list">{revisions.map((revision) => <article key={revision.id}><header><strong>Revision {revision.revision}</strong><span>{revision.has_conflict ? "与正式版本冲突" : statusLabels[revision.status] || revision.status}</span></header><p>{revision.changed_fields.join("、") || "未记录字段差异"}</p><small>base {revision.base_revision} · {revision.change_note || "无编辑说明"}</small>{revision.publish_url ? <ActionButton state={publishingRevision === revision.id ? "pending" : "idle"} pendingLabel="发布中" disabled={Boolean(publishingRevision) || revision.has_conflict} onClick={() => void publishRevision(revision)}>单人确认并发布</ActionButton> : null}</article>)}</div>
        </details>

        <section className="knowledge-object-impact" aria-label="前台影响与投影">
          <header><strong>前台影响与投影</strong><span>{impact ? staleProjections.length ? `${staleProjections.length} 项待更新` : "已读取" : "未接通"}</span></header>
          {impact ? <><p>{(impact.modules ?? []).join("、") || "没有适用的前台模块。"}</p><div>{projectionStates.map((row) => <article key={row.type}><span>{row.name || row.label || row.type}</span><b>{statusLabels[row.status] || row.status}</b><small>source {row.source_revision} · projected {row.projected_revision}{row.lag ? ` · 落后 ${row.lag}` : ""}{row.last_error_code ? ` · ${row.last_error_code}` : ""}</small></article>)}</div>{!projectionStates.length ? <p className="knowledge-object-context-state">Dependency Resolver 尚未返回 ProjectionState。</p> : null}</> : <p className="knowledge-object-context-state">API 尚未返回前台影响和投影状态。</p>}
        </section>

        <footer>
          <Link href={studioHref}>在 Knowledge Studio 查看完整对象</Link>
          {previewRoutes?.draft ? <Link href={previewRoutes.draft} target="_blank">预览当前草稿 <ExternalLink size={12} /></Link> : null}
          {previewRoutes?.published ? <Link href={previewRoutes.published} target="_blank">查看当前公开版 <ExternalLink size={12} /></Link> : null}
        </footer>
      </> : null}
    </aside>
  );
}
