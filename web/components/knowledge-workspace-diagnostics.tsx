"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { PreviewViewport } from "./admin/curation/fixed-page-editor";
import { PreviewSurface, type KnowledgePreviewPayload } from "./admin/preview/knowledge-page-preview";
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
  const returnUrl = selected?.editor_url || (objectId && valid ? `/admin/knowledge?object_type=${encodeURIComponent(kind)}&object_id=${encodeURIComponent(objectId)}` : "/admin/knowledge");
  const projections = selected?.frontend_impact?.projection_states;
  const preview = useApiResource<KnowledgePreviewPayload>(selected && kind !== "work" ? `/catalog/admin/knowledge-preview/${kind}/${objectId}/` : "", getServerSessionCredential());
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [step, setStep] = useState(1);
  const [section, setSection] = useState("overview");
  const fullPreview = useRef<HTMLDialogElement>(null);
  const draft = preview.data?.perspectives.draft;
  const published = preview.data?.perspectives.published;
  const hasDraft = Boolean(draft?.available && draft.source !== published?.source);
  const latest = selected?.revisions?.find(row => row.status === "draft");
  const visible = selected?.frontend_impact?.public_visibility;
  const staleProjection = projections?.find(row => row.lag > 0 || Boolean(row.last_error_code));
  const reason = latest ? "修改已保存为草稿，尚未发布。读者仍看到当前线上内容。" : staleProjection ? "已保存内容的显示更新仍有未完成项，请检查下面的处理记录。" : visible === false ? "当前对象尚未公开，请回到页面编辑器检查发布条件。" : "请对照当前线上与已保存内容；没有诊断记录的环节仍待核实。";
  const comparison = <div className="diagnostics-comparison">{(["published", "draft"] as const).map(perspective => {
    const value = preview.data?.perspectives[perspective];
    return <section key={perspective}><h3>{perspective === "published" ? "当前线上（网站上的内容）" : "修改后（已保存内容）"}</h3>{value?.available && preview.data ? <PreviewViewport device={device}><PreviewSurface payload={{...preview.data,active_perspective:perspective,perspective:value}} pageId={section}/></PreviewViewport> : <p className="empty-state">—</p>}</section>;
  })}</div>;
  return <div className="admin-page diagnostics-reference">
    <header className="admin-page-title"><div><h1>为什么修改还没显示</h1><span>检查内容发布状态，找到当前停留的环节，并继续处理。</span></div><button className="button secondary" type="button" disabled={loading || !valid} onClick={()=>{retry();preview.retry();}}>重新检查</button></header>
    <nav className="knowledge-reference-steps" aria-label="检查步骤">{["选择页面","找到停在哪一步","回去处理"].map((label,index)=><button type="button" key={label} aria-current={step===index ? "step" : undefined} onClick={()=>setStep(index)}><span>{index+1}</span><strong>{label}</strong></button>)}</nav>
    {!valid ? <p role="alert">对象类型或编号无效，未读取其他对象作为替代。</p> : null}
    {error ? <p role="alert">{error}</p> : null}{loading && valid ? <p role="status">正在读取已保存的诊断记录…</p> : null}
    {objectId && studio?.selection_error ? <p role="alert">无法找到指定对象，没有显示其他对象的结果。</p> : null}
    {studio && (!objectId || step===0) ? <section className="admin-panel"><h2>选择需要检查的页面</h2><div className="knowledge-studio-list">{studio.objects.map(row=><Link key={`${row.object_type}:${row.id}`} href={`/admin/processing/health/knowledge?object_type=${encodeURIComponent(row.object_type)}&object_id=${encodeURIComponent(row.id)}`} onClick={()=>{setStep(1);setSection("overview");}}>{row.label}<small>{row.secondary_label}</small></Link>)}</div></section> : null}
    {selected && step!==0 ? <div className="diagnostics-reference-columns"><section className="admin-panel"><h2>当前检查的页面</h2><h3>{selected.label}</h3>{selected.preview_routes?.published ? <Link className="button secondary" href={selected.preview_routes.published} target="_blank">查看当前公开页面</Link> : null}
      <h3>发布流程与当前状态</h3><ol className="diagnostics-publication-steps">
        <li><b>1</b><div><strong>已保存草稿</strong><p>{latest || hasDraft ? "有已保存的修改" : draft?.available ? "可读取已保存内容" : "—"}</p><small>{latest?.created_at ? new Date(latest.created_at).toLocaleString("zh-CN") : ""}</small></div></li>
        <li className={latest || visible===false ? "current" : ""}><b>2</b><div><strong>{latest ? "尚未发布（当前原因）" : "发布状态"}</strong><p>{latest ? "内容仍在草稿中" : visible === undefined ? "—" : visible ? "当前有公开内容" : "尚未公开"}</p></div></li>
        <li><b>3</b><div><strong>前台显示</strong><p>{published?.available ? "可查看当前线上内容" : "—"}</p></div></li>
        <li className={staleProjection ? "current" : ""}><b>4</b><div><strong>搜索更新</strong><p>{projections?.length ? projections.map(row=>`${row.name}：${row.last_error_code ? "处理失败" : row.lag > 0 ? "等待更新" : row.status}`).join("；") : "—"}</p></div></li>
      </ol><aside className="diagnostics-reason"><h3>当前检查结果</h3><p>{reason}</p></aside>
      <h3>相关信息</h3><dl><div><dt>预计生效时间</dt><dd>—</dd></div><div><dt>对读者的影响</dt><dd>{latest ? "前台保留当前公开内容，草稿不会自行生效" : visible ? "已有公开页面，具体修改请对照右侧" : "当前对象尚未公开"}</dd></div></dl>
      <details><summary>修订与处理记录</summary>{projections?.map(row=><p key={row.type}>{row.name} · 来源修订 {row.source_revision} · 已处理 {row.projected_revision}{row.last_error_code ? ` · ${row.last_error_code}` : ""}</p>)}{selected.revisions?.map(row=><p key={row.id}>修订 {row.revision} · {row.status}{row.has_conflict ? " · 存在冲突" : ""}</p>)}</details>
      <details><summary>原文依据与定位</summary>{selected.evidence?.map((row,index)=><EvidenceEnvelopeCard key={index} evidence={row}/>)}</details>
    </section><section className="admin-panel diagnostics-preview"><header><h2>读者会看到什么</h2><div className="diagnostics-preview-tools"><button type="button" aria-pressed={device==="desktop"} onClick={()=>setDevice("desktop")}>电脑</button><button type="button" aria-pressed={device==="mobile"} onClick={()=>setDevice("mobile")}>手机</button><button type="button" onClick={()=>fullPreview.current?.showModal()}>放大查看</button></div></header>
      {preview.data?.public_control?.page_tree?.length ? <label>查看位置<select value={section} onChange={event=>setSection(event.target.value)}>{preview.data.public_control.page_tree.map(page=><option key={page.page_id} value={page.page_id}>{page.display_name}</option>)}</select></label> : null}
      {preview.error ? <p role="alert">{preview.error}</p> : null}{comparison}
      <aside className="diagnostics-change"><h3>本次修改的主要内容</h3><p>{latest?.change_note || (latest?.changed_fields.length ? latest.changed_fields.join("、") : "—")}</p></aside><footer><Link className="button" href={returnUrl}>回到页面继续处理 →</Link></footer>
    </section></div> : null}
    <dialog ref={fullPreview} className="fixed-preview-dialog"><header><strong>当前线上与已保存内容</strong><button type="button" onClick={()=>fullPreview.current?.close()}>关闭</button></header>{comparison}</dialog>
  </div>;
}
