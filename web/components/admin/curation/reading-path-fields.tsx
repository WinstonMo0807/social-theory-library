"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useAdminSession } from "@/lib/admin-session";
import type { CollectionPage, WorkLibraryRow } from "@/lib/api/admin-collections";
import { outlinePath, type OutlineState } from "@/lib/api/curation-workspace.client";
import { EntityPicker, RepeatableField } from "../forms/workflow-fields";

export type PathLearningFields = { learning_questions: string[]; related_debate_ids: string[] };
export type PathMaterialFields = {
  learning_goal:string;
  dependencies: import("./reading-path-dependencies").PathDependency[];
  material_kind: "work" | "chapter" | "paper" | "node"; edition: string | null; asset: string | null;
  document_revision: string | null; page_start: number | null; page_end: number | null;
  chapter_title: string; printed_page_label: string; status: "active" | "withdrawn"; substitute_edition_ids: string[];
};
export const emptyLearning: PathLearningFields = { learning_questions: [], related_debate_ids: [] };
export const emptyMaterial: PathMaterialFields = { learning_goal:"", dependencies: [], material_kind: "work", edition: null, asset: null, document_revision: null,
  page_start: null, page_end: null, chapter_title: "", printed_page_label: "", status: "active", substitute_edition_ids: [] };
export const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
export function learningFields(row: Record<string, unknown>): PathLearningFields {
  return { learning_questions: strings(row.learning_questions), related_debate_ids: strings(row.related_debate_ids) };
}
export function materialFields(row: Record<string, unknown>): PathMaterialFields {
  return { learning_goal:typeof row.learning_goal === "string"?row.learning_goal:"", dependencies:Array.isArray(row.dependencies)?row.dependencies.filter((item): item is import("./reading-path-dependencies").PathDependency=>Boolean(item && typeof item === "object" && typeof item.item_id === "string" && ["learning_order","theory_related"].includes(item.kind))).map(item=>({...item,reason:typeof item.reason === "string"?item.reason:""})):[], material_kind: ["chapter", "paper", "node"].includes(String(row.material_kind)) ? row.material_kind as PathMaterialFields["material_kind"] : row.node ? "node" : "work",
    edition: typeof row.edition === "string" ? row.edition : null, asset: typeof row.asset === "string" ? row.asset : null,
    document_revision: typeof row.document_revision === "string" ? row.document_revision : null,
    page_start: typeof row.page_start === "number" ? row.page_start : null, page_end: typeof row.page_end === "number" ? row.page_end : null,
    chapter_title: typeof row.chapter_title === "string" ? row.chapter_title : "", printed_page_label: typeof row.printed_page_label === "string" ? row.printed_page_label : "",
    status: row.status === "withdrawn" ? "withdrawn" : "active", substitute_edition_ids: strings(row.substitute_edition_ids) };
}

export function PathLearningEditor({ value, onChange, label }: { value: PathLearningFields; onChange: (patch: Partial<PathLearningFields>) => void; label: string }) {
  return <section aria-label={`${label}学习问题与争论`}>
    <RepeatableField label={`${label}学习问题`} values={value.learning_questions} create={() => ""} onChange={learning_questions => onChange({ learning_questions })}
      render={(question, index, update) => <label><span>问题 {index + 1}</span><input value={question} maxLength={1000} onChange={event => update(event.target.value)} /></label>} />
    <EntityPicker label={`${label}相关争论`} endpoint="/catalog/admin/theory-system/nodes/?type=debate" queryParam="q" nameField="canonical_name_zh"
      values={value.related_debate_ids.map(id => ({ id, name: "已选择的争论" }))} onChange={rows => onChange({ related_debate_ids: rows.flatMap(row => row.id ? [row.id] : []) })} />
    <small>只会公开当前已发布的争论。学习问题为策划者填写，未填写时保持空态。</small>
  </section>;
}

function usePathResource<T>(url:string) {
  const owner=String(useAdminSession()?.id||"");
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<T>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<T>(url,owner,undefined,load);
  return {data:resource.data,error:resource.error,loading:!resource.data&&!resource.error,retry:resource.reload};
}

export function PathMaterialEditor({ work, value, onChange }: { work: string | null; value: PathMaterialFields; onChange: (patch: Partial<PathMaterialFields>) => void }) {
  const [page, setPage] = useState(1);
  const base = "/catalog/admin/library/works/?view=editions";
  const rows = usePathResource<CollectionPage<WorkLibraryRow>>(work ? `${base}&work_id=${encodeURIComponent(work)}&page=${page}` : "");
  const listed = rows.data?.results.find(row => row.id === value.edition);
  const selected = usePathResource<CollectionPage<WorkLibraryRow>>(value.edition && !listed ? `${base}&edition_id=${encodeURIComponent(value.edition)}` : "");
  const edition = listed || selected.data?.results.find(row => row.id === value.edition);
  const files = edition?.assets?.filter(row => row.kind === "normalized") || [], file = files.find(row => row.id === value.asset);
  const source = usePathResource<OutlineState>(value.asset ? outlinePath(value.asset) : "");
  const currentRevision = source.data?.asset?.document_revision_id;
  const error = rows.error || selected.error || source.error;
  return <section aria-label="材料版本与阅读位置">
    <div className="inline-fields"><label><span>材料类型</span><select value={value.material_kind} onChange={event => onChange({ material_kind: event.target.value as PathMaterialFields["material_kind"] })}>
      {work ? <><option value="work">整部作品</option><option value="chapter">章节或选段</option><option value="paper">论文</option></> : <option value="node">理论或概念条目</option>}
    </select></label><label><span>材料在路径中的状态</span><select value={value.status} onChange={event => onChange({ status: event.target.value as PathMaterialFields["status"] })}><option value="active">保留在阅读路线</option><option value="withdrawn">已从路线撤回，保留位置说明</option></select></label></div>
    {work ? <>
      {error ? <p role="alert">{error}<button type="button" onClick={() => { rows.retry(); selected.retry(); source.retry(); }}>重新读取材料版本</button></p> : null}
      <label><span>明确出版版本</span><select value={value.edition || ""} disabled={rows.loading} onChange={event => onChange({ edition: event.target.value || null, asset: null, document_revision: null, page_start: null, page_end: null })}>
        <option value="">版本尚未明确</option>{value.edition && !listed ? <option value={value.edition}>{edition?.label || "已保存版本，待核对"}</option> : null}
        {rows.data?.results.map(row => <option key={row.id} value={row.id}>{row.label || row.title}{row.is_primary ? "（主版本）" : ""}</option>)}
      </select></label><nav aria-label="阅读材料版本分页"><button type="button" disabled={!rows.data?.previous || rows.loading} onClick={() => setPage(p => p - 1)}>上一页版本</button><span>第 {page} 页 · 共 {rows.data?.count ?? "—"} 个版本</span><button type="button" disabled={!rows.data?.next || rows.loading} onClick={() => setPage(p => p + 1)}>下一页版本</button></nav>
      <label><span>原文文件</span><select value={value.asset || ""} disabled={!edition} onChange={event => onChange({ asset: event.target.value || null, document_revision: null, page_start: null, page_end: null })}>
        <option value="">暂无明确原文，只保留书目</option>{value.asset && !file ? <option value={value.asset}>已保存文件，待核对</option> : null}
        {files.map(row => <option key={row.id} value={row.id} disabled={row.status !== "ready" || row.validation_status !== "valid" || row.page_count < 1}>{row.original_filename || "阅读文件"} · 第 {row.version} 版 · {row.page_count} 页</option>)}
      </select></label>
      {value.asset ? <div><p>{source.loading ? "正在核对当前原文修订…" : currentRevision ? value.document_revision === currentRevision ? "材料已固定到当前文件修订。" : "请核对原文，再明确采用当前文件修订。旧选择不会自动替换。" : "尚无可用的原文修订，不能生成阅读链接。"}</p>
        <button type="button" disabled={!currentRevision || value.document_revision === currentRevision || source.data?.asset?.source_current === false} onClick={() => { if (currentRevision) onChange({ document_revision: currentRevision }); }}>采用当前文件修订</button></div> : null}
      <div className="inline-fields"><label><span>起始 PDF 页序</span><input type="number" min={1} max={file?.page_count} value={value.page_start ?? ""} onChange={event => onChange({ page_start: event.target.value ? Number(event.target.value) : null })} /></label><label><span>结束 PDF 页序</span><input type="number" min={value.page_start || 1} max={file?.page_count} value={value.page_end ?? ""} onChange={event => onChange({ page_end: event.target.value ? Number(event.target.value) : null })} /></label></div>
      <p>更换出版版或文件后需重新核对页序。没有全文的材料仍保留在路径中；指定版失效时不自动改用其他版。</p>
      {value.edition ? <Link href={`/admin/library/works/${encodeURIComponent(work)}?edition=${encodeURIComponent(value.edition)}#file`} target="_blank" rel="noopener noreferrer">管理这份版本与原文 ↗</Link> : null}
    </> : null}
    <div className="inline-fields"><label><span>章节或选段标题</span><input value={value.chapter_title} maxLength={300} onChange={event => onChange({ chapter_title: event.target.value })} /></label><label><span>印刷页码说明</span><input value={value.printed_page_label} maxLength={120} onChange={event => onChange({ printed_page_label: event.target.value })} /></label></div>
    <EntityPicker label="明确推荐的替代版本" endpoint={`${base}`} queryParam="q" nameField="label" values={value.substitute_edition_ids.map(id => ({ id, name: "已指定替代版本" }))} onChange={items => onChange({ substitute_edition_ids: items.flatMap(row => row.id ? [row.id] : []) })} />
    <small>替代材料只作明确的策划建议，不会替换读者已有进度与笔记。</small>
  </section>;
}
