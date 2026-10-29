"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useAdminSession } from "@/lib/admin-session";
import type { Paginated } from "@/lib/api/pagination";
import type { AdminTimelineEvent, TimelineEditorGuard } from "@/components/theory-system-admin";
import { Dialog } from "@/components/ui/dialog";
import styles from "./scholar-editor.module.css";

const EventEditor=dynamic(()=>import("@/components/theory-system-admin").then(module=>module.ScholarTimelineEditor),{ssr:false,loading:()=> <p role="status">正在打开原事件编辑器…</p>});

export function ScholarTimeline({scholarId,blocked,onChanged}:{scholarId:string;blocked:boolean;onChanged:()=>void}) {
  const user=useAdminSession(),owner=String(user?.id||"");
  const [page,setPage]=useState(1),[attempt,setAttempt]=useState(0),[data,setData]=useState<Paginated<AdminTimelineEvent>|null>(null),[error,setError]=useState("");
  const [selected,setSelected]=useState<string|null>(null),[notice,setNotice]=useState("");
  const guard=useRef<TimelineEditorGuard>({dirty:false,pending:false,composing:false}),ime=useRef(false);
  useEffect(()=>{
    if(!owner)return;
    const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    queueMicrotask(()=>{if(!controller.signal.aborted){setData(null);setError("");}});
    withPrivateOwner(owner,()=>apiRequest<Paginated<AdminTimelineEvent>>(`/catalog/admin/theory-timeline/?${new URLSearchParams({scholar:scholarId,page:String(page)})}`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal).then(value=>{if(!controller.signal.aborted)setData(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"事件读取失败。");});
    return()=>controller.abort();
  },[scholarId,owner,page,attempt]);
  function open(id:string){if(blocked)return;guard.current={dirty:false,pending:false,composing:false};setNotice("");setSelected(id);}
  function close(){
    if(ime.current||guard.current.composing)return;
    if(guard.current.pending){setNotice("请先查询或停止未确认的原操作，再关闭事件编辑。");return;}
    if(guard.current.dirty&&!window.confirm("事件有未保存输入，放弃并返回学者页吗？"))return;
    setSelected(null);setNotice("");setAttempt(value=>value+1);onChanged();
  }
  return <>
    <header><h2>生平时间线 <small>{data?.count??"…"}</small></h2><button type="button" disabled={blocked} onClick={()=>open("")}>＋ 添加事件</button></header>
    {blocked?<p>请先保存学者草稿，并核对未完成的操作，再编辑生平事件。</p>:null}
    {error?<p role="alert">{error}<button type="button" onClick={()=>setAttempt(value=>value+1)}>重新读取事件</button>{page>1?<button type="button" onClick={()=>setPage(1)}>返回第一页</button>:null}</p>:!data?<p role="status">正在读取原事件与当前编辑草稿…</p>:<>
      <ol className={styles.eventList}>{data.results.map(row=>{
        const stillRelated=row.scholar===scholarId||row.relations.some(relation=>relation.scholar===scholarId);
        const complete=Boolean(row.description.trim()&&row.source.trim()&&row.editorial_details?.confirmed);
        return <li key={row.id}><time>{row.date_label||row.start_date||row.start_year||"时间待核"}{!row.date_label&&row.end_year?`—${row.end_year}`:""}</time><div><strong>{row.title}</strong><small>{row.public_status==="approved"?"已公开":row.public_status==="rejected"?"已下线或不采用":"待核对"}{row.editorial_revision?" · 有未发布修改":""}{!complete?" · 资料待补":""}</small>{!stillRelated?<small>当前草稿已移除此学者，公开版本仍有关联；发布后将从此处移除。</small>:null}<p>{row.description}</p>{row.source?<details><summary>查看来源</summary><p>{row.source}</p>{row.evidence_printed_label?<small>出处页标 {row.evidence_printed_label}</small>:null}{row.evidence_file?.reader_href?<Link href={row.evidence_file.reader_href} target="_blank" rel="noopener">核对 PDF 第 {row.evidence_page} 页 ↗</Link>:row.evidence_asset?<small>{row.evidence_file?.detail||"原文件当前不可读，引用仍保留，请进入编辑核对。"}</small>:null}</details>:<small>请补充可核对的出处。</small>}</div><button type="button" disabled={blocked} onClick={()=>open(row.id)}>编辑</button></li>;
      })}</ol>
      {!data.count?<p>尚无生平事件。新建事件先保存草稿，补足出处并确认后再发布。</p>:null}
      {data.previous||data.next?<nav className={styles.pagination} aria-label="生平事件分页"><button type="button" disabled={!data.previous} onClick={()=>setPage(value=>Math.max(1,value-1))}>上一页</button><span>第 {page} 页 · 共 {data.count} 项</span><button type="button" disabled={!data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav>:null}
    </>}
    {selected!==null?<Dialog open onRequestClose={close} className={`${styles.relationDialog} ${styles.timelineDialog}`} aria-label="编辑生平事件" onCompositionStartCapture={()=>{ime.current=true;}} onCompositionEndCapture={()=>{ime.current=false;}}>
      <header><h2>编辑生平事件</h2><button type="button" onClick={close}>返回学者页</button></header>{notice?<p role="status">{notice}</p>:null}
      <EventEditor key={`${owner}:${selected}`} scholarId={scholarId} eventId={selected} onGuardChange={value=>{guard.current=value;}} onSaved={()=>setAttempt(value=>value+1)}/>
    </Dialog>:null}
  </>;
}
