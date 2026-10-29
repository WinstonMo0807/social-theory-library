"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { uploadNeedsRefresh, type DocumentStage as Stage, type UploadStageState as Item } from "@/lib/ingestion-staging-status";
import type { components } from "@/lib/api/generated/schema";
import { useCatalogCommand } from "./use-intake-command";
import styles from "./upload-batch-view.module.css";

type Queue = components["schemas"]["ProcessingWorkspace"];
type Job = components["schemas"]["ProcessingWorkspaceTask"];
type Receipt = components["schemas"]["ProcessingReceipt"];
type Action = "pause"|"resume"|"cancel";
type Command = {job_id:string;source:Job["source"];expected_version:string;action:Action};
const labels:Record<string,string>={file:"文件与正文",ocr:"OCR识别",index:"检索索引"};
const statuses:Record<string,string>={pending:"等待处理",queued:"等待处理",running:"处理中",paused:"已暂停",succeeded:"已完成",completed:"已完成",failed:"处理失败",partial:"部分失败",canceled:"已取消"};
const actions:Record<Action,string>={pause:"暂停处理",resume:"继续处理",cancel:"取消后续处理"};
const active=(value:string)=>["pending","queued","running","paused"].includes(value);

/** Mounted only inside the selected upload's open details, never for all batch rows. */
export function UploadProcessingControls({owner,itemId}:{owner:string;itemId:string}){
  const user=useAdminSession();
  if(!hasAdminCapability(user,"can_view_system_status"))return <p>后台处理的暂停与继续需要任务管理权限；文件和已完成结果保留，可联系管理员核对。</p>;
  return <Controls key={`${owner}:${itemId}`} owner={owner} itemId={itemId}/>;
}

function Controls({owner,itemId}:{owner:string;itemId:string}){
  const [selected,setSelected]=useState(""),[message,setMessage]=useState(""),[confirm,setConfirm]=useState<Job|null>(null);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const loadItem=useCallback((path:string,signal:AbortSignal)=>apiRequest<Item>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const item=usePersistentWorkspace<Item>(`/ingestion/items/${itemId}/`,owner,data=>uploadNeedsRefresh(data)?5000:null,loadItem);
  const stages=Object.entries(item.data?.document_stages||{}).filter((entry):entry is [string,Stage]=>Boolean(entry[1]));
  const current=stages.find(([name])=>name===selected)||stages.find(([,stage])=>stage.job_id&&["running","paused","pending"].includes(stage.status))||stages.find(([,stage])=>stage.job_id)||stages[0];
  const stage=current?.[1],path=stage?.job_id&&["processing_job","semantic_index_job"].includes(stage.source)?`/ingestion/processing-workspace/?task_id=${stage.job_id}&task_source=${stage.source}`:"";
  const loadTask=useCallback((url:string,signal:AbortSignal)=>apiRequest<Queue>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const task=usePersistentWorkspace<Queue>(path,owner,data=>data.results.some(row=>active(row.status))?5000:null,loadTask);
  const job=task.data?.results[0];
  const command=useCatalogCommand<Command,Receipt>(owner,"/ingestion/processing-workspace/",`stl-processing-command:${owner}`);
  const locked=!command.ready||command.busy||!!command.recovery;
  useUnsavedForm(Boolean(command.recovery),false);
  function accept(receipt:Receipt|null){
    if(!mounted.current||!receipt)return;
    setConfirm(null);setMessage(receipt.state==="cancelled"?"原待定操作已停止，没有撤销已执行任务。":"操作已记录；暂停需要等待当前安全步骤结束，请以刷新后的状态为准。");
    task.reload();item.reload();
  }
  async function execute(row:Job,action:Action){
    if(locked||!row.actions.includes(action))return;
    setMessage("");accept(await command.send({job_id:row.id,source:row.source,action,expected_version:row.version}));
  }
  return <section className={styles.taskControls} aria-label="此文件的后台处理控制">
    <h3>后台处理</h3><p>这里只控制所选文件阶段；已上传文件、已保存页和原处理记录保留。</p>
    {item.error?<p role="alert">{item.error}<button type="button" onClick={item.reload}>重新读取</button></p>:null}
    {command.error?<p role="alert">{command.error}</p>:null}
    {message?<p role="status">{message}</p>:null}
    {command.recovery?<div className={styles.notice}><p>上次任务操作尚未确认，先查询原结果再继续。关闭详情后，原请求编号仍保留。</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={()=>void command.lookup().then(accept)}>查询原操作</button>{command.canRetry?<button type="button" disabled={command.busy} onClick={()=>void command.send().then(accept)}>按原请求重试</button>:null}<button type="button" disabled={command.busy} onClick={()=>void command.lookup(true).then(accept)}>停止未执行操作</button></div></div>:null}
    <nav className={styles.actions} aria-label="处理阶段">{stages.map(([name,value])=><button type="button" key={name} aria-pressed={current?.[0]===name} disabled={locked} onClick={()=>{setSelected(name);setConfirm(null);}}>{labels[name]||"处理阶段"} · {statuses[value.status]||"以收件状态为准"}</button>)}</nav>
    {task.error?<p role="alert">{task.error}<button type="button" onClick={task.reload}>刷新任务</button></p>:job?<>
      <p>{job.pause_requested&&job.status==="running"?"已请求暂停，等待当前步骤结束":statuses[job.status]||"状态待核对"} · {job.progress}%</p>
      {job.last_error?<p role="alert">{job.last_error}</p>:null}
      {job.permission_reason?<p>{job.permission_reason}</p>:null}
      <div className={styles.actions}>{(["pause","resume","cancel"] as const).filter(action=>job.actions.includes(action)).map(action=><button type="button" key={action} disabled={locked} onClick={()=>action==="cancel"?setConfirm(job):void execute(job,action)}>{actions[action]}</button>)}<Link href={`/admin/processing?task_id=${job.id}&task_source=${job.source}`}>打开完整任务详情</Link></div>
    </>:path?<p role="status">{task.data?"此任务当前不可用，请刷新收件记录。":"正在核对后台任务状态…"}</p>:<p>{item.data?"当前阶段尚无可单独暂停的任务；后台处理继续时会在此更新。":"正在读取当前文件的处理阶段…"}</p>}
    {confirm?<section className={styles.notice} aria-label="确认取消后续处理"><h4>取消当前任务的后续步骤？</h4><p>已保存的页和结果保留。正在完成的步骤可能先保存，状态变化时需要重新核对。</p><div className={styles.actions}><button type="button" disabled={locked} onClick={()=>setConfirm(null)}>返回核对</button><button type="button" disabled={locked} onClick={()=>void execute(confirm,"cancel")}>确认取消后续步骤</button></div></section>:null}
  </section>;
}
