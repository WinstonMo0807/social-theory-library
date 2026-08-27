import Link from "next/link";
import { ExternalLink } from "lucide-react";

export type PublicControlModule = {
  module_id: string;
  display_name: string;
  content_source_type: string;
  data_source_type: string;
  completeness_group: string;
  requirement: string;
  admin_editor_section: string;
  preview_anchor: string;
  status: string;
  complete: boolean;
  available: boolean;
  empty_reason?: string;
  has_candidate?: boolean;
  has_evidence?: boolean;
  serializer_fields: string[];
};

export type PublicControlPage = {
  page_id: string;
  display_name: string;
  route: string;
  status: string;
  modules: PublicControlModule[];
  preview: { supported: boolean; published_route: string; draft_route: string; protected: boolean };
  admin_management_destination: string;
};

export type PublicControl = {
  contract_version: string;
  eligibility: {
    eligible: boolean;
    reason?: string;
    person_authority_status?: string;
  };
  page_tree: PublicControlPage[];
  public_appearances: Array<{ page_id: string; label: string; count: number; route: string }>;
  content_completeness: {
    overall_percent: number;
    required_ready: number;
    required_total: number;
    computed_empty_is_manual_missing: boolean;
    groups: Array<{
      group: string;
      manual_ready: number;
      manual_total: number;
      computed_available: number;
      computed_total: number;
      percent: number;
      status: string;
    }>;
  };
  draft_published_diff: Array<{
    field: string;
    kind: string;
    added?: unknown[];
    removed?: unknown[];
    published?: unknown;
    draft?: unknown;
  }>;
  legacy_fallbacks: Array<{ public_route: string; module: string; legacy_source: string; canonical_equivalent: string }>;
  source_authority: Array<{ identity: string; canonical_source: string; relation_sources: string[] }>;
  admin_field_usage: Array<{ field: string; classification: string; consumers: string[] }>;
  ai_status: { enabled: boolean; workspace_message: string; publication_blocking: boolean };
};

const statusMeta: Record<string, { symbol: string; label: string }> = {
  complete: { symbol: "●", label: "完整" },
  partial: { symbol: "△", label: "部分完成" },
  missing: { symbol: "○", label: "缺内容" },
  draft: { symbol: "•", label: "有草稿" },
  empty_computed: { symbol: "○", label: "馆内暂无关联" },
  not_curated: { symbol: "○", label: "尚未策展" },
};

const sourceLabels: Record<string, string> = {
  editorial: "编辑内容",
  relation: "规范关系",
  curated: "策展内容",
  computed: "由馆藏自动生成",
  ai_optional: "人工策展，可选自动候选",
};

const groupLabels: Record<string, string> = {
  Identity: "身份",
  "Core Content": "核心内容",
  Knowledge: "知识关系",
  Curation: "策展",
  Evidence: "馆藏与依据",
};

export function PublicPageTree({ control }: { control: PublicControl }) {
  return (
    <section className="public-page-tree" aria-label="公开页面管理树">
      <header>
        <div><strong>公开页面</strong><small>契约 {control.contract_version}</small></div>
        <span>{control.content_completeness.overall_percent}% 内容覆盖</span>
      </header>
      {!control.eligibility.eligible ? <p className="public-page-eligibility-warning">
        当前不满足公开条件。{control.eligibility.reason === "person_authority_not_verified" ? `人物权威状态为 ${control.eligibility.person_authority_status || "未核验"}。` : "对象尚未发布。"}
      </p> : null}
      <div className="public-page-completeness-groups" aria-label="公开内容分组覆盖">
        {control.content_completeness.groups.map((group) => <p className={`is-${group.status}`} key={group.group}>
          <strong>{groupLabels[group.group] || group.group}</strong>
          <span>{group.manual_ready}/{group.manual_total} 人工内容</span>
          {group.computed_total ? <small>{group.computed_available}/{group.computed_total} 馆藏模块有内容</small> : null}
        </p>)}
      </div>
      <div className="public-page-tree-list">
        {control.page_tree.map((page) => {
          const pageMeta = statusMeta[page.status] ?? statusMeta.partial;
          return <details key={page.page_id} open={page.page_id === "overview"}>
            <summary>
              <span aria-hidden="true">{pageMeta.symbol}</span>
              <strong>{page.display_name}</strong>
              <small>{pageMeta.label}</small>
            </summary>
            <div>
              {page.modules.map((module) => {
                const meta = statusMeta[module.status] ?? statusMeta.partial;
                const preview = `${page.preview.draft_route}&module=${encodeURIComponent(module.preview_anchor)}`;
                return <article key={module.module_id}>
                  <span aria-hidden="true">{meta.symbol}</span>
                  <p><strong>{module.display_name}</strong><small>{sourceLabels[module.content_source_type] || module.content_source_type} · {meta.label}</small>{module.empty_reason ? <em>{module.empty_reason}</em> : null}</p>
                  {page.preview.supported ? <Link href={preview} target="_blank" aria-label={`预览${module.display_name}`}>预览<ExternalLink size={11} /></Link> : <span title="请从所属对象页面预览">关联入口</span>}
                </article>;
              })}
              <footer><Link href={page.admin_management_destination}>编辑对应内容</Link>{page.preview.supported ? <Link href={page.preview.draft_route} target="_blank">预览此页</Link> : <Link href={page.preview.published_route} target="_blank">查看公开位置</Link>}</footer>
            </div>
          </details>;
        })}
      </div>
      {control.source_authority.length ? <details className="public-page-source-authority">
        <summary>规范来源与关系来源</summary>
        {control.source_authority.map((row) => <p key={row.identity}><strong>{row.canonical_source}</strong><small>{row.relation_sources.join("、")}</small></p>)}
      </details> : null}
      {control.legacy_fallbacks.length ? <details className="public-page-legacy-warning" open>
        <summary>Legacy fallback 正在使用</summary>
        {control.legacy_fallbacks.map((row) => <p key={`${row.public_route}:${row.module}`}><strong>{row.module}</strong><span>{row.legacy_source}</span><small>规范来源为 {row.canonical_equivalent}</small></p>)}
      </details> : null}
      <details className="public-page-field-usage">
        <summary>后台字段用于哪些公开位置</summary>
        {control.admin_field_usage.map((row) => <p key={row.field}><strong>{row.field}</strong><small>{row.consumers.join("、")}</small></p>)}
      </details>
    </section>
  );
}
