"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type MouseEvent } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useAdminSession } from "@/lib/admin-session";
import { NodeRelations, type NodeRelationGuard } from "./node-relations";
import styles from "./concept-editor.module.css";
import relationStyles from "./node-relations.module.css";

type Profile = { preferred_name: string; original_name: string; short_description: string; portrait: string | null; birth_year: number | null; death_year: number | null };

export function ScholarKnowledgeRelations({ scholarId }: { scholarId: string }) {
  const user = useAdminSession(), [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  return user ? <Workspace key={`${user.id}:${epoch}:${scholarId}`} scholarId={scholarId} owner={String(user.id)}/> : <p role="status">正在核对编辑账户…</p>;
}

function Workspace({ scholarId, owner }: { scholarId: string; owner: string }) {
  const params = useSearchParams(), guard = useRef<NodeRelationGuard>({ dirty: false, pending: false, composing: false });
  const [notice, setNotice] = useState("");
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<Profile>(path, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), [owner]);
  const profile = usePersistentWorkspace<Profile>(`/catalog/admin/scholars/${scholarId}/`, owner, undefined, load);
  function leave(event: MouseEvent<HTMLAnchorElement>) {
    if (guard.current.composing || guard.current.pending) { event.preventDefault(); setNotice("请先完成输入或查回原请求，再离开关系工作区。"); return; }
    if (guard.current.dirty && !window.confirm("关系还有未保存输入，放弃这些输入并离开吗？")) event.preventDefault();
  }
  const data = profile.error ? null : profile.data;
  return <div className={`admin-page ${styles.workspace}`}>
    <header className="admin-page-title"><p>学者与知识</p><h1>理论、概念与关系编辑</h1><p>维护有来源的知识关系，核对方向、依据与发布状态。</p></header>
    {notice ? <p role="status">{notice}</p> : null}
    {profile.error ? <p role="alert">{profile.error}<button type="button" onClick={profile.reload}>重新读取学者</button></p> : !data ? <p role="status">正在读取原学者资料…</p> : <>
      <section className={`${styles.nodeHero} ${relationStyles.scholarHero}`} aria-label="当前学者">
        {data.portrait ? <img className={relationStyles.scholarPortrait} src={normalizePublicResourceUrl(data.portrait)} alt={`${data.preferred_name}肖像`}/> : null}
        <div><h2>{data.preferred_name}</h2>{data.original_name ? <p>{data.original_name}</p> : null}{data.birth_year != null || data.death_year != null ? <p>{data.birth_year ?? "生年待考"} — {data.death_year ?? ""}</p> : null}<span>学者</span></div>
        {data.short_description ? <p>{data.short_description}</p> : null}<Link href={`/admin/scholars/${scholarId}`} onClick={leave}>编辑学者信息 ↗</Link>
      </section>
      <nav className={relationStyles.relatedEntries} aria-label="学者资料与关系"><strong aria-current="page">相关关系</strong><Link href={`/admin/scholars/${scholarId}?section=theory`} onClick={leave}>概念与理论资料</Link><Link href={`/admin/scholars/${scholarId}?section=passages`} onClick={leave}>原文材料</Link></nav>
      <NodeRelations centerKind="scholar" nodeId={scholarId} nodeName={data.preferred_name} blocked={false} initialRelationId={params.get("relation") || undefined} initialRelationKind={params.get("kind") === "person" ? "person" : "scholar"} onGuardChange={value => { guard.current = value; }}/>
    </>}
  </div>;
}
