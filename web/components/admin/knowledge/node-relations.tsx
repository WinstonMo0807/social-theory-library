"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import type { components } from "@/lib/api/generated/schema";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { ScholarNodeLinkEditor } from "./scholar-links";
import shared from "./scholar-editor.module.css";
import styles from "./node-relations.module.css";

const Editor = dynamic(() => import("@/components/theory-system-admin").then(module => module.NodeRelationEditor), { loading: () => <p role="status">正在打开原关系编辑器…</p> });
type Page = components["schemas"]["NodeRelationPage"];
type Row = Page["results"][number];
export type NodeRelationGuard = { dirty: boolean; pending: boolean; composing: boolean };
type Props = { nodeId: string; nodeName: string; blocked: boolean; onChanged?: () => void; onGuardChange?: (value: NodeRelationGuard) => void };
type Selection = { kind: "node" | "person" | "choose"; id: string; scholarId?: string; personName?: string };
const statuses: Record<string, string> = { published: "已确认公开", draft: "草稿", pending: "待确认", rejected: "不采用", archived: "已下线" };
const clearGuard: NodeRelationGuard = { dirty: false, pending: false, composing: false };

export function NodeRelations(props: Props) {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return user ? <RelationList key={`${user.id}:${epoch}:${props.nodeId}`} {...props} owner={String(user.id)} /> : <p role="status">正在核对编辑账户…</p>;
}

function RelationList({ nodeId, nodeName, blocked, onChanged, onGuardChange, owner }: Props & { owner: string }) {
  const user = useAdminSession(), canCreate = hasAdminCapability(user, "can_create_authority");
  const [page, setPage] = useState(1), [attempt, setAttempt] = useState(0), [data, setData] = useState<Page | null>(null), [error, setError] = useState("");
  const [relationTypes, setRelationTypes] = useState<Page["relation_types"]>([]);
  const [filters, setFilters] = useState({ status: "", kind: "", relation_type: "", direction: "", q: "" }), [query, setQuery] = useState("");
  const [selection, setSelection] = useState<Selection | null>(null), [notice, setNotice] = useState("");
  const guard = useRef(clearGuard), ime = useRef(false), detail = useRef<HTMLElement>(null), createButton = useRef<HTMLButtonElement>(null);
  const guardCallback = useRef(onGuardChange);
  useEffect(() => { guardCallback.current = onGuardChange; }, [onGuardChange]);
  useEffect(() => () => guardCallback.current?.(clearGuard), []);
  function updateGuard(value: NodeRelationGuard) { guard.current = value; onGuardChange?.(value); }
  useEffect(() => {
    const controller = new AbortController(), signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
    queueMicrotask(() => { if (!controller.signal.aborted) { setData(null); setError(""); } });
    withPrivateOwner(owner, () => apiRequest<Page>(`/catalog/admin/theory-system/nodes/${nodeId}/relations/?${new URLSearchParams({ ...filters, page: String(page) })}`, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal)
      .then(value => { if (!controller.signal.aborted) { setData(value); setRelationTypes(value.relation_types); } }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "关系读取失败。"); });
    return () => controller.abort();
  }, [owner, nodeId, page, filters, attempt]);
  function canLeave() {
    if (ime.current || guard.current.composing) return false;
    if (guard.current.pending) { setNotice("请先查回原请求，或停止未执行的请求，再切换关系。"); return false; }
    return !guard.current.dirty || window.confirm("关系还有未保存输入，放弃这些输入并切换吗？");
  }
  function open(value: Selection) {
    if (blocked || !canLeave()) return;
    updateGuard(clearGuard); setNotice(""); setSelection(value);
    requestAnimationFrame(() => detail.current?.focus());
  }
  function selectRow(row: Row) {
    if (row.kind === "person" && !row.scholar_id) return;
    if (selection?.kind === row.kind && selection.id === row.id) { detail.current?.focus(); return; }
    open({ kind: row.kind, id: row.id, scholarId: row.scholar_id || undefined, personName: row.source_kind === "人物" ? row.source_name : row.target_name });
  }
  function close() {
    if (!canLeave()) return;
    updateGuard(clearGuard); setSelection(null); setNotice(""); setAttempt(value => value + 1); onChanged?.(); createButton.current?.focus();
  }
  function filter(field: keyof typeof filters, value: string) { setFilters(current => ({ ...current, [field]: value })); setPage(1); }
  return <section className={`${shared.canonical} ${styles.workspace}`} aria-label="理论与人物关系" onCompositionStartCapture={() => { ime.current = true; }} onCompositionEndCapture={() => { ime.current = false; }}>
    <header><div><h2>关系类型、方向与来源 <small>{data?.count ?? "…"}</small></h2><p>核对人物、概念与理论之间的关系，以及原记录的出处。</p></div><button ref={createButton} type="button" disabled={blocked || !canCreate} onClick={() => open({ kind: "choose", id: "" })}>＋ 新建关系</button></header>
    {blocked ? <p>请先保存主体草稿并核对未完成的操作，再编辑关联。</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <div className={styles.columns}>
      <div className={styles.directory}>
        <form className={styles.filters} onSubmit={event => { event.preventDefault(); if (!ime.current) filter("q", query.trim()); }}>
          <label><span className="sr-only">关系类型</span><select value={filters.relation_type} onChange={event => filter("relation_type", event.target.value)}><option value="">全部类型</option>{relationTypes.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label><span className="sr-only">关系方向</span><select value={filters.direction} onChange={event => filter("direction", event.target.value)}><option value="">全部方向</option><option value="directed">有方向</option><option value="undirected">无方向</option></select></label>
          <label><span className="sr-only">当前公开状态</span><select value={filters.status} onChange={event => filter("status", event.target.value)}><option value="">全部状态</option>{Object.entries(statuses).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
          <label><span className="sr-only">关系对象类别</span><select value={filters.kind} onChange={event => filter("kind", event.target.value)}><option value="">全部对象</option><option value="person">人物与当前条目</option><option value="node">概念与理论</option></select></label>
          <label className={styles.search}><span className="sr-only">搜索关系对象与出处</span><input type="search" value={query} maxLength={300} onChange={event => setQuery(event.target.value)} placeholder="搜索关系对象、说明或出处…" /></label><button type="submit">搜索</button>
        </form>
        {error ? <p role="alert">{error}<button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取</button>{page > 1 ? <button type="button" onClick={() => setPage(1)}>返回第一页</button> : null}</p> : !data ? <p role="status">正在读取原关系及草稿…</p> : <>
          <ul className={styles.rows}>{data.results.map(row => <li key={`${row.kind}:${row.id}`} data-selected={selection?.id === row.id && selection.kind === row.kind}>
            <button type="button" disabled={blocked || row.kind === "person" && !row.scholar_id} onClick={() => selectRow(row)} aria-pressed={selection?.id === row.id && selection.kind === row.kind}>
              <span><strong>{row.source_name}</strong><small>{row.source_kind}</small></span><span className={styles.arrow} aria-label={row.direction === "undirected" ? "无方向关联" : "指向"}>{row.direction === "undirected" ? "—" : "→"}</span><span><strong>{row.target_name}</strong><small>{row.target_kind}</small></span><span><strong>{row.relation_label}</strong><small>{statuses[row.status] || row.status}{row.has_unpublished_changes ? " · 有未发布修改" : ""}</small></span>
            </button>
            {!row.remains_in_draft ? <p>草稿已移出本条目；正式发布前仍保留此关系。</p> : null}
            {row.kind === "person" && !row.scholar_id ? <p>原人物尚未建立学者页面。关系已保留，请先在人物资料中核对身份并建立学者页面。</p> : null}
            {row.evidence_source ? <details><summary>关系依据</summary><p>{row.evidence_source}</p>{row.description ? <p>{row.description}</p> : null}</details> : <small>出处尚缺，请补齐后再公开。</small>}
          </li>)}</ul>
          {!data.count ? <p>当前范围没有关系。可调整筛选，或新建待核对记录。</p> : null}
          {data.count > 24 ? <nav className={shared.pagination} aria-label="节点关系分页"><button type="button" disabled={!data.previous} onClick={() => setPage(data.previous || 1)}>上一页</button><span>第 {page} 页 · 共 {data.count} 项</span><button type="button" disabled={!data.next} onClick={() => setPage(data.next || page)}>下一页</button></nav> : null}
        </>}
      </div>
      <section ref={detail} tabIndex={-1} className={`${styles.detail} ${shared.nodeRelationDialog}`} aria-label="关系详情">
        <header><h3>关系详情</h3>{selection ? <button type="button" onClick={close}>收起详情</button> : null}</header>
        {!selection ? <p>从左侧选择一条关系，核对方向与出处。新建关系先保存，再明确确认公开。</p> : selection.kind === "choose" ? <div className={styles.choices}><p>选择关系对象</p><button type="button" disabled={blocked} onClick={() => open({ kind: "node", id: "" })}>概念或理论之间</button><button type="button" disabled={blocked} onClick={() => open({ kind: "person", id: "" })}>人物与当前条目</button></div> : selection.kind === "person" ? selection.scholarId ? <ScholarNodeLinkEditor key={`${selection.scholarId}:${selection.id}`} owner={owner} scholarId={selection.scholarId} initialId={selection.id} node={{ id: nodeId, name: nodeName }} personName={selection.personName} onGuard={updateGuard} onSaved={() => { setAttempt(value => value + 1); onChanged?.(); }} /> : <EntityPicker owner={owner} label="选择已有学者" endpoint="/catalog/admin/scholars/" nameField="preferred_name" values={[]} onChange={values => { const person = values.at(-1); if (person?.id) open({ kind: "person", id: "", scholarId: person.id, personName: person.name }); }} /> : <Editor key={selection.id} nodeId={nodeId} requestedId={selection.id} onGuardChange={updateGuard} onSaved={() => { setAttempt(value => value + 1); onChanged?.(); }} />}
      </section>
    </div>
  </section>;
}
