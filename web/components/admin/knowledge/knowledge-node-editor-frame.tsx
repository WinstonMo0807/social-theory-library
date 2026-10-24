"use client";

import Link from "next/link";
import { NodeRelations } from "./node-relations";
import { cloneElement, useId, type FormHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { PreviewViewport } from "../curation/fixed-page-editor";
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

export function KnowledgeNodeEditorFrame({ composing=false, form, groups, active, changeSection, dirty, disabled, locked, saved, draft, objectType, publication, preview, rail, extra, onRelationsChanged }: {
  composing?: boolean; form: ReactElement<{ children: ReactNode }>; groups: Group[]; active: string; changeSection: (id: string) => void;
  dirty: boolean; disabled: boolean; locked: boolean; saved?: object | null; draft: object; objectType: string;
  publication: ReactNode; preview: ReactNode; rail: ReactNode; extra: ReactNode; onRelationsChanged?:()=>void;
}) {
  const formId = useId(), record = (saved || {}) as { id?: string; updated_at?: string; editorial_revision?: { status?: string }; status?: string };
  const input = draft as { canonical_name_zh?: string; canonical_name_en?: string; name?: string; summary?: string };
  const status = !saved ? "尚未建立草稿" : dirty ? "有未保存修改" : record.editorial_revision?.status === "draft" ? "已保存未发布" : record.status === "published" ? "当前版本已公开" : record.status === "archived" ? "已下线" : "已保存未公开";
  const editForm = cloneElement(form as ReactElement<FormHTMLAttributes<HTMLFormElement>>, { id: formId,
    onInvalidCapture: event => {
      const target = event.target as HTMLElement, group = target.closest<HTMLElement>("[data-field-section]");
      if (group) { event.preventDefault(); changeSection(knowledgeNodeSection(group.dataset.fieldSection || "identity")); requestAnimationFrame(() => target.focus()); }
    },
  }, <fieldset disabled={disabled || locked} style={{ display: "contents" }}>{groups.map((group, index) =>
    <div key={index} data-field-section={group.section} hidden={!group.persistent && knowledgeNodeSection(group.section) !== active}>{group.node}</div>
  )}</fieldset>);
  return <section className={`${styles.workspace} ${styles.nodeForm}`} aria-label="理论与概念编辑">
    <header className={styles.nodeHero}><div><h2>{input.canonical_name_zh || input.name || "新的知识条目"}</h2>{input.canonical_name_en ? <p>{input.canonical_name_en}</p> : null}<p>{status}{record.updated_at ? ` · 上次保存 ${new Date(record.updated_at).toLocaleString("zh-CN")}` : ""}</p></div><div className={styles.nodeActions}><button type="submit" form={formId} disabled={disabled || locked || composing}>保存草稿</button><button type="button" onClick={() => changeSection("preview")}>预览</button><button type="button" className={styles.primary} onClick={() => changeSection("publication")}>发布</button></div></header>
    <nav className={styles.nodeTabs} aria-label="理论与概念编辑栏目">{tabs.map(tab => <button key={tab.id} type="button" aria-current={tab.id === active ? "page" : undefined} onClick={() => changeSection(tab.id)}>{tab.label}</button>)}<label><span className="sr-only">其他编辑区域</span><select aria-label="其他编辑区域" value={tabs.some(tab => tab.id === active) ? "" : active} onChange={event => { if (event.target.value) changeSection(event.target.value); }}><option value="">更多</option>{knowledgeNodeSections.slice(tabs.length).map(tab => <option key={tab.id} value={tab.id}>{tab.label}</option>)}</select></label></nav>
    {locked && active !== "publication" ? <p role="status" className={styles.notice}>发布记录正在核对。<button type="button" onClick={() => changeSection("publication")}>查看原操作</button></p> : null}
    {editForm}
    {active === "relations" ? record.id ? <NodeRelations nodeId={record.id} blocked={dirty || disabled || locked} onChanged={onRelationsChanged}/> : <p>先保存当前条目，再建立正式关系。</p> : null}
    {extra}
    <div hidden={active !== "publication"}>{publication}</div>
    <div hidden={!["media", "relations", "versions"].includes(active)} inert={locked}>{rail}</div>
    {active === "versions" ? <section className={styles.panel}><h2>原版本与恢复记录</h2>{record.id && !dirty && !locked ? <Link href={`/admin/publication/knowledge/${objectType}/${record.id}`}>查看主体历史、影响、撤回与恢复 →</Link> : <p>保存当前填写并核对未完成操作后可查看历史。</p>}<p>原文编排的修订记录保留准确的来源标识。</p></section> : null}
    {active === "preview" ? <section className={styles.panel}><p>当前输入预览 · 公开内容以已发布版本为准</p><PreviewViewport>{preview}</PreviewViewport></section> : null}
    <footer className={styles.mobileActions}><span>{status}</span><button type="submit" form={formId} disabled={disabled || locked || composing}>保存</button><button type="button" onClick={() => changeSection("publication")}>发布</button></footer>
  </section>;
}
