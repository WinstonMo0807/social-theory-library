"use client";

import { useState } from "react";
import { EntityPicker } from "../forms/workflow-fields";
import { InlineMediaPicker } from "./inline-media-picker";
import type { ArticleMetadata } from "@/lib/api/recommendation-issues.types";

export const emptyArticleMetadata: ArticleMetadata = { kind: "article", keywords: [], topic_ids: [], scholar_ids: [], reading_path_ids: [], curator_role: "", curator_affiliation: "", curator_portrait_id: null };
export function ArticleMetadataFields({ value, onChange, onPortrait }: { value?: ArticleMetadata; onChange: (value: ArticleMetadata) => void; onPortrait: (id: string | null, url: string) => void }) {
  const [labels, setLabels] = useState<Record<string, string>>({});
  const data = { ...emptyArticleMetadata, ...value }, update = (patch: Partial<ArticleMetadata>) => onChange({ ...data, ...patch });
  return <section><h3>文章分类与公开策划资料</h3>
    <label>内容类型<select value={data.kind} onChange={event => update({ kind: event.target.value as ArticleMetadata["kind"] })}><option value="article">策划文章</option><option value="research">研究论文</option><option value="exhibition">原文展览</option></select></label>
    <label>关键词（每行一个）<textarea rows={3} value={data.keywords.join("\n")} onChange={event => update({ keywords: event.target.value.split("\n") })} /></label>
    {([ ["topic_ids", "相关主题", "/catalog/admin/topics/", "search", "name"],
      ["scholar_ids", "相关学者档案", "/catalog/admin/scholars/", "search", "name"],
      ["reading_path_ids", "相关阅读路径", "/catalog/admin/theory-system/reading-paths/", "q", "title"] ] as const).map(([key,label,endpoint,queryParam,nameField]) => <EntityPicker key={key} label={label} endpoint={endpoint} queryParam={queryParam} nameField={nameField}
      values={data[key].map(id => ({id,name:labels[id] || `${label} · ${id.slice(0,8)}`}))}
      onChange={rows => { update({ [key]: rows.flatMap(row => row.id ? [row.id] : []) }); setLabels(previous => ({ ...previous, ...Object.fromEntries(rows.flatMap(row => row.id ? [[row.id,row.name]] : [])) })); }} />)}
    <label>公开策划者身份<input maxLength={240} value={data.curator_role} onChange={event => update({ curator_role: event.target.value })} /></label>
    <label>公开策划者机构<input maxLength={240} value={data.curator_affiliation} onChange={event => update({ curator_affiliation: event.target.value })} /></label>
    <p>署名沿用上方公开署名。这里只填写可公开的资料，不读取或修改操作账户。关联未公开对象只留在草稿中。</p>
    <details><summary>选择公开策划者头像</summary><InlineMediaPicker selectedRenditionId={data.curator_portrait_id} kind="portrait" onSelect={(id, url) => onPortrait(id, url)} />{data.curator_portrait_id ? <button type="button" onClick={() => onPortrait(null, "")}>移除公开头像</button> : null}</details>
  </section>;
}
