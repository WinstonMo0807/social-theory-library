"use client";

import Link from "next/link";
import { normalizePublicResourceUrl } from "@/lib/api";
import { NodeRelations, type NodeRelationGuard } from "./node-relations";
import { cloneElement, useId, type FormHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { PreviewViewport } from "../curation/fixed-page-editor";
import type { KnowledgeNodeDetail } from "@/lib/api/knowledge.types";
import { MaterialAssistantEntry } from "../workflow/material-assistant";
import styles from "./concept-editor.module.css";

type Group = { node: ReactNode; section: string; persistent?: boolean };
const tabs = [
  { id: "identity", label: "基本信息" }, { id: "usages", label: "概念用法" },
  { id: "relations", label: "相关关系" }, { id: "materials", label: "关联材料" },
  { id: "impact", label: "受影响对象" }, { id: "versions", label: "历史记录" },
];
export const knowledgeNodeSections = [...tabs, { id: "preview", label: "页面预览" },
  { id: "passages", label: "原文策展" }, { id: "media", label: "页面图片" }, { id: "publication", label: "发布与状态" }];
export function knowledgeNodeSection(section: string) {
  if (["content", "questions", "history", "dimensions", "methods", "concepts", "learning", "curation", "sources", "paths"].includes(section)) return "identity";
  if (["network", "concept-map", "scholars"].includes(section)) return "relations";
  if (section === "works") return "materials";
  return section;
}

export function KnowledgeNodeEditorFrame({ previewData, composing=false, form, groups, active, changeSection, dirty, disabled, locked, saved, draft, objectType, publication, preview, rail, extra, onRelationsChanged, onRelationGuardChange, relationBusy=false }: {
  previewData?:KnowledgeNodeDetail|null; composing?: boolean; form: ReactElement<{ children: ReactNode }>; groups: Group[]; active: string; changeSection: (id: string) => void;
  dirty: boolean; disabled: boolean; locked: boolean; saved?: object | null; draft: object; objectType: string;
  publication: ReactNode; preview: ReactNode; rail: ReactNode; extra: ReactNode; onRelationsChanged?:()=>void; onRelationGuardChange?:(value:NodeRelationGuard)=>void; relationBusy?:boolean;
}) {
  const formId = useId(), record = (saved || {}) as { id?: string; cover_url?:string; created_at?:string; updated_at?: string; editorial_revision?: { status?: string }; status?: string };
  const input = draft as { canonical_name_zh?: string; canonical_name_en?: string; name?: string; summary?: string; parent?:string; preview_labels?:Record<string,string> };
  const scholars=previewData?.representative_scholars||[];
  const status = !saved ? "尚未建立草稿" : dirty ? "有未保存修改" : record.editorial_revision?.status === "draft" ? "已保存未发布" : record.status === "published" ? "当前版本已公开" : record.status === "archived" ? "已下线" : "已保存未公开";
  const editForm = cloneElement(form as ReactElement<FormHTMLAttributes<HTMLFormElement>>, { id: formId,
    onInvalidCapture: event => {
      const target = event.target as HTMLElement, group = target.closest<HTMLElement>("[data-field-section]");
      if (group) { event.preventDefault(); changeSection(knowledgeNodeSection(group.dataset.fieldSection || "identity")); requestAnimationFrame(() => { let parent=target.parentElement; while(parent){if(parent instanceof HTMLDetailsElement)parent.open=true;parent=parent.parentElement;} target.focus(); }); }
    },
  }, <fieldset disabled={disabled || locked || relationBusy} style={{ display: "contents" }}>{groups.map((group, index) =>
    <div key={index} data-field-section={group.section} hidden={!group.persistent && knowledgeNodeSection(group.section) !== active}>{group.node}</div>
  )}</fieldset>);
  return <section className={`${styles.workspace} ${styles.nodeForm}`} data-node-section={active} aria-label="理论与概念编辑">
    <header className={styles.nodeToolbar}><span className={styles.draftStatus}>{status}</span>{record.updated_at?<small>上次保存 · {new Date(record.updated_at).toLocaleString("zh-CN")}</small>:null}<div className={styles.nodeActions}>{dirty||!saved?<button type="submit" form={formId} disabled={disabled || locked || composing || relationBusy}>保存草稿</button>:null}<button type="button" onClick={() => changeSection("preview")}>预览</button><button type="button" className={styles.primary} onClick={() => changeSection("publication")}>发布</button></div></header>
    <section className={styles.nodeHero} aria-label="当前知识条目">{record.cover_url?<img className={styles.heroImage} src={normalizePublicResourceUrl(record.cover_url)} alt=""/>:null}<div>{input.parent&&input.preview_labels?.[input.parent]?<small>{input.preview_labels[input.parent]}</small>:null}<h2>{input.canonical_name_zh || input.name || "新的知识条目"}<span className={styles.typeLabel}>{{theory:"理论",concept:"概念",debate:"争论",research_problem:"研究问题"}[objectType]||"知识条目"}</span></h2>{input.canonical_name_en ? <p>{input.canonical_name_en}</p> : null}{input.summary?<p>{input.summary}</p>:null}</div>{record.created_at||record.updated_at?<dl className={styles.heroFacts}>{record.created_at?<><dt>创建时间</dt><dd>{new Date(record.created_at).toLocaleDateString("zh-CN")}</dd></>:null}{record.updated_at?<><dt>最近更新</dt><dd>{new Date(record.updated_at).toLocaleDateString("zh-CN")}</dd></>:null}</dl>:null}</section>
    <nav className={styles.nodeTabs} aria-label="理论与概念编辑栏目">{tabs.map(tab => <button key={tab.id} type="button" aria-current={tab.id === active ? "page" : undefined} onClick={() => changeSection(tab.id)}>{tab.label}</button>)}<label><span className="sr-only">其他编辑区域</span><select aria-label="其他编辑区域" value={tabs.some(tab => tab.id === active) ? "" : active} onChange={event => { if (event.target.value) changeSection(event.target.value); }}><option value="">更多</option>{knowledgeNodeSections.slice(tabs.length).map(tab => <option key={tab.id} value={tab.id}>{tab.label}</option>)}</select></label></nav>
    {locked && active !== "publication" ? <p role="status" className={styles.notice}>发布记录正在核对。<button type="button" onClick={() => changeSection("publication")}>查看原操作</button></p> : null}
    <div className={styles.identityLayout} data-identity={active==="identity"}>{active==="identity"?<aside className={styles.scholarIdentity}>{scholars.length?scholars.map(person=><article key={person.id}>{person.portrait_url?<img src={normalizePublicResourceUrl(person.portrait_url)} alt={person.name}/>:null}<small>学者</small><h3>{person.name}</h3>{person.birth_year!=null?<p>{person.birth_year} — {person.death_year??""}</p>:null}{person.scholar_slug?<Link href={`/scholars/${person.scholar_slug}`} target="_blank">查看学者页</Link>:null}</article>):<p>尚未关联代表学者</p>}<button type="button" onClick={()=>changeSection("relations")}>管理学者关系</button></aside>:null}{editForm}</div>
    {active==="identity"?<details className={styles.assistance}><summary>字段候选与材料助手</summary><MaterialAssistantEntry/></details>:null}
    {active === "relations" ? record.id ? <NodeRelations onGuardChange={onRelationGuardChange} nodeName={input.canonical_name_zh || input.name || "当前条目"} nodeId={record.id} blocked={dirty || disabled || locked} onChanged={onRelationsChanged}/> : <p>先保存当前条目，再建立正式关系。</p> : null}
    {extra}
    <div hidden={active !== "publication"}>{publication}</div>
    <div hidden={!["media", "relations", "versions"].includes(active)} inert={locked || relationBusy}>{rail}</div>
    {active === "versions" ? <section className={styles.panel}><h2>原版本与恢复记录</h2>{record.id && !dirty && !locked ? <Link href={`/admin/publication/knowledge/${objectType}/${record.id}`}>查看主体历史、影响、撤回与恢复 →</Link> : <p>保存当前填写并核对未完成操作后可查看历史。</p>}<p>原文编排的修订记录保留准确的来源标识。</p></section> : null}
    {active === "preview" ? <section className={styles.panel}><p>当前输入预览 · 公开内容以已发布版本为准</p><PreviewViewport>{preview}</PreviewViewport></section> : null}
    <footer className={styles.mobileActions}><span>{status}</span><button type="submit" form={formId} disabled={disabled || locked || composing || relationBusy}>保存</button><button type="button" onClick={() => changeSection("publication")}>发布</button></footer>
  </section>;
}
