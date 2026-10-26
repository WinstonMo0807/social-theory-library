"use client";

import Link from "next/link";
import { cloneElement, isValidElement, useId, useState, type FormHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { PreviewViewport } from "../curation/fixed-page-editor";
import styles from "./scholar-editor.module.css";

type Group = { node: ReactNode; section: string; persistent?: boolean };
const tabs = [{ id: "identity", label: "基本信息" }, { id: "works", label: "代表作品" }, { id: "theory", label: "理论与关系" }, { id: "timeline", label: "时间线" }, { id: "paths", label: "推荐阅读" }, { id: "preview", label: "页面预览" }];
export const scholarEditorSections = [...tabs, { id: "passages", label: "原文策展" }, { id: "publication", label: "发布与状态" }, { id: "versions", label: "版本记录" }];
export function scholarEditorSection(section: string) {
  if (["concepts", "concept-map", "network", "relations"].includes(section)) return "theory";
  if (["biography", "sources", "media"].includes(section) || section.startsWith("identity")) return "identity";
  return section;
}
export function ScholarEditorFrame({ composing=false, form, groups, active, changeSection, dirty, disabled, locked, saved, portrait, publication, preview, previewError, rail, extra, canonical }: {
  composing?: boolean; form: ReactElement<{ children: ReactNode }>; groups: Group[]; active: string; changeSection: (id: string) => void;
  dirty: boolean; disabled: boolean; locked: boolean; saved?: object | null; portrait?: ReactNode; publication: ReactNode;
  preview: ReactNode; previewError?: ReactNode; rail: ReactNode; extra?: ReactNode; canonical?: ReactNode;
}) {
  const formId = useId(), [copyStatus, setCopyStatus] = useState("");
  const record = (saved || {}) as { public_eligible?: boolean; slug?: string; updated_at?: string; editorial_revision?: { status?: string } };
  const status = dirty ? "草稿有未保存修改" : record.editorial_revision?.status === "draft" || !record.public_eligible ? "已保存未发布" : "当前版本已公开";
  const publicPath = record.public_eligible && record.slug ? `/scholars/${encodeURIComponent(record.slug)}` : "";
  function field(group: Group, index: number) {
    const node = group.node, props = isValidElement<{ type?: string; className?: string; role?: string }>(node) ? node.props : {};
    if (props.type === "submit") return null;
    const persistent = ["status", "alert"].includes(props.role || "") || props.className?.includes("form-message");
    return <div key={index} className={styles.field} data-field-section={group.section} hidden={!persistent && scholarEditorSection(group.section) !== active}>{node}</div>;
  }
  const identity = groups.filter(group => group.section.startsWith("identity-"));
  const workFields = groups.filter(group => group.section === "works");
  const mainFields = groups.filter(group => !group.section.startsWith("identity-") && group.section !== "works" && group.section !== "assistance" && !group.persistent && group.section !== "feedback");
  const title = tabs.find(tab => tab.id === active)?.label;
  const editForm = cloneElement(form as ReactElement<FormHTMLAttributes<HTMLFormElement>>, { id: formId,
    onInvalidCapture: event => { const target = event.target as HTMLElement, group = target.closest<HTMLElement>("[data-field-section]"); if (group) { event.preventDefault(); changeSection(scholarEditorSection(group.dataset.fieldSection || "identity")); requestAnimationFrame(() => target.focus()); } },
  }, <fieldset disabled={disabled || locked} style={{ display: "contents" }}>
    <div hidden={active !== "identity"}><h2>一、基本信息</h2><div className={styles.identity}><div className={styles.portrait}>{portrait || <p>保存草稿后可选择肖像。</p>}</div><div className={styles.identityFields}>{identity.map(field)}</div></div></div>
    {mainFields.filter(group => group.section === "biography").map(field)}{mainFields.filter(group => group.section !== "biography" && !["theory", "timeline"].includes(scholarEditorSection(group.section))).map(field)}
    <details className={styles.support} hidden={!["theory", "timeline"].includes(active)}><summary>历史编排记录与原编辑入口</summary><p>保留已有记录供核对；自由文字不会自动成为正式关系或事件。</p>{mainFields.filter(group => ["theory", "timeline"].includes(scholarEditorSection(group.section))).map(field)}</details>
    <details className={styles.support} hidden={active !== "identity"}><summary>候选资料与编辑辅助</summary>{groups.filter(group => group.section === "assistance").map((group, index) => <div key={index}>{group.node}</div>)}</details>
  </fieldset>);
  return <section className={styles.editor} data-section={active} aria-label="学者公开页编辑">
    <header className={styles.header}><div><p><span className={styles.status}>{saved ? status : "尚未建立草稿"}</span></p>{record.updated_at ? <p>上次保存 · {new Date(record.updated_at).toLocaleString("zh-CN")}</p> : null}</div><div className={styles.actions}>{dirty||!saved?<button type="submit" form={formId} disabled={disabled || locked || composing}>保存草稿</button>:null}<button type="button" disabled={composing} onClick={() => changeSection("preview")}>预览</button><button type="button" className={styles.primary} onClick={() => changeSection("publication")}>发布</button></div></header>
    <nav className={styles.tabs} aria-label="学者编辑栏目">{tabs.map(tab => <button type="button" key={tab.id} aria-current={active === tab.id ? "page" : undefined} onClick={() => changeSection(tab.id)}>{tab.label}</button>)}<label><span>更多</span><select value={tabs.slice(0,3).some(tab => tab.id === active) ? "" : active} onChange={event => { if (event.target.value) changeSection(event.target.value); }}><option value="">编辑工具</option>{scholarEditorSections.slice(3).map(tab => <option key={tab.id} value={tab.id}>{tab.label}</option>)}</select></label></nav>
    {groups.filter(group => group.persistent || group.section === "feedback").filter(group => !(isValidElement<{type?:string}>(group.node) && group.node.props.type === "submit")).map((group, index) => <div key={index}>{group.node}</div>)}
    <div className={styles.layout}><div className={styles.main} hidden={["preview", "passages", "versions", "works"].includes(active)}>{active !== "identity" && active !== "works" && title ? <h2>{title}</h2> : null}{canonical}{editForm}</div>
      <aside className={styles.aside}>
        <section className={styles.statusCard} hidden={!["identity","publication"].includes(active)&&!locked}><h2>页面状态</h2><strong className={styles.status}>{saved ? status : "尚未保存"}</strong><p>{record.public_eligible ? "读者继续看到已公开版本，草稿须经核对后另行发布。" : "当前资料用于编辑，完成来源与身份核对后可发布。"}</p>{publicPath ? <div className={styles.publicLink}><Link href={publicPath} target="_blank" rel="noopener">{publicPath}</Link><button type="button" onClick={() => void navigator.clipboard.writeText(new URL(publicPath, location.origin).href).then(() => setCopyStatus("页面链接已复制。"), () => setCopyStatus("未能复制，请从页面链接手动复制。"))}>复制</button></div> : <p>公开链接将在正式发布后显示。</p>}{copyStatus ? <p role="status">{copyStatus}</p> : null}
          <div hidden={active !== "publication" && !locked}>{publication}</div>{active !== "publication" && !locked ? <button type="button" onClick={() => changeSection("publication")}>发布</button> : null}{!saved ? <p>请先保存学者草稿。</p> : null}
        </section>
        <fieldset disabled={disabled || locked} style={{ border: 0, padding: 0, margin: 0 }} hidden={active !== "identity" && active !== "works"}>{workFields.map((group, index) => <div key={index}>{group.node}</div>)}</fieldset>
        <div hidden={!["publication", "theory", "versions"].includes(active)} inert={locked}><details className={styles.support}><summary>原资料、关联与操作记录</summary>{rail}</details></div>
      </aside>
      {active === "preview" ? <section className={styles.preview}><p>当前输入预览 · 保存与发布相互独立</p>{previewError}<PreviewViewport>{preview}</PreviewViewport></section> : null}
      {extra}
    </div><footer className={styles.mobileActions}><span className={styles.status}>{dirty ? "草稿有变化" : saved ? "已保存" : "未保存"}</span>{dirty||!saved?<button type="submit" form={formId} disabled={disabled||locked||composing}>保存</button>:null}<button type="button" onClick={() => changeSection("preview")}>预览</button><button type="button" className={styles.primary} onClick={() => changeSection("publication")}>发布</button></footer>
  </section>;
}
