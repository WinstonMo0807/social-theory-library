"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import type { Paginated } from "@/lib/api/pagination";
import type { AdminKnowledgeRelation } from "@/components/theory-system-admin";
import { Dialog } from "@/components/ui/dialog";
import styles from "./scholar-editor.module.css";

const Editor = dynamic(() => import("@/components/theory-system-admin").then(module => module.NodeRelationEditor), { loading: () => <p role="status">正在打开原关系编辑器…</p> });
type Props = { nodeId: string; blocked: boolean; onChanged?: () => void };
const statuses: Record<string, string> = { published: "已公开", draft: "草稿", pending: "待核对", rejected: "不采用", archived: "已下线" };

export function NodeRelations(props: Props) {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return user ? <RelationList key={`${user.id}:${epoch}:${props.nodeId}`} {...props} owner={String(user.id)} /> : <p role="status">正在核对编辑账户…</p>;
}

function RelationList({ nodeId, blocked, onChanged, owner }: Props & { owner: string }) {
  const user = useAdminSession(), canCreate = hasAdminCapability(user, "can_create_authority");
  const [page, setPage] = useState(1), [attempt, setAttempt] = useState(0), [data, setData] = useState<Paginated<AdminKnowledgeRelation> | null>(null), [error, setError] = useState("");
  const [status, setStatus] = useState(""), [selection, setSelection] = useState<string | null>(null), [notice, setNotice] = useState("");
  const guard = useRef({ dirty: false, pending: false, composing: false }), ime = useRef(false);
  useEffect(() => {
    const controller = new AbortController(), signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
    queueMicrotask(() => { if (!controller.signal.aborted) { setData(null); setError(""); } });
    withPrivateOwner(owner, () => apiRequest<Paginated<AdminKnowledgeRelation>>(`/catalog/admin/theory-system/relations/?${new URLSearchParams({ node: nodeId, page: String(page), status })}`, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal)
      .then(value => { if (!controller.signal.aborted) setData(value); }).catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "关系读取失败。"); });
    return () => controller.abort();
  }, [owner, nodeId, page, status, attempt]);
  function open(id: string) { if (blocked) return; guard.current = { dirty: false, pending: false, composing: false }; setNotice(""); setSelection(id); }
  function close() {
    if (ime.current || guard.current.composing) return;
    if (guard.current.pending) { setNotice("请先查回原请求，或停止未执行的请求，再返回当前条目。"); return; }
    if (guard.current.dirty && !window.confirm("关系还有未保存输入，放弃这些输入并返回当前条目吗？")) return;
    setSelection(null); setNotice(""); setAttempt(value => value + 1); onChanged?.();
  }
  return <section className={styles.canonical} aria-label="理论与概念关系">
    <header><h2>关系类型、方向与来源 <small>{data?.count ?? "…"}</small></h2><button type="button" disabled={blocked || !canCreate} onClick={() => open("")}>＋ 新建关系</button></header>
    <label>当前公开状态 <select value={status} onChange={event => { setStatus(event.target.value); setPage(1); }}><option value="">全部状态</option>{Object.entries(statuses).map(([value, name]) => <option key={value} value={value}>{name}</option>)}</select></label>
    {blocked ? <p>请先保存主体草稿并核对未完成的操作，再编辑关联。</p> : null}
    {error ? <p role="alert">{error}<button type="button" onClick={() => setAttempt(value => value + 1)}>重新读取</button>{page > 1 ? <button type="button" onClick={() => setPage(1)}>返回第一页</button> : null}</p> : !data ? <p role="status">正在读取原关系及草稿…</p> : <>
      <ul>{data.results.map(row => <li key={row.id}><div><strong>{row.source_name} {row.direction === "undirected" ? "—" : "→"} {row.target_name}</strong><small>{row.relation_label} · {statuses[row.public_status ?? row.status] || row.status}{row.editorial_revision ? " · 有未发布修改" : ""}</small>{row.description ? <p>{row.description}</p> : null}{row.source_node !== nodeId && row.target_node !== nodeId ? <p>当前草稿已移出本条目；正式发布前仍保留此关系。</p> : null}{row.evidence_source ? <details><summary>查看关系依据</summary><p>{row.evidence_source}</p></details> : <small>出处尚缺，请补齐后再公开。</small>}</div><button type="button" disabled={blocked} onClick={() => open(row.id)}>编辑</button></li>)}</ul>
      {!data.count ? <p>当前范围没有关系记录。新建后先保存草稿，再明确确认发布。</p> : null}
      {data.count > 24 ? <nav className={styles.pagination} aria-label="节点关系分页"><button type="button" disabled={!data.previous} onClick={() => setPage(value => value - 1)}>上一页</button><span>第 {page} 页 · 共 {data.count} 项</span><button type="button" disabled={!data.next} onClick={() => setPage(value => value + 1)}>下一页</button></nav> : null}
    </>}
    {selection !== null ? <Dialog open onRequestClose={close} className={`${styles.relationDialog} ${styles.nodeRelationDialog}`} aria-label="编辑节点关系" onCompositionStartCapture={() => { ime.current = true; }} onCompositionEndCapture={() => { ime.current = false; }}>
      <header><h2>编辑关系</h2><button type="button" onClick={close}>返回当前条目</button></header>{notice ? <p role="status">{notice}</p> : null}
      <Editor key={selection} nodeId={nodeId} requestedId={selection} onGuardChange={value => { guard.current = value; }} onSaved={() => setAttempt(value => value + 1)} />
    </Dialog> : null}
  </section>;
}
