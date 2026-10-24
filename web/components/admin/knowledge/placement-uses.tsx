"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { components } from "@/lib/api/generated/schema";
import styles from "./concept-editor.module.css";

type Page=components["schemas"]["PlacementUsePage"];

export function PlacementUses({owner,sourceType,sourceId}:{owner:string;sourceType:"node"|"scholar";sourceId:string}) {
  const [page,setPage]=useState(1);
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Page>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Page>(`/catalog/admin/content-placements/uses/${sourceType}/${sourceId}/?page=${page}`,owner,undefined,load);
  return <section className={styles.panel} aria-label="其他页面的编排引用">
    <header className={styles.heading}><h2>其他页面的编排引用</h2><button type="button" onClick={resource.reload}>重新读取</button></header>
    <p>这里列出当前账号可编辑的页面中，最新草稿或原发布修订的准确引用。同一页面两版分别保留，移除草稿引用不等于撤下已发布引用。</p>
    {resource.error?<p role="alert">{resource.error}<button type="button" onClick={()=>{setPage(1);resource.reload();}}>返回第一页</button></p>:!resource.data?<p role="status">正在核对页面编排引用…</p>:<>
      <p>当前可见 {resource.data.count} 份编排修订 · 第 {page} 页</p>
      <ol className={styles.usageReferences}>{resource.data.results.map(row=><li key={row.revision_id}>
        <header><h3>{row.title}</h3><span>{row.page_label} · 第 {row.revision} 版</span></header>
        <p>{row.is_published?row.is_latest?"原发布修订，也是当前最新编排":"原发布修订；另有新的编排记录":"当前已保存草稿"}</p>
        <p>{row.items.length} 处引用{row.items.some(item=>item.group)?` · ${[...new Set(row.items.map(item=>item.group).filter(Boolean))].join("、")}`:""}</p>
        <Link href={row.edit_url}>核对所属页面的编排 →</Link>
      </li>)}</ol>
      {!resource.data.count?<p>当前可见范围内未发现此类编排引用。文章正文、旧版本和其他引用类型不计入此处。</p>:null}
      {resource.data.count>12?<nav className={styles.pagination} aria-label="页面引用分页"><button type="button" disabled={!resource.data.previous} onClick={()=>setPage(value=>value-1)}>上一页</button><button type="button" disabled={!resource.data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>:null}
    </>}
  </section>;
}
