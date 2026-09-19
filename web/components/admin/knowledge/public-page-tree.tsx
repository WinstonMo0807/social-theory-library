"use client";

import Link from "next/link";
import { useState } from "react";
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
  control_note?: string;
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
  ai_status: { enabled: boolean | null; workspace_message: string; publication_blocking: boolean };
};


export function PublicPageTree({ control }: { control: PublicControl }) {
  const [selectedPage,setSelectedPage]=useState("overview");
  const page=control.page_tree.find(row=>row.page_id===selectedPage) ?? control.page_tree[0];
  const changes=control.draft_published_diff;
  const fieldNames:Record<string,string>={short_description:"简介",description:"说明",person:"人物资料",portrait_selection:"人物图片",image_selection:"页面图片",cover_rendition:"封面",timeline:"时间线",curation:"页面内容",biography:"人物介绍",title:"标题",summary:"简介",definition:"定义",aliases:"其他名称"};
  return <section className="public-page-manager" aria-label="公开页面管理">
    <header><h3>读者会看到什么</h3><p>{control.eligibility.eligible ? "这个条目已经公开。保存修改后，仍需点击发布，读者才会看到新版。" : "这个条目还没有公开。可以先完善内容并预览。"}</p></header>
    {page ? <>
      <label>选择页面<select value={page.page_id} onChange={event=>setSelectedPage(event.target.value)}>{control.page_tree.map(row=><option value={row.page_id} key={row.page_id}>{row.display_name}</option>)}</select></label>
      <div className="public-page-manager-modules">{page.modules.map(module=>{
        const preview=`${page.preview.draft_route}${page.preview.draft_route.includes("?")?"&":"?"}module=${encodeURIComponent(module.preview_anchor)}`;
        const status=({complete:"已有内容",partial:"可以补充",missing:"尚未填写",draft:"有未发布修改",empty_computed:"暂无相关内容",not_curated:"尚未选择内容"} as Record<string,string>)[module.status]||"请核对内容";
        const source=({editorial:"手工填写",relation:"根据关联的作品、人物或主题显示",curated:"由管理员选择内容",computed:"根据馆藏自动显示",ai_optional:"只显示已核对的内容"} as Record<string,string>)[module.content_source_type]||"请在编辑页核对来源";
        return <article key={module.module_id}><div><h4>{module.display_name}</h4><p>{status} · {source}</p></div><div>
          <Link href={page.admin_management_destination}>修改</Link>
          {page.preview.supported ? <Link href={preview} target="_blank" aria-label={`预览${module.display_name}`}>预览<ExternalLink size={12}/></Link> : <span>发布后可在关联页面查看</span>}
        </div></article>;
      })}</div>
      <p>不必补齐每个栏目。没有相关馆藏或暂不需要的内容，可以留空。</p>
      {page.preview.supported ? <Link className="button secondary" href={page.preview.draft_route} target="_blank">预览整个页面</Link> : null}
    </> : <p>这个条目没有单独的读者页面，请从相关作品或分类中查看。</p>}
    {changes.length ? <section className="public-page-manager-changes"><h4>还没有发布的修改</h4>{changes.map(row=><div key={row.field}><strong>{fieldNames[row.field]||"相关资料"}</strong>{row.kind === "collection" ? <p>增加 {row.added?.length??0} 项，移除 {row.removed?.length??0} 项</p> : typeof row.draft === "object" || typeof row.published === "object" ? <details><summary>查看这项修改</summary><p>原内容</p><pre>{publicValue(row.published)}</pre><p>修改后</p><pre>{publicValue(row.draft)}</pre></details> : <p>原来：{publicValue(row.published)}<br/>修改后：{publicValue(row.draft)}</p>}</div>)}</section> : null}
    {control.public_appearances.length ? <details><summary>还会显示在哪里</summary>{control.public_appearances.map(row=><p key={`${row.page_id}:${row.route}`}><Link href={row.route} target="_blank">{row.label}</Link> · {row.count} 项</p>)}</details> : null}
    <details className="public-page-technical"><summary>技术详情</summary><p>配置版本：{control.contract_version}</p>{control.legacy_fallbacks.map(row=><p key={`${row.public_route}:${row.module}`}>{row.module}：{row.legacy_source}；对应新来源：{row.canonical_equivalent}</p>)}{control.admin_field_usage.map(row=><p key={row.field}>{row.field}：{row.consumers.join("、")}</p>)}</details>
  </section>;
}


function publicValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "尚无内容";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
