"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import type { components } from "@/lib/api/generated/schema";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { ScholarNodeLinkEditor } from "./scholar-links";
import { ScholarRelationsEditor } from "./scholar-relations-editor";
import { MaterialRelationCandidates } from "./material-relation-candidates";
import shared from "./scholar-editor.module.css";
import styles from "./node-relations.module.css";

const Editor = dynamic(() => import("@/components/theory-system-admin").then(module => module.NodeRelationEditor), { loading: () => <p role="status">正在打开原关系编辑器…</p> });
type Page = components["schemas"]["NodeRelationPage"];
type Row = Page["results"][number];
export type NodeRelationGuard = { dirty: boolean; pending: boolean; composing: boolean };
type Props = { centerKind?: "node" | "scholar"; initialRelationId?: string; initialRelationKind?: "person" | "scholar"; nodeId: string; nodeName: string; blocked: boolean; onChanged?: () => void; onGuardChange?: (value: NodeRelationGuard) => void };
type Selection = { kind: "node" | "person" | "scholar" | "choose"; id: string; scholarId?: string; personName?: string; sourceRequest?: number };
const statuses: Record<string, string> = { published: "已确认公开", draft: "草稿", pending: "待确认", rejected: "不采用", archived: "已下线" };
const clearGuard: NodeRelationGuard = { dirty: false, pending: false, composing: false };

export function NodeRelations(props: Props) {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return user ? <RelationList key={`${user.id}:${epoch}:${props.nodeId}:${props.centerKind || "node"}`} {...props} owner={String(user.id)} /> : <p role="status">正在核对编辑账户…</p>;
}

function RelationList({ nodeId, nodeName, blocked, onChanged, onGuardChange, owner, centerKind = "node", initialRelationId, initialRelationKind }: Props & { owner: string }) {
  const user = useAdminSession(), canCreate = hasAdminCapability(user, "can_create_authority");
  const [page, setPage] = useState(1), [attempt, setAttempt] = useState(0), [data, setData] = useState<Page | null>(null), [error, setError] = useState("");
  const [relationTypes, setRelationTypes] = useState<Page["relation_types"]>([]);
  const [filters, setFilters] = useState({ status: "", kind: "", relation_type: "", direction: "", q: "" }), [query, setQuery] = useState("");
  const [selection, setSelection] = useState<Selection | null>(()=>initialRelationId&&centerKind==="scholar"?{kind:initialRelationKind||"scholar",id:initialRelationId,scholarId:nodeId,personName:nodeName}:null), [notice, setNotice] = useState("");
  const sourceSequence = useRef(0);
  const guard = useRef(clearGuard), ime = useRef(false), detail = useRef<HTMLElement>(null), createButton = useRef<HTMLButtonElement>(null);
  const guardCallback = useRef(onGuardChange);
  useEffect(() => { guardCallback.current = onGuardChange; }, [onGuardChange]);
  useEffect(() => () => guardCallback.current?.(clearGuard), []);
  function updateGuard(value: NodeRelationGuard) { guard.current = value; onGuardChange?.(value); }
  const directoryPath = centerKind === "scholar" ? `/catalog/admin/scholars/${nodeId}/knowledge-relations/` : `/catalog/admin/theory-system/nodes/${nodeId}/relations/`;
  useEffect(() => {
    const controller = new AbortController(), signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
    queueMicrotask(() => { if (!controller.signal.aborted) { setData(null); setError(""); } });
    withPrivateOwner(owner, () => apiRequest<Page>(`${directoryPath}?${new URLSearchParams({ ...filters, page: String(page) })}`, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal)
      .then(value => { if (!controller.signal.aborted) { setData(value); setRelationTypes(value.relation_types); } }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "关系读取失败。"); });
    return () => controller.abort();
  }, [owner, directoryPath, page, filters, attempt]);
  function canLeave() {
    if (ime.current || guard.current.composing) return false;
    if (guard.current.pending) { setNotice("请先查询原请求，或停止未执行的请求，再切换关系。"); return false; }
    return !guard.current.dirty || window.confirm("关系还有未保存输入，放弃这些输入并切换吗？");
  }
  function open(value: Selection) {
    if (blocked || !canLeave()) return;
    updateGuard(clearGuard); setNotice(""); setSelection(value);
    requestAnimationFrame(() => detail.current?.focus());
  }
  function selectSource() {
    if (blocked || ime.current || guard.current.composing) return;
    if (guard.current.pending) { setNotice("请先核对原请求结果，再更换原文依据。"); return; }
    if (!selection && !canCreate) return;
    const request = ++sourceSequence.current;
    setSelection(value => ({...(value || {kind:"choose",id:""}),sourceRequest:request}));
    setNotice(selection && selection.kind !== "choose" ? "原输入保留，请在详情中选择准确材料。" : "先选择关系对象，再选取准确原文。选材不会自动建立或公开关系。");
    requestAnimationFrame(() => detail.current?.focus());
  }
  function sourceOpened() { setSelection(value => value ? {...value,sourceRequest:0} : value); }
  const sourceRequest = {sourceRequest:selection?.sourceRequest,onSourceOpened:sourceOpened};
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
    <header><div><h2>关系类型、方向与来源 <small>{data?.count ?? "…"}</small></h2></div><div className={styles.relationActions}><button ref={createButton} type="button" disabled={blocked || !canCreate} onClick={() => open({ kind: "choose", id: "" })}>＋ 新建关系</button><button type="button" disabled={blocked || !selection && !canCreate} onClick={selectSource}>从材料选原文</button></div></header>
    {blocked ? <p>请先保存主体草稿并核对未完成的操作，再编辑关联。</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    <div className={styles.columns}>
      <div className={styles.directory}>
        <form className={styles.filters} onSubmit={event => { event.preventDefault(); if (!ime.current) filter("q", query.trim()); }}>
          <label><span className="sr-only">关系类型</span><select value={filters.relation_type} onChange={event => filter("relation_type", event.target.value)}><option value="">全部类型</option>{relationTypes.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label><span className="sr-only">关系方向</span><select value={filters.direction} onChange={event => filter("direction", event.target.value)}><option value="">全部方向</option><option value="directed">有方向</option><option value="undirected">无方向</option>{centerKind === "scholar" ? <option value="bidirectional">双向</option> : null}</select></label>
          <label><span className="sr-only">当前公开状态</span><select value={filters.status} onChange={event => filter("status", event.target.value)}><option value="">全部状态</option>{Object.entries(statuses).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
          <label><span className="sr-only">关系对象类别</span><select value={filters.kind} onChange={event => filter("kind", event.target.value)}><option value="">全部对象</option>{centerKind === "scholar" ? <><option value="person">概念与理论</option><option value="scholar">人物</option></> : <><option value="person">人物与当前条目</option><option value="node">概念与理论</option></>}</select></label>
          <label className={styles.search}><span className="sr-only">搜索关系对象与出处</span><input type="search" value={query} maxLength={300} onChange={event => setQuery(event.target.value)} placeholder="搜索关系对象、说明或出处…" /></label><button type="submit">搜索</button>
        </form>
        {error ? <p role="alert">{error}<button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取</button>{page > 1 ? <button type="button" onClick={() => setPage(1)}>返回第一页</button> : null}</p> : !data ? <p role="status">正在读取原关系及草稿…</p> : <>
          <ul className={styles.rows}>{data.results.map(row => <li key={`${row.kind}:${row.id}`} data-selected={selection?.id === row.id && selection.kind === row.kind}>
            <button type="button" disabled={blocked || row.kind === "person" && !row.scholar_id} onClick={() => selectRow(row)} aria-pressed={selection?.id === row.id && selection.kind === row.kind}>
              <span><strong>{row.source_name}</strong><small>{row.source_kind}</small></span><span className={styles.arrow} aria-label={row.direction === "undirected" ? "无方向关联" : row.direction === "bidirectional" ? "双向关联" : "指向"}>{row.direction === "undirected" ? "—" : row.direction === "bidirectional" ? "↔" : "→"}</span><span><strong>{row.target_name}</strong><small>{row.target_kind}</small></span><span><strong>{row.relation_label}</strong><small>{statuses[row.status] || row.status}{row.has_unpublished_changes ? " · 有未发布修改" : ""}</small></span>
            </button>
            {!row.remains_in_draft ? <p>草稿已移出本条目；正式发布前仍保留此关系。</p> : null}
            {row.kind === "person" && !row.scholar_id ? <p>原人物尚未建立学者页面。关系已保留，请先在人物资料中核对身份并建立学者页面。</p> : null}
            {row.evidence_source ? <details><summary>关系依据</summary><p>{row.evidence_source}</p>{row.description ? <p>{row.description}</p> : null}</details> : row.has_source_anchor ? <small>已绑定馆内原文，请在详情核对准确版本。</small> : <small>出处尚缺，请补齐后再公开。</small>}
          </li>)}</ul>
          {!data.count ? <p>当前范围没有关系。可调整筛选，或新建待核对记录。</p> : null}
          {data.count > 24 ? <nav className={shared.pagination} aria-label="节点关系分页"><button type="button" disabled={!data.previous} onClick={() => setPage(data.previous || 1)}>上一页</button><span>第 {page} 页 · 共 {data.count} 项</span><button type="button" disabled={!data.next} onClick={() => setPage(data.next || page)}>下一页</button></nav> : null}
        </>}
        <RelationCandidates centerKind={centerKind} centerId={nodeId} owner={owner} path={directoryPath} attempt={attempt} blocked={blocked} selected={selection} onSelect={selectRow}/>
      </div>
      <section ref={detail} tabIndex={-1} className={`${styles.detail} ${shared.nodeRelationDialog}`} aria-label="关系详情">
        <header><h3>关系详情</h3>{selection ? <button type="button" onClick={close}>收起详情</button> : null}</header>
        {!selection ? <p>从左侧选择一条关系，核对方向与出处。新建关系先保存，再明确确认公开。</p>
          : selection.kind === "choose" ? <div className={styles.choices}><p>选择关系对象</p>
              <button type="button" disabled={blocked} onClick={() => open({ kind: centerKind === "scholar" ? "person" : "node", id: "", sourceRequest:selection.sourceRequest, ...(centerKind === "scholar" ? {scholarId:nodeId,personName:nodeName} : {}) })}>{centerKind === "scholar" ? "学者与概念或理论" : "概念或理论之间"}</button>
              <button type="button" disabled={blocked} onClick={() => open({ kind: centerKind === "scholar" ? "scholar" : "person", id: "", sourceRequest:selection.sourceRequest })}>{centerKind === "scholar" ? "学者之间" : "人物与当前条目"}</button></div>
          : selection.kind === "scholar" ? <ScholarRelationsEditor {...sourceRequest} key={selection.id} scholarId={nodeId} initialRelationId={selection.id} embedded detailOnly onGuardChange={updateGuard} onSaved={() => {setAttempt(value=>value+1);onChanged?.();}}/>
          : selection.kind === "person" ? selection.scholarId ? <ScholarNodeLinkEditor {...sourceRequest} key={`${selection.scholarId}:${selection.id}`} owner={owner} scholarId={selection.scholarId} initialId={selection.id} node={centerKind === "node" ? {id:nodeId,name:nodeName} : undefined} personName={selection.personName} onGuard={updateGuard} onSaved={() => {setAttempt(value=>value+1);onChanged?.();}}/>
              : <EntityPicker owner={owner} label="选择已有学者" endpoint="/catalog/admin/scholars/" nameField="preferred_name" values={[]} onChange={values => { const person=values.at(-1);if(person?.id)open({kind:"person",id:"",scholarId:person.id,personName:person.name,sourceRequest:selection.sourceRequest}); }}/>
          : <Editor {...sourceRequest} key={selection.id} nodeId={nodeId} requestedId={selection.id} onGuardChange={updateGuard} onSaved={() => {setAttempt(value=>value+1);onChanged?.();}}/>}
      </section>
    </div>
  </section>;
}

function RelationCandidates({owner,path,attempt,blocked,selected,onSelect,centerKind,centerId}:{centerKind:"node"|"scholar";centerId:string;owner:string;path:string;attempt:number;blocked:boolean;selected:Selection|null;onSelect:(row:Row)=>void}) {
  const [source,setSource]=useState<"materials"|"records">("materials");
  const [page,setPage]=useState(1),[data,setData]=useState<Page|null>(null),[error,setError]=useState(""),[retry,setRetry]=useState(0);
  useEffect(()=>{
    if(source!=="records")return;
    const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    queueMicrotask(()=>{if(!controller.signal.aborted){setData(null);setError("");}});
    withPrivateOwner(owner,()=>apiRequest<Page>(`${path}?review_only=true&page_size=6&page=${page}`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal)
      .then(value=>{if(!controller.signal.aborted)setData(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"候选关系暂不可读。");});
    return()=>controller.abort();
  },[owner,path,attempt,page,retry,source]);
  return <section className={styles.candidates} aria-label="候选关系">
    <header><h3>候选关系 {source==="records"?<small>{data?.count??"…"}</small>:null}</h3><p>核对材料证据、关系含义与准确对象后，再明确公开。</p></header>
    <nav className={styles.candidateSources} aria-label="候选来源"><button type="button" aria-pressed={source==="materials"} onClick={()=>setSource("materials")}>材料线索</button><button type="button" aria-pressed={source==="records"} onClick={()=>setSource("records")}>已保存待确认关系</button></nav>
    {source==="materials"?<MaterialRelationCandidates key={attempt} owner={owner} centerKind={centerKind} centerId={centerId}/>:error?<p role="alert">{error}<button type="button" onClick={()=>{setPage(1);setRetry(value=>value+1);}}>从第一页重新读取</button></p>:!data?<p role="status">正在读取待核对关系…</p>:<>
      <ul className={styles.candidateRows}>{data.results.map(row=><li key={`${row.kind}:${row.id}`} data-selected={selected?.kind===row.kind&&selected.id===row.id}>
        <div><strong>{row.source_name} {row.direction==="undirected"?"—":row.direction==="bidirectional"?"↔":"→"} {row.target_name}</strong><p>{row.relation_label} · {statuses[row.status]||"待核对"}</p>
          <small>{row.evidence_source|| (row.has_source_anchor?"已有馆内原文，请核对准确版本。":"出处尚缺，请补齐后再公开。")}</small>
          {!row.remains_in_draft?<p>当前草稿已移出此条目，核对新端点后再处理。</p>:null}
          {row.kind==="person"&&!row.scholar_id?<p>请先核对原人物身份并建立学者页面；此关系仍保留。</p>:null}</div>
        <button type="button" disabled={blocked||row.kind==="person"&&!row.scholar_id} onClick={()=>onSelect(row)} aria-pressed={selected?.kind===row.kind&&selected.id===row.id}>查看依据</button>
      </li>)}</ul>
      {!data.count?<p>当前没有待核对关系。</p>:null}
      {data.count>6?<nav className={shared.pagination} aria-label="候选关系分页"><button type="button" disabled={!data.previous} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>:null}
    </>}
  </section>;
}
