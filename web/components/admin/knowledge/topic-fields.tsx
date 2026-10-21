"use client";

import Link from "next/link";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { PublishedEvidenceCuration } from "@/lib/api/evidence-curation.types";
import { EntityPicker } from "../forms/workflow-fields";

export const topicSelectionFields = {
  questionNodeIds: "question_node_ids", debateNodeIds: "debate_node_ids", conceptNodeIds: "concept_node_ids",
  editionIds: "edition_ids", foundationalEditionIds: "foundational_edition_ids", disputedEditionIds: "disputed_edition_ids",
  topicScholarIds: "related_scholar_ids", readingPathIds: "reading_path_ids", issueIds: "issue_ids",
} as const;
export type TopicCurationFields = { [K in keyof typeof topicSelectionFields]: string[] } & {
  parentId: string; featuredSourceId: string; preview_labels: Record<string, string>;
};
export function topicFields(curation: Record<string, unknown> = {}, parent: string | null = null): TopicCurationFields {
  return { ...Object.fromEntries(Object.entries(topicSelectionFields).map(([field, key]) => [field,
    Array.isArray(curation[key]) ? curation[key].filter((id): id is string => typeof id === "string") : []])),
    parentId: parent || "", featuredSourceId: typeof curation.featured_source_id === "string" ? curation.featured_source_id : "", preview_labels: {},
  } as TopicCurationFields;
}
export function topicCuration(value: TopicCurationFields): Record<string, unknown> {
  return { ...Object.fromEntries(Object.entries(topicSelectionFields).map(([field, key]) => [key, value[field as keyof typeof topicSelectionFields]])),
    featured_source_id: value.featuredSourceId || null };
}
const choices = [
  ["questions", "questionNodeIds", "核心问题", "/catalog/admin/theory-system/nodes/?type=research_problem", "canonical_name_zh"],
  ["questions", "debateNodeIds", "相关争论", "/catalog/admin/theory-system/nodes/?type=debate", "canonical_name_zh"],
  ["concepts", "conceptNodeIds", "规范概念条目", "/catalog/admin/theory-system/nodes/?type=concept", "canonical_name_zh"],
  ["works", "editionIds", "相关作品的出版版本", "/catalog/admin/library/works/?view=editions", "label"],
  ["works", "foundationalEditionIds", "基础阅读版本", "/catalog/admin/library/works/?view=editions", "label"],
  ["works", "disputedEditionIds", "争议阅读版本", "/catalog/admin/library/works/?view=editions", "label"],
  ["scholars", "topicScholarIds", "相关学者档案", "/catalog/admin/scholars/", "name"],
  ["paths", "readingPathIds", "研究路径", "/catalog/admin/theory-system/reading-paths/", "title"],
  ["articles", "issueIds", "策划文章", "/catalog/admin/recommendation-issues/", "title"],
] as const;

export function TopicFieldsEditor({ topicId, section, value, onChange }: {
  topicId: string | null; section: string; value: TopicCurationFields; onChange: (patch: Partial<TopicCurationFields>) => void;
}) {
  return <section>
    {section === "identity" ? <><EntityPicker label="上级主题" endpoint="/catalog/admin/topics/" queryParam="search"
      values={value.parentId ? [{ id: value.parentId, name: value.preview_labels[value.parentId] || "已保存的上级主题" }] : []}
      onChange={rows => { const row = rows.at(-1); onChange({ parentId: row?.id || "", preview_labels: { ...value.preview_labels, ...(row?.id ? { [row.id]: row.name } : {}) } }); }} />
      <p>留空表示一级主题。不能选择自身或后代；上级未公开时不对读者展示其名称。</p></> : null}
    {choices.filter(row => row[0] === section).map(([, field, label, endpoint, nameField]) => <EntityPicker key={field} label={label} endpoint={endpoint}
      queryParam={field === "topicScholarIds" ? "search" : "q"} nameField={nameField}
      values={value[field].map(id => ({ id, name: value.preview_labels[id] || `${label} · ${id.slice(0, 8)}` }))}
      onChange={rows => onChange({ [field]: rows.flatMap(row => row.id ? [row.id] : []), preview_labels: { ...value.preview_labels, ...Object.fromEntries(rows.flatMap(row => row.id ? [[row.id, row.name]] : [])) } })} />)}
    {section === "questions" ? <p>问题与争论关联规范条目；导读中的文字问题不会自动创建条目或生成讨论数量。</p> : null}
    {section === "works" ? <p>每项固定到准确出版版本。没有全文只显示书目；待购状态来自已发布策划中的明确计划记录。</p> : null}
    {section === "paths" ? <><p>复用已有阅读路径及其真实阶段、材料和来源。草稿或撤下的路径不会公开显示。</p><Link href="/admin/reading-paths">管理阅读路径</Link></> : null}
    {section === "articles" ? <p>只显示已发布的策划文章及其明确编排的计划材料；不会把私人研究内容公开。</p> : null}
    {section === "sources" ? <TopicQuoteField topicId={topicId} value={value.featuredSourceId} onChange={featuredSourceId => onChange({ featuredSourceId })} /> : null}
  </section>;
}

function TopicQuoteField({ topicId, value, onChange }: { topicId: string | null; value: string; onChange: (value: string) => void }) {
  const evidence = useApiResource<PublishedEvidenceCuration>(topicId ? `/catalog/evidence-curation/topic/${topicId}/` : "", getServerSessionCredential());
  const sources = evidence.data?.items.filter(row => row.source.public_eligible) || [];
  return <><label><span>首屏原文引语</span><select value={value} disabled={evidence.loading} onChange={event => onChange(event.target.value)}>
    <option value="">不展示引语</option>{value && !sources.some(row => row.id === value) ? <option value={value}>原选择当前不可公开，需核对</option> : null}
    {sources.map(row => <option key={row.id} value={row.id}>{row.source.work_title} · {row.source.printed_label || `PDF ${row.source.page_start}`} · {row.source.text.slice(0, 65)}</option>)}
  </select></label>{evidence.error ? <p role="alert">原文读取失败。<button type="button" onClick={evidence.retry}>重新读取引语来源</button></p> : null}
  <p>引语只取自本主题正式发布且仍可阅读的准确原文。保存选择不等于发布。</p>
  {topicId ? <Link href={`/admin/topics/${topicId}?section=passages`}>管理本主题原文策展</Link> : <p>先保存主题草稿，再编排原文。</p>}</>;
}
