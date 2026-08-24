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

type DirectoryObject = {
  id: string;
  object_type: string;
  label: string;
  secondary_label: string;
  status: string;
  updated_at: string;
};

type EvidenceEnvelope = {
  id: string;
  kind: string;
  source: { work_title?: string; authors?: string[] };
  text: string;
  locator: { page?: number; printed_page_label?: string; section?: string };
  quality: { score?: number; stale?: boolean; review_status?: string };
  reader_url: string;
  pdf_url: string;
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
  evidence?: EvidenceEnvelope | EvidenceEnvelope[];
};

type StudioSelection = {
  id: string;
  object_type: string;
  label: string;
  status: string;
  canonical: Record<string, unknown>;
  relations: Array<{ id: string; kind: string; label: string; target: string; status: string; description?: string; direction?: string }>;
  evidence: EvidenceEnvelope[];
  claims: { curated: ClaimRow[]; derived: ClaimRow[]; derived_is_machine_only: boolean };
  ai_candidates: Array<{ id: string; candidate_type: string; field_name: string; proposed_value: unknown; confidence: number; status: string; source: string; evidence?: string; conflicts?: unknown }>;
  revisions: Array<{ id: string; revision: number; base_revision: number; status: string; changed_fields: string[]; change_note: string; patch: Record<string, unknown>; created_at: string }>;
  preview: { source: string; revision_id: string | null; materialized: Record<string, unknown> };
  frontend_impact: { public_visibility: boolean; modules: string[]; projections: string[] };
  editor_url: string;
  preview_url: string;
  related_editor_urls: Array<{ label: string; url: string }>;
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
    candidate_overview: { debates: number; reading_paths: number };
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
  topic: "主题",
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
};

function displayValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "尚未填写";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.length ? value.map((item) => typeof item === "object" ? JSON.stringify(item) : String(item)).join("、") : "尚未填写";
  return JSON.stringify(value, null, 2);
}

function EvidenceCard({ evidence }: { evidence: EvidenceEnvelope }) {
  const page = evidence.locator.printed_page_label || evidence.locator.page;
  return (
    <article className="knowledge-studio-evidence">
      <header><span>{evidence.source.work_title || "馆藏原文"}</span><b>{page ? `页码 ${page}` : "页码待核"}</b></header>
      <blockquote>{evidence.text || "当前证据没有可展示文本。"}</blockquote>
      <footer>
        <span>{evidence.locator.section || evidence.kind}{evidence.quality.stale ? " · 已失效" : ""}</span>
        <Link href={evidence.reader_url} target="_blank">查看原文 <ExternalLink size={13} /></Link>
      </footer>
    </article>
  );
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
      {evidence.slice(0, 2).map((row) => <EvidenceCard evidence={row} key={row.id} />)}
    </article>
  );
}

function ObjectDetail({ selection }: { selection: StudioSelection }) {
  return (
    <section className="knowledge-studio-detail" aria-label={`${selection.label}知识对象详情`}>
      <header className="knowledge-studio-object-header">
        <div><p>{objectLabels[selection.object_type] || selection.object_type}</p><h2>{selection.label}</h2><span className={`status-badge ${selection.status}`}>{statusLabels[selection.status] || selection.status}</span></div>
        <div>
          <Link className="button" href={selection.editor_url}>进入专门编辑器 <ArrowRight size={14} /></Link>
          <Link className="button secondary" href={selection.preview_url} target="_blank">公开页预览 <ExternalLink size={14} /></Link>
        </div>
      </header>

      <div className="knowledge-studio-summary-grid">
        <section className="admin-panel knowledge-studio-canonical">
          <header><h3>正式内容</h3><span>当前 Canonical</span></header>
          <dl>{Object.entries(selection.canonical).map(([key, value]) => <div key={key}><dt>{fieldLabels[key] || key}</dt><dd>{displayValue(value)}</dd></div>)}</dl>
        </section>
        <section className="admin-panel knowledge-studio-impact">
          <header><h3>前台影响</h3><span>{selection.frontend_impact.public_visibility ? "当前公开" : "当前不公开"}</span></header>
          <strong>页面模块</strong><p>{selection.frontend_impact.modules.join("、")}</p>
          <strong>相关投影</strong><p>{selection.frontend_impact.projections.join("、")}</p>
          <nav>{selection.related_editor_urls.map((row) => <Link href={row.url} key={row.url}>{row.label}<ArrowRight size={13} /></Link>)}</nav>
        </section>
      </div>

      <section className="admin-panel knowledge-studio-preview">
        <header><h3>Preview</h3><span>{selection.preview.source === "editorial_revision" ? "未发布 EditorialRevision" : "当前正式内容"}</span></header>
        <dl>{Object.entries(selection.preview.materialized).map(([key, value]) => <div key={key}><dt>{fieldLabels[key] || key}</dt><dd>{displayValue(value)}</dd></div>)}</dl>
      </section>

      <div className="knowledge-studio-section-grid">
        <section className="admin-panel">
          <header><h3><GitFork size={16} />关系</h3><span>{selection.relations.length} 条已载入</span></header>
          <div className="knowledge-studio-list">{selection.relations.map((row) => <article key={row.id}><div><b>{row.label}</b><span>{statusLabels[row.status] || row.status}</span></div><strong>{row.target}</strong>{row.description ? <p>{row.description}</p> : null}<small>{row.kind}{row.direction ? ` · ${row.direction}` : ""}</small></article>)}{!selection.relations.length ? <p className="admin-list-state">尚未建立正式关系。</p> : null}</div>
        </section>
        <section className="admin-panel">
          <header><h3><FileText size={16} />Evidence</h3><span>馆藏原文与真实定位</span></header>
          <div className="knowledge-studio-list">{selection.evidence.map((row) => <EvidenceCard evidence={row} key={row.id} />)}{!selection.evidence.length ? <p className="admin-list-state">当前对象没有独立 Evidence。命题所附依据仍显示在 Claims 中。</p> : null}</div>
        </section>
      </div>

      <section className="admin-panel knowledge-studio-claims">
        <header><h3><BookOpen size={16} />Claims</h3><span>人工策展与机器派生严格分层</span></header>
        <div className="knowledge-studio-claim-columns">
          <div><h4>CuratedClaim</h4>{selection.claims.curated.map((row) => <ClaimCard claim={row} key={row.id} />)}{!selection.claims.curated.length ? <p className="admin-list-state">尚无人工采用的策展命题。</p> : null}</div>
          <div><h4>DerivedClaim · Shadow</h4><p className="knowledge-studio-boundary-note">这些命题只用于研究与候选排序，不会自动写入正式知识。</p>{selection.claims.derived.map((row) => <ClaimCard claim={row} derived key={row.id} />)}{!selection.claims.derived.length ? <p className="admin-list-state">尚无有效机器命题。</p> : null}</div>
        </div>
      </section>

      <div className="knowledge-studio-section-grid">
        <section className="admin-panel">
          <header><h3><Bot size={16} />AI candidates</h3><span>返回受限，人工决定</span></header>
          <div className="knowledge-studio-list">{selection.ai_candidates.map((row) => <article key={`${row.candidate_type}:${row.id}`}><div><b>{row.field_name}</b><span>{Math.round(row.confidence * 100)}%</span></div><p>{displayValue(row.proposed_value)}</p>{row.evidence ? <blockquote>{row.evidence}</blockquote> : null}<small>{row.source} · {statusLabels[row.status] || row.status}</small></article>)}{!selection.ai_candidates.length ? <p className="admin-list-state">当前没有需要处理的高价值候选。</p> : null}</div>
        </section>
        <section className="admin-panel">
          <header><h3><FileClock size={16} />EditorialRevision</h3><span>草稿、发布与取代历史</span></header>
          <div className="knowledge-studio-list">{selection.revisions.map((row) => <article key={row.id}><div><b>Revision {row.revision}</b><span>{statusLabels[row.status] || row.status}</span></div><p>{row.changed_fields.join("、") || "未记录字段差异"}</p><small>base {row.base_revision} · {row.change_note || "无编辑说明"}</small></article>)}{!selection.revisions.length ? <p className="admin-list-state">尚无 EditorialRevision。</p> : null}</div>
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
        <Link href="/admin/theory-nodes">理论与概念</Link><Link href="/admin/scholars">学者</Link><Link href="/admin/topics">主题</Link><Link href="/admin/theory-relations">关系</Link><Link href="/admin/theory-timeline">时间轴</Link><Link href="/admin/reading-paths">阅读路径</Link>
      </section>

      {payload ? <section className="knowledge-studio-overview">
        <div><span>未知实体</span><strong>{payload.unknown_observations}</strong></div>
        <div><span>待核关系</span><strong>{payload.relations.pending}</strong></div>
        <div><span>待核时间线</span><strong>{payload.timelines.pending}</strong></div>
        <div><span>Debate 候选</span><strong>{studio?.candidate_overview.debates || 0}</strong></div>
        <div><span>Reading Path 候选</span><strong>{studio?.candidate_overview.reading_paths || 0}</strong></div>
      </section> : null}

      <form className="admin-toolbar knowledge-studio-toolbar" onSubmit={submitSearch}>
        <label><span>对象类型</span><select value={objectType} onChange={(event) => { setObjectType(event.target.value); setSelected(null); }}>{studio?.object_types.map((row) => <option value={row.value} key={row.value}>{row.label}{row.value !== "all" ? ` (${studio.counts[row.value] || 0})` : ""}</option>) || <option value="all">全部对象</option>}</select></label>
        <label className="knowledge-studio-search"><span>名称</span><div><Search size={15} /><input value={queryDraft} onChange={(event) => setQueryDraft(event.target.value)} placeholder="搜索理论、概念、争论、学者或主题" /></div></label>
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
        {current ? <ObjectDetail selection={current} /> : <section className="admin-panel knowledge-studio-empty"><Sparkles size={22} /><h2>选择一个知识对象</h2><p>选择后可统一检查正式内容、关系、原文证据、Claims、候选和编辑草稿。</p></section>}
      </div> : null}

      {payload ? <section className="admin-panel knowledge-studio-authority-queue">
        <header><h2>未归并 Authority 候选</h2><span>匹配或建草稿后仍不会自动公开</span></header>
        <div className="admin-table-wrap"><table><thead><tr><th>术语</th><th>对象</th><th>置信度</th><th>证据</th><th>关联作品</th><th>状态</th></tr></thead><tbody>{payload.new_authority.slice(0, 20).map((row) => <tr key={row.id}><td><strong>{row.term}</strong><small>{row.works.map((work) => work.work__title).join("、") || "馆藏作品待补"}</small></td><td>{objectLabels[row.entity_type] || row.entity_type}</td><td>{Math.round(row.confidence * 100)}%</td><td>{row.evidence_count}</td><td>{row.works.length}</td><td>{statusLabels[row.status] || row.status}</td></tr>)}{!payload.new_authority.length ? <tr><td colSpan={6}>当前没有未知实体候选。0 也是有效状态。</td></tr> : null}</tbody></table></div>
      </section> : null}
    </div>
  );
}
