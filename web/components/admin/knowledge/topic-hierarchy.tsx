"use client";

import { confirmAction } from "@/lib/ui-dialog";


import { LoadingState } from "@/components/ui/loading-state";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import type { components } from "@/lib/api/generated/schema";
import { topicCuration, type TopicCurationFields } from "./topic-fields";
import { TopicTreeBranch } from "./topic-organization";
import styles from "./topic-editor.module.css";

type Parent = { id: string; name: string };
type Impact = components["schemas"]["TopicOrganizationPreview"];

function HierarchyProposal({ topicId, name, value, onApply, onClose }: {
  topicId: string | null; name: string; value: TopicCurationFields;
  onApply: (parent: Parent | null) => void; onClose: () => void;
}) {
  const owner = String(useAdminSession()?.id || "");
  const [baseParent] = useState(value.parentId);
  const [parent, setParent] = useState<Parent | null>(value.parentId ? { id: value.parentId, name: value.preview_labels[value.parentId] || "原上级主题" } : null);
  const [input, setInput] = useState(""), [query, setQuery] = useState(""), [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; data?: Impact; error?: string } | null>(null);
  const body = JSON.stringify({ parent: parent?.id || null, curation: topicCuration(value) });
  const key = `${owner}:${topicId}:${body}:${attempt}`, result = state?.key === key ? state : null;
  const changed = baseParent !== value.parentId, dirty = (parent?.id || "") !== baseParent;
  useUnsavedForm(dirty, false);
  useEffect(() => {
    if (!topicId || !owner) return;
    const controller = new AbortController(), signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
    const timer = window.setTimeout(() => {
      void withPrivateOwner(owner, () => apiRequest<Impact>(`/catalog/admin/topics/${topicId}/organization-preview/`, {
        method: "POST", body, signal, cache: "no-store", headers: { "X-Editor-Owner": owner },
      }, getServerSessionCredential(), false), signal).then(data => {
        if (data.topic_id !== topicId || String(data.parent_id || "") !== String(parent?.id || "")) throw Error("调整预览对象不一致，请重新核对。");
        if (!controller.signal.aborted) setState({ key, data });
      }).catch(reason => {
        if (!controller.signal.aborted) setState({ key, error: reason instanceof Error ? reason.message : "暂时无法核对层级。" });
      });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [topicId, owner, body, key, parent?.id]);
  async function close() { if (!dirty || (await confirmAction("放弃这次尚未应用的层级选择？"))) onClose(); }
  return <Dialog open data-editor-transient className={styles.hierarchyDialog} onRequestClose={close} aria-label="调整主题层级">
    <header><h2>调整层级</h2><button type="button" onClick={close} aria-label="关闭层级调整">关闭</button></header>
    <p>当前主题 <strong>{name || "未命名主题"}</strong></p>
    <div className={styles.parentSelection}><div><span>新的上级主题</span><strong>{parent?.name || "无上级 · 一级主题"}</strong></div>
      {parent ? <button type="button" onClick={() => setParent(null)}>改为一级主题</button> : null}</div>
    <details className={styles.parentChoices}><summary>选择其他上级</summary>
      <div className={styles.treeSearch}><input value={input} maxLength={240} aria-label="查找上级主题" placeholder="搜索名称或别名" onChange={event => setInput(event.target.value)} onKeyDown={event => {
        if (event.key === "Enter" && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); setQuery(input.trim()); }
      }} /><button type="button" onClick={() => setQuery(input.trim())}>查找</button></div>
      <TopicTreeBranch key={`${owner}:${query}`} owner={owner} selected={parent?.id} query={query} onChoose={setParent} />
    </details>
    {changed ? <p role="alert">原表单的上级已变化，请取消后重新打开，避免覆盖更新。</p> : null}
    {topicId ? result?.error ? <p role="alert">{result.error}<button type="button" onClick={() => setAttempt(value => value + 1)}>重新核对</button></p>
      : !result?.data ? <LoadingState role="status">正在核对本次调整的影响…</LoadingState> : <section className={styles.hierarchyImpact} aria-live="polite">
        {result.data.problems.map((problem, index) => <p role="alert" key={index}>{String(problem.detail || "层级需要核对。")}</p>)}
        {result.data.cycle_path.length ? <p className={styles.cyclePath}>形成循环：{result.data.cycle_path.map(row => row.id === topicId ? name || row.name : row.name).join(" → ")}</p>
          : <p>上级链：{result.data.parent_path.map(row => row.id === topicId ? name || row.name : row.name).join(" → ")}</p>}
        <h3>影响范围</h3><p>涉及 {result.data.descendant_count} 个后代主题，其中 {result.data.public_descendant_count} 个已公开。原主题和关联材料保留。</p>
        <p>当前关联 {result.data.content_counts.works} 部公开作品、{result.data.content_counts.scholars} 位学者、{result.data.content_counts.knowledge} 个知识条目、{result.data.content_counts.articles} 篇策划。</p>
        {!result.data.can_publish && !result.data.problems.length ? <p>关联内容尚未满足发布要求；可先保存层级草稿。</p> : null}
      </section> : <p>新主题尚未保存，没有后代主题。保存时会核对所选上级是否仍可用。</p>}
    <footer><p>确认只更新当前表单，保存与发布后才改变读者入口。</p><div><button type="button" onClick={close}>取消</button>
      <button type="button" className={styles.primary} disabled={!owner || changed || Boolean(topicId && (!result?.data || result.data.problems.length))}
        onClick={() => { onApply(parent); onClose(); }}>确认调整</button></div></footer>
  </Dialog>;
}

export function TopicHierarchy({ topicId, name, value, onChange }: {
  topicId: string | null; name: string; value: TopicCurationFields; onChange: (patch: Partial<TopicCurationFields>) => void;
}) {
  const [open, setOpen] = useState(false), owner = String(useAdminSession()?.id || "");
  return <section className={styles.hierarchyField}><div><span>上级主题</span><strong>{value.parentId ? value.preview_labels[value.parentId] || "已保存的上级主题" : "无上级 · 一级主题"}</strong></div>
    <button type="button" onClick={() => setOpen(true)}>调整层级</button>
    {open ? <HierarchyProposal key={`${owner}:${topicId}`} topicId={topicId} name={name} value={value} onClose={() => setOpen(false)} onApply={parent => {
      if ((parent?.id || "") !== value.parentId) onChange({ parentId: parent?.id || "", preview_labels: { ...value.preview_labels, ...(parent ? { [parent.id]: parent.name } : {}) } });
    }} /> : null}
  </section>;
}
