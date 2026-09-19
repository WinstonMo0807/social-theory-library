"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { CandidateActionSource } from "./admin/research/candidate-action-contract";
import { EvidenceEnvelopeCard } from "./admin/research/evidence-envelope-card";

type DirectoryObject = {
  id: string;
  object_type: string;
  label: string;
  secondary_label: string;
  status: string;
  updated_at: string;
};

export type ClaimRow = {
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

export type RevisionRow = {
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

export type StudioSelection = {
  public_control?: import("./admin/knowledge/public-page-tree").PublicControl;
  assistance_usage?: import("./admin/knowledge/assistance-usage-panel").AssistanceUsage;
  id: string;
  object_type: string;
  field_assistant_target?: { object_type: "person" | "work" | "discipline" | "subdiscipline" | "knowledge_node" | "topic" | "reading_path"; object_id: string };
  field_assistant_values?: Record<string, unknown>;
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

export type KnowledgePayload = {
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
    public_management_coverage?: { public_surfaces?: Array<{ object_type: string; page_id: string; display_name: string; admin_management_destination: string; modules: Array<{ module_id: string; display_name: string; control_note: string; content_source_type: string }> }> };
  };
};

const diagnosticTypes = new Set(["all", "theory", "concept", "debate", "research_problem", "scholar", "discipline", "subdiscipline", "topic", "reading_path", "work"]);

// The diagnostic route retains its object identity, source versions and raw
// evidence checks. Catalog editing, candidate decisions and publication have
// one owner: the normal Studio and its established object editors.
export function KnowledgeWorkspaceDiagnostics() {
  const search = useSearchParams();
  const kind = search.get("object_type") || "all";
  const objectId = search.get("object_id") || "";
  const valid = diagnosticTypes.has(kind) && (!objectId || (kind !== "all" && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(objectId)));
  const params = new URLSearchParams({ object_type: kind, status: "pending", limit: "40" });
  if (objectId) { params.set("selected_type", kind); params.set("selected_id", objectId); }
  const { data, loading, error, retry } = useApiResource<KnowledgePayload>(
    valid ? `/catalog/admin/knowledge-workspace/?${params}` : "", getServerSessionCredential(), `${kind}:${objectId}`,
  );
  const studio = data?.studio;
  const selected = objectId ? studio?.selection : null;
  const returnUrl = objectId && valid ? `/admin/knowledge?object_type=${encodeURIComponent(kind)}&object_id=${encodeURIComponent(objectId)}` : "/admin/knowledge";
  const projections = selected?.frontend_impact?.projection_states;
  return <div className="admin-page">
    <header className="admin-page-title"><div><p>系统诊断</p><h1>知识处理诊断</h1><span>只读核对对象来源、修订和投影；编辑、候选决定及发布统一回到知识工作台。</span></div><div className="admin-title-actions"><Link className="button" href={returnUrl}>返回当前对象工作台</Link><button className="button secondary" type="button" disabled={loading || !valid} onClick={retry}>重新读取诊断</button></div></header>
    {!valid ? <p role="alert">对象类型或编号无效，未读取其他对象作为替代。</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {loading ? <p role="status">正在读取已保存的诊断记录…</p> : null}
    {objectId && studio?.selection_error ? <p role="alert">无法找到指定对象，没有显示其他对象的结果。</p> : null}
    {selected ? <section className="admin-panel" aria-label="当前知识对象诊断"><h2>{selected.label}</h2><p>对象 {selected.object_type} · {selected.id}</p>
      <h3>投影与来源修订</h3>{projections ? projections.length ? <div className="knowledge-studio-list">{projections.map((row) => <article key={row.type}><strong>{row.name} · {row.status}</strong><p>来源修订 {row.source_revision} · 已处理修订 {row.projected_revision} · 落后 {row.lag}</p>{row.last_error_code ? <p role="status">错误 {row.last_error_code}；从工作台的原发布记录检查影响及允许的恢复操作。</p> : null}</article>)}</div> : <p>当前没有投影记录，不能据此认定所有能力就绪。</p> : <p>当前API未返回投影诊断，状态待核实。</p>}
      <details><summary>修订与并发约束</summary><p>正式内容发布资格由原后端执行，不在诊断页重建发布动作。</p><pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(selected.mutation_contract ?? {}, null, 2)}</pre>{selected.revisions?.map((row) => <p key={row.id}>修订 {row.revision} · 基于 {row.base_revision} · {row.status}{row.has_conflict ? " · 存在冲突" : ""} · {row.id}</p>)}</details>
      <details><summary>原文依据与定位检查</summary>{selected.evidence?.length ? selected.evidence.map((row, index) => <EvidenceEnvelopeCard evidence={row} key={index} />) : <p>当前对象没有独立依据，不能用候选存在代替原文依据。</p>}</details>
      <details><summary>机器派生记录（非正式内容）</summary>{selected.claims?.derived?.length ? selected.claims.derived.map((row) => <article key={row.id}><strong>{row.title || row.claim_type || "机器命题"}</strong><p>{row.proposition}</p><small>{row.id} · {row.status} · {row.attribution || "归因待核"}</small></article>) : <p>当前没有机器派生记录。</p>}</details>
      <details><summary>候选来源与状态</summary>{selected.ai_candidates?.length ? selected.ai_candidates.map((row) => <article key={`${row.candidate_type}:${row.id}`}><strong>{String(row.field_name || row.field || row.candidate_type)} · {row.status}</strong><p>候选 {row.id}</p><p>{typeof row.source === "object" ? JSON.stringify(row.source) : String(row.source || "未提供来源")}</p></article>) : <p>当前没有高价值候选。无结果不等于服务失败。</p>}<Link href={returnUrl}>在当前对象核对并决定</Link></details>
    </section> : !objectId && studio ? <section className="admin-panel"><h2>选择需要诊断的对象</h2><p>专业入口只展示来源与处理记录，日常编辑使用同一知识工作台。下列最多 {studio.filters.limit} 项。</p><div className="knowledge-studio-list">{studio.objects.map((row) => <article key={`${row.object_type}:${row.id}`}><Link href={`/admin/system-health/knowledge?object_type=${encodeURIComponent(row.object_type)}&object_id=${encodeURIComponent(row.id)}`}>{row.label}</Link><small>{row.object_type} · {row.status}</small></article>)}</div></section> : null}
  </div>;
}
