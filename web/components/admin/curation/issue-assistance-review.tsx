"use client";
import { SourceText } from "@/components/source-text";


import { confirmAction } from "@/lib/ui-dialog";

import { createRequestKey } from "../../../lib/request-key";
import { useEffect, useRef, useState } from "react";
import { PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { ApiRequestError } from "@/lib/api";
import type { EditorialAssistance } from "@/lib/api/curation-workspace.client";
import { editorialAssistancePath } from "@/lib/api/curation-workspace.client";
import { pollBudgetExpired, taskPollDelay } from "@/lib/api/task-polling";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { IssueBlock, IssueSelection } from "@/lib/api/recommendation-issues.types";
import styles from "./issue-selection.module.css";

type Task=EditorialAssistance;
type Pending={path:string;body:string;refresh:boolean};
type Receipt={owner_id:string;issue_id:string;request_id:string;state:"applied"|"cancelled";operation:"request"|"adopt"|"dismiss"|"retry"|"cancel"|"stop";task:Task|null};
const names={outline:"结构提纲",guide:"内容修改",comparison:"比较视角"};
export function IssueAssistanceReview({owner,onApplied,issueId,version,selection,blocks,operation,onOperation,onRelated,disabled,dirty,request,auxiliary,onPending,onDirty}: {owner:string;onApplied:()=>Promise<void>;issueId:string;version:string;selection:IssueSelection;blocks:IssueBlock[];operation:Task["operation"];onOperation:(operation:Task["operation"])=>void;onRelated:()=>void;disabled:boolean;dirty:boolean;request:<T>(url:string,init?:RequestInit)=>Promise<T>;auxiliary:<T>(url:string,body:string,refresh?:boolean)=>Promise<T>;onPending:(value:boolean)=>void;onDirty:(value:boolean)=>void}) {
  const [task,setTask]=useState<Task|null>(null),[error,setError]=useState(""),[message,setMessage]=useState("");
  const [history,setHistory]=useState<Task[]>([]),[historyPage,setHistoryPage]=useState(1),[pages,setPages]=useState(1),[showHistory,setShowHistory]=useState(false),[attempt,setAttempt]=useState(0);
  const [pending,setPending]=useState<Pending|null>(null),[busy,setBusy]=useState(false),[edits,setEdits]=useState<Record<string,string>>({});
  const lifetime=useRef<AbortController|null>(null),inFlight=useRef(false),generation=useRef(0);
  const endpoint=editorialAssistancePath(issueId),storageKey=`stl-assistance-command:${owner}:${issueId}`;
  const [recovery,setRecovery]=useState(""),[ready,setReady]=useState(false);
  const taskId=task?.id,taskRunning=Boolean(taskPollDelay(task||{}));
  useUnsavedForm({pending,recovery,edits},{pending:null,recovery:"",edits:{}});
  useEffect(()=>{onDirty(Boolean(Object.keys(edits).length));return()=>onDirty(false);},[edits,onDirty]);
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;queueMicrotask(()=>{if(controller.signal.aborted)return;try{const saved=sessionStorage.getItem(storageKey)||"";if(saved&&!/^[0-9a-f-]{36}$/i.test(saved))throw Error("原操作编号格式异常，请保留本页并核对助手任务历史。");setRecovery(saved);onPending(Boolean(saved));setReady(true);}catch(reason){setError(reason instanceof Error?reason.message:"浏览器不能保留请求编号，请保留当前页面。");}});return()=>controller.abort();},[storageKey,onPending]);
  function clearRecovery(){try{sessionStorage.removeItem(storageKey);}catch{setError("原结果已收到，但浏览器不能清除恢复标记。请保留此页并稍后查询。");return false;}setRecovery("");setPending(null);onPending(false);return true;}
  async function lookup(cancel=false){
    if(!ready||!recovery||inFlight.current)return;inFlight.current=true;setBusy(true);setError("");
    try{
      const value=await request<Receipt>(`${endpoint}commands/${recovery}/`,cancel?{method:"POST",body:JSON.stringify({action:"cancel_pending"})}:{});
      if(lifetime.current?.signal.aborted)return;
      if(value.owner_id!==owner||value.issue_id!==issueId||value.request_id!==recovery||!["applied","cancelled"].includes(value.state))throw Error("原操作结果与当前页面不一致，请重新核对。");
      if(value.state==="applied"&&value.operation==="adopt")await onApplied();
      if(lifetime.current?.signal.aborted)return;
      if(value.task){setTask(value.task);setEdits(previous=>Object.fromEntries(Object.entries(previous).filter(([id])=>!value.task!.adopted_ids.includes(id)&&!value.task!.dismissed_ids.includes(id))));}
      if(!clearRecovery())return;setAttempt(n=>n+1);setMessage(value.state==="cancelled"?"已停止未执行的原操作；已运行任务和已采用文字没有撤销。":"已查询原操作，任务和文章按现有结果继续。");
    }catch(reason){if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"原操作暂时无法查询，请保留原编号后重试。");}
    finally{inFlight.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  useEffect(()=>{
    const controller=new AbortController();
    void request<{results:Task[];total_pages:number}>(`${endpoint}?page=${historyPage}`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted){setHistory(value.results);setPages(value.total_pages);}}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"历史读取失败。");});
    return()=>controller.abort();
  },[endpoint,historyPage,attempt,request]);
  useEffect(()=>{
    if(!taskId||!taskRunning)return;
    const controller=new AbortController(),started=Date.now(),expected=generation.current;let timer:ReturnType<typeof setTimeout>;
    const read=async()=>{
      if(controller.signal.aborted)return;
      if(pollBudgetExpired(started)){setMessage("自动刷新已暂停，请读取当前进度；后台任务可能仍在继续。");return;}
      if(document.visibilityState!=="visible"||inFlight.current){timer=setTimeout(read,3000);return;}
      try{const value=await request<Task>(editorialAssistancePath(issueId,taskId),{signal:controller.signal});if(controller.signal.aborted||expected!==generation.current)return;setTask(value);const delay=taskPollDelay(value);if(delay)timer=setTimeout(read,delay);}
      catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"任务状态读取失败。");}
    };
    timer=setTimeout(read,1500);return()=>{controller.abort();clearTimeout(timer);};
  // Status changes restart the foreground observation budget; candidates never start a task implicitly.
  },[issueId,taskId,taskRunning,attempt,request]);
  const selectedReady=selection.references.length>0&&selection.materials?.length===selection.references.length&&selection.materials.every(row=>row.available&&row.public_eligible);
  const locked=!ready||disabled||dirty||busy||Boolean(pending)||Boolean(recovery);
  async function send(command:Pending){
    if(!ready||inFlight.current)return;
    try{const id=String(JSON.parse(command.body).request_id||"");if(!id||recovery&&recovery!==id)throw Error("请先查询原操作。");sessionStorage.setItem(storageKey,id);setRecovery(id);}catch(reason){setError(reason instanceof Error?reason.message:"无法保留原请求编号，请保留当前页面。");return;}
    inFlight.current=true;generation.current+=1;setBusy(true);setPending(command);onPending(true);setError("");setMessage("");
    try{const result=await auxiliary<Task>(command.path,command.body,command.refresh);if(lifetime.current?.signal.aborted)return;setTask(result);if(!clearRecovery())return;setEdits(previous=>Object.fromEntries(Object.entries(previous).filter(([id])=>!result.adopted_ids.includes(id)&&!result.dismissed_ids.includes(id))));setAttempt(value=>value+1);setMessage(command.refresh?"已追加到文章草稿，原有人工段落保留。":"操作已保存。");}
    catch(reason){if(lifetime.current?.signal.aborted)return;const definite=reason instanceof ApiRequestError&&!(reason instanceof PrivateOwnerVerificationError)&&[400,409].includes(reason.status);if(definite&&!clearRecovery())return;setError(definite?(reason as Error).message:"暂时无法确认操作结果。请重试同一请求，或读取任务历史核对；已选材料保持原样。");}
    finally{inFlight.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  function start(){if(locked||!selectedReady||!selection.question.trim()||Object.keys(edits).length)return;void send({path:endpoint,refresh:false,body:JSON.stringify({request_id:createRequestKey(),edit_version:version,operation,question:selection.question,references:selection.references})});}
  function act(action:"adopt"|"dismiss"|"retry"|"cancel",id?:string){
    if(!task||locked)return;
    void send({path:editorialAssistancePath(issueId,task.id),refresh:action==="adopt",body:JSON.stringify({action,request_id:createRequestKey(),edit_version:task.edit_version,task_token:task.task_token,...(id?{suggestion_ids:[id]}:{}),...(id&&edits[id]!==undefined?{edits:{[id]:edits[id]}}:{})})});
  }
  async function refresh(){if(!task||busy)return;try{const value=await request<Task>(editorialAssistancePath(issueId,task.id),{signal:lifetime.current?.signal});if(!lifetime.current?.signal.aborted){setTask(value);setAttempt(n=>n+1);setError("");}}catch(reason){if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"任务读取失败。");}}
  const stale=Boolean(task&&(task.draft_changed||task.edit_version!==version));
  const numbering=[0,0,0];
  const labels=task?.suggestions.map(row=>{if(row.kind!=="heading")return "导读";const level=row.level||1;numbering[level-1]+=1;numbering.fill(0,level);return `${numbering.slice(0,level).join(".")} · ${level}级提纲`;})||[];
  return <aside className={styles.assistant} aria-label="智能助手建议"><header><h2>智能助手建议</h2><button type="button" onClick={()=>setShowHistory(value=>!value)}>历史记录</button></header>
    <nav aria-label="生成建议类型">{Object.entries(names).filter(([key])=>key!=="comparison").map(([key,label])=><button type="button" key={key} aria-pressed={operation===key} disabled={!ready||busy||Boolean(recovery)} onClick={()=>onOperation(key as Task["operation"])}>{label}</button>)}<button type="button" onClick={onRelated}>概念关联</button><button type="button" aria-pressed={operation==="comparison"} disabled={!ready||busy||Boolean(recovery)} onClick={()=>onOperation("comparison")}>比较视角</button></nav>
    <p>依据已选公开材料生成待审阅文字。采用只追加草稿，原文和人工段落保持原样。</p><button type="button" className={styles.gold} disabled={locked||!selectedReady||!selection.question.trim()||Boolean(taskPollDelay(task||{}))||Boolean(Object.keys(edits).length)} onClick={start}>生成{names[operation]}</button>
    {dirty?<p>请先保存当前选材与问题，再生成或采用建议。</p>:!selectedReady?<p>请选择并保存至少一项当前可公开的材料。</p>:null}
    {error?<p role="alert" className={styles.warning}>{error}</p>:null}{message?<p role="status">{message}</p>:null}
    {recovery?<section className={styles.warning} role="status"><p>上次操作尚未确认，原编号已按账户保留。先查询结果，再继续生成或采用。</p><button type="button" disabled={busy} onClick={()=>void lookup()}>查询原操作</button>{pending?<button type="button" disabled={busy||disabled||dirty} onClick={()=>void send(pending)}>重试同一请求</button>:null}<button type="button" disabled={busy} onClick={()=>void lookup(true)}>停止未执行请求</button></section>:null}
    {showHistory?<section aria-label="助手任务历史"><h3>任务历史</h3>{history.map(row=><button type="button" key={row.id} disabled={!ready||busy||Boolean(recovery)} onClick={async ()=>{if(Object.keys(edits).length&&!(await confirmAction("尚有未采用的审阅修改，切换任务会放弃这些修改。是否继续？")))return;generation.current+=1;setTask(row);setEdits({});}}>{names[row.operation]} · {new Date(row.created_at).toLocaleString("zh-CN")} · {row.created_by}</button>)}{!history.length?<p>尚无助手任务。</p>:null}<nav><button type="button" disabled={historyPage===1} onClick={()=>setHistoryPage(n=>n-1)}>上一页</button><span>{historyPage} / {pages}</span><button type="button" disabled={historyPage>=pages} onClick={()=>setHistoryPage(n=>n+1)}>下一页</button></nav></section>:null}
    {task?<section aria-label="当前助手任务"><header><h3>{names[task.operation]}</h3><button type="button" disabled={busy} onClick={()=>void refresh()}>读取进度</button></header><p>{task.question}</p>
      {taskPollDelay(task)?<><p role="status">{task.status==="pending"?"任务已排队":"正在生成候选…"}</p><progress aria-label={`${names[task.operation]}生成进度`} max={100} value={task.progress}/><button type="button" disabled={locked} onClick={()=>act("cancel")}>取消当前任务</button></>:null}
      {task.status==="failed"?<div className={styles.warning}><h3>{task.stage==="partial"?"任务部分完成":"智能助手暂不可用"}</h3><p>{task.error_message} 已选材料仍可用于人工编辑。{task.suggestions.length?` 已保留 ${task.suggestions.length} 条完整候选，可逐项审阅；重试将重新生成尚未采用的候选。`:""}</p><button type="button" disabled={locked||stale||!task.source_available||Boolean(task.adopted_ids.length)||Boolean(Object.keys(edits).length)} onClick={()=>act("retry")}>重试任务</button>{task.stage==="partial"?<button type="button" disabled={locked} onClick={()=>act("cancel")}>取消任务并保留完整候选</button>:null}</div>:null}
      {task.status==="canceled"?<p>任务已取消，已选材料和人工草稿保留。</p>:null}
      {stale?<p className={styles.warning}>建议所依据的正文版本已有变化。请比较原文与当前文章；重新生成前不自动合并或覆盖人工内容。</p>:null}
      {!task.source_available?<p className={styles.warning}>有来源已失效，当前不能采用这些建议。可保留人工输入并重新选材。</p>:null}
      {task.suggestions.map((row,index)=>{const adopted=task.adopted_ids.includes(row.id),dismissed=task.dismissed_ids?.includes(row.id),done=adopted||dismissed,current=blocks.find(block=>block.id===row.target_block_id);return <article key={row.id} className={styles.suggestion} data-level={row.kind==="heading"?row.level||1:undefined} aria-label={`${labels[index]}建议`}><header><span>{labels[index]}{done?adopted?" · 已采用":" · 已忽略":""}</span><small>{row.source_keys.length} 项依据</small></header>
        {row.target_block_id?<section className={styles.proseComparison} aria-label="人工正文对比"><h4>涉及已有段落，请核对</h4><p>建议关联到当前文章中的人工段落。是否存在观点冲突，由编辑依据材料判断。</p><strong>生成时的人工文字</strong><blockquote>{row.original_text||"当时该段尚未填写文字。"}</blockquote>{!current?<p className={styles.warning}>当前正文已没有这一段，请重新生成后再处理。</p>:current.text!==row.original_text?<><strong>当前人工文字</strong><blockquote>{current.text||"当前该段为空。"}</blockquote><p className={styles.warning}>这一段在生成后已有变化。</p></>:null}<strong>助手建议{edits[row.id]!==undefined?" · 审阅修改中":""}</strong></section>:null}
        {edits[row.id]===undefined?<p className={styles.suggestionText}>{row.text}</p>:<label>审阅修改<textarea maxLength={6000} value={edits[row.id]} disabled={locked} onChange={event=>setEdits(value=>({...value,[row.id]:event.target.value}))}/></label>}{row.gap?<p className={styles.warning}>材料缺口：{row.gap}</p>:null}<details data-disclosure="collection"><summary>查看依据与原文对比</summary>{row.source_keys.map(key=>{const source=task.sources.find(value=>value.source_key===key)?.source;return source?<div key={key}><strong>{source.title}</strong><p>{source.edition_label}</p>{source.text?<blockquote><SourceText text={(source.text) || ""} /></blockquote>:<p>{source.summary || "这条依据为资料记录，尚无直接原文。"}</p>}{source.reader_url?.startsWith("/reader/")?<a href={source.reader_url} target="_blank" rel="noopener">查看原文 ↗</a>:null}</div>:<p key={key}>该来源当前不可读。</p>;})}{!row.source_keys.length?<p>本项没有直接原文依据，请核对其标题或材料缺口。</p>:null}</details>{row.target_block_id?<p>采用后追加为新草稿段落；原段落保留，可继续在编辑区整理。</p>:null}<footer><button type="button" className={styles.gold} disabled={locked||done||stale||!task.can_adopt||edits[row.id]?.trim()===""||Boolean(row.target_block_id&&!current)} onClick={()=>act("adopt",row.id)}>采用</button><button type="button" disabled={locked||done} onClick={()=>setEdits(value=>({...value,[row.id]:value[row.id]??row.text}))}>修改</button><button type="button" disabled={locked||done} onClick={()=>act("dismiss",row.id)}>忽略</button></footer></article>;})}
    </section>:<p className={styles.empty}>尚未生成建议。先确定策划问题，再选择材料。</p>}
  </aside>;
}
