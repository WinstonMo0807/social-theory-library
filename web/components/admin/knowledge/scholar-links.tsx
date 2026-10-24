"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useActionGuard } from "@/lib/use-action-guard";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { Dialog } from "@/components/ui/dialog";
import type { components } from "@/lib/api/generated/schema";
import type { ScholarKnowledge } from "@/lib/api/scholars.types";
import { RelationSourcePicker } from "./relation-source-picker";
import { useScholarSave } from "./use-scholar-save";
import styles from "./scholar-editor.module.css";

type Kind = "node" | "topic";
type Association = components["schemas"]["AdminScholarLink"];
type LinkPage = components["schemas"]["ScholarLinkPage"];
type Guard = { dirty: boolean; pending: boolean; composing: boolean };
type Props = { scholarId: string; kind: Kind; blocked: boolean; onChanged: () => void; derived?: ScholarKnowledge[] };
const relationTypes:Record<string,string>={related:"相关",proposes:"提出",defines:"定义",develops:"发展",criticizes:"批判",interprets:"解释",uses:"运用",influences:"影响"};
const label = (kind: Kind) => kind === "node" ? "概念" : "主题";
const endpoint = (scholarId: string, kind: Kind) => `/catalog/admin/scholars/${scholarId}/links/${kind}/`;
const stateLabel = (row: Association) => row.confirmed ? "已确认" : ["archived", "rejected"].includes(row.status) ? "已撤回或拒绝" : "待确认";

export function ScholarLinks(props: Props) {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return user ? <LinksWorkspace key={`${user.id}:${epoch}:${props.scholarId}:${props.kind}`} {...props} owner={String(user.id)} /> : <p role="status">正在核对编辑账户…</p>;
}

function LinksWorkspace({ scholarId, kind, blocked, onChanged, derived = [], owner }: Props & { owner: string }) {
  const user = useAdminSession(), canCreate = hasAdminCapability(user, "can_create_authority");
  const [page, setPage] = useState(1), [attempt, setAttempt] = useState(0), [data, setData] = useState<LinkPage | null>(null), [error, setError] = useState("");
  const [selection, setSelection] = useState<string | null>(null), [notice, setNotice] = useState("");
  const guard = useRef<Guard>({ dirty: false, pending: false, composing: false }), ime = useRef(false);
  useEffect(() => {
    const controller = new AbortController(), signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
    queueMicrotask(() => { if (!controller.signal.aborted) { setData(null); setError(""); } });
    withPrivateOwner(owner, () => apiRequest<LinkPage>(`${endpoint(scholarId, kind)}?page=${page}`, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal)
      .then(value => { if (!controller.signal.aborted) setData(value); }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "关联读取失败。"); });
    return () => controller.abort();
  }, [owner, scholarId, kind, page, attempt]);
  function open(id: string) { if (blocked) return; guard.current = { dirty: false, pending: false, composing: false }; setNotice(""); setSelection(id); }
  function close() {
    if (ime.current || guard.current.composing) return;
    if (guard.current.pending) { setNotice("请先查回原请求结果，或停止未执行的请求，再关闭编辑。"); return; }
    if (guard.current.dirty && !window.confirm("有未保存的关联输入，放弃这些输入并返回学者页吗？")) return;
    setSelection(null); setNotice(""); setAttempt(value => value + 1); onChanged();
  }
  return <>
    <header><h2>{kind === "node" ? "核心概念" : "相关主题"} <small>{data?.count ?? "…"}</small></h2><button type="button" disabled={blocked || !canCreate} onClick={() => open("")}>＋ 关联{label(kind)}</button></header>
    {blocked ? <p>请先保存学者草稿并核对未完成的操作，再编辑关联。</p> : null}
    {error ? <p role="alert">{error}<button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取</button>{page > 1 ? <button type="button" onClick={() => setPage(1)}>返回第一页</button> : null}</p> : !data ? <p role="status">正在读取全部关联状态…</p> : <>
      <ul>{data.results.map(row => <li key={row.id}><div><strong>{row.target_name}</strong><small>{stateLabel(row)}{row.featured ? " · 主要关联" : ""}{!row.target_published ? " · 对象尚未公开" : ""}</small><p>{row.relation_label || "关系说明尚缺"}</p>{kind==="node"?<small>{row.node_is_source?row.target_name:row.person_name} {row.direction==="undirected"?"—":"→"} {row.node_is_source?row.person_name:row.target_name} · {row.relation_type_label}</small>:null}{row.source ? <details><summary>查看关系出处</summary><p>{row.source}</p></details> : row.source_anchor ? <small>已绑定馆内原文，请在详情核对准确版本。</small> : <small>出处尚缺，须补齐后再确认。</small>}</div><button type="button" disabled={blocked} onClick={() => open(row.id)}>{row.confirmed ? "编辑" : "核对"}</button></li>)}</ul>
      {!data.count ? <p>还没有直接关联。可以先保存待核对记录，补齐出处后明确确认。</p> : null}
      {data.count > 24 ? <nav className={styles.pagination} aria-label={`${label(kind)}关联分页`}><button type="button" disabled={!data.previous} onClick={() => setPage(data.previous || 1)}>上一页</button><span>第 {page} 页 · 共 {data.count} 项</span><button type="button" disabled={!data.next} onClick={() => setPage(data.next || page)}>下一页</button></nav> : null}
    </>}
    {kind === "node" && derived.length ? <details className={styles.materialLinks}><summary>馆藏著作涉及的概念 · 当前公开摘要 {derived.length} 项</summary><p>这些关联来自已公开著作，不能据此确认学者提出或代表该概念。完整来源沿概念页核对。</p><ul>{derived.map(row => <li key={row.id}><div><strong>{row.name}</strong><small>{row.relation_label} · {row.source_count} 项原文来源</small></div><Link href={row.href} target="_blank" rel="noopener">查看来源 ↗</Link></li>)}</ul></details> : null}
    {selection !== null ? <Dialog open onRequestClose={close} className={`${styles.relationDialog} ${styles.linkDialog}`} aria-label={`核对${label(kind)}关联`} onCompositionStartCapture={() => { ime.current = true; }} onCompositionEndCapture={() => { ime.current = false; }}>
      <header><h2>核对{label(kind)}关联</h2><button type="button" onClick={close}>返回学者页</button></header>{notice ? <p role="status">{notice}</p> : null}
      <LinkEditor key={selection} owner={owner} scholarId={scholarId} kind={kind} initialId={selection} onGuard={value => { guard.current = value; }} onSaved={() => setAttempt(value => value + 1)} />
    </Dialog> : null}
  </>;
}

type Fields = { source_anchor: Association["source_anchor"]; relation_type:Association["relation_type"]; direction:Association["direction"]; node_is_source:boolean; target_id: string; target_name: string; relation_label: string; source: string; featured: boolean; sort_order: number };
const empty: Fields = { source_anchor: null, relation_type:"related",direction:"undirected",node_is_source:false, target_id: "", target_name: "", relation_label: "", source: "", featured: false, sort_order: 0 };
const fields = (row: Association): Fields => ({ source_anchor: row.source_anchor, relation_type:row.relation_type,direction:row.direction,node_is_source:row.node_is_source, target_id: row.target_id, target_name: row.target_name, relation_label: row.relation_label, source: row.source, featured: row.featured, sort_order: row.sort_order });

export function ScholarNodeLinkEditor({ owner, scholarId, initialId, node, personName, onGuard, onSaved }: { owner: string; scholarId: string; initialId: string; node: { id: string; name: string }; personName?: string; onGuard: (value: Guard) => void; onSaved: () => void }) {
  return <LinkEditor owner={owner} scholarId={scholarId} initialId={initialId} kind="node" fixedTarget={node} personName={personName} onGuard={onGuard} onSaved={onSaved} />;
}

function LinkEditor({ owner, scholarId, kind, initialId, fixedTarget, personName, onGuard, onSaved }: { owner: string; scholarId: string; kind: Kind; initialId: string; fixedTarget?: { id: string; name: string }; personName?: string; onGuard: (value: Guard) => void; onSaved: () => void }) {
  const user = useAdminSession(), command = useScholarSave(owner, kind === "node" ? "node_link" : "topic_link");
  const canEdit = hasAdminCapability(user, "can_edit_draft_authority"), canCreate = hasAdminCapability(user, "can_create_authority"), canPublish = hasAdminCapability(user, "can_publish_authority");
  const initialFields = { ...empty, target_id: fixedTarget?.id || "", target_name: fixedTarget?.name || "" };
  const fixedTargetId = fixedTarget?.id;
  const [id, setId] = useState(initialId), [row, setRow] = useState<Association | null>(null), [draft, setDraft] = useState<Fields>(initialFields), [saved, setSaved] = useState<Fields>(initialFields);
  const [loading, setLoading] = useState(Boolean(initialId)), [attempt, setAttempt] = useState(0), [error, setError] = useState(""), [message, setMessage] = useState(""), [ime, setIme] = useState(false);
  const composing = useRef(false), mounted = useRef(true), { pendingAction, startAction, finishAction } = useActionGuard(), busy = Boolean(pendingAction);
  const dirty = useUnsavedForm(draft, saved);
  useUnsavedForm(Boolean(command.recovery) || busy, false);
  const notifyGuard = useEffectEvent(onGuard);
  useEffect(() => { notifyGuard({ dirty, pending: busy || Boolean(command.recovery), composing: ime }); }, [dirty, busy, command.recovery, ime]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController(), signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
    queueMicrotask(() => { if (!controller.signal.aborted) { setLoading(true); setRow(null); setError(""); } });
    withPrivateOwner(owner, () => apiRequest<LinkPage>(`${endpoint(scholarId, kind)}?id=${encodeURIComponent(id)}`, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal)
      .then(value => { if (controller.signal.aborted) return; const current = value.results.find(item => item.id === id); if (!current || fixedTargetId && current.target_id !== fixedTargetId) throw Error("原记录不在当前人物与条目的关联中；可能已归并，请从原页面核对。不会据此新建记录。"); setRow(current); setDraft(fields(current)); setSaved(fields(current)); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "原记录暂不可读。"); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, owner, scholarId, kind, attempt, fixedTargetId]);
  const ready = !loading && (!id || row?.id === id), locked = !canEdit || !command.ready || busy || Boolean(command.recovery) || !ready;
  const validDirection = kind !== "node" || (draft.relation_type === "related" || draft.direction === "directed") && !(draft.node_is_source && ["proposes", "defines", "develops", "interprets", "uses"].includes(draft.relation_type));
  const valid = Boolean(draft.target_id && Number.isInteger(draft.sort_order) && draft.sort_order >= 0 && draft.sort_order <= 2147483647);
  function apply(value: Association) { setRow(value); setId(value.id); setDraft(fields(value)); setSaved(fields(value)); onSaved(); }
  async function act(action: "save" | "confirm" | "withdraw" | "retry") {
    if (composing.current || !canEdit || !command.ready || !ready || command.recovery && action !== "retry") return;
    if (action === "save" && (!valid || row?.confirmed || !id && !canCreate)) return;
    if (action === "confirm" && (!id || !canPublish || !valid || !validDirection || !(draft.source.trim() || draft.source_anchor) || !draft.relation_label.trim() || !window.confirm("确认这条关联及其出处？相关公开页面将同步使用本次说明；原记录和操作历史保留。"))) return;
    if (action === "withdraw" && (!id || !canPublish || dirty || !window.confirm("撤回这条关联？公开页面将不再使用此关系，记录与出处仍保留，可重新核对。"))) return;
    if (!startAction(action)) return;
    setError(""); setMessage("");
    try {
      const payload = action === "withdraw" ? { action, id, edit_version: row?.edit_version } : { action, target_id: draft.target_id, relation_label: draft.relation_label, source: draft.source, featured: draft.featured, sort_order: draft.sort_order, relation_type:draft.relation_type,direction:draft.direction,node_is_source:draft.node_is_source, source_anchor:draft.source_anchor, ...(id ? { id, edit_version: row?.edit_version } : {}) };
      const result = await command.save<Association>(endpoint(scholarId, kind), JSON.stringify(payload), {}, "POST");
      if (!mounted.current) return;
      apply(result); setMessage(action === "retry" ? "原请求已查回，显示当前保存版本。" : action === "confirm" ? "关联已明确确认。" : action === "withdraw" ? "关联已撤回，原记录保留。" : "已保存待核对记录，尚未确认公开。");
    } catch (reason) { if (mounted.current) setError(reason instanceof Error ? reason.message : "操作结果待核对，输入仍保留。"); } finally { finishAction(action); }
  }
  async function recover(cancel = false) {
    if (composing.current || !startAction("recover")) return;
    try { const receipt = await command.lookup(cancel); if (!receipt || !mounted.current) return; if (receipt.state === "applied" && receipt.relation_id) { setId(receipt.relation_id); setLoading(true); setAttempt(value => value + 1); onSaved(); } setMessage(receipt.state === "cancelled" ? "未执行的原请求已停止，当前输入仍保留。" : "原请求已经完成，正在重新读取当前记录。若来自其他学者，请回原页面核对。"); } finally { finishAction("recover"); }
  }
  return <form className={styles.linkForm} onSubmit={event => { event.preventDefault(); void act("save"); }} onCompositionStartCapture={() => { composing.current = true; setIme(true); }} onCompositionEndCapture={() => { composing.current = false; setIme(false); }}>
    {error || command.error ? <p role="alert">{error || command.error}</p> : null}{message ? <p role="status">{message}</p> : null}{loading ? <p role="status">正在读取原关联…</p> : null}
    {command.recovery ? <section aria-label="查回未确认操作"><p>上次操作的结果尚未确认。查回或停止后才能修改输入。</p><button type="button" disabled={busy || ime} onClick={() => void recover()}>查回原请求</button><button type="button" disabled={busy || ime} onClick={() => void recover(true)}>停止未执行的请求</button>{command.canRetry ? <button type="button" disabled={busy || ime} onClick={() => void act("retry")}>重试同一请求</button> : null}</section> : null}
    <fieldset disabled={locked}>
      {id || fixedTarget ? <div><strong>{draft.target_name || "原关联对象"}</strong><p>{row ? stateLabel(row) : id ? "等待读取" : "新关联 · 尚未保存"}{row && !row.target_published ? " · 对象尚未公开，不能确认" : ""}</p>{row ? <Link href={row.target_href} target="_blank" rel="noopener">查看对象资料 ↗</Link> : null}</div> : <EntityPicker owner={owner} label={`选择已有${label(kind)}`} endpoint={kind === "node" ? "/catalog/admin/theory-system/nodes/" : "/catalog/admin/topics/"} queryParam={kind === "node" ? "q" : "search"} nameField={kind === "node" ? "canonical_name_zh" : "name"} values={draft.target_id ? [{ id: draft.target_id, name: draft.target_name }] : []} onChange={values => { const item = values.at(-1); setDraft(value => ({ ...value, target_id: item?.id || "", target_name: item?.name || "" })); }} />}
      {kind==="node"?<><label>关系类型<select value={draft.relation_type} onChange={event=>{const value=event.target.value as Fields["relation_type"];setDraft(current=>({...current,relation_type:value,direction:value==="related"?current.direction:"directed",node_is_source:["proposes","defines","develops","interprets","uses"].includes(value)?false:current.node_is_source}));}}>{Object.entries(relationTypes).map(([value,name])=><option key={value} value={value}>{name}</option>)}</select></label><label>来源与目标<select value={draft.direction==="undirected"?"undirected":draft.node_is_source?"node":"person"} onChange={event=>setDraft(value=>({...value,direction:event.target.value==="undirected"?"undirected":"directed",node_is_source:event.target.value==="node"}))}><option value="undirected">无方向关联</option><option value="person">学者 → 概念或理论</option><option value="node" disabled={["proposes","defines","develops","interprets","uses"].includes(draft.relation_type)}>概念或理论 → 学者</option></select></label><p aria-live="polite">{draft.node_is_source?draft.target_name:row?.person_name||personName||"当前学者"} {draft.direction==="undirected"?"—":"→"} {draft.node_is_source?row?.person_name||personName||"当前学者":draft.target_name||"待选概念"} · {relationTypes[draft.relation_type]}</p></>:null}
      <label>关系说明<input value={draft.relation_label} maxLength={120} onChange={event => setDraft(value => ({ ...value, relation_label: event.target.value }))} placeholder="说明这位学者与所选对象的关系" /></label>
      {kind === "node" ? <RelationSourcePicker owner={owner} value={draft.source_anchor} saved={row?.source_anchor} material={row?.source_material} onChange={source_anchor => setDraft(value => ({ ...value, source_anchor }))} /> : null}
      <label>可追溯出处<textarea value={draft.source} maxLength={kind === "node" ? 160 : 120} rows={4} onChange={event => setDraft(value => ({ ...value, source: event.target.value }))} placeholder="填写作品、版本、页码或可靠来源定位" /></label>
      <label className={styles.linkCheckbox}><input type="checkbox" checked={draft.featured} onChange={event => setDraft(value => ({ ...value, featured: event.target.checked }))} />{kind === "node" ? "作为代表性关联展示" : "作为主要主题关联"}</label>
      {kind === "node" ? <label>展示顺序<input type="number" min={0} max={2147483647} step={1} value={Number.isNaN(draft.sort_order) ? "" : draft.sort_order} onChange={event => setDraft(value => ({ ...value, sort_order: event.target.value === "" ? NaN : Number(event.target.value) }))} /><small>数值小的在前。同顺序按固定记录顺序展示。</small></label> : null}
    </fieldset>
    {!validDirection ? <p role="status">确认前须明确关系方向；提出、定义、发展、解释与运用以人物为来源。</p> : null}
    {row?.confirmed ? <p>这条关联已公开确认。输入修改尚未保存，只有明确确认更新后才会改变公开关系。</p> : <p>待核对关联不会公开。确认需要学者、关联对象均已发布，且关系说明和出处完整。</p>}
    <footer><button type="submit" disabled={locked || ime || !valid || Boolean(row?.confirmed) || !id && !canCreate}>保存待核对</button><button type="button" disabled={locked || ime || !id || !canPublish || !valid || !validDirection || !(draft.source.trim() || draft.source_anchor) || !draft.relation_label.trim() || !row?.target_published} onClick={() => void act("confirm")}>{row?.confirmed ? "确认更新公开关联" : "确认关联"}</button>{id ? <button type="button" disabled={locked || ime || !canPublish || dirty || ["archived", "rejected"].includes(row?.status || "")} onClick={() => void act("withdraw")}>撤回关联</button> : null}</footer>
    {id ? <button type="button" disabled={busy || ime || Boolean(command.recovery)} onClick={() => { if (dirty && !window.confirm("放弃当前输入并重新读取已保存记录吗？")) return; setLoading(true); setAttempt(value => value + 1); }}>重新读取原记录</button> : null}
  </form>;
}
