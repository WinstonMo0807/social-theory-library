"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { Drawer } from "@/components/ui/dialog";
import { IssueBlockView } from "@/components/public/issue-block-view";
import type { IssueDraft } from "./use-issue-draft";
import styles from "./issue-editor.module.css";

type Revision={id:string;revision:number;status:string;created_at:string;created_by:string;note:string;is_current:boolean;block_count:number};
type Page={count:number;next:string|null;previous:string|null;results:Revision[]};
export function IssueHistory({issueId,onClose,onRestore,canRestore,request,initialRevision=""}:{issueId:string;onClose:()=>void;onRestore:(value:IssueDraft)=>void;canRestore:boolean;request:<T>(url:string,init?:RequestInit)=>Promise<T>;initialRevision?:string}) {
  const [page,setPage]=useState(1),[attempt,setAttempt]=useState(0),[data,setData]=useState<Page|null>(null),[error,setError]=useState("");
  const [selected,setSelected]=useState(initialRevision),[revision,setRevision]=useState<IssueDraft|null>(null),[detailError,setDetailError]=useState("");
  useEffect(()=>{
    let active=true;queueMicrotask(()=>{if(active){setData(null);setError("");}});
    void request<Page>(`/catalog/admin/recommendation-issues/${issueId}/history/?page=${page}`).then(value=>{if(active)setData(value);}).catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"历史读取失败。");});
    return()=>{active=false;};
  },[issueId,page,attempt,request]);
  useEffect(()=>{
    let active=true;queueMicrotask(()=>{if(active){setRevision(null);setDetailError("");}});
    if(selected)void request<IssueDraft>(`/catalog/admin/recommendation-issues/${issueId}/?revision=${selected}`).then(value=>{if(active)setRevision(value);}).catch(reason=>{if(active)setDetailError(reason instanceof Error?reason.message:"修订读取失败。");});
    return()=>{active=false;};
  },[selected,issueId,attempt,request]);
  return <Drawer open onRequestClose={onClose} className={styles.history} aria-label="专题版本历史"><header><h2>版本历史</h2><button type="button" aria-label="关闭版本历史" onClick={onClose}><X size={18}/></button></header><p>以下为实际保存与发布记录。恢复会先放入编辑区，保存后形成新的草稿。</p>
    {error?<p role="alert">{error}<button type="button" onClick={()=>setAttempt(value=>value+1)}>重试</button></p>:!data?<LoadingState role="status">正在读取保存记录…</LoadingState>:<><ol className={styles.revisions}>{data.results.map(row=><li key={row.id}><button type="button" aria-pressed={selected===row.id} onClick={()=>setSelected(row.id)}><strong>修订 {row.revision}{row.is_current?" · 当前版本":""}</strong><span>{row.status==="published"?"已发布":row.status==="draft"?"草稿":"历史草稿"} · {row.block_count} 个内容块</span><span>{row.created_by || "未记录署名"} · <time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString("zh-CN")}</time></span>{row.note?<span>{row.note}</span>:null}</button></li>)}</ol><nav aria-label="修订历史分页"><button type="button" disabled={!data.previous} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {page} 页 · 共 {data.count} 次修订</span><button type="button" disabled={!data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav></>}
    {selected?<section className={styles.historyPreview}><h3>修订内容</h3>{detailError?<p role="alert">{detailError}<button type="button" onClick={()=>setAttempt(value=>value+1)}>重试读取</button></p>:!revision?<LoadingState role="status">正在核对历史来源…</LoadingState>:<><h2>{revision.title}</h2><p>{revision.introduction}</p>{revision.body_blocks.map((block,index)=><section key={block.id || index}><IssueBlockView block={block}/></section>)}{revision.items.length?<p>包含 {revision.items.length} 项推荐：{revision.items.map(item=>item.title).join("、")}</p>:null}<button type="button" disabled={!canRestore} onClick={()=>{onRestore(revision);onClose();}}>将修订 {revision.viewed_revision} 恢复到编辑区</button>{!canRestore?<p>请先保存或处理当前输入，再恢复历史内容。</p>:null}</>}</section>:null}
  </Drawer>;
}
