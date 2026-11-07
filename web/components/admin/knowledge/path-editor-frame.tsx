"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { cloneElement, useId, useState, type ReactElement, type ReactNode, type FormHTMLAttributes } from "react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { PublicReadingPath } from "@/lib/api/reading-paths.types";
import { PreviewViewport } from "../curation/fixed-page-editor";
import type { PreviewSelection } from "../curation/fixed-page-editor";
import styles from "./path-editor.module.css";

export const pathEditorSections = [{id:"identity",label:"基本信息"},{id:"paths",label:"阶段编排"},{id:"dependencies",label:"先修关系"},{id:"candidates",label:"候选路线"},{id:"preview",label:"预览"},{id:"publication",label:"发布与状态"},{id:"versions",label:"历史版本"},{id:"media",label:"图片"}];
export const pathEditorSection=(id:string)=>["content","learning","curation","sources","relations"].includes(id)?"identity":id;

export function PathEditorFrame({ form,groups,active,changeSection,dirty,disabled,locked,saved,data,preview,publication,rail,onSelect,stageId,composing,previewStatus,candidates }: {
  form:ReactElement<{children:ReactNode}>;groups:{node:ReactNode;section:string;persistent?:boolean}[];active:string;changeSection:(id:string)=>void;
  dirty:boolean;disabled:boolean;locked:boolean;saved?:object|null;data:PublicReadingPath|null;preview:ReactNode;publication:ReactNode;rail:ReactNode;
  candidates?:ReactNode;onSelect?:(value:PreviewSelection)=>void;stageId?:string;composing?:boolean;previewStatus?:import("../curation/use-reading-path-preview").PathPreviewState;
}) {
  const fallbackId=useId(),formId=(form.props as FormHTMLAttributes<HTMLFormElement>).id||fallbackId;
  const [selectedId,setSelectedId]=useState(""),[detailTab,setDetailTab]=useState("reason");
  const row=(saved||{}) as {id?:string;status?:string;updated_at?:string;editorial_revision?:{status:string}};
  const selected=data?.items.find(item=>item.id===selectedId && (!stageId||item.stage_id===stageId))||data?.stages.find(stage=>stage.id===stageId)?.items[0]||data?.items[0];
  const status=dirty?"有未保存修改":!row.id?"尚未保存":row.editorial_revision?.status==="draft"?"已保存未发布":row.status==="published"?"当前版本已公开":"已保存未公开";
  const editSelected=()=>{if(!selected)return;changeSection("paths");onSelect?.({stageId:selected.stage_id,itemId:selected.id});requestAnimationFrame(()=>{const root=document.getElementById(formId),item=root?.querySelector<HTMLElement>(`[data-editor-item-id="${CSS.escape(selected.id)}"]`),details=item?.querySelector("details");if(details)details.open=true;item?.scrollIntoView({block:"center",behavior:"smooth"});item?.querySelector<HTMLElement>("input,textarea,select")?.focus();});};
  const edit=cloneElement(form as ReactElement<FormHTMLAttributes<HTMLFormElement>>,{id:formId,onSubmitCapture:event=>{if(composing)event.preventDefault();},onInvalidCapture:event=>{const target=event.target as HTMLElement,group=target.closest<HTMLElement>("[data-field-section]");if(group){event.preventDefault();changeSection(pathEditorSection(group.dataset.fieldSection||"identity"));const stage=target.closest<HTMLElement>("[data-editor-stage-id]"),item=target.closest<HTMLElement>("[data-editor-item-id]");if(stage)onSelect?.({stageId:stage.dataset.editorStageId||"",itemId:item?.dataset.editorItemId});requestAnimationFrame(()=>{let parent=target.parentElement;while(parent){if(parent instanceof HTMLDetailsElement)parent.open=true;parent=parent.parentElement;}target.focus();});}},onClickCapture:event=>{const target=(event.target as Element).closest<HTMLElement>("[data-preview-item-id]");if(target){setSelectedId(target.dataset.previewItemId||"");if(target.dataset.pathNavigation){changeSection("paths");const item=data?.items.find(row=>row.id===target.dataset.previewItemId);if(item){onSelect?.({stageId:item.stage_id,itemId:item.id});changeSection("paths");}}}}},
    <fieldset disabled={disabled||locked} style={{display:"contents"}}>{groups.map((group,index)=><div key={index} data-field-section={group.section} data-path-field-hidden={!group.persistent&&pathEditorSection(group.section)!==active}>{group.node}</div>)}</fieldset>);
  return <section className={styles.editor} data-section={active}>
    <header className={styles.header}><div><span>{status}</span>{row.updated_at?<small>上次保存 · {new Date(row.updated_at).toLocaleString("zh-CN")}</small>:null}</div><nav><button type="button" onClick={()=>changeSection("preview")}>预览</button><button className={styles.primary} type="submit" form={formId} disabled={disabled||locked}>保存</button></nav></header>
    <nav className={styles.tabs} aria-label="阅读路径编辑区域">{pathEditorSections.slice(0,5).map(section=><button key={section.id} type="button" aria-current={active===section.id?"page":undefined} onClick={()=>changeSection(section.id)}>{section.label}</button>)}<select aria-label="更多阅读路径操作" value={pathEditorSections.slice(5).some(section=>section.id===active)?active:""} onChange={event=>{if(event.target.value)changeSection(event.target.value);}}><option value="">更多</option>{pathEditorSections.slice(5).map(section=><option value={section.id} key={section.id}>{section.label}</option>)}</select></nav>
    <div className={styles.layout} data-full={active==="preview"||active==="publication"||active==="versions"||active==="candidates"}>
      <div className={styles.form}>{edit}<div hidden={active!=="publication"}>{publication}</div><div hidden={!["versions","media"].includes(active)} inert={locked}>{rail}</div>

        {active==="preview"?<PreviewViewport>{preview}</PreviewViewport>:null}
        {active==="versions"&&row.id?<p>{dirty||locked?"请先保存当前输入并核对未完成的操作。":<Link href={`/admin/publication/knowledge/reading_path/${row.id}`}>查看原路径版本、撤回与恢复 →</Link>}</p>:null}
        {locked&&active!=="publication"?<p role="status">正在核对发布记录。<button type="button" onClick={()=>changeSection("publication")}>查看原记录</button></p>:null}
      </div>
      <aside className={styles.detail} aria-label="所选阅读材料详情" hidden={["preview","publication","versions","candidates"].includes(active)}>
        <h2>条目详情</h2>{previewStatus?.error ? <p role="alert">{previewStatus.error}<button type="button" onClick={previewStatus.retry}>重新核对材料</button></p> : null}{data?<><div className={styles.materials}>{(selected?[selected]:[]).map(item=><button key={item.id} type="button" aria-current={selected?.id===item.id?"true":undefined} onClick={()=>{setSelectedId(item.id);onSelect?.({stageId:item.stage_id,itemId:item.id});}}>{item.cover_url?<img src={normalizePublicResourceUrl(item.cover_url)} alt=""/>:<span className={styles.placeholder}>暂无封面</span>}<span><strong>{item.title}</strong><small>{[item.authors.join("、"),item.publication_year,item.version_label].filter(Boolean).join(" · ")}</small><small>{item.is_required?"必读":"选读"}</small></span></button>)}</div>{selected?.href?<Link className={styles.catalogueLink} href={selected.href} target="_blank" rel="noopener noreferrer">查看馆藏信息 →</Link>:null}{selected?<>
          <nav className={styles.detailTabs} aria-label="材料详情">{[{id:"reason",label:"推荐理由"},{id:"learning",label:"阅读目标"},{id:"dependency",label:"先修依赖"},{id:"edition",label:"版本信息"}].map(tab=><button key={tab.id} type="button" aria-current={detailTab===tab.id?"true":undefined} onClick={()=>setDetailTab(tab.id)}>{tab.label}</button>)}</nav>
          {detailTab==="reason"?<><h3>在本路径中的作用 <button type="button" disabled={disabled||locked} onClick={editSelected}>编辑</button></h3><p>{selected.reason||"尚未填写推荐理由。"}</p></>:detailTab==="learning"?<><h3>阅读目标 <button type="button" disabled={disabled||locked} onClick={editSelected}>编辑</button></h3><p>{selected.learning_goal||"尚未填写阅读目标。"}</p><h3>阅读范围</h3><p>{selected.chapter_title||"整部材料"}{selected.page_start?` · PDF ${selected.page_start}${selected.page_end?`–${selected.page_end}`:""} 页`:""}</p></>:detailTab==="dependency"?<><p>{selected.prerequisite||"尚未填写文字先修说明。"}</p><ul>{selected.dependencies?.map(relation=><li key={`${relation.item_id}:${relation.kind}`}>{relation.kind==="learning_order"?"学习顺序":"理论相关"} · {data.items.find(item=>item.id===relation.item_id)?.title||"原材料"}<p>{relation.reason}</p></li>)}</ul>{!selected.dependencies?.length?<p>无已记录的先修依赖。</p>:null}</>:<><p>{selected.version_label||"版本尚未明确"}</p><p>{selected.source_notice}</p>{selected.href?<Link href={selected.href} target="_blank" rel="noopener noreferrer">查看馆藏信息 →</Link>:<p>材料当前不可公开访问，请检查原馆藏或知识条目的发布状态。</p>}</>}
        </>:<p>从馆藏选择材料后，才能查看条目详情。</p>}</>:<LoadingState>正在核对当前选择；未选材料与无公开来源会保留空态。</LoadingState>}</aside>
    </div>
    <div className={styles.candidateSection} hidden={!["identity","paths","candidates"].includes(active)} inert={locked}>{candidates}</div>
    <footer className={styles.mobile}><span>{status}</span><button type="button" onClick={()=>changeSection("preview")}>预览</button><button type="submit" form={formId} disabled={disabled||locked}>保存</button></footer>
  </section>;
}
