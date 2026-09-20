"use client";

import { Children, Fragment, cloneElement, isValidElement, useEffect, useMemo, useState, type ReactElement, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { FixedPageEditor } from "@/components/admin/curation/fixed-page-editor";
import { PreviewSurface, type KnowledgePreviewPayload } from "@/components/admin/preview/knowledge-page-preview";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { editorialHeaders } from "@/lib/editorial-version";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { EditorialConflictHelp } from "@/components/admin/knowledge/editorial-conflict-help";
import { AsyncStatus } from "@/components/action-feedback";
import { EvidenceCurationEditor } from "@/components/admin/curation/evidence-curation-editor";
import type { EvidenceCurationType } from "@/lib/api/evidence-curation.types";

type Props = {objectType: string; objectId?: string | null; draft: object; dirty: boolean; refreshKey?: string | number; children: ReactNode; initialSection?: string; mediaFile?: File | null; savedRecord?: object | null; onPublished?: () => void};
type FieldProps = {children?: ReactNode; label?: string; className?: string; type?: string; role?: string; disabled?: boolean; style?: {display?: string}; "data-editor-section"?: string};
const sectionLabels: Record<string, string> = {identity:"基本信息", biography:"传记与机构", questions:"研究问题", history:"形成与发展", dimensions:"研究维度", methods:"研究方法 / 工具", concepts:"关键概念", timeline:"生平与事件", "concept-map":"概念图", network:"学术关系", content:"内容与说明", relations:"人物与馆藏关联", works:"代表作品", paths:"阅读路径", passages:"原文策展", media:"图片", publication:"保存与发布"};
function textOf(node: ReactNode): string { if (typeof node === "string") return node; if (!isValidElement<FieldProps>(node)) return ""; return node.props.label || Children.toArray(node.props.children).map(textOf).join(" "); }
function flatten(nodes: ReactNode): ReactNode[] {return Children.toArray(nodes).flatMap(node => {
  if (!isValidElement<FieldProps>(node)) return [node];
  if (node.type === "legend" || node.type === "summary") return [];
  return node.type === Fragment || node.type === "fieldset" || node.type === "details" || node.props.style?.display === "contents" || /^(structured-editor-pair|curation-fieldset|knowledge-form-grid|inline-fields)/.test(node.props.className || "") ? flatten(node.props.children) : [node];
});}
function sectionFor(node: ReactNode): string {
  if (!isValidElement<FieldProps>(node)) return "identity";
  if (node.props["data-editor-section"]) return node.props["data-editor-section"]!;
  if(node.type === EntityLifecycleActions) return "publication";
  const text = textOf(node);
  if (node.props.type === "submit" || node.props.className?.includes("footer") || node.props.className?.includes("actions") || /编辑状态|公开状态|发布状态|审核状态|确认发布|准备公开|保存本页|保存并公开|保存.*草稿|生命周期|历史版本|合并/.test(text)) return "publication";
  if (/概念地图|概念关系图/.test(text)) return "concept-map";
  if (/学术关系|历史关联阅读/.test(text)) return "network";
  if (/时间线|生平与|时间节点/.test(text)) return "timeline";
  if (/形成背景|形成与发展/.test(text)) return "history";
  if (/研究维度/.test(text)) return "dimensions";
  if (/常用方法|研究方法/.test(text)) return "methods";
  if (/问题陈述|核心问题/.test(text)) return "questions";
  if (/关键概念|核心概念|关键主题/.test(text)) return "concepts";
  if (/阅读路径|本路径文献/.test(text)) return "paths";
  if (/摘录|原文|出处/.test(text)) return "passages";
  if (/奠基文献|重要文献|推荐书目|最近入库/.test(text)) return "works";
  if (/相关学者|代表学者|相邻流派|关联理论|经常连着|相关理论|学科|子学科|主题关联/.test(text)) return "relations";
  if (/完整传记|机构|代表语录|语录来源/.test(text)) return "biography";
  if (/图片|主视觉|肖像|封面/.test(text)) return "media";
  if (/定义|命题|理论边界|更多名称|其他名称/.test(text)) return "content";
  return "identity";
}
function alwaysVisible(node:ReactNode) {return isValidElement<FieldProps>(node) && (node.type === EditorialConflictHelp || node.type === AsyncStatus || ["status","alert"].includes(node.props.role || "") || node.props.type === "submit" || node.type === "footer" || /footer|editor-actions|form-message/.test(node.props.className || ""));}
type Row = Record<string, unknown>;
function selectRows(ids: unknown, ...pools: unknown[]): Row[] { const all = pools.flatMap(pool => Array.isArray(pool) ? pool as Row[] : []); return (Array.isArray(ids) ? ids : []).flatMap(id => { const found = all.find(row => row.id === id || (row.person as Row)?.id === id); return found ? [found] : []; }); }
const lines = (value: unknown) => typeof value === "string" ? value.split(/\r?\n/).map(row => row.trim()).filter(Boolean) : Array.isArray(value) ? value : [];
const structured = (value: unknown, keys: string[]) => lines(value).map(line => {const values = String(line).split(/[｜|]/); return Object.fromEntries(keys.map((key, index) => [key, values[index]?.trim() || ""]));});
function project(type: string, raw: unknown, draft: Record<string, unknown>): Record<string, unknown> {
  const base = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
  const curated = base.curated && typeof base.curated === "object" ? base.curated as Record<string, unknown> : {};
  const defaults = {id: draft.id || "new", slug: draft.slug || "draft-preview", works: [], knowledge_nodes: [], ...base};
  const suggestions = (draft.suggestions || {}) as Row;
  const labels = (draft.preview_labels || {}) as Record<string,string>;
  const reference = (id:unknown,previous:unknown) => {const existing=(previous || {}) as Row;return id && typeof id === "string" ? (existing.id === id ? existing : {id,name:labels[id] || "已选择的馆内条目",slug:""}) : null;};
  const workPool = [base.works, curated.essential_works, curated.foundational_works, curated.recent_works];
  const candidateWorks = ((suggestions.works || []) as Row[]).map(row=>({id:row.id,title:row.title || row.name || "",document_type:row.document_type || "book",theories:[],topics:[],language:"",abstract:row.description || "",edition:null}));
  workPool.push(candidateWorks);
  if (type === "reading_path") return {...defaults,...draft,primary_discipline_data:base.primary_discipline_data || null, items:((draft.stages || []) as Row[]).flatMap((stage,stageIndex) => ((stage.items || []) as Row[]).map((item,index) => {const saved = ((base.items || []) as Row[]).find(row => (item.id && row.id === item.id) || (item.work && row.work === item.work) || (item.node && row.node === item.node)); return {id:item.id || `${stageIndex}-${index}`,reading_order:index+1,stage_name:stage.name,stage_description:stage.description,recommendation_reason:item.recommendation_reason,prerequisite:item.prerequisite,is_required:item.is_required,work_data:item.work ? saved?.work_data || {id:item.work,title:item.work_name,detail_href:`/works/${item.work}`} : null,node_data:item.node ? saved?.node_data || {id:item.node,canonical_name_zh:item.node_name,slug:"",summary:""}:null};}))};
  if (type === "scholar") return {...defaults, person:{id: draft.personId || "new", ...(base.person as object || {}), preferred_name: draft.name, original_name:draft.originalName, biography:draft.biography, birth_year:Number(draft.birthYear)||null, death_year:Number(draft.deathYear)||null}, short_description:draft.description, affiliations:lines(draft.affiliations), key_concerns:lines(draft.concerns), timeline:structured(draft.timeline,["year","type","event"]).map(row => [row.year,row.event]), featured_quote:draft.quote, quote_source:draft.quoteSource, curated:{...curated, essential_works:selectRows(draft.essentialWorkIds,...workPool), frequently_read_scholars:selectRows(draft.frequentScholarIds,curated.frequently_read_scholars,suggestions.related_scholars), related_theories:selectRows(draft.relatedTheoryIds,curated.related_theories,suggestions.theories), key_concepts:structured(draft.keyConcepts,["name","description","source"]), concept_map:structured(draft.conceptMap,["source","target","relation","description"]), network:selectRows(draft.networkScholarIds,((curated.network || []) as Row[]).map(row=>row.scholar),suggestions.related_scholars).map(row=>({scholar:{id:row.id,name:row.name || row.title,slug:row.slug || ""},relation:"",source:"",...(draft.networkRelations as Record<string,object> || {})[String(row.id)]}))}};
  if (type === "topic") return {...defaults, name:draft.name, description:draft.description, problem_statement:draft.problemStatement, formation_context:draft.formationContext, core_questions:lines(draft.coreQuestions), research_dimensions:lines(draft.researchDimensions), methods:lines(draft.methods), key_concepts:lines(draft.terms), timeline:structured(draft.timeline,["year","title","description"]).map(row => [row.year,row.title,row.description]), disciplines:base.disciplines || [], subdisciplines:base.subdisciplines || [], theories:base.theories || [], scholars:[...((base.scholars || []) as Row[]), ...selectRows(draft.scholarIds,suggestions.scholars).filter(row=>!((base.scholars || []) as Row[]).some(saved=>saved.id===row.id || (saved.person as Row)?.id===row.id)).map(row=>({id:row.id,slug:row.slug || "",person:{id:row.id,preferred_name:row.name || row.title,original_name:"",biography:row.description || ""},short_description:row.description || "",key_concerns:[]}))], passages:base.passages || [], work_count:base.work_count || 0, curated:{...curated, foundational_works:selectRows(draft.primaryWorkIds,...workPool), recent_works:selectRows(draft.secondaryWorkIds,...workPool), related_scholars:selectRows(draft.scholarIds,curated.related_scholars,suggestions.scholars), linked_theories:selectRows(draft.theoryIds,curated.linked_theories,suggestions.theories), reading_paths:((draft.readingPaths || []) as Row[]).map(path => ({...path,works:selectRows(path.workIds,...workPool)})), hero_caption:draft.heroCaption, featured_passage_id:(draft.featuredPassageIds as string[] || [])[0] || ""}};
  if (["theory", "concept", "debate", "research_problem"].includes(type)) return {...defaults, ...draft, core_questions:lines(draft.core_questions), basic_propositions:lines(draft.basic_propositions), representative_scholars:base.representative_scholars || [], related_disciplines:(draft.related_disciplines as string[] || []).map(id=>reference(id,((base.related_disciplines || []) as Row[]).find(row=>row.id===id))), primary_discipline:reference(draft.primary_discipline,base.primary_discipline), work_groups:base.work_groups || {}, evidence:base.evidence || [], direct_relations:base.direct_relations || [], updated_at:base.updated_at || ""};
  return {...defaults, ...draft, discipline:reference(draft.discipline,base.discipline) || base.discipline || {name:"",slug:""}, theories:base.theories || [], works:base.works || [], disciplines:base.disciplines || [], core_questions:lines(draft.core_questions), research_directions:lines(draft.research_directions), methods:lines(draft.methods), representative_issues:lines(draft.representative_issues), research_questions:lines(draft.research_questions)};
}

/** One content task at a time; preview uses the same public component and only local form input. */
export function KnowledgeVisualEditor({objectType, objectId, draft, dirty, refreshKey, children, initialSection, mediaFile, savedRecord, onPublished}: Props) {
  const searchParams = useSearchParams();
  const [active, setActive] = useState(initialSection || searchParams.get("section") || "identity");
  const [payload, setPayload] = useState<KnowledgePreviewPayload | null>(null);
  const [error, setError] = useState("");
  const [evidenceDirty, setEvidenceDirty] = useState(false);
  const canPublish = hasAdminCapability(useAdminSession(),"can_publish_authority");
  const [publishing,setPublishing] = useState(false);
  const [publicationMessage,setPublicationMessage] = useState("");
  async function publishSaved() {
    if(!objectId || !savedRecord || dirty || publishing || !canPublish)return;
    const endpoint = ({scholar:"scholars",topic:"topics",discipline:"disciplines",subdiscipline:"subdisciplines",reading_path:"theory-system/reading-paths"} as Record<string,string>)[objectType] || "theory-system/nodes";
    setPublishing(true);setPublicationMessage("");
    try {
      const field=["scholar","topic","discipline","subdiscipline"].includes(objectType)?"editorial_status":"status";
      const saved=await apiRequest<{editorial_revision?:{id:string;status:string}}>(`/catalog/admin/${endpoint}/${objectId}/`,{method:"PATCH",headers:editorialHeaders(savedRecord),body:JSON.stringify({[field]:"published"})},getServerSessionCredential());
      if(saved.editorial_revision?.status === "draft") await apiRequest(`/catalog/admin/editorial-revisions/${saved.editorial_revision.id}/publish/`,{method:"POST",body:"{}"},getServerSessionCredential());
      setPublicationMessage("已提交发布。内容和检索更新结果可在发布记录中核对。");onPublished?.();
    } catch(reason){setPublicationMessage(reason instanceof Error?reason.message:"发布失败，已保存草稿仍然保留。");}
    finally{setPublishing(false);}
  }
  const [localImage, setLocalImage] = useState("");
  useEffect(()=>{let active=true;const url=mediaFile?URL.createObjectURL(mediaFile):"";queueMicrotask(()=>{if(active)setLocalImage(url);});return()=>{active=false;if(url)URL.revokeObjectURL(url);};},[mediaFile]);
  useEffect(() => {let current = true; queueMicrotask(()=>{if(current){setPayload(null);setError("");}}); if (!objectId) return()=>{current=false;}; apiRequest<KnowledgePreviewPayload>(`/catalog/admin/knowledge-preview/${objectType}/${objectId}/`, {}, getServerSessionCredential()).then(value => {if (current) setPayload(value);}).catch(reason => {if (current) setError(reason instanceof Error ? reason.message : "预览读取失败");}); return () => {current = false;};},[objectType, objectId, refreshKey]);
  const childList = Children.toArray(children);
  const form = childList.find(node => isValidElement(node) && node.type === "form") as ReactElement<{children:ReactNode}> | undefined;
  const rail = childList.filter(node => node !== form);
  const originalFields = form ? Children.toArray(form.props.children) : [];
  const disabled = originalFields.some(node => isValidElement<FieldProps>(node) && node.props.disabled);
  const fields = form ? flatten(form.props.children) : [];
  const groups = fields.map(node => ({node, section:sectionFor(node)}));
  const evidenceType: EvidenceCurationType | null = objectType === "scholar" || objectType === "topic" ? objectType : ["theory", "concept", "debate", "research_problem"].includes(objectType) ? "node" : null;
  const sections = Object.entries(sectionLabels).filter(([id]) => groups.some(row => row.section === id) || ["publication","media"].includes(id) || (id === "passages" && evidenceType)).map(([id,label]) => ({id,label}));
  const selected = sections.some(row => row.id === active) ? active : "identity";
  const live = useMemo(() => {const projected=project(objectType,payload?.perspective.data,draft as Record<string,unknown>);return localImage ? {...projected,hero_image:localImage,cover_url:localImage,cover_media:null,...(objectType === "scholar" ? {person:{...(projected.person as Row),portrait:localImage,portrait_media:null}} : {})}:projected;},[objectType,payload,draft,localImage]);
  const previewPayload = {...payload, object_type:objectType, object_id:objectId || "new", active_perspective:"draft", perspective:{source:"browser_input", available:true, serializer:payload?.perspective.serializer || "", data:live}} as KnowledgePreviewPayload;
  const page = objectType === "scholar" && ["timeline","concepts","concept-map","network","biography","works"].includes(selected) ? selected : objectType === "topic" && ["questions","history","dimensions","methods","passages","timeline","concepts","works","paths"].includes(selected) ? (selected === "paths" ? "reading-paths" : selected) : ["theory","concept","debate","research_problem"].includes(objectType) && selected === "content" ? "propositions" : "overview";
  function changeSection(id: string) {
    if (id === selected) return;
    if (selected === "passages" && evidenceDirty && !window.confirm("原文策展尚未保存，确定切换并放弃这些输入吗？")) return;
    setEvidenceDirty(false); setActive(id);
    const url = new URL(window.location.href); url.searchParams.set("section",id); window.history.replaceState(null,"",url.pathname+url.search);
  }
  if (selected === "passages" && evidenceType) return <div className="knowledge-visual-editor">{objectId ? <EvidenceCurationEditor key={`${evidenceType}:${objectId}`} objectType={evidenceType} objectId={objectId} sections={sections} onSectionChange={changeSection} onDirtyChange={setEvidenceDirty} /> : <><nav className="fixed-editor-sections" aria-label="编辑区域">{sections.map(section => <button type="button" key={section.id} onClick={() => changeSection(section.id)}>{section.label}</button>)}</nav><p className="admin-panel">请先保存当前对象，再选择馆内原文。当前基本信息输入仍然保留。</p></>}</div>;
  return <div className="knowledge-visual-editor">{objectType === "scholar" && selected === "network" ? <section className="private-preview-label"><strong>规范学术关系</strong><p>两端学者共用同一关系、方向、说明和来源。下方历史关联阅读保持原记录。</p>{objectId ? <Link className="button secondary" href={`/admin/scholars/${objectId}/relations`}>进入学者关系图编辑</Link> : <p>请先保存学者草稿，再建立关系。</p>}</section> : null}<FixedPageEditor sections={sections} activeSection={selected} onSectionChange={changeSection} dirty={dirty} previewHref={objectId ? `/admin/preview/knowledge/${objectType}/${objectId}?page=${page}` : undefined}
    fields={form ? cloneElement(form,{},<fieldset disabled={disabled} style={{display:"contents"}}>{groups.map(({node,section},index) => <div key={index} hidden={section !== selected && !alwaysVisible(node)} data-field-section={section}>{node}</div>)}</fieldset>) : children}
    preview={error ? <p className="form-message" role="alert">{error}。当前输入仍保留，保存后可重新打开预览。</p> : objectId && !payload ? <p role="status">正在读取当前对象的受控预览…</p> : <div onClickCapture={event => {const target = event.target as HTMLElement; const row = target.closest<HTMLElement>("[data-edit-row]"); if (row) window.dispatchEvent(new CustomEvent("knowledge-row-select",{detail:Number(row.dataset.editRow)})); if (target.closest("a")) event.preventDefault();}}><PreviewSurface payload={previewPayload} pageId={page}/></div>}/>
    <details className="knowledge-editor-support" hidden={!["publication","media","relations"].includes(selected)} open><summary>{selected === "media" ? "选择图片" : selected === "relations" ? "管理共享关联" : "已保存草稿、发布与记录"}</summary>{selected === "publication" && objectId && savedRecord ? <section className="knowledge-publish-action"><button type="button" className="button" disabled={dirty || publishing || !canPublish} onClick={()=>void publishSaved()}>{publishing?"正在发布…":"发布已保存内容"}</button><p>{dirty?"当前输入尚未保存，请先保存草稿。":!canPublish?"当前账号没有正式发布权限。":"将已保存的当前对象内容发布给读者。"}</p>{publicationMessage?<p role="status">{publicationMessage}</p>:null}</section>:null}{rail}</details>
  </div>;
}
