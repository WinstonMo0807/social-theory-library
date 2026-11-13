"use client";
import { SourceText } from "@/components/source-text";



import { LoadingState } from "@/components/ui/loading-state";
import { FileSearch, BookOpen } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { taskPollDelay } from "@/lib/api/task-polling";
import type { DiscoveryContext, DiscoveryPassage, DiscoverySearch, DiscoverySort } from "@/lib/api/discovery.types";
import { canKeepDiscoveryContext } from "@/lib/api/discovery.client";
import type { IssueSelection, IssueSourceReference } from "@/lib/api/recommendation-issues.types";
import { EditorialImage } from "@/components/public/editorial-directory";
import { Dialog } from "@/components/ui/dialog";
import type { IssueSourceChoice } from "./issue-source-picker";
import styles from "./issue-selection.module.css";

export function IssueDiscoveryMaterials({issueId,owner,selection,disabled,request,onChoose,onInsert,onRemove,onAdjustScope,onRelated}:{issueId:string;owner:string;selection:IssueSelection;disabled:boolean;request:<T>(url:string,init?:RequestInit)=>Promise<T>;onChoose:(choice:IssueSourceChoice)=>void;onInsert:(choice:IssueSourceChoice)=>void;onRemove:(ref:IssueSourceReference)=>void;onAdjustScope:()=>void;onRelated:()=>void}) {
  const [session,setSession]=useState(""),[limit,setLimit]=useState(6),[sort,setSort]=useState<DiscoverySort>("relevance"),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const [context,setContext]=useState<DiscoveryContext|null>(null),[contextOpen,setContextOpen]=useState(false);
  const lifetime=useRef<AbortController|null>(null),operation=useRef(false),contextVersion=useRef(0),contextAnchor=useRef<DiscoveryPassage|null>(null);
  const callbacks=useRef({onChoose,onInsert,disabled});
  useLayoutEffect(()=>{callbacks.current={onChoose,onInsert,disabled};},[onChoose,onInsert,disabled]);
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;return()=>controller.abort();},[]);
  const load=useCallback((path:string,signal:AbortSignal)=>request<DiscoverySearch>(path,{signal}),[request]);
  const resource=usePersistentWorkspace<DiscoverySearch>(session?`/catalog/discovery-search/${session}/?limit=${limit}&sort=${sort}`:"",owner,taskPollDelay,load);
  const result=resource.data;
  useEffect(()=>{
    if(!result||!contextAnchor.current||canKeepDiscoveryContext(contextAnchor.current,result))return;
    contextAnchor.current=null;contextVersion.current+=1;
    queueMicrotask(()=>{setContext(null);setContextOpen(false);setError("候选来源已重新读取，请重新打开上下文核对。");});
  },[result]);
  async function start(){
    if(disabled||operation.current||!selection.query.trim())return;operation.current=true;contextAnchor.current=null;contextVersion.current+=1;setBusy(true);setError("");setContext(null);setContextOpen(false);
    try{const next=await request<DiscoverySearch>("/catalog/discovery-search/",{method:"POST",body:JSON.stringify({q:selection.query,filters:selection.filters}),signal:lifetime.current?.signal});if(!lifetime.current?.signal.aborted){setSession(next.id);setLimit(6);}}
    catch(reason){if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"本次检索未确认，已选材料保留。");}
    finally{operation.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  async function choose(row:DiscoveryPassage,insert=false){
    if(disabled||operation.current||!row.evidence_span_id)return;operation.current=true;setBusy(true);setError("");
    try{const params=new URLSearchParams({type:"span",id:row.evidence_span_id,document_revision_id:row.document_revision_id});const value=await request<{results:IssueSourceChoice[]}>(`/catalog/admin/recommendation-issues/${issueId}/sources/?${params}`,{signal:lifetime.current?.signal});if(!lifetime.current?.signal.aborted&&value.results[0]){if(callbacks.current.disabled){setError("草稿正在保存或等待核对，请完成后再次选择这份材料。");return;}if(insert)callbacks.current.onInsert(value.results[0]);else callbacks.current.onChoose(value.results[0]);}}
    catch(reason){if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"来源已变化，请重新读取候选。");}
    finally{operation.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  async function readContext(row:DiscoveryPassage){
    const expected=++contextVersion.current;contextAnchor.current=row;setContext(null);setContextOpen(true);setError("");
    try{const value=await request<DiscoveryContext>(`/catalog/discovery-search/${session}/context/?result_id=${encodeURIComponent(row.id)}`,{signal:lifetime.current?.signal});if(!lifetime.current?.signal.aborted&&expected===contextVersion.current)setContext(value);}
    catch(reason){if(!lifetime.current?.signal.aborted&&expected===contextVersion.current)setError(reason instanceof Error?reason.message:"原文上下文读取失败。");}
  }
  async function taskAction(action:"cancel"|"retry"){
    if(!result||operation.current)return;operation.current=true;setBusy(true);
    try{await request(`/catalog/discovery-search/${result.id}/${action}/`,{method:"POST",body:JSON.stringify(action==="retry"?{expected_generation:result.generation}:{}),signal:lifetime.current?.signal});if(!lifetime.current?.signal.aborted)resource.reload();}
    catch(reason){if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"任务操作未确认，请读取进度核对。");}
    finally{operation.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  return <section className={styles.candidates} aria-label="原文候选"><header><h2>原文候选 {result?.count??""}</h2><select data-stl-select aria-label="候选排序" value={sort} onChange={event=>setSort(event.target.value as DiscoverySort)}><option value="relevance">相关性排序</option><option value="year_desc">出版年从新到旧</option><option value="year_asc">出版年从旧到新</option></select></header>
    <button type="button" className={styles.primary} disabled={disabled||busy||!selection.query.trim()} onClick={()=>void start()}>按当前范围查找原文</button>
    <p className={styles.queryNote}>按当前主题与馆藏范围查找原文，可逐项查看上下文。</p>
    {error||resource.error?<p role="alert" className={styles.warning}>{error||resource.error}{session?<button type="button" disabled={busy} onClick={resource.reload}>读取当前结果</button>:null}</p>:null}
    {resource.loading?<LoadingState role="status">正在读取检索结果…</LoadingState>:null}
    {result?<><p role="status">{result.status_message || ({queued:"已排队",running:"正在检索",partial:"任务部分完成",failed:"检索未完成",completed:"本次检索完成",canceled:"检索已取消"}[result.status])} · {result.query}</p>
      {taskPollDelay(result)?<><progress max={result.task_progress.total||1} value={result.task_progress.completed}/><button type="button" disabled={busy} onClick={()=>void taskAction("cancel")}>取消当前检索</button></>:null}
      {result.can_retry?<button type="button" disabled={busy} onClick={()=>void taskAction("retry")}>继续未完成的检索</button>:null}
      {result.warnings.map((warning,index)=><p key={index} className={styles.warning}>{typeof warning==="string"?warning:warning.message}</p>)}
      {result.passages.map(row=>{const selectedRef=selection.references.find(ref=>ref.type==="span"&&ref.id===row.evidence_span_id&&ref.document_revision_id===row.document_revision_id);const included=Boolean(selectedRef);return <article key={row.id} className={styles.candidate} data-selected={included||undefined}><div className={styles.materialTitle}><input type="checkbox" aria-label={"选择"+row.work.title+"的这处原文"} checked={included} disabled={disabled||busy||!row.evidence_span_id||(!included&&selection.references.length>=40)} onChange={event=>{if(event.target.checked)void choose(row);else if(selectedRef)onRemove(selectedRef);}}/>{row.bibliography?.cover_url?<EditorialImage src={row.bibliography.cover_url} className={styles.cover}/>:null}<div><h3>{row.work.title}</h3><p>{row.authors.join("、")}</p><small>{row.bibliography?.version_label} · PDF 第 {row.pdf_page} 页{row.printed_page?` · 印刷页 ${row.printed_page}`:""}</small></div></div><blockquote><SourceText text={(row.excerpt) || ""} /></blockquote><p className={styles.matchBasis}>{row.match_basis.join(" · ")}</p><footer><button type="button" disabled={disabled||busy||included||!row.evidence_span_id||selection.references.length>=40} onClick={()=>void choose(row)}>{included?"已选":"加入已选"}</button><button type="button" onClick={()=>void readContext(row)}><BookOpen size={12}/>查看上下文</button><button type="button" className={styles.primary} disabled={disabled||busy||!row.evidence_span_id} onClick={()=>void choose(row,true)}>选作证据插入 →</button></footer>{!row.evidence_span_id?<small>这条材料暂不能引用，可以先打开原页阅读。</small>:null}</article>;})}
      {!result.passages.length&&!taskPollDelay(result)?<div className={styles.empty}><FileSearch size={42} strokeWidth={1}/><h3>未找到与“{result.query}”直接相关的原文候选</h3><p>可调整检索范围或使用相关概念继续查找。已选的 {selection.references.length} 项材料仍然保留。</p><div><button type="button" className={styles.primary} onClick={onAdjustScope}>调整检索范围</button><button type="button" onClick={onRelated}>查看相关概念</button></div></div>:null}
      {result.next_cursor&&limit<48?<button type="button" onClick={()=>setLimit(n=>n+6)}>读取更多候选</button>:null}
    </>:!resource.loading?<p className={styles.empty}>确定关键词与馆藏范围后查找原文。</p>:null}
    <Dialog open={contextOpen} onRequestClose={()=>{contextVersion.current+=1;setContextOpen(false);setContext(null);}} className={styles.context} aria-label="原文上下文"><header><h2>原文上下文</h2><button type="button" onClick={()=>{contextVersion.current+=1;setContextOpen(false);setContext(null);}}>关闭</button></header>{context?<><p><SourceText text={(context.before) || ""} /></p><blockquote><SourceText text={(context.excerpt) || ""} /></blockquote><p><SourceText text={(context.after) || ""} /></p><small>{context.notice}</small>{context.reader_url.startsWith("/reader/")?<a href={context.reader_url} target="_blank" rel="noopener">打开原文阅读位置 ↗</a>:null}</>:error?<p role="alert">{error}</p>:<LoadingState role="status">正在核对来源…</LoadingState>}</Dialog>
  </section>;
}
