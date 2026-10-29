"use client";

import { ScholarTagInput } from "./scholar-tag-input";
import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { PublishedEvidenceCuration } from "@/lib/api/evidence-curation.types";
import type { ScholarProfileSource } from "@/lib/api/scholars.types";
import { EntityPicker, RepeatableField } from "../forms/workflow-fields";

const sourceFields = { preferred_name: "标准名称", original_name: "原名", birth_year: "出生年", death_year: "逝世年", biography: "传记", short_description: "页面简介", nationalities: "国别", occupations: "研究身份", affiliations: "机构", key_concerns: "关注领域" };
export type ScholarProfileFields = { profileSources: ScholarProfileSource[]; nationalities: string[]; occupations: string[]; featuredSourceId: string; readingPathIds: string[] };
export function ScholarProfileFieldsEditor({ profileId, value, onChange, section = "all" }: { section?: "all" | "identity" | "sources" | "paths"; profileId: string | null; value: ScholarProfileFields; onChange: (patch: Partial<ScholarProfileFields>) => void }) {
  const evidence = useApiResource<PublishedEvidenceCuration>(profileId && (section === "all" || section === "sources") ? `/catalog/evidence-curation/scholar/${profileId}/` : "", getServerSessionCredential());
  const sources = evidence.data?.items.filter(row => row.id && row.source.public_eligible) || [];
  return <>
    {section === "all" || section === "identity" ? <section data-editor-section="identity"><ScholarTagInput label="身份标签" value={value.occupations} onChange={occupations=>onChange({occupations})}/></section> : null}
    {section === "all" || section === "sources" ? <section data-editor-section="sources"><ScholarTagInput label="国籍／地区" value={value.nationalities} onChange={nationalities=>onChange({nationalities})}/><p>为人物资料明确记录出处，并选择该来源支持的字段。这里只保存资料说明和链接，不抓取外站正文；机器候选仍需审核。</p>
      <RepeatableField label="人物资料来源" values={value.profileSources} create={() => ({ id: createRequestKey(), title: "", url: "", fields: [], note: "" })} onChange={profileSources => onChange({ profileSources })} render={(row, index, update) => <div><label><span>来源 {index + 1} 名称</span><input required maxLength={500} value={row.title} onChange={event => update({ ...row, title: event.target.value })} /></label><label><span>来源网址</span><input type="url" maxLength={2000} value={row.url} onChange={event => update({ ...row, url: event.target.value })} /></label><fieldset><legend>此来源支持哪些资料</legend>{Object.entries(sourceFields).map(([field, label]) => <label key={field} className="workflow-checkbox"><input type="checkbox" checked={row.fields.includes(field)} onChange={event => update({ ...row, fields: event.target.checked ? [...row.fields, field] : row.fields.filter(item => item !== field) })} /><span>{label}</span></label>)}</fieldset><label><span>书目或核对说明</span><textarea rows={2} maxLength={2000} value={row.note} onChange={event => update({ ...row, note: event.target.value })} /></label></div>} />
      <label><span>首屏原文引语</span><select value={value.featuredSourceId} disabled={evidence.loading} onChange={event => onChange({ featuredSourceId: event.target.value })}><option value="">不展示引语</option>{value.featuredSourceId && !sources.some(row => row.id === value.featuredSourceId) ? <option value={value.featuredSourceId}>原选择当前不可公开，需核对</option> : null}{sources.map(row => <option value={row.id} key={row.id}>{row.source.work_title} · {row.source.printed_label || `PDF ${row.source.page_start}`} · {row.source.text.slice(0, 65)}</option>)}</select></label>
      {evidence.error ? <p role="alert">原文来源读取失败。<button type="button" onClick={evidence.retry}>重新读取引语来源</button></p> : null}
      <p>引语只从本学者已正式发布、当前仍可阅读的原文策展选取。缺失原文时保留空态。</p>{profileId ? <Link href={`/admin/scholars/${profileId}?section=passages`}>管理本学者的原文策展</Link> : <p>先保存学者草稿，再编排原文。</p>}
    </section> : null}
    {section === "all" || section === "paths" ? <section data-editor-section="paths"><EntityPicker label="人工编排的相关阅读路径" endpoint="/catalog/admin/theory-system/reading-paths/" nameField="title" values={value.readingPathIds.map(id => ({ id, name: "已选择的阅读路径" }))} onChange={rows => onChange({ readingPathIds: rows.flatMap(row => row.id ? [row.id] : []) })} /><p>仅当前正式公开的路径对读者显示。由材料自动关联的路径会注明关联依据，不冒充学者本人策划。</p></section> : null}
  </>;
}
