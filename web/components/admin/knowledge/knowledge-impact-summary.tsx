"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { useCallback } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import styles from "./concept-editor.module.css";

type Impact = {object_type:string;object_id:string;scope:string;has_draft:boolean;dependencies:{key:string;accessor?:string;label:string;count:number}[]};

export function KnowledgeImpactSummary({objectType,objectId,owner}:{objectType:string;objectId:string;owner:string}) {
  const load=useCallback(async(path:string,signal:AbortSignal)=>{
    const result=await apiRequest<Impact>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false);
    if(result.object_type!==objectType||result.object_id!==objectId)throw Error("关联记录与当前对象不一致，请重新读取。");
    return result;
  },[owner,objectType,objectId]);
  const data=usePersistentWorkspace<Impact>(`/catalog/admin/knowledge-publications/${objectType}/${objectId}/history/`,owner,undefined,load);
  return <section className={styles.panel} aria-label="已存馆藏关联">
    <header className={styles.heading}><h2>已存关联与影响核对</h2><button type="button" onClick={data.reload}>重新读取</button></header>
    {data.error?<p role="alert">{data.error}</p>:!data.data?<LoadingState role="status">正在读取当前对象的馆藏关联…</LoadingState>:<>
      <p>{data.data.scope}</p>
      <dl className={styles.impactCounts}>{data.data.dependencies.map((row,index)=><div key={`${row.key}:${row.accessor||index}`}><dt>{row.label}</dt><dd>{row.count} 条关联</dd></div>)}</dl>
      {!data.data.dependencies.length?<p>当前结构记录中未发现馆藏关联。其他页面的编排引用仍须分别核对。</p>:null}
      {data.data.has_draft?<p>主体已有未发布草稿；修改不会在确认前替换公开内容。</p>:null}
      <Link href={`/admin/publication/knowledge/${objectType}/${objectId}?tab=dependencies`}>查看主体历史与依赖 →</Link>
      <p>这里不统计读者私人记录，也不会自动改绑其他页面的原文或执行数据迁移。</p>
    </>}
  </section>;
}
