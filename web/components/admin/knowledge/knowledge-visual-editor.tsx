"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { Children, Fragment, cloneElement, isValidElement, useEffect, useMemo, useState, useRef, type ReactElement, type ReactNode } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import Link from "next/link";
import { PathEditorFrame, pathEditorSection, pathEditorSections } from "./path-editor-frame";
import type { PublicReadingPath } from "@/lib/api/reading-paths.types";
import { nodeEditorialForSave, type NodeEditorialDetails } from "@/lib/api/node-editorial";
import { TopicEditorFrame, topicEditorSection, topicEditorSections } from "./topic-editor-frame";
import type { PublicTopicDetail } from "@/lib/api/topics.types";
import { ScholarCanonicalSections } from "./scholar-canonical-sections";
import type { NodeRelationGuard } from "./node-relations";
import { KnowledgeNodeSummary } from "./knowledge-node-summary";
import { ConceptPlacementEditor } from "./concept-placement-editor";
import { KnowledgeNodeEditorFrame, knowledgeNodeSection, knowledgeNodeSections } from "./knowledge-node-editor-frame";
import type { PublicScholarDetail } from "@/lib/api/scholars.types";
import { ScholarEditorFrame, scholarEditorSection, scholarEditorSections } from "./scholar-editor-frame";
import { projectScholar, scholarPreviewBody } from "./scholar-preview";
import { projectTopic, topicPreviewBody } from "./topic-preview";
import type { TopicCurationFields } from "./topic-fields";
import type { PathPreviewState } from "../curation/use-reading-path-preview";
import { projectReadingPath } from "@/components/admin/curation/reading-path-preview";
import { FixedPageEditor, type PreviewSelection } from "@/components/admin/curation/fixed-page-editor";
import { MaterialAssistantProvider, MaterialAssistantEntry } from "../workflow/material-assistant";
import { PreviewSurface, type KnowledgePreviewPayload } from "@/components/admin/preview/knowledge-page-preview";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { KnowledgePublishControl, KnowledgePublicationContext } from "./knowledge-publish-control";
import { EntityLifecycleActions } from "@/components/entity-lifecycle-actions";
import { EditorialConflictHelp } from "@/components/admin/knowledge/editorial-conflict-help";
import { AsyncStatus } from "@/components/action-feedback";
import { EvidenceCurationEditor } from "@/components/admin/curation/evidence-curation-editor";
import type { EvidenceCurationType } from "@/lib/api/evidence-curation.types";

type Props = {readingPathCandidates?:ReactNode;readingPathPreview?: PathPreviewState; onRelationGuardChange?: (value: NodeRelationGuard) => void; portrait?: ReactNode; objectType: string; objectId?: string | null; draft: object; dirty: boolean; refreshKey?: string | number; children: ReactNode; initialSection?: string; mediaFile?: File | null; savedRecord?: object | null; onPublished?: () => void; previewStageId?: string; onPreviewSelect?: (selection: PreviewSelection) => void};
type FieldProps = {children?: ReactNode; label?: string; className?: string; type?: string; role?: string; disabled?: boolean; style?: {display?: string}; "data-editor-section"?: string};
const sectionLabels: Record<string, string> = {dependencies:"先修关系",stages:"阶段编排",identity:"基本信息", biography:"传记与机构", questions:"研究问题", scholars:"相关学者", articles:"策划文章", history:"形成与发展", dimensions:"研究维度", methods:"研究方法 / 工具", concepts:"关键概念", timeline:"生平与事件", "concept-map":"概念图", network:"学术关系", content:"内容与说明", relations:"人物与馆藏关联", works:"代表作品", paths:"阅读路径", passages:"原文策展", media:"图片", learning:"学习问题与争论", curation:"策划说明与署名", versions:"版本记录", sources:"资料来源与路径", publication:"保存与发布"};
function textOf(node: ReactNode): string { if (typeof node === "string") return node; if (!isValidElement<FieldProps>(node)) return ""; return node.props.label || Children.toArray(node.props.children).map(textOf).join(" "); }
function flatten(nodes: ReactNode): ReactNode[] {return Children.toArray(nodes).flatMap(node => {
  if (!isValidElement<FieldProps>(node)) return [node];
  if (node.type === "legend" || node.type === "summary") return [];
  if (node.props["data-editor-section"]) return [node];
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
const lines = (value: unknown) => typeof value === "string" ? value.split(/\r?\n/).map(row => row.trim()).filter(Boolean) : Array.isArray(value) ? value : [];
function project(type: string, raw: unknown, draft: Record<string, unknown>): Record<string, unknown> {
  const base = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
  const defaults = {id: draft.id || "new", slug: draft.slug || "draft-preview", works: [], knowledge_nodes: [], ...base};
  const labels = (draft.preview_labels || {}) as Record<string,string>;
  const reference = (id:unknown,previous:unknown) => {const existing=(previous || {}) as Row;return id && typeof id === "string" ? (existing.id === id ? existing : {id,name:labels[id] || "已选择的馆内条目",slug:""}) : null;};
  if (type === "reading_path") return projectReadingPath(base, draft);
  if (type === "scholar") return projectScholar(base, draft);
  if (type === "topic") return projectTopic(base, draft);
  if (["theory", "concept", "debate", "research_problem"].includes(type)) return {...defaults, ...draft, prose:nodeEditorialForSave(draft.editorial_details as NodeEditorialDetails | undefined,{summary:String(draft.summary||""),definition:String(draft.definition||""),theoretical_boundary:String(draft.theoretical_boundary||"")}).prose, core_questions:lines(draft.core_questions), basic_propositions:lines(draft.basic_propositions), representative_scholars:base.representative_scholars || [], related_disciplines:(draft.related_disciplines as string[] || []).map(id=>reference(id,((base.related_disciplines || []) as Row[]).find(row=>row.id===id))), primary_discipline:reference(draft.primary_discipline,base.primary_discipline), work_groups:base.work_groups || {}, evidence:base.evidence || [], direct_relations:base.direct_relations || [], updated_at:base.updated_at || ""};
  return {...defaults, ...draft, discipline:reference(draft.discipline,base.discipline) || base.discipline || {name:"",slug:""}, theories:base.theories || [], works:base.works || [], disciplines:base.disciplines || [], core_questions:lines(draft.core_questions), research_directions:lines(draft.research_directions), methods:lines(draft.methods), representative_issues:lines(draft.representative_issues), research_questions:lines(draft.research_questions)};
}

/** Public components project local fields and server-verified, unsaved selections. */
export function KnowledgeVisualEditor({objectType, objectId, draft, dirty, refreshKey, children, initialSection, mediaFile, savedRecord, onPublished, previewStageId, onPreviewSelect, portrait, onRelationGuardChange, readingPathPreview, readingPathCandidates}: Props) {
  const assistantRoot=useRef<HTMLDivElement|null>(null);
  const composing=useRef(false);
  const [ime,setIme]=useState(false);
  const searchParams = useSearchParams();
  const pathname=usePathname();
  const user=useAdminSession(),owner=user?String(user.id):"",savedVersion=(savedRecord as {edit_version?:string}|null)?.edit_version||"";
  const [active, setActive] = useState(initialSection || searchParams.get("section") || "identity");
  const [resolved, setResolved] = useState<{ key: string; payload: KnowledgePreviewPayload } | null>(null);
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);
  const [previewRetry, setPreviewRetry] = useState(0);
  const previewQuery = "";
  const hasPathPreview = Boolean(readingPathPreview);
  const previewBody = objectType === "scholar" ? scholarPreviewBody(draft as Row) : objectType === "topic" ? topicPreviewBody(draft as TopicCurationFields) : "";
  const previewKey = JSON.stringify([objectType, objectId, refreshKey, previewQuery, previewBody, previewRetry, owner, savedVersion]);
  const payload = resolved?.key === previewKey ? resolved.payload : null;
  const error = failure?.key === previewKey ? failure.message : "";
  const [evidenceDirty, setEvidenceDirty] = useState(false);
  const [publicationLocked,setPublicationLocked] = useState(Boolean(objectId && savedRecord));
  const [relationGuard, setRelationGuard] = useState<NodeRelationGuard>({dirty:false,pending:false,composing:false});
  useEffect(() => { onRelationGuardChange?.(relationGuard); }, [onRelationGuardChange, relationGuard]);
  const [placementPending, setPlacementPending] = useState(false);
  const [localImage, setLocalImage] = useState("");
  useEffect(()=>{let active=true;const url=mediaFile?URL.createObjectURL(mediaFile):"";queueMicrotask(()=>{if(active)setLocalImage(url);});return()=>{active=false;if(url)URL.revokeObjectURL(url);};},[mediaFile]);
  useEffect(() => {
    if (!objectId || !owner || objectType === "reading_path" && hasPathPreview) return;
    const controller = new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    const params=new URLSearchParams(previewQuery);if(savedVersion)params.set("edit_version",savedVersion);
    const unsubscribe=subscribeToSessionChanges(()=>{controller.abort();setResolved(null);setFailure({key:previewKey,message:"账户已变化，请重新打开当前对象。"});});
    queueMicrotask(() => { if (!controller.signal.aborted) { setResolved(null); setFailure(null); } });
    withPrivateOwner(owner,()=>apiRequest<KnowledgePreviewPayload>(`/catalog/admin/knowledge-preview/${objectType}/${objectId}/${params.size ? `?${params}` : ""}`, { signal,cache:"no-store",headers:{"X-Editor-Owner":owner}, ...(previewBody ? { method: "POST", body: previewBody } : {}) }, getServerSessionCredential()),signal)
      .then(value => { if(value.object_type!==objectType||value.object_id!==objectId||savedVersion&&value.edit_version!==savedVersion)throw Error("预览与保存版本不一致，请重新核对。");if (!controller.signal.aborted) { setResolved({ key: previewKey, payload: value }); setFailure(null); } })
      .catch(reason => { if (!controller.signal.aborted) setFailure({ key: previewKey, message: reason instanceof Error ? reason.message : "预览读取失败" }); });
    return () => {controller.abort();unsubscribe();};
  }, [objectType, objectId, previewQuery, previewBody, previewKey,owner,savedVersion,hasPathPreview]);
  const childList = Children.toArray(children);
  const form = childList.find(node => isValidElement(node) && node.type === "form") as ReactElement<{children:ReactNode}> | undefined;
  const rail = childList.filter(node => node !== form);
  const originalFields = form ? Children.toArray(form.props.children) : [];
  const disabled = originalFields.some(node => isValidElement<FieldProps>(node) && node.props.disabled);
  const fields = form ? flatten(form.props.children) : [];
  const groups = fields.map(node => ({node, section:sectionFor(node), persistent:alwaysVisible(node)}));
  const evidenceType: EvidenceCurationType | null = objectType === "scholar" || objectType === "topic" ? objectType : ["theory", "concept", "debate", "research_problem"].includes(objectType) ? "node" : null;
  const isNode = ["theory", "concept", "debate", "research_problem"].includes(objectType);
  const sections = objectType === "reading_path" ? pathEditorSections : objectType === "scholar" ? scholarEditorSections : objectType === "topic" ? topicEditorSections : isNode ? knowledgeNodeSections : Object.entries(sectionLabels).filter(([id]) => groups.some(row => row.section === id) || ["publication","media"].includes(id) || (id === "versions" && objectId) || (id === "passages" && evidenceType)).map(([id,label]) => ({id,label}));
  const activeSection = objectType === "reading_path" ? pathEditorSection(active) : objectType === "scholar" ? scholarEditorSection(active) : objectType === "topic" ? topicEditorSection(active) : isNode ? knowledgeNodeSection(active) : active;
  const selected = sections.some(row => row.id === activeSection) ? activeSection : "identity";
  const live = useMemo(() => {const projected=project(objectType,payload?.perspective.data,draft as Record<string,unknown>);return localImage ? {...projected,hero_image:localImage,cover_url:localImage,cover_media:null,...(objectType === "scholar" ? {person:{...(projected.person as Row),portrait:localImage,portrait_media:null}} : {})}:projected;},[objectType,payload,draft,localImage]);
  const previewPayload = {...payload, object_type:objectType, object_id:objectId || "new", active_perspective:"draft", perspective:{source:"browser_input", available:true, serializer:payload?.perspective.serializer || "", data:live}} as KnowledgePreviewPayload;
  const page = objectType === "reading_path" ? selected : objectType === "scholar" && ["timeline","concepts","concept-map","network","biography","works","sources","paths"].includes(selected) ? selected : objectType === "topic" && ["questions","history","dimensions","methods","passages","timeline","concepts","works","paths","scholars","articles"].includes(selected) ? (selected === "paths" ? "reading-paths" : selected) : ["theory","concept","debate","research_problem"].includes(objectType) && selected === "content" ? "propositions" : "overview";
  function changeSection(id: string) {
    if (composing.current || id === selected || (publicationLocked && id !== "publication")) return;
    if (selected === "relations" && isNode) {
      if (relationGuard.composing) return;
      if (relationGuard.pending) { window.alert("请先在关系详情查询原请求，或停止未执行的请求，再切换栏目。"); return; }
      if (relationGuard.dirty && !window.confirm("关系还有未保存输入，放弃这些输入并切换栏目吗？")) return;
    }
    if (selected === "passages" && evidenceDirty && !window.confirm("原文策展尚未保存，确定切换并放弃这些输入吗？")) return;
    setEvidenceDirty(false); setActive(id);
    const url = new URL(window.location.href); url.searchParams.set("section",id); window.history.replaceState(null,"",url.pathname+url.search);
  }
  function withAssistant(content:ReactNode){return <MaterialAssistantProvider dirty={dirty} disabled={disabled||publicationLocked} save={()=>{assistantRoot.current?.querySelector<HTMLFormElement>("form")?.requestSubmit();}} preview={readingPathPreview ? readingPathPreview.error ? <p role="alert">{readingPathPreview.error}</p> : readingPathPreview.data ? <div inert><PreviewSurface payload={{...previewPayload,perspective:{...previewPayload.perspective,data:readingPathPreview.data}}} pageId="overview"/></div> : <LoadingState>正在核对当前路径材料…</LoadingState> : error?<p role="alert">{error}</p>:objectId&&!payload?<LoadingState>正在核对页面资料…</LoadingState>:<div inert><PreviewSurface payload={previewPayload} pageId="overview"/></div>}><div ref={assistantRoot} onCompositionStartCapture={()=>{composing.current=true;setIme(true);}} onCompositionEndCapture={()=>{composing.current=false;setIme(false);}}>{objectType==="reading_path"?<details className="path-field-assistance"><summary>字段候选与材料助手</summary><MaterialAssistantEntry autoOpen={searchParams.get("assistant")==="fields"}/></details>:<MaterialAssistantEntry autoOpen={searchParams.get("assistant")==="fields"}/>}{content}</div></MaterialAssistantProvider>;}
  const evidenceEditor = evidenceType ? <div className="knowledge-visual-editor" inert={publicationLocked}>{objectId ? <EvidenceCurationEditor key={`${evidenceType}:${objectId}`} objectType={evidenceType} objectId={objectId} sections={sections} onSectionChange={changeSection} onDirtyChange={setEvidenceDirty} /> : <><nav className="fixed-editor-sections" aria-label="编辑区域">{sections.map(section => <button type="button" key={section.id} onClick={() => changeSection(section.id)}>{section.label}</button>)}</nav><p className="admin-panel">请先保存当前对象，再选择馆内原文。当前基本信息输入仍然保留。</p></>}</div> : null;
  if (objectType === "scholar" && form) {
    const publish = objectId && savedRecord ? <KnowledgePublishControl embedded objectType={objectType} objectId={objectId} savedRecord={savedRecord} dirty={dirty || evidenceDirty} onPublished={onPublished} onLockChange={setPublicationLocked} reviewHref={`/admin/preview/knowledge/${objectType}/${objectId}?${new URLSearchParams({review:"1",edit_version:savedVersion,return_to:`${pathname}?${searchParams}`})}`} /> : null;
    const renderedPreview = error ? <p role="alert">{error}。当前输入仍然保留。</p> : objectId && !payload ? <LoadingState role="status">正在核对已选馆藏与正式来源…</LoadingState> : <div onClickCapture={event => {if ((event.target as Element).closest("a")) event.preventDefault();}}><PreviewSurface payload={previewPayload} pageId="overview" /></div>;
    return withAssistant(<KnowledgePublicationContext value={{locked:publicationLocked,requestReview:()=>setActive("publication"),requestHistory:()=>setActive("versions")}}><ScholarEditorFrame composing={ime} canonical={objectId ? <ScholarCanonicalSections blocked={dirty||disabled||publicationLocked} section={selected} scholarId={objectId} data={payload ? live as unknown as PublicScholarDetail : null} error={error} reload={() => setPreviewRetry(value => value + 1)} /> : null} form={form} groups={groups} active={selected} changeSection={changeSection} dirty={dirty} disabled={disabled} locked={publicationLocked} saved={savedRecord} portrait={portrait} publication={publish} preview={renderedPreview} rail={rail} previewError={error ? <button type="button" onClick={() => setPreviewRetry(value => value + 1)}>重新核对预览</button> : null} extra={<>{selected === "passages" ? evidenceEditor : null}{selected === "versions" && objectId ? <section className="private-preview-label"><h2>完整版本记录</h2>{dirty || evidenceDirty || publicationLocked ? <p>请先保存当前填写，并核对未完成的发布操作。</p> : <Link href={`/admin/publication/knowledge/scholar/${objectId}?${new URLSearchParams({return_to:`${pathname}?${searchParams}`})}`}>查看原版本历史、撤回与恢复 →</Link>}</section> : null}</>} /></KnowledgePublicationContext>);
  }
  if (isNode && form) {
    const publish = objectId && savedRecord ? <KnowledgePublishControl embedded objectType={objectType} objectId={objectId} savedRecord={savedRecord} dirty={dirty || evidenceDirty || placementPending || relationGuard.dirty || relationGuard.pending} onPublished={onPublished} onLockChange={setPublicationLocked} reviewHref={`/admin/preview/knowledge/${objectType}/${objectId}?${new URLSearchParams({review:"1",edit_version:savedVersion,return_to:`${pathname}?${searchParams}`})}`} /> : null;
    const renderedPreview = error ? <p role="alert">{error}。当前输入仍然保留。<button type="button" onClick={() => setPreviewRetry(value => value + 1)}>重新核对</button></p> : objectId && !payload ? <LoadingState role="status">正在读取当前对象的页面预览…</LoadingState> : <div onClickCapture={event => { if ((event.target as Element).closest("a")) event.preventDefault(); }}><PreviewSurface payload={previewPayload} pageId="overview" /></div>;
    return withAssistant(<KnowledgePublicationContext value={{locked:publicationLocked || placementPending,requestReview:()=>changeSection("publication"),requestHistory:()=>changeSection("versions")}}><KnowledgeNodeEditorFrame previewData={error || objectId && !payload ? null : live as unknown as import("@/lib/api/knowledge.types").KnowledgeNodeDetail} relationBusy={relationGuard.dirty || relationGuard.pending} onRelationGuardChange={setRelationGuard} onRelationsChanged={()=>setPreviewRetry(value=>value+1)} composing={ime} form={form} groups={groups} active={selected} changeSection={changeSection} dirty={dirty} disabled={disabled || placementPending} locked={publicationLocked} saved={savedRecord} draft={draft} objectType={objectType} publication={publish} preview={renderedPreview} rail={rail} extra={<>{placementPending && !["usages", "materials", "impact", "versions"].includes(selected) ? <p role="status">原编排请求需要核对。<button type="button" onClick={() => setActive("usages")}>查看原编排操作</button></p> : null}<div hidden={!["usages", "materials", "impact", "versions"].includes(selected)}>{objectId ? <ConceptPlacementEditor onSectionChange={changeSection} summary={<KnowledgeNodeSummary draft={draft} objectType={objectType} onEdit={()=>changeSection("identity")}/>} key={`${owner}:${objectId}`} nodeId={objectId} objectType={objectType} mode={selected === "materials" ? "materials" : selected === "impact" ? "impact" : selected === "versions" ? "history" : "usages"} blocked={dirty || publicationLocked} onPendingChange={setPlacementPending} /> : <p>先保存主体草稿，再从馆内选择准确来源。</p>}</div>{selected === "passages" ? evidenceEditor : null}</>} /></KnowledgePublicationContext>);
  }
  if (objectType === "reading_path" && form) {
    const publish = objectId && savedRecord ? <KnowledgePublishControl embedded objectType={objectType} objectId={objectId} savedRecord={savedRecord} dirty={dirty} onPublished={onPublished} onLockChange={setPublicationLocked} reviewHref={`/admin/preview/knowledge/${objectType}/${objectId}?${new URLSearchParams({review:"1",edit_version:savedVersion,return_to:`${pathname}?${searchParams}`})}`} /> : null;
    const pathError = readingPathPreview?.error || error;
    const pathData = readingPathPreview ? readingPathPreview.data : live as unknown as PublicReadingPath;
    const pathPayload = { ...previewPayload, perspective: { ...previewPayload.perspective, data: pathData || live } };
    const rendered = pathError ? <p role="alert">{pathError}。当前输入仍然保留。<button type="button" onClick={()=>readingPathPreview ? readingPathPreview.retry() : setPreviewRetry(value=>value+1)}>重新核对</button></p> : (readingPathPreview ? readingPathPreview.loading : objectId && !payload) ? <LoadingState role="status">正在读取原路径及所选材料…</LoadingState> : <div onClickCapture={event=>{if((event.target as Element).closest("a"))event.preventDefault();}}><PreviewSurface payload={pathPayload} pageId="overview"/></div>;
    return withAssistant(<KnowledgePublicationContext value={{locked:publicationLocked,requestReview:()=>setActive("publication"),requestHistory:()=>setActive("versions")}}><PathEditorFrame candidates={readingPathCandidates} composing={ime} previewStatus={readingPathPreview} form={form} groups={groups} active={selected} changeSection={changeSection} dirty={dirty} disabled={disabled} locked={publicationLocked} saved={savedRecord} data={pathError ? null : pathData} preview={rendered} publication={publish} rail={rail} stageId={previewStageId} onSelect={onPreviewSelect}/></KnowledgePublicationContext>);
  }
  if (objectType === "topic" && form) {
    const publish = objectId && savedRecord ? <KnowledgePublishControl embedded objectType={objectType} objectId={objectId} savedRecord={savedRecord} dirty={dirty || evidenceDirty} onPublished={onPublished} onLockChange={setPublicationLocked} reviewHref={`/admin/preview/knowledge/${objectType}/${objectId}?${new URLSearchParams({review:"1",edit_version:savedVersion,return_to:`${pathname}?${searchParams}`})}`} /> : null;
    const rendered = error ? <p role="alert">{error}<button type="button" onClick={()=>setPreviewRetry(value=>value+1)}>重新核对预览</button></p> : objectId && !payload ? <LoadingState role="status">正在核对当前关联…</LoadingState> : <div onClickCapture={event=>{if((event.target as Element).closest("a"))event.preventDefault();}}><PreviewSurface payload={previewPayload} pageId="overview"/></div>;
    return withAssistant(<KnowledgePublicationContext value={{locked:publicationLocked,requestReview:()=>setActive("publication"),requestHistory:()=>setActive("versions")}}><TopicEditorFrame form={form} groups={groups} active={selected} changeSection={changeSection} dirty={dirty} disabled={disabled} locked={publicationLocked} saved={savedRecord} draft={draft} previewData={error || objectId && !payload ? null : live as unknown as PublicTopicDetail} publication={publish} preview={rendered} rail={rail} extra={selected === "passages" ? evidenceEditor : null}/></KnowledgePublicationContext>);
  }
  return withAssistant(<KnowledgePublicationContext value={{locked:publicationLocked,requestReview:()=>setActive("publication"),requestHistory:()=>setActive("versions")}}><div className="knowledge-visual-editor">{selected==="versions"&&objectId?<section className="private-preview-label"><strong>完整版本历史</strong>{dirty||evidenceDirty||publicationLocked?<p>请先保存当前填写并核对待处理操作，再进入版本历史。</p>:<Link className="button secondary" href={`/admin/publication/knowledge/${objectType}/${objectId}?${new URLSearchParams({return_to:`${pathname}?${searchParams}`})}`}>查看历史、撤回与恢复 →</Link>}</section>:null}{publicationLocked && selected !== "publication" ? <p role="status">发布记录正在核对，编辑暂时锁定。<button type="button" onClick={()=>setActive("publication")}>查看发布记录</button></p>:null}{objectType === "scholar" && selected === "network" ? <section className="private-preview-label"><strong>学术关系</strong><p>修改关系会同步到两位学者的页面。原有阅读关联保留。</p>{objectId ? <Link className="button secondary" href={`/admin/scholars/${objectId}/relations`}>进入学者关系图编辑</Link> : <p>请先保存学者草稿，再建立关系。</p>}</section> : null}{selected === "passages" && evidenceType ? evidenceEditor : <FixedPageEditor sections={sections} activeSection={selected} onSectionChange={changeSection} onPreviewSelect={onPreviewSelect} dirty={dirty} previewHref={objectId ? `/admin/preview/knowledge/${objectType}/${objectId}?page=${page}${savedVersion ? `&edit_version=${encodeURIComponent(savedVersion)}` : ""}` : undefined}
    fields={form ? cloneElement(form,{},<fieldset disabled={disabled || publicationLocked} style={{display:"contents"}}>{groups.map(({node,section},index) => <div key={index} hidden={section !== selected && !alwaysVisible(node)} data-field-section={section}>{node}</div>)}</fieldset>) : children}
    toolbar={error ? <button type="button" className="button secondary" onClick={() => setPreviewRetry(value => value + 1)}>重新核对预览</button> : null}
    preview={error ? <p className="form-message" role="alert">{error}。当前输入仍保留，本次选择尚未核对，请在左侧重新核对预览。</p> : objectId && !payload ? <p role="status">{objectType === "scholar" ? "正在核对本次选择的原文引语与阅读路径…" : "正在读取当前对象的页面预览…"}</p> : <div onClickCapture={event => {const target = event.target as HTMLElement; const row = target.closest<HTMLElement>("[data-edit-row]"); if (row) window.dispatchEvent(new CustomEvent("knowledge-row-select",{detail:Number(row.dataset.editRow)})); if (target.closest("a")) event.preventDefault();}}><PreviewSurface payload={previewPayload} pageId={page} previewStageId={previewStageId}/></div>}/> }
    <details className="knowledge-editor-support" hidden={!["publication","media","relations","versions"].includes(selected)} open><summary>{selected === "media" ? "选择图片" : selected === "relations" ? "管理共享关联" : "已保存草稿、发布与记录"}</summary>{objectId && savedRecord ? <div hidden={selected !== "publication"}><KnowledgePublishControl objectType={objectType} objectId={objectId} savedRecord={savedRecord} dirty={dirty||evidenceDirty} onPublished={onPublished} onLockChange={setPublicationLocked} reviewHref={`/admin/preview/knowledge/${objectType}/${objectId}?${new URLSearchParams({review:"1",edit_version:savedVersion,return_to:`${pathname}?${searchParams}`})}`}/></div>:null}<div inert={publicationLocked}>{rail}</div></details>
  </div></KnowledgePublicationContext>);
}
