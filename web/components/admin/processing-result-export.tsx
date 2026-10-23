"use client";

import {useCallback, useEffect, useRef, useState, type FormEvent} from "react";
import {apiRequest, getServerSessionCredential} from "@/lib/api";
import {apiEndpoint} from "@/lib/runtime-api";
import {withPrivateOwner} from "@/lib/api/private-owner";
import {usePersistentWorkspace} from "@/lib/api/use-persistent-workspace";
import type {components} from "@/lib/api/generated/schema";
import styles from "./processing-workspace.module.css";

type Manifest=components["schemas"]["ProcessingResultManifest"];
export function ProcessingResultExport({owner,taskId}:{owner:string;taskId:string}){
  const [from,setFrom]=useState("1"),[to,setTo]=useState(""),[range,setRange]=useState({from:"1",to:""});
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(""),[error,setError]=useState("");
  const lifetime=useRef<AbortController|null>(null);
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;return()=>controller.abort();},[]);
  const params=new URLSearchParams({page_from:range.from});if(range.to)params.set("page_to",range.to);
  const path=`/ingestion/processing-workspace/results/${taskId}/?${params}`;
  const load=useCallback(async(url:string,signal:AbortSignal)=>{const result=await apiRequest<Manifest>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false);if(result.owner_id!==owner||result.task_id!==taskId)throw Error("结果不属于当前账户或任务，请重新打开。");return result;},[owner,taskId]);
  const resource=usePersistentWorkspace<Manifest>(path,owner,undefined,load),data=resource.data;
  const rangeChanged=from!==range.from||to!==range.to;
  function read(event:FormEvent){event.preventDefault();setRange({from,to});setError("");setMessage("");resource.reload();}
  async function download(format:string){
    const active=lifetime.current;if(!active||active.signal.aborted||busy||!data||rangeChanged||resource.error)return;
    setBusy(true);setMessage("");setError("");
    const signal=AbortSignal.any([active.signal,AbortSignal.timeout(120000)]);
    try{
      const query=new URLSearchParams(params);query.set("download",format);query.set("expected_version",data.version);
      const blob=await withPrivateOwner(owner,async()=>{
        const response=await fetch(apiEndpoint(`/ingestion/processing-workspace/results/${taskId}/?${query}`),{credentials:"include",cache:"no-store",signal,headers:{"X-Editor-Owner":owner}});
        if(!response.ok){const failure=await response.json().catch(()=>null);const detail=failure?.detail??failure?.error?.detail?.detail??failure?.error?.detail;throw Error(typeof detail==="string"?detail:`结果暂时无法导出（${response.status}），请重新读取范围。`);}
        return response.blob();
      },signal);
      if(signal.aborted)return;
      const url=URL.createObjectURL(blob),anchor=document.createElement("a");anchor.href=url;anchor.download=`stl-task-${taskId}-${data.kind}.${format}`;document.body.appendChild(anchor);anchor.click();anchor.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
      setMessage(`已生成包含 ${data.count} ${data.kind==="ocr"?"页文字":"个目录条目"}的下载文件。`);
    }catch(reason){if(!active.signal.aborted)setError(reason instanceof Error?reason.message:"导出未完成，请重新读取范围后重试。");}
    finally{if(!active.signal.aborted)setBusy(false);}
  }
  return <section className={styles.resultExport} aria-busy={busy}><h3>导出已保存结果</h3><p className={styles.note}>先读取本任务的可导出范围。导出保留来源和状态说明，可按PDF页序分批下载。</p>
    <form className={styles.exportRange} onSubmit={read}><label>起始PDF页<input type="number" min={1} max={data?.page_count||20000} required value={from} disabled={busy} onChange={event=>setFrom(event.target.value)}/></label><label>结束PDF页<input type="number" min={Number(from)||1} max={data?.page_count||20000} value={to} disabled={busy} placeholder="文件末页" onChange={event=>setTo(event.target.value)}/></label><button type="submit" disabled={busy}>读取范围</button></form>
    {resource.error?<p role="alert">{resource.error}<button type="button" disabled={busy} onClick={resource.reload}>重新读取</button></p>:null}{!data&&!resource.error?<p role="status">正在核对原任务结果…</p>:null}
    {data?<><p>{data.notice}</p><p className={styles.note}>本任务已记录 {data.total_recorded} {data.kind==="ocr"?"页成功文字":"个目录条目"}，所选范围内 {data.count} 项。范围：PDF {range.from}–{range.to||data.page_count}。</p>{rangeChanged?<p role="status">页序输入已变化，请先读取新范围。</p>:null}<div className={styles.exportActions}>{data.formats.map(format=><button type="button" key={format} disabled={busy||rangeChanged||Boolean(resource.error)} onClick={()=>void download(format)}>{busy?"正在准备文件…":format==="txt"?"下载纯文本 TXT":"下载结构化记录 JSONL"}</button>)}</div></>:null}
    {error?<p role="alert">{error}</p>:null}{message?<p role="status">{message}</p>:null}
  </section>;
}
