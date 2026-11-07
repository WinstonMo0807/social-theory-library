"use client";

import { useState } from "react";
import { EntityPicker } from "../forms/workflow-fields";
import { InlineMediaPicker } from "./inline-media-picker";
import type { ArticleMetadata } from "@/lib/api/recommendation-issues.types";

export const emptyArticleMetadata: ArticleMetadata = { kind: "article", keywords: [], topic_ids: [], theory_ids: [], scholar_ids: [], reading_path_ids: [], curator_role: "", curator_affiliation: "", curator_portrait_id: null };
export function ArticleMetadataFields({ value, owner, onChange, onPortrait }: { value?: ArticleMetadata; owner: number; onChange: (value: ArticleMetadata) => void; onPortrait: (id: string | null, url: string) => void }) {
  const [labels, setLabels] = useState<Record<string, string>>({});
  const data = { ...emptyArticleMetadata, ...value }, update = (patch: Partial<ArticleMetadata>) => onChange({ ...data, ...patch });
  return <section><h3>文章分类与公开策划资料</h3>
    <label>内容类型<select value={data.kind} onChange={event => update({ kind: event.target.value as ArticleMetadata["kind"] })}><option value="article">策划文章</option><option value="research">研究论文</option><option value="exhibition">原文展览</option></select></label>
    <label>关键词（每行一个）<textarea rows={3} value={data.keywords.join("\n")} onChange={event => update({ keywords: event.target.value.split("\n") })} /></label>
    {([ ["topic_ids", "相关主题", "/catalog/admin/topics/", "search", "name"],
      ["theory_ids", "理论流派", "/catalog/admin/theory-system/nodes/?type=theory_tradition", "q", "canonical_name_zh"],
      ["scholar_ids", "相关学者档案", "/catalog/admin/scholars/", "search", "name"],
      ["reading_path_ids", "相关阅读路径", "/catalog/admin/theory-system/reading-paths/", "q", "title"] ] as const).map(([key,label,endpoint,queryParam,nameField]) => <EntityPicker key={key} label={label} endpoint={endpoint} queryParam={queryParam} nameField={nameField}
      values={(data[key] || []).map(id => ({id,name:labels[id] || `${label} · ${id.slice(0,8)}`}))}
      onChange={rows => { update({ [key]: rows.flatMap(row => row.id ? [row.id] : []) }); setLabels(previous => ({ ...previous, ...Object.fromEntries(rows.flatMap(row => row.id ? [[row.id,row.name]] : [])) })); }} />)}
    <label>策划者署名<input maxLength={240} value={data.curator_role} onChange={event => update({ curator_role: event.target.value })} /></label>
    <label>公开策划者机构<input maxLength={240} value={data.curator_affiliation} onChange={event => update({ curator_affiliation: event.target.value })} /></label>
    <label>策展人头像<select value={data.curator_account_id ? String(data.curator_account_id) : "separate"} onChange={event => update({ curator_account_id: event.target.value === "separate" ? null : owner, curator_portrait_id: null })}>
      {data.curator_account_id && data.curator_account_id !== owner ? <option value={data.curator_account_id}>保留原策展人的账号头像</option> : null}
      <option value={owner}>使用我的账号头像</option><option value="separate">单独设置</option>
    </select></label>
    {data.curator_account_id ? <p>账号头像更新后，已发布的策展署名也会同步更新。</p> : <details><summary>选择公开头像</summary><InlineMediaPicker selectedRenditionId={data.curator_portrait_id} kind="portrait" onSelect={(id, url) => onPortrait(id, url)} />{data.curator_portrait_id ? <button type="button" onClick={() => onPortrait(null, "")}>移除公开头像</button> : null}</details>}
  </section>;
}
