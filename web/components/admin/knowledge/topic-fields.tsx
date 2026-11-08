"use client";

import Link from "next/link";
import { useAdminSession } from "@/lib/admin-session";
import { TopicAssociations } from "./topic-associations";
import { ScholarTagInput } from "./scholar-tag-input";
import { TopicOrganizationChecks } from "./topic-organization";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { PublishedEvidenceCuration } from "@/lib/api/evidence-curation.types";
import { TopicHierarchy } from "./topic-hierarchy";

export const topicSelectionFields = {
  questionNodeIds: "question_node_ids", debateNodeIds: "debate_node_ids", conceptNodeIds: "concept_node_ids",
  editionIds: "edition_ids", foundationalEditionIds: "foundational_edition_ids", disputedEditionIds: "disputed_edition_ids",
  topicScholarIds: "related_scholar_ids", readingPathIds: "reading_path_ids", issueIds: "issue_ids",
} as const;
export type TopicCurationFields = { [K in keyof typeof topicSelectionFields]: string[] } & {
  associationNotes: Record<string, Record<string, string>>; parentId: string; topicAliases: string[]; featuredSourceId: string; preview_labels: Record<string, string>;
};
export function topicFields(curation: Record<string, unknown> = {}, parent: string | null = null, aliases: string[] = []): TopicCurationFields {
  return { ...Object.fromEntries(Object.entries(topicSelectionFields).map(([field, key]) => [field,
    Array.isArray(curation[key]) ? curation[key].filter((id): id is string => typeof id === "string") : []])),
    associationNotes: typeof curation.association_notes === "object" && curation.association_notes !== null
      ? Object.fromEntries(Object.values(topicSelectionFields).map(key => {
        const group = (curation.association_notes as Record<string, unknown>)[key];
        return [key, group && typeof group === "object" && !Array.isArray(group)
          ? Object.fromEntries(Object.entries(group).filter((entry): entry is [string, string] => typeof entry[1] === "string")) : {}];
      })) : {},
    parentId: parent || "", topicAliases:aliases, featuredSourceId: typeof curation.featured_source_id === "string" ? curation.featured_source_id : "", preview_labels: {},
  } as TopicCurationFields;
}
export function topicCuration(value: TopicCurationFields): Record<string, unknown> {
  return { ...Object.fromEntries(Object.entries(topicSelectionFields).map(([field, key]) => [key, value[field as keyof typeof topicSelectionFields]])),
    association_notes: Object.fromEntries(Object.entries(topicSelectionFields).map(([field, key]) => [key,
      Object.fromEntries(value[field as keyof typeof topicSelectionFields].flatMap(id => {
        const text = value.associationNotes[key]?.[id]?.trim(); return text ? [[id, text]] : [];
      }))])), featured_source_id: value.featuredSourceId || null };
}
const choices = [
  ["questions", "questionNodeIds", "核心问题"],
  ["questions", "debateNodeIds", "相关争论"],
  ["concepts", "conceptNodeIds", "概念条目"],
  ["works", "editionIds", "关联作品"],
  ["works", "foundationalEditionIds", "基础阅读版本"],
  ["works", "disputedEditionIds", "争议阅读版本"],
  ["scholars", "topicScholarIds", "相关学者档案"],
  ["paths", "readingPathIds", "研究路径"],
  ["articles", "issueIds", "策划文章"],
] as const;

export function TopicFieldsEditor({ topicId, name, section, value, onChange }: {
  topicId: string | null; name: string; section: string; value: TopicCurationFields; onChange: (patch: Partial<TopicCurationFields>) => void;
}) {
  const owner = String(useAdminSession()?.id || "");
  return <section>
    {section === "identity" ? <><ScholarTagInput label="别名" addLabel="添加别名" value={value.topicAliases} onChange={topicAliases=>onChange({topicAliases})}/><TopicHierarchy topicId={topicId} name={name} value={value} onChange={onChange} />
      <section data-content-section className="topic-organization-checks"><header data-section-heading>层级规则与相似主题</header><p>一级主题没有上级。不能以自身或后代为上级；上级未公开时不对读者展示其名称。</p><TopicOrganizationChecks topicId={topicId} name={name} value={value}/></section></> : null}
    {choices.filter(row => row[0] === section).map(([, field, label]) => {
      const key = topicSelectionFields[field];
      const editor=<TopicAssociations key={`${owner}:${topicId}:${field}`} field={key} label={label} ids={value[field]} labels={value.preview_labels}
        notes={value.associationNotes[key] || {}} onChange={(ids, labels) => onChange({ [field]: ids, preview_labels: { ...value.preview_labels, ...labels },
          associationNotes: { ...value.associationNotes, [key]: Object.fromEntries(ids.flatMap(id => value.associationNotes[key]?.[id] ? [[id, value.associationNotes[key][id]]] : [])) } })}
        onNote={(id, text) => onChange({ associationNotes: { ...value.associationNotes, [key]: { ...value.associationNotes[key], [id]: text } } })} />;
      return field==="foundationalEditionIds"||field==="disputedEditionIds"?<section data-content-section key={field} className="topic-additional-readings"><header data-section-heading>{label}</header>{editor}</section>:editor;
    })}
    {section === "questions" ? <p>请选择已有的问题和争论。导读文字不会新增条目。</p> : null}
    {section === "works" ? <p>每项固定到准确出版版本。没有全文只显示书目；待购状态来自已发布策划中的明确计划记录。</p> : null}
    {section === "paths" ? <><p>只有已发布的阅读路径会向读者展示。</p><Link href="/admin/reading-paths">管理阅读路径</Link></> : null}
    {section === "articles" ? <p>只展示已发布的策划文章和计划材料，不含私人研究。</p> : null}
    {section === "sources" ? <TopicQuoteField topicId={topicId} value={value.featuredSourceId} onChange={featuredSourceId => onChange({ featuredSourceId })} /> : null}
  </section>;
}

function TopicQuoteField({ topicId, value, onChange }: { topicId: string | null; value: string; onChange: (value: string) => void }) {
  const evidence = useApiResource<PublishedEvidenceCuration>(topicId ? `/catalog/evidence-curation/topic/${topicId}/` : "", getServerSessionCredential());
  const sources = evidence.data?.items.filter(row => row.source.public_eligible) || [];
  return <><label><span>首屏原文引语</span><select data-stl-select value={value} disabled={evidence.loading} onChange={event => onChange(event.target.value)}>
    <option value="">不展示引语</option>{value && !sources.some(row => row.id === value) ? <option value={value}>原选择当前不可公开，需核对</option> : null}
    {sources.map(row => <option key={row.id} value={row.id}>{row.source.work_title} · {row.source.printed_label || `PDF ${row.source.page_start}`} · {row.source.text.slice(0, 65)}</option>)}
  </select></label>{evidence.error ? <p role="alert">原文读取失败。<button type="button" onClick={evidence.retry}>重新读取引语来源</button></p> : null}
  <p>可选引语来自本主题已发布、仍可阅读的原文。保存后仍需发布。</p>
  {topicId ? <Link href={`/admin/topics/${topicId}?section=passages`}>管理本主题原文策展</Link> : <p>先保存主题草稿，再编排原文。</p>}</>;
}
