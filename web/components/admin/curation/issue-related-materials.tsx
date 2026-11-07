"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useEffect, useState } from "react";
import type { IssueSourceReference } from "@/lib/api/recommendation-issues.types";
import type { IssueSourceChoice } from "./issue-source-picker";
import { IssueSourceThumbnail } from "./issue-source-summary";
import styles from "./issue-selection.module.css";

type RelatedPage={count:number;next:string|null;previous:string|null;results:Array<IssueSourceChoice&{reasons:string[]}>;edit_version:string;truncated:boolean;unavailable_count:number;notice:string};
export function IssueRelatedMaterials({issueId,version,initialKind="person",dirty,disabled,references,request,onChoose,onInsert}:{initialKind?:string;issueId:string;version:string;dirty:boolean;disabled:boolean;references:IssueSourceReference[];request:<T>(url:string,init?:RequestInit)=>Promise<T>;onChoose:(value:IssueSourceChoice)=>void;onInsert:(value:IssueSourceChoice)=>void}) {
  const [kind,setKind]=useState(initialKind),[page,setPage]=useState(1),[attempt,setAttempt]=useState(0);
  const [result,setResult]=useState<RelatedPage|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(true);
  useEffect(()=>{const controller=new AbortController();queueMicrotask(()=>{if(!controller.signal.aborted){setLoading(true);setError("");}});
    void request<RelatedPage>(`/catalog/admin/recommendation-issues/${issueId}/sources/?${new URLSearchParams({related:kind,page:String(page)})}`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setResult(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"关联资料读取失败。");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();
  },[issueId,version,kind,page,attempt,request]);
  const locked=disabled||dirty||loading||Boolean(error)||result?.edit_version!==version;
  return <section className={styles.candidates} aria-label="已选材料的关联资料"><header><h2>关联人物 / 概念</h2><button type="button" disabled={loading} onClick={()=>setAttempt(n=>n+1)}>重新读取</button></header>
    <nav aria-label="关联资料类型">{[["person","人物"],["node","概念与理论"]].map(([value,label])=><button type="button" key={value} aria-pressed={kind===value} onClick={()=>{setKind(value);setPage(1);}}>{label}</button>)}</nav>
    {dirty?<p className={styles.warning}>先保存当前选材，再核对关联结果。</p>:null}
    {!loading&&!dirty&&result&&result.edit_version!==version?<p className={styles.warning}>文章版本已变化，请重新读取关联结果后选择。</p>:null}
    {error?<p role="alert" className={styles.warning}>{error}</p>:loading?<LoadingState role="status">正在读取已记录的关联…</LoadingState>:result?<><p>{result.notice}</p>{result.unavailable_count?<p className={styles.warning}>{result.unavailable_count} 项选材已失效，本次未用于查找关联。</p>:null}{result.truncated?<p>已达到本次关联范围上限，以下不是全部关系；可减少已选材料后继续核对。</p>:null}
      <p>本次可选 {result.count} 项 · 第 {page} 页</p>{result.results.map(row=>{const included=references.some(ref=>ref.type===row.target.type&&ref.id===row.target.id);return <article className={styles.candidate} key={`${row.target.type}:${row.target.id}`}><div className={styles.materialTitle}><IssueSourceThumbnail kind={row.target.type} src={row.source.image_url}/><h3>{row.source.title}</h3></div>{row.source.summary?<p>{row.source.summary}</p>:null}<ul>{row.reasons.map(reason=><li key={reason}>{reason}</li>)}</ul><footer><button type="button" disabled={locked||included||references.length>=40} onClick={()=>onChoose(row)}>{included?"已选":"加入已选"}</button><button type="button" disabled={locked} onClick={()=>onInsert(row)}>插入文章</button>{row.source.href?.startsWith("/")&&!row.source.href.startsWith("//")?<a href={row.source.href} target="_blank" rel="noopener">查看资料 ↗</a>:null}</footer></article>;})}
      {!result.results.length?<p className={styles.empty}>当前选材尚无可公开的已记录关联。可继续从馆藏选择资料。</p>:null}<nav aria-label="关联资料分页"><button type="button" disabled={!result.previous} onClick={()=>setPage(n=>n-1)}>上一页</button><button type="button" disabled={!result.next} onClick={()=>setPage(n=>n+1)}>下一页</button></nav>
    </>:null}
  </section>;
}
