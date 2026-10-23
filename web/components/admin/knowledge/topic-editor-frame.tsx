"use client";

import Link from "next/link";
import { cloneElement, useId, useState, type ReactNode, type ReactElement, type FormHTMLAttributes } from "react";
import { normalizePublicResourceUrl } from "@/lib/api";
import type { PublicTopicDetail } from "@/lib/api/topics.types";
import { PreviewViewport } from "../curation/fixed-page-editor";
import { TopicOrganizationTree } from "./topic-organization";
import styles from "./topic-editor.module.css";

const contentTabs = [{id:"works",label:"关联作品"},{id:"scholars",label:"关联学者"},{id:"concepts",label:"关联知识"},{id:"articles",label:"关联策划"},{id:"questions",label:"问题与争论"},{id:"paths",label:"阅读路径"}];
export const topicEditorSections = [{id:"identity",label:"基本信息"},...contentTabs,{id:"preview",label:"目录预览"},{id:"versions",label:"历史版本"},{id:"publication",label:"发布与状态"},{id:"passages",label:"原文策展"},{id:"media",label:"图片与关联"}];
export function topicEditorSection(section:string) {return ["history","dimensions","methods","timeline","sources","curation","content","relations"].includes(section)?"identity":section;}
export function TopicEditorFrame({form,groups,active,changeSection,dirty,disabled,locked,saved,draft,previewData,publication,preview,rail,extra}: {
  form:ReactElement<{children:ReactNode}>;groups:{node:ReactNode;section:string;persistent?:boolean}[];active:string;changeSection:(id:string)=>void;
  dirty:boolean;disabled:boolean;locked:boolean;saved?:object|null;draft:object;previewData:PublicTopicDetail|null;
  publication:ReactNode;preview:ReactNode;rail:ReactNode;extra:ReactNode;
}) {
  const formId=useId(),[detail,setDetail]=useState(false),row=(saved||{}) as {id?:string;editorial_status?:string;editorial_revision?:{status?:string};updated_at?:string},input=draft as {name?:string;description?:string};
  const status=dirty?"有未保存修改":!saved?"尚未保存":row.editorial_revision?.status === "draft"?"已保存未发布":row.editorial_status === "published"?"当前版本已公开":"已保存未公开";
  const content=contentTabs.some(tab=>tab.id===active),main=content?"related":active;
  const editForm=cloneElement(form as ReactElement<FormHTMLAttributes<HTMLFormElement>>,{id:formId,onInvalidCapture:event=>{const target=event.target as HTMLElement,field=target.closest<HTMLElement>("[data-field-section]");if(field){event.preventDefault();changeSection(topicEditorSection(field.dataset.fieldSection||"identity"));setDetail(true);requestAnimationFrame(()=>target.focus());}}},<fieldset disabled={disabled||locked} style={{display:"contents"}}>{groups.map((group,index)=>{const advanced=["history","dimensions","methods","timeline","curation","sources"].includes(group.section);return <div key={index} data-field-section={group.section} hidden={!group.persistent&&(topicEditorSection(group.section)!==active || advanced&&!detail)}>{group.node}</div>;})}</fieldset>);
  return <section className={styles.editor}><header className={styles.header}><div><span>{status}</span>{row.updated_at?<small>上次保存 · {new Date(row.updated_at).toLocaleString("zh-CN")}</small>:null}</div><nav><button type="submit" form={formId} disabled={disabled||locked}>保存草稿</button><button type="button" onClick={()=>changeSection("preview")}>预览</button><button type="button" className={styles.primary} onClick={()=>changeSection("publication")}>发布</button></nav></header>
    <div className={styles.columns}><TopicOrganizationTree selected={row.id}/><div className={styles.form}><nav className={styles.tabs} aria-label="主题编辑区域">{[{id:"identity",label:"基本信息"},{id:"related",label:"关联内容"},{id:"preview",label:"目录预览"},{id:"versions",label:"历史版本"}].map(tab=><button type="button" key={tab.id} aria-current={main===tab.id?"page":undefined} onClick={()=>changeSection(tab.id==="related"?"works":tab.id)}>{tab.label}</button>)}<select aria-label="更多主题编辑区域" value={["publication","passages","media"].includes(active)?active:""} onChange={event=>{if(event.target.value)changeSection(event.target.value);}}><option value="">更多</option><option value="publication">发布与状态</option><option value="passages">原文策展</option><option value="media">图片与关联</option></select></nav>
      {content?<nav className={styles.contentTabs} aria-label="关联内容类型">{contentTabs.map(tab=><button key={tab.id} type="button" aria-current={active===tab.id?"page":undefined} onClick={()=>changeSection(tab.id)}>{tab.label}</button>)}</nav>:null}
      {active==="identity"?<button type="button" className={styles.disclosure} aria-expanded={detail} onClick={()=>setDetail(value=>!value)}>{detail?"收起详细导读与原记录":"展开详细导读与原记录"}</button>:null}
      {editForm}<div hidden={active!=="publication"}>{publication}</div>{extra}<div hidden={!["media","versions"].includes(active)} inert={locked}>{rail}</div>
      {active==="versions"&&row.id?<p>{dirty||locked?"保存当前输入并核对原操作后，可以读取历史。":<Link href={`/admin/publication/knowledge/topic/${row.id}`}>查看原主题版本、撤回与恢复 →</Link>}</p>:null}
      {active==="preview"?<PreviewViewport>{preview}</PreviewViewport>:null}
      {locked&&active!=="publication"?<p role="status">发布操作正在核对。<button type="button" onClick={()=>changeSection("publication")}>查看原记录</button></p>:null}
    </div><aside className={styles.preview} aria-label="主题页面预览"><header><strong>页面预览</strong><button type="button" onClick={()=>changeSection("preview")}>完整预览 ↗</button></header>{previewData?<><h2>{input.name||"尚未填写主题名称"}</h2><p>{input.description||"尚未填写导读"}</p><h3>代表作品</h3><div className={styles.coverGrid}>{previewData.works.results.slice(0,3).map(work=><article key={work.edition_id||work.id}>{work.cover_url?<img src={normalizePublicResourceUrl(work.cover_url)} alt=""/>:<span className={styles.placeholder}>暂无封面</span>}<strong>{work.title}</strong></article>)}</div>{!previewData.works.results.length?<p>尚无可公开作品。</p>:null}<h3>代表学者</h3><div className={styles.coverGrid}>{previewData.scholars.results.slice(0,3).map(scholar=><article key={scholar.id}>{scholar.person.portrait?<img src={normalizePublicResourceUrl(scholar.person.portrait)} alt=""/>:<span className={styles.placeholder}>暂无肖像</span>}<strong>{scholar.person.preferred_name}</strong></article>)}</div><h3>相关策划</h3>{previewData.articles.results.slice(0,3).map(article=><p key={article.id}>{article.title}</p>)}{!previewData.articles.results.length?<p>尚无可公开策划。</p>:null}</>:<p>正在读取当前内容预览。未核对的关联不会伪装为可公开内容。</p>}</aside></div>
    <footer className={styles.mobile}><span>{status}</span><button type="button" onClick={()=>changeSection("preview")}>预览</button><button type="button" className={styles.primary} onClick={()=>changeSection("publication")}>发布</button></footer>
  </section>;
}
