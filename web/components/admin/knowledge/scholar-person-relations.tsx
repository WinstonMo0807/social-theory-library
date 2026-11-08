"use client";

import { confirmAction } from "@/lib/ui-dialog";


import { LoadingState } from "@/components/ui/loading-state";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useAdminSession } from "@/lib/admin-session";
import type { Paginated } from "@/lib/api/pagination";
import { relationArrow, scholarRelationLabels, scholarRelationStatus, type ScholarRelation } from "@/lib/api/scholar-relations.types";
import { Dialog } from "@/components/ui/dialog";
import { ScholarRelationsEditor, type ScholarRelationGuard } from "./scholar-relations-editor";
import styles from "./scholar-editor.module.css";

/** Same relationship records and editor, opened without leaving the scholar. */
export function ScholarPersonRelations({scholarId,blocked,onChanged}:{scholarId:string;blocked:boolean;onChanged:()=>void}) {
  const user=useAdminSession(),owner=String(user?.id||"");
  const [page,setPage]=useState(1),[attempt,setAttempt]=useState(0),[data,setData]=useState<Paginated<ScholarRelation>|null>(null),[error,setError]=useState("");
  const [selected,setSelected]=useState<string|null>(null),[notice,setNotice]=useState("");
  const guard=useRef<ScholarRelationGuard>({dirty:false,pending:false,composing:false}),ime=useRef(false);
  useEffect(()=>{
    if(!owner)return;
    const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    queueMicrotask(()=>{if(!controller.signal.aborted){setData(null);setError("");}});
    withPrivateOwner(owner,()=>apiRequest<Paginated<ScholarRelation>>(`/catalog/admin/scholar-relations/?${new URLSearchParams({scholar:scholarId,page:String(page)})}`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal).then(value=>{if(!controller.signal.aborted)setData(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"关系读取失败。");});
    return()=>controller.abort();
  },[scholarId,owner,page,attempt]);
  function open(id:string){if(blocked)return;guard.current={dirty:false,pending:false,composing:false};setNotice("");setSelected(id);}
  async function close(){
    if(ime.current||guard.current.composing)return;
    if(guard.current.pending){setNotice("请先核对原请求的结果，或使用停止未执行请求，再关闭编辑。");return;}
    if(guard.current.dirty&&!(await confirmAction("关系有未保存输入，放弃这些输入并返回学者页吗？")))return;
    setSelected(null);setNotice("");setAttempt(value=>value+1);onChanged();
  }
  return <>
    <header><h2>相关人物 <small>{data?.count??"…"}</small></h2><button type="button" disabled={blocked} onClick={()=>open("")}>＋ 关联人物</button></header>
    {blocked?<p>请先保存当前学者草稿，并核对未完成的操作，再编辑其关系。</p>:null}
    {error?<p role="alert">{error}<button type="button" onClick={()=>setAttempt(value=>value+1)}>重新读取关系</button></p>:!data?<LoadingState role="status">正在读取正式记录与待核对草稿…</LoadingState>:<>
      <ul>{data.results.map(row=><li key={row.id}><div><strong>{row.source_scholar===scholarId?row.target_name:row.source_name}</strong><small>{scholarRelationLabels[row.relation_type]} · {scholarRelationStatus(row)}</small><p>{row.source_name} {relationArrow(row.direction)} {row.target_name}</p>{row.summary?<p>{row.summary}</p>:null}{row.source?<details><summary>关系依据</summary><p>{row.source}</p></details>:<small>来源尚缺，可保存草稿，不能发布。</small>}</div><button type="button" disabled={blocked} onClick={()=>open(row.id)}>{row.has_unpublished_changes||row.status!=="published"?"核对":"编辑"}</button></li>)}</ul>
      {!data.count?<p>尚无人物关系。新建关系先保存草稿，有来源并明确发布后才对读者显示。</p>:null}
      {data.count>24?<nav className={styles.pagination} aria-label="相关人物分页"><button type="button" disabled={page===1} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {page} 页 · 共 {data.count} 项</span><button type="button" disabled={!data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>:null}
    </>}
    {selected!==null?<Dialog open onRequestClose={close} className={styles.relationDialog} aria-label="编辑学者关系" onCompositionStartCapture={()=>{ime.current=true;}} onCompositionEndCapture={()=>{ime.current=false;}}>
      <header><h2>编辑学者关系</h2><button type="button" onClick={close}>返回学者页</button></header>{notice?<p role="status">{notice}</p>:null}
      <ScholarRelationsEditor key={`${owner}:${selected}`} scholarId={scholarId} initialRelationId={selected} embedded onGuardChange={value=>{guard.current=value;}} onSaved={()=>setAttempt(value=>value+1)}/>
    </Dialog>:null}
  </>;
}
