"use client";

import {
  ArrowRight,
  Bot,
  BookOpen,
  ExternalLink,
  FileClock,
  FileText,
  GitFork,
  LoaderCircle,
  RefreshCw,
  Search,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { ActionButton, type ActionState } from "./action-feedback";
import {
  buildCandidateActionBody,
  type CandidateActionDescriptor,
  type CandidateActionSource,
} from "./admin/research/candidate-action-contract";
import { CandidateDecisionBar } from "./admin/research/candidate-decision-bar";
import { EvidenceEnvelopeCard } from "./admin/research/evidence-envelope-card";

type DirectoryObject = {
  id: string;
  object_type: string;
  label: string;
  secondary_label: string;
  status: string;
  updated_at: string;
};

type ClaimRow = {
  id: string;
  kind?: string;
  title?: string;
  proposition: string;
  status?: string;
  claim_type?: string;
  attribution?: string;
  polarity?: string;
  quality_score?: number;
  importance_score?: number;
  shadow?: boolean;
  evidence?: unknown | unknown[];
};

type RevisionRow = {
  id: string;
  revision: number;
  base_revision: number;
  status: string;
  changed_fields: string[];
  change_note: string;
  patch: Record<string, unknown>;
  created_at: string;
  has_conflict: boolean;
  publish_url: string;
};

type FrontendImpact = {
  public_visibility?: boolean;
  modules?: string[];
  projections?: string[];
  projection_states?: Array<{ type: string; name: string; label: string; status: string; source_revision: number; projected_revision: number; lag: number; last_error_code: string }>;
  targets?: Array<{ label: string; url: string; modules: string[] }>;
};

type StudioCandidate = CandidateActionSource & {
  id: string;
  candidate_type: string;
  field_name: string;
  proposed_value: unknown;
  confidence: number;
  status: string;
  source: string;
  evidence?: unknown | unknown[];
  conflicts?: unknown;
  knowledge_update_id?: string;
  knowledge_update_kind?: string;
  why_now?: string;
  signal_sources?: string[];
  decision_target?: { object_type?: string; object_id?: string; label?: string };
};

type StudioSelection = {
  id: string;
  object_type: string;
  label: string;
  status: string;
  canonical?: Record<string, unknown>;
  relations?: Array<{ id: string; kind: string; label: string; target: string; status: string; description?: string; direction?: string }>;
  evidence?: unknown[];
  claims?: { curated?: ClaimRow[]; derived?: ClaimRow[]; derived_is_machine_only?: boolean };
  ai_candidates?: StudioCandidate[];
  knowledge_update_suggestions?: StudioCandidate[];
  knowledge_update_signal_counts?: Record<string, number>;
  knowledge_update_read_model?: {
    visible_count: number;
    limit: number;
    derived_read_model: boolean;
    persistent_model: null;
    canonical_write_policy: string;
  };
  revisions?: RevisionRow[];
  preview?: { source: string; revision_id: string | null; materialized?: Record<string, unknown> };
  frontend_impact?: FrontendImpact;
  mutation_contract?: { target_type: string; current_revision: number; published_changes_require_revision: boolean; single_editor_publish: boolean; canonical_commit_is_atomic: boolean; dependency_propagation_on_publish: boolean };
  editor_url?: string;
  preview_url?: string;
  preview_routes?: {
    published?: string;
    draft?: string;
    draft_is_protected?: boolean;
    uses_public_serializer?: boolean;
  };
  related_editor_urls?: Array<{ label: string; url: string }>;
};

type KnowledgePayload = {
  new_authority: Array<{ id: string; entity_type: string; term: string; status: string; confidence: number; evidence_count: number; works: Array<{ work_id: string; work__title: string }> }>;
  aliases: Array<{ id: string; alias: string; language: string; alias_type: string; source_kind: string; is_verified: boolean; node__canonical_name_zh: string }>;
  relations: { pending: number };
  timelines: { pending: number };
  classification: { pending_enrichment: number };
  unknown_observations: number;
  studio: {
    object_types: Array<{ value: string; label: string }>;
    filters: { query: string; object_type: string; limit: number };
    counts: Record<string, number>;
    objects: DirectoryObject[];
    selection: StudioSelection | null;
    selection_error?: string;
    candidate_overview: { debates: number; reading_paths: number };
    generated_candidates?: StudioCandidate[];
    knowledge_update_suggestions?: StudioCandidate[];
    knowledge_update_signal_counts?: Record<string, number>;
    knowledge_update_read_model?: {
      visible_count: number;
      limit: number;
      derived_read_model: boolean;
      persistent_model: null;
      canonical_write_policy: string;
    };
    read_only_aggregation: boolean;
    machine_claims_are_canonical: boolean;
  };
};

const objectLabels: Record<string, string> = {
  theory: "理论",
  concept: "概念",
  debate: "争论",
  research_problem: "研究问题",
  scholar: "学者",
  discipline: "学科",
  subdiscipline: "子学科",
  topic: "主题",
  reading_path: "阅读路径",
  work: "重要作品",
};

const statusLabels: Record<string, string> = {
  pending: "待处理",
  draft: "草稿",
  published: "已发布",
  archived: "已下线",
  verified: "已核验",
  needs_review: "待核验",
  accepted: "已采用",
  rejected: "已拒绝",
  superseded: "已取代",
  ready: "待发布",
  current: "最新",
  stale: "待更新",
  projecting: "更新中",
  failed: "更新失败",
  not_materialized: "尚未建立",
};

const fieldLabels: Record<string, string> = {
  canonical_name_zh: "中文规范名",
  canonical_name_en: "外文名",
  node_type: "对象类型",
  name: "名称",
  preferred_name: "规范姓名",
  original_name: "原文姓名",
  slug: "固定链接",
  summary: "摘要",
  definition: "定义",
  description: "说明",
  short_description: "学术位置",
  biography: "生平与贡献",
  problem_statement: "核心研究问题",
  core_questions: "核心问题",
  basic_propositions: "基本命题",
  theoretical_boundary: "理论边界",
  research_dimensions: "研究维度",
  methods: "常用方法",
  formation_context: "形成背景",
  key_concepts: "关键概念",
  key_concerns: "核心关注",
  affiliations: "机构",
  timeline: "发展脉络",
  featured_quote: "代表引文",
  quote_source: "引文出处",
  aliases: "名称变体",
  birth_year: "出生年",
  death_year: "逝世年",
  period: "时期",
  primary_discipline: "主要学科",
  foreign_name: "外文名称",
  discipline: "所属学科",
  parent: "上级子学科",
  research_object: "研究对象",
  formation_period: "形成时期",
  research_directions: "研究方向",
  representative_issues: "代表性议题",
  title: "题名",
  canonical_title: "规范题名",
  subtitle: "副题名",
  original_title: "原题名",
  abstract: "摘要",
  document_type: "文献类型",
  language: "作品语言",
  original_language: "原作语言",
  first_publication_date: "首次出版日期",
  editions: "版本",
  audience: "目标读者",
  difficulty: "阅读难度",
  estimated_reading: "预计阅读量",
  stages: "阶段与作品",
};

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "尚未填写";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.length ? value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join("、") : "尚未填写";
  return JSON.stringify(value, null, 2);
}

function EvidenceCard({ evidence }: { evidence: unknown }) {
  return <EvidenceEnvelopeCard evidence={evidence} compact />;
}

function ClaimCard({ claim, derived }: { claim: ClaimRow; derived?: boolean }) {
  const evidence = Array.isArray(claim.evidence) ? claim.evidence : claim.evidence ? [claim.evidence] : [];
  return (
    <article className={`knowledge-studio-claim ${derived ? "derived" : "curated"}`}>
      <header>
        <span>{derived ? "机器派生命题" : claim.kind || "人工策展命题"}</span>
        <b>{derived ? `${Math.round((claim.importance_score || 0) * 100)}% 重要性` : statusLabels[claim.status || ""] || claim.status}</b>
      </header>
      {claim.title ? <strong>{claim.title}</strong> : null}
      <p>{claim.proposition}</p>
      <footer>{derived ? `${claim.claim_type || "claim"} · ${claim.attribution || "归因待核"} · shadow` : "人工采用后才进入正式内容"}</footer>
      {evidence.slice(0, 2).map((row, index) => <EvidenceCard evidence={row} key={`claim-evidence-${claim.id}-${index}`} />)}
    </article>
  );
}

function StudioCandidateCard({
  candidate,
  busyCandidate,
  onAction,
}: {
  candidate: StudioCandidate;
  busyCandidate: string;
  onAction: (candidate: StudioCandidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) => void;
}) {
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const evidence = Array.isArray(candidate.evidence)
    ? candidate.evidence
    : candidate.evidence
      ? [candidate.evidence]
      : [];
  const busyPrefix = `${candidate.id}:`;
  return (
    <article className="knowledge-studio-candidate-card">
      <div>
        <b>{fieldLabels[candidate.field_name] || candidate.field_name}</b>
        <span>{Math.round(Number(candidate.confidence || 0) * 100)}%</span>
      </div>
      <p>{displayValue(candidate.proposed_value)}</p>
      <small>{candidate.source} · {statusLabels[candidate.status] || candidate.status}</small>
      {candidate.why_now ? <p className="knowledge-update-why"><strong>为什么现在处理</strong>{candidate.why_now}</p> : null}
      {candidate.signal_sources?.length ? <small>新信号 {candidate.signal_sources.join("、")}</small> : null}
      <CandidateDecisionBar
        candidate={candidate}
        busyAction={busyCandidate.startsWith(busyPrefix) ? busyCandidate.slice(busyPrefix.length) : ""}
        disabled={Boolean(busyCandidate)}
        onInspect={() => setEvidenceOpen(true)}
        onAction={(descriptor, editedValue) => onAction(candidate, descriptor, editedValue)}
      />
      <details open={evidenceOpen} onToggle={(event) => setEvidenceOpen(event.currentTarget.open)}>
        <summary>依据与冲突</summary>
        {evidence.map((row, index) => <EvidenceCard evidence={row} key={`${candidate.id}-evidence-${index}`} />)}
        {!evidence.length ? <p className="admin-list-state">当前没有达到采用要求的 Evidence。</p> : null}
        {candidate.conflicts ? <pre>{displayValue(candidate.conflicts)}</pre> : null}
      </details>
    </article>
  );
}

function ObjectDetail({
  selection,
  publishingRevision,
  publishState,
  onPublishRevision,
  busyCandidate,
  onCandidateAction,
}: {
  selection: StudioSelection;
  publishingRevision: string;
  publishState: ActionState;
  onPublishRevision: (revision: RevisionRow) => void;
  busyCandidate: string;
  onCandidateAction: (candidate: StudioCandidate, descriptor: CandidateActionDescriptor, editedValue?: unknown) => void;
}) {
  const canonicalProvided = selection.canonical !== undefined;
  const relationsProvided = Array.isArray(selection.relations);
  const evidenceProvided = Array.isArray(selection.evidence);
  const claimsProvided = selection.claims !== undefined;
  const candidatesProvided = Array.isArray(selection.ai_candidates);
  const revisionsProvided = Array.isArray(selection.revisions);
  const previewProvided = selection.preview?.materialized !== undefined;
  const impactProvided = selection.frontend_impact !== undefined;
  const mutationContractProvided = selection.mutation_contract !== undefined;
  const canonical = selection.canonical ?? {};
  const relations = selection.relations ?? [];
  const evidence = selection.evidence ?? [];
  const curatedClaims = selection.claims?.curated ?? [];
  const derivedClaims = selection.claims?.derived ?? [];
  const candidates = selection.ai_candidates ?? [];
  const knowledgeUpdates = selection.knowledge_update_suggestions ?? [];
  const revisions = selection.revisions ?? [];
  const preview = selection.preview;
  const impact = selection.frontend_impact;
  const impactModules = impact?.modules ?? [];
  const impactProjections = impact?.projections ?? [];
  const impactTargets = impact?.targets ?? [];
  const projectionStates = impact?.projection_states ?? [];
  const staleProjectionCount = projectionStates.filter((row) => row.status !== "current" || row.lag > 0).length;
  const relatedEditors = selection.related_editor_urls ?? [];

  const shellSections = [
    { id: "studio-canonical", label: "正式内容", state: canonicalProvided ? `${Object.keys(canonical).length} 字段` : "未接通" },
    { id: "studio-candidates", label: "候选", state: candidatesProvided ? `${candidates.length} 项` : "未接通" },
    { id: "studio-growth", label: "知识增长", state: `${knowledgeUpdates.length} 项` },
    { id: "studio-evidence", label: "Evidence", state: evidenceProvided ? `${evidence.length} 条` : "未接通" },
    { id: "studio-claims", label: "Claims", state: claimsProvided ? `${curatedClaims.length + derivedClaims.length} 条` : "未接通" },
    { id: "studio-relations", label: "关系", state: relationsProvided ? `${relations.length} 条` : "未接通" },
    { id: "studio-revisions", label: "Revision", state: revisionsProvided ? `${revisions.length} 条` : "未接通" },
    { id: "studio-impact", label: "前台影响", state: impactProvided ? (staleProjectionCount ? `${staleProjectionCount} 项待更新` : "已读取") : "未接通" },
    { id: "studio-preview", label: "Preview", state: previewProvided ? (preview?.source === "editorial_revision" ? "Revision" : "Canonical") : "未接通" },
  ];

  return (
    <section className="knowledge-studio-detail" aria-label={`${selection.label}知识对象详情`}>
      <header className="knowledge-studio-object-header">
        <div><p>{objectLabels[selection.object_type] || selection.object_type}</p><h2>{selection.label}</h2><span className={`status-badge ${selection.status}`}>{statusLabels[selection.status] || selection.status}</span></div>
        <div>
          {selection.editor_url ? <Link className="button" href={selection.editor_url}>进入专门编辑器 <ArrowRight size={14} /></Link> : <span className="knowledge-studio-unavailable">专门编辑器未接通</span>}
          {selection.preview_routes?.draft ? <Link className="button secondary" href={selection.preview_routes.draft} target="_blank">预览当前草稿 <ExternalLink size={14} /></Link> : null}
          {selection.preview_routes?.published ? <Link className="button secondary" href={selection.preview_routes.published} target="_blank">查看公开版 <ExternalLink size={14} /></Link> : null}
        </div>
      </header>

      <nav className="knowledge-studio-section-nav" aria-label={`${selection.label}对象分区`}>
        {shellSections.map((row) => <a href={`#${row.id}`} key={row.id}><span>{row.label}</span><small>{row.state}</small></a>)}
      </nav>

      <div className="knowledge-studio-summary-grid">
        <section className="admin-panel knowledge-studio-canonical" id="studio-canonical">
          <header><h3>正式内容</h3><span>当前 Canonical</span></header>
          {canonicalProvided ? Object.keys(canonical).length ? <dl>{Object.entries(canonical).map(([key, value]) => <div key={key}><dt>{fieldLabels[key] || key}</dt><dd>{displayValue(value)}</dd></div>)}</dl> : <p className="admin-list-state">接口已接通。该对象暂无可展示的正式字段。</p> : <p className="admin-list-state is-unavailable">当前 Knowledge Workspace API 未提供 Canonical 内容。请进入专门编辑器核对。</p>}
        </section>
        <section className="admin-panel knowledge-studio-impact" id="studio-impact">
          <header><h3>前台影响</h3><span>{impactProvided ? impact?.public_visibility ? "当前公开" : "当前不公开" : "状态未接通"}</span></header>
          {impact ? <>
            <strong>页面模块</strong><p>{impactModules.length ? impactModules.join("、") : "Dependency metadata 未返回页面模块。"}</p>
            <strong>相关投影</strong><p>{impactProjections.length ? impactProjections.join("、") : "Dependency Resolver 未返回适用投影。"}</p>
            <strong>实际前台位置</strong>
            <nav>{impactTargets.filter((row) => row.url).map((row) => <Link href={row.url} key={`${row.label}:${row.url}`} target="_blank">{row.label}<ArrowRight size={13} /></Link>)}</nav>
            {!impactTargets.some((row) => row.url) ? <p className="admin-list-state">后端尚未返回可访问的前台目标。</p> : null}
            <div className="knowledge-studio-list">{projectionStates.map((row) => <article key={row.type}><div><b>{row.name}</b><span>{statusLabels[row.status] || row.status}</span></div><small>source {row.source_revision} · projected {row.projected_revision}{row.lag ? ` · 落后 ${row.lag}` : ""}{row.last_error_code ? ` · ${row.last_error_code}` : ""}</small></article>)}{!projectionStates.length ? <p className="admin-list-state">Dependency Resolver 尚未返回 ProjectionState。</p> : null}</div>
          </> : <p className="admin-list-state is-unavailable">当前 API 未提供 dependency 和 projection 元数据，无法判断真实前台影响。</p>}
          {relatedEditors.length ? <nav>{relatedEditors.map((row) => <Link href={row.url} key={row.url}>{row.label}<ArrowRight size={13} /></Link>)}</nav> : null}
          {mutationContractProvided ? <p className="knowledge-studio-boundary-note">{selection.mutation_contract?.published_changes_require_revision ? "该对象已公开。保存会先建立 EditorialRevision，单个有权限的 Editor 确认发布后才更新正式内容和相关投影。" : "该对象尚未公开，可在专门编辑器完善草稿。首次发布会记录 Canonical change 并更新相关投影。"}</p> : <p className="admin-list-state is-unavailable">当前 API 未提供修订发布约束，请在专门编辑器核对。</p>}
        </section>
      </div>

      <section className="admin-panel knowledge-studio-preview" id="studio-preview">
        <header><h3>Preview</h3><span>{previewProvided ? preview?.source === "editorial_revision" ? "未发布 EditorialRevision" : "当前正式内容" : "未接通"}</span></header>
        {previewProvided ? Object.keys(preview?.materialized ?? {}).length ? <dl>{Object.entries(preview?.materialized ?? {}).map(([key, value]) => <div key={key}><dt>{fieldLabels[key] || key}</dt><dd>{displayValue(value)}</dd></div>)}</dl> : <p className="admin-list-state">后端已返回 Preview，但当前没有可物化字段。</p> : <p className="admin-list-state is-unavailable">当前 API 未提供 materialized preview，本页不会伪造预览。</p>}
      </section>

      <div className="knowledge-studio-section-grid">
        <section className="admin-panel" id="studio-relations">
          <header><h3><GitFork size={16} />关系</h3><span>{relationsProvided ? `${relations.length} 条已载入` : "未接通"}</span></header>
          <div className="knowledge-studio-list">{relations.map((row) => <article key={row.id}><div><b>{row.label}</b><span>{statusLabels[row.status] || row.status}</span></div><strong>{row.target}</strong>{row.description ? <p>{row.description}</p> : null}<small>{row.kind}{row.direction ? ` · ${row.direction}` : ""}</small></article>)}{relationsProvided && !relations.length ? <p className="admin-list-state">尚未建立正式关系。</p> : !relationsProvided ? <p className="admin-list-state is-unavailable">当前对象类型尚未接通关系汇总。</p> : null}</div>
        </section>
        <section className="admin-panel" id="studio-evidence">
          <header><h3><FileText size={16} />Evidence</h3><span>{evidenceProvided ? "馆藏原文与真实定位" : "未接通"}</span></header>
          <div className="knowledge-studio-list">{evidence.map((row, index) => <EvidenceCard evidence={row} key={`object-evidence-${selection.id}-${index}`} />)}{evidenceProvided && !evidence.length ? <p className="admin-list-state">当前对象没有独立 Evidence。命题所附依据仍显示在 Claims 中。</p> : !evidenceProvided ? <p className="admin-list-state is-unavailable">当前对象类型尚未接通 Evidence 汇总。</p> : null}</div>
        </section>
      </div>

      <section className="admin-panel knowledge-studio-claims" id="studio-claims">
        <header><h3><BookOpen size={16} />Claims</h3><span>{claimsProvided ? "人工策展与机器派生严格分层" : "未接通"}</span></header>
        <div className="knowledge-studio-claim-columns">
          <div><h4>CuratedClaim</h4>{curatedClaims.map((row) => <ClaimCard claim={row} key={row.id} />)}{claimsProvided && !curatedClaims.length ? <p className="admin-list-state">尚无人工采用的策展命题。</p> : !claimsProvided ? <p className="admin-list-state is-unavailable">当前对象类型尚未接通 CuratedClaim 汇总。</p> : null}</div>
          <div><h4>DerivedClaim · Shadow</h4><p className="knowledge-studio-boundary-note">这些命题只用于研究与候选排序，不会自动写入正式知识。</p>{derivedClaims.map((row) => <ClaimCard claim={row} derived key={row.id} />)}{claimsProvided && !derivedClaims.length ? <p className="admin-list-state">尚无有效机器命题。</p> : !claimsProvided ? <p className="admin-list-state is-unavailable">当前对象类型尚未接通 DerivedClaim 汇总。</p> : null}</div>
        </div>
      </section>

      <section className="admin-panel knowledge-studio-growth" id="studio-growth">
        <header><h3><Sparkles size={16} />Knowledge Growth</h3><span>{knowledgeUpdates.length ? `${knowledgeUpdates.length} 项当前建议` : "没有高价值更新"}</span></header>
        <p className="knowledge-studio-boundary-note">新馆藏 Evidence、DerivedClaim 与研究候选在这里汇总。它是有界读模型，不会自动修改已发布知识。</p>
        <div className="knowledge-studio-list">{knowledgeUpdates.map((row) => <StudioCandidateCard candidate={row} busyCandidate={busyCandidate} onAction={onCandidateAction} key={row.knowledge_update_id || `${row.candidate_type}:${row.id}`} />)}{!knowledgeUpdates.length ? <p className="admin-list-state">当前没有需要主动呈现的知识更新。</p> : null}</div>
      </section>

      <div className="knowledge-studio-section-grid">
        <section className="admin-panel" id="studio-candidates">
          <header><h3><Bot size={16} />AI/Research 候选</h3><span>{candidatesProvided ? "统一人工决定" : "未接通"}</span></header>
          {candidatesProvided ? <p className="knowledge-studio-boundary-note">操作由后端 CandidateDecisionProtocol 提供。采用前会核对 Evidence 要求，机器候选不会自行修改正式内容。</p> : null}
          <div className="knowledge-studio-list">{candidates.map((row) => <StudioCandidateCard candidate={row} busyCandidate={busyCandidate} onAction={onCandidateAction} key={`${row.candidate_type}:${row.id}`} />)}{candidatesProvided && !candidates.length ? <p className="admin-list-state">当前没有需要处理的高价值候选。</p> : !candidatesProvided ? <p className="admin-list-state is-unavailable">当前对象类型尚未接通候选汇总。</p> : null}</div>
        </section>
        <section className="admin-panel" id="studio-revisions">
          <header><h3><FileClock size={16} />EditorialRevision</h3><span>{revisionsProvided ? "草稿、发布与取代历史" : "未接通"}</span></header>
          <div className="knowledge-studio-list">{revisions.map((row) => <article key={row.id}><div><b>Revision {row.revision}</b><span>{row.has_conflict ? "与正式版本冲突" : statusLabels[row.status] || row.status}</span></div><p>{row.changed_fields.join("、") || "未记录字段差异"}</p><small>base {row.base_revision} · {row.change_note || "无编辑说明"}</small>{row.publish_url && !row.has_conflict ? <ActionButton className="button" state={publishingRevision === row.id ? publishState : "idle"} pendingLabel="发布中" successLabel="已发布" onClick={() => onPublishRevision(row)}>确认发布此修订</ActionButton> : null}</article>)}{revisionsProvided && !revisions.length ? <p className="admin-list-state">尚无 EditorialRevision。</p> : !revisionsProvided ? <p className="admin-list-state is-unavailable">当前对象类型尚未接通 EditorialRevision 历史。</p> : null}</div>
        </section>
      </div>
    </section>
  );
}

export function KnowledgeWorkspace() {
  const [payload, setPayload] = useState<KnowledgePayload | null>(null);
  const [candidateStatus, setCandidateStatus] = useState("pending");
  const [objectType, setObjectType] = useState("all");
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<{ type: string; id: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [publishingRevision, setPublishingRevision] = useState("");
  const [publishState, setPublishState] = useState<ActionState>("idle");
  const [busyCandidate, setBusyCandidate] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: candidateStatus, object_type: objectType, q: query, limit: "40" });
      if (selected) {
        params.set("selected_type", selected.type);
        params.set("selected_id", selected.id);
      }
      const next = await apiRequest<KnowledgePayload>(`/catalog/admin/knowledge-workspace/?${params.toString()}`, {}, getServerSessionCredential());
      setPayload(next);
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Knowledge Studio 读取失败。");
    } finally {
      setLoading(false);
    }
  }, [candidateStatus, objectType, query, selected]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setSelected(null);
    setQuery(queryDraft.trim());
  }

  async function publishRevision(revision: RevisionRow) {
    if (!revision.publish_url || publishingRevision) return;
    setPublishingRevision(revision.id);
    setPublishState("pending");
    try {
      await apiRequest(revision.publish_url, { method: "POST", body: JSON.stringify({}) }, getServerSessionCredential());
      setPublishState("success");
      await load();
      setMessage(`Revision ${revision.revision} 已发布，正式内容和相关投影已开始更新。`);
    } catch (error) {
      setPublishState("error");
      setMessage(error instanceof Error ? error.message : "EditorialRevision 发布失败。");
    } finally {
      window.setTimeout(() => {
        setPublishingRevision("");
        setPublishState("idle");
      }, 1200);
    }
  }

  async function decideCandidate(
    candidate: StudioCandidate,
    descriptor: CandidateActionDescriptor,
    editedValue?: unknown,
  ) {
    if (!descriptor.url || descriptor.method === "CLIENT" || busyCandidate) {
      setMessage(descriptor.disabledReason || "该候选没有提供可执行的安全入口。");
      return;
    }
    const key = `${candidate.id}:${descriptor.action}`;
    setBusyCandidate(key);
    try {
      const body = buildCandidateActionBody(descriptor, editedValue);
      await apiRequest(
        descriptor.url,
        {
          method: descriptor.method || "POST",
          body: JSON.stringify(body),
        },
        getServerSessionCredential(),
      );
      setMessage(
        descriptor.action === "reject"
          ? "已记录不采用决定。"
          : descriptor.action === "defer"
            ? "已标记稍后处理。"
            : "候选已采用。需要发布的内容已进入现有草稿流程。",
      );
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "候选决定失败。");
    } finally {
      setBusyCandidate("");
    }
  }

  const studio = payload?.studio;
  const current = studio?.selection;
  const currentKey = current ? `${current.object_type}:${current.id}` : "";

  return (
    <div className="admin-page knowledge-studio">
      <header className="admin-page-title">
        <div><p>知识对象中心</p><h1>Knowledge Studio</h1><span>在一个工作面核对正式内容、关系、证据、Claims、候选、修订与前台影响。实际编辑仍由现有专门编辑器完成。</span></div>
        <div className="admin-title-actions"><button className="button secondary" type="button" onClick={() => void load()} disabled={loading}><RefreshCw className={loading ? "spin" : ""} size={15} />刷新</button></div>
      </header>

      <section className="knowledge-studio-quick-links" aria-label="知识专门工作区">
        <Link href="/admin/theory-nodes">理论与概念</Link><Link href="/admin/scholars">学者</Link><Link href="/admin/subdisciplines">子学科</Link><Link href="/admin/topics">主题</Link><Link href="/admin/library">重要作品</Link><Link href="/admin/theory-relations">关系</Link><Link href="/admin/theory-timeline">时间轴</Link><Link href="/admin/reading-paths">阅读路径</Link>
      </section>

      {payload ? <section className="knowledge-studio-overview">
        <div><span>未知实体</span><strong>{payload.unknown_observations}</strong></div>
        <div><span>待核关系</span><strong>{payload.relations.pending}</strong></div>
        <div><span>待核时间线</span><strong>{payload.timelines.pending}</strong></div>
        <div><span>Debate 候选</span><strong>{studio?.candidate_overview.debates || 0}</strong></div>
        <div><span>Reading Path 候选</span><strong>{studio?.candidate_overview.reading_paths || 0}</strong></div>
      </section> : null}

      {studio ? <nav className="knowledge-studio-object-types" aria-label="知识对象导航">
        {studio.object_types.map((row) => <button className={objectType === row.value ? "active" : ""} type="button" key={row.value} onClick={() => { setObjectType(row.value); setSelected(null); }}><span>{row.label}</span>{row.value !== "all" ? <small>{studio.counts[row.value] ?? 0}</small> : null}</button>)}
      </nav> : null}

      <form className="admin-toolbar knowledge-studio-toolbar" onSubmit={submitSearch}>
        <label><span>对象类型</span><select value={objectType} onChange={(event) => { setObjectType(event.target.value); setSelected(null); }}>{studio?.object_types.map((row) => <option value={row.value} key={row.value}>{row.label}{row.value !== "all" ? ` (${studio.counts[row.value] || 0})` : ""}</option>) || <option value="all">全部对象</option>}</select></label>
        <label className="knowledge-studio-search"><span>名称</span><div><Search size={15} /><input value={queryDraft} onChange={(event) => setQueryDraft(event.target.value)} placeholder="搜索理论、概念、学者、子学科、主题、阅读路径或重要作品" /></div></label>
        <button className="button" type="submit">搜索</button>
        <label><span>Authority 候选</span><select value={candidateStatus} onChange={(event) => setCandidateStatus(event.target.value)}><option value="pending">待审核</option><option value="all">全部</option><option value="matched">已关联</option><option value="draft_created">已创建草稿</option><option value="rejected">已拒绝</option></select></label>
      </form>

      {message ? <p className="form-message" role="status">{message}</p> : null}
      {loading && !payload ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />正在读取 Knowledge Studio……</p> : null}

      {studio ? <div className="knowledge-studio-layout">
        <aside className="admin-panel knowledge-studio-directory">
          <header><h2>知识对象</h2><span>最多载入 {studio.filters.limit} 项</span></header>
          <div>{studio.objects.map((row) => {
            const key = `${row.object_type}:${row.id}`;
            return <button className={currentKey === key ? "active" : ""} type="button" key={key} onClick={() => setSelected({ type: row.object_type, id: row.id })}><span>{objectLabels[row.object_type] || row.object_type}</span><strong>{row.label}</strong><small>{row.secondary_label || statusLabels[row.status] || row.status}</small><ArrowRight size={14} /></button>;
          })}{!studio.objects.length ? <p className="admin-list-state">当前筛选下没有知识对象。</p> : null}</div>
        </aside>
        {current ? <ObjectDetail selection={current} publishingRevision={publishingRevision} publishState={publishState} onPublishRevision={(revision) => void publishRevision(revision)} busyCandidate={busyCandidate} onCandidateAction={(candidate, descriptor, editedValue) => void decideCandidate(candidate, descriptor, editedValue)} /> : <section className="admin-panel knowledge-studio-empty"><Sparkles size={22} /><h2>{studio.selection_error ? "无法载入该知识对象" : "选择一个知识对象"}</h2><p>{studio.selection_error ? "后端返回对象不存在或类型不匹配。本页没有用其他对象的数据代替。" : "选择后可统一检查正式内容、关系、原文证据、Claims、候选和编辑草稿。"}</p></section>}
      </div> : null}

      {studio?.knowledge_update_suggestions?.length ? <section className="admin-panel knowledge-studio-generated-queue">
        <header><h2>全馆 Knowledge Growth</h2><span>{studio.knowledge_update_read_model?.visible_count ?? studio.knowledge_update_suggestions.length} 项当前建议</span></header>
        <p className="knowledge-studio-boundary-note">系统从新 Evidence、DerivedClaim 与现有研究候选中挑选少量高价值事项。采用仍走既有人工决定与草稿发布流程。</p>
        <div className="knowledge-studio-list">{studio.knowledge_update_suggestions.map((candidate) => <StudioCandidateCard candidate={candidate} busyCandidate={busyCandidate} onAction={(row, descriptor, editedValue) => void decideCandidate(row, descriptor, editedValue)} key={candidate.knowledge_update_id || `${candidate.candidate_type}:${candidate.id}`} />)}</div>
      </section> : null}

      {payload ? <section className="admin-panel knowledge-studio-authority-queue">
        <header><h2>未归并 Authority 候选</h2><span>匹配或建草稿后仍不会自动公开</span></header>
        <div className="admin-table-wrap"><table><thead><tr><th>术语</th><th>对象</th><th>置信度</th><th>证据</th><th>关联作品</th><th>状态</th></tr></thead><tbody>{payload.new_authority.slice(0, 20).map((row) => <tr key={row.id}><td><strong>{row.term}</strong><small>{row.works.map((work) => work.work__title).join("、") || "馆藏作品待补"}</small></td><td>{objectLabels[row.entity_type] || row.entity_type}</td><td>{Math.round(row.confidence * 100)}%</td><td>{row.evidence_count}</td><td>{row.works.length}</td><td>{statusLabels[row.status] || row.status}</td></tr>)}{!payload.new_authority.length ? <tr><td colSpan={6}>当前没有未知实体候选。0 也是有效状态。</td></tr> : null}</tbody></table></div>
      </section> : null}
    </div>
  );
}
