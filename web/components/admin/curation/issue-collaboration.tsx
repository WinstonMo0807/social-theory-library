"use client";

import { useEffect, useRef, useState } from "react";
import styles from "./issue-editor.module.css";

type Presence={participants:Array<{id:string;name:string;is_self:boolean;mode:"editing"|"viewing";last_seen:string}>;checked_at:string;expires_after_seconds:number;shared:boolean;notice:string};
type History={results:Array<{id:string;revision:number;created_at:string;created_by:string;note:string;is_current:boolean}>};
export function IssueCollaboration({issueId,version,editing,request,onHistory}:{issueId:string;version:string;editing:boolean;request:<T>(url:string,init?:RequestInit)=>Promise<T>;onHistory:()=>void}) {
  const [presence,setPresence]=useState<Presence|null>(null),[error,setError]=useState(""),[history,setHistory]=useState<History|null>(null),[historyError,setHistoryError]=useState(""),[attempt,setAttempt]=useState(0);
  const mode=useRef(editing);useEffect(()=>{mode.current=editing;},[editing]);
  const endpoint=`/catalog/admin/recommendation-issues/${issueId}/`;
  useEffect(()=>{
    const controller=new AbortController(),session=crypto.randomUUID();let timer=0,running=false,changed=false;
    async function pulse() {
      if(controller.signal.aborted)return;
      if(running){changed=true;return;}
      running=true;changed=false;
      const visible=document.visibilityState==="visible";
      if(!visible)setPresence(null);
      try {
        const value=await request<Presence>(endpoint+"presence/",{method:"POST",signal:controller.signal,body:JSON.stringify({session_id:session,mode:visible?(mode.current?"editing":"viewing"):"leave"})});
        if(!controller.signal.aborted&&visible&&document.visibilityState==="visible"){setPresence(value);setError("");}
      } catch(reason) {if(!controller.signal.aborted){setPresence(null);setError(reason instanceof Error?reason.message:"协作状态暂时不可用。");}}
      finally {running=false;if(!controller.signal.aborted){if(changed)void pulse();else if(document.visibilityState==="visible")timer=window.setTimeout(()=>void pulse(),20000);}}
    }
    function visibility(){window.clearTimeout(timer);void pulse();}
    void pulse();document.addEventListener("visibilitychange",visibility);
    return()=>{controller.abort();window.clearTimeout(timer);document.removeEventListener("visibilitychange",visibility);};
  },[endpoint,request,attempt]);
  useEffect(()=>{
    const controller=new AbortController();queueMicrotask(()=>{if(!controller.signal.aborted){setHistory(null);setHistoryError("");}});
    void request<History>(endpoint+"history/",{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setHistory(value);}).catch(reason=>{if(!controller.signal.aborted)setHistoryError(reason instanceof Error?reason.message:"版本历史读取失败。");});
    return()=>controller.abort();
  },[endpoint,version,request,attempt]);
  return <section className={styles.collaboration} aria-label="协作与版本"><header><h2>协作与版本</h2><button type="button" onClick={()=>setAttempt(value=>value+1)}>重新读取</button></header>
    {error?<p role="status">{error} 未将未确认的连接显示为在线。</p>:!presence?<p role="status">正在读取当前协作状态…</p>:<><ul className={styles.participants}>{presence.participants.map(row=><li key={row.id}><span aria-hidden="true">{Array.from(row.name)[0] || "·"}</span><div><strong>{row.is_self?"我":row.name}</strong><small>{row.mode==="editing"?"编辑中 · 有未保存输入":"浏览中"} · <time dateTime={row.last_seen}>{new Date(row.last_seen).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"})}</time>最近连接</small></div></li>)}</ul><p>{presence.notice}</p>{!presence.participants.length?<p>当前没有可确认的连接。</p>:null}</>}
    <header><h3>版本历史</h3><button type="button" onClick={onHistory}>查看全部版本</button></header>{historyError?<p role="alert">{historyError}</p>:!history?<p>正在读取保存记录…</p>:<ol className={styles.recentVersions}>{history.results.slice(0,4).map(row=><li key={row.id}><button type="button" onClick={onHistory}><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleString("zh-CN",{month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit"})}</time><span>{row.note || "保存草稿"}</span><span>{row.created_by || "未记录署名"}</span>{row.is_current?<small>当前版本</small>:null}</button></li>)}</ol>}
  </section>;
}
