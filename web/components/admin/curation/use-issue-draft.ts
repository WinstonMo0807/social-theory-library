"use client";

import { createRequestKey } from "../../../lib/request-key";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { RecommendationIssue, IssueBlock, IssueItem } from "@/lib/api/recommendation-issues.types";

export type IssueDraft = RecommendationIssue & { cover_rendition_id?: string | null };
type PendingSave = { requestId:string; body:string };
type Recovery = { version:1; owner:string; issueId:string; at:number; draft:IssueDraft; pending:PendingSave|null };
const pick = <T extends object>(value:T, keys:readonly (keyof T)[]) => Object.fromEntries(keys.filter(key=>value[key]!==undefined).map(key=>[key,value[key]]));

/** Store/send editable fields only; never cache source excerpts, cookies or task output. */
export function issueInput(value:IssueDraft):IssueDraft {
  return {...pick(value,["id","slug","title","issue_label","introduction","public_byline","display_from","article_metadata","cover_rendition_id","edit_version","restore_revision_id"]),
    ...(value.selection_workspace?{selection_workspace:pick(value.selection_workspace,["question","query","filters","references"])}:{}),
    cover_url:value.cover_rendition_id ? "" : value.cover_url,
    body_blocks:value.body_blocks.map(row=>pick(row,["id","type","text","text_style","text_marks","heading_level","url","source","target","references","style","dimensions","rows","image_rendition_id","alt_text"]) as IssueBlock),
    items:value.items.map(row=>pick(row,["id","kind","work_id","edition_id","title","authors","version_note","isbn","doi","note","position","section_id"]) as IssueItem),
  } as IssueDraft;
}
function restoredDraft(remote:IssueDraft, input:IssueDraft):IssueDraft {
  return {...remote,...input,body_blocks:input.body_blocks.map(block=>{
    const previous=remote.body_blocks.find(row=>row.id===block.id);
    return {...block, image_url:previous?.image_rendition_id===block.image_rendition_id?previous?.image_url:"",
      resolved_sources:[], source_status:block.target || block.references?.length || block.rows?.length ? "unavailable" : undefined};
  }),cover_url:input.cover_rendition_id===remote.cover_rendition_id?remote.cover_url:input.cover_url};
}
function readRecovery(key:string, owner:string, issueId:string):Recovery|null {
  try {
    const raw=sessionStorage.getItem(key); if(!raw)return null;
    const value=JSON.parse(raw) as Recovery;
    if(value.version!==1 || value.owner!==owner || value.issueId!==issueId || !Number.isFinite(value.at) || Date.now()-value.at>86400000 || !value.draft || !Array.isArray(value.draft.body_blocks) || !Array.isArray(value.draft.items) || typeof value.draft.title!=="string" || typeof value.draft.edit_version!=="string") { sessionStorage.removeItem(key); return null; }
    if(value.pending && (typeof value.pending.body!=="string" || typeof value.pending.requestId!=="string"))value.pending=null;
    return value;
  } catch {return null;}
}

export function useIssueDraft(issueId:string, owner:string, fullPreview:boolean) {
  const endpoint=`/catalog/admin/recommendation-issues/${issueId}/`;
  const key=`stl:issue-draft:v1:${owner}:${issueId}`;
  const [draft,setDraft]=useState<IssueDraft|null>(null),[saved,setSaved]=useState<IssueDraft|null>(null);
  const [initialError,setInitialError]=useState(""),[attempt,setAttempt]=useState(0),[message,setMessage]=useState("");
  const [busy,setBusy]=useState(""),[conflict,setConflict]=useState(false),[sessionInvalid,setSessionInvalid]=useState(false);
  const [pending,setPending]=useState<PendingSave|null>(null),[recovery,setRecovery]=useState<Recovery|null>(null);
  const [autosave,setAutosave]=useState(true),[autoBlocked,setAutoBlocked]=useState(false),[storageError,setStorageError]=useState(false);
  const [manualRequired,setManualRequired]=useState(false),[composing,setComposingState]=useState(false);
  const active=useRef<AbortController|null>(null), action=useRef(false),compositionActive=useRef(false);
  const setComposing=useCallback((value:boolean)=>{compositionActive.current=value;setComposingState(value);},[]);
  const input=useMemo(()=>draft?issueInput(draft):null,[draft]);
  const savedInput=useMemo(()=>saved?issueInput(saved):null,[saved]);
  const dirty=useUnsavedForm(composing?{input,composing:true}:input,savedInput);
  const request=useCallback(async<T,>(url:string, init:RequestInit={}):Promise<T>=>{
    const lifetime=active.current;
    const signal=AbortSignal.any([lifetime?.signal || new AbortController().signal,...(init.signal?[init.signal]:[]),AbortSignal.timeout(25000)]);
    try {
      return await withPrivateOwner(owner,()=>apiRequest<T>(url,{...init,signal,headers:{...init.headers,"X-Editor-Owner":owner}},getServerSessionCredential()),signal);
    } catch(reason) {
      const articleAccessRead=url.split("?")[0]===endpoint||url.split("?")[0]===`${endpoint}presence/`;
      if(!lifetime?.signal.aborted && reason instanceof ApiRequestError && ([401,403].includes(reason.status)||articleAccessRead&&[404,410].includes(reason.status))) {
        try{sessionStorage.removeItem(key);}catch{/* No further private persistence when access is lost. */}
        setDraft(null);setSaved(null);setPending(null);setRecovery(null);setSessionInvalid(true);setInitialError("当前账户、项目范围或编辑权限已变化，请重新读取工作。");
        lifetime?.abort();
      }
      throw reason;
    }
  },[owner,key,endpoint]);
  useEffect(()=>{
    const controller=new AbortController(); active.current=controller; action.current=false;
    queueMicrotask(()=>{if(!controller.signal.aborted){setDraft(null);setSaved(null);setPending(null);setRecovery(null);setBusy("");setInitialError("");setConflict(false);setSessionInvalid(false);setAutoBlocked(false);setMessage("");}});
    queueMicrotask(()=>{if(!owner||controller.signal.aborted)return;void request<IssueDraft>(endpoint+(fullPreview?"preview/":"")).then(value=>{
      if(controller.signal.aborted)return;
      setDraft(value);setSaved(value);
      if(!fullPreview)setRecovery(readRecovery(key,owner,issueId));
    }).catch(reason=>{if(!controller.signal.aborted)setInitialError(reason instanceof Error?reason.message:"草稿读取失败。");});});
    const unsubscribe=subscribeToSessionChanges(()=>{
      controller.abort();try{sessionStorage.removeItem(key);}catch{/* Storage can be disabled. */}
      setDraft(null);setSaved(null);setPending(null);setRecovery(null);setSessionInvalid(true);setInitialError("登录状态已变化，请重新读取当前账户的工作。");
    });
    return ()=>{controller.abort();unsubscribe();};
  },[endpoint,fullPreview,key,owner,issueId,attempt,request]);
  useEffect(()=>{
    if(!input || fullPreview || recovery || sessionInvalid)return;
    try {
      if(dirty || pending)sessionStorage.setItem(key,JSON.stringify({version:1,owner,issueId,at:Date.now(),draft:input,pending} satisfies Recovery));
      else sessionStorage.removeItem(key);
    }catch{queueMicrotask(()=>setStorageError(true));}
  },[input,dirty,pending,recovery,fullPreview,key,owner,issueId,sessionInvalid]);
  const accept=useCallback((value:IssueDraft)=>{setDraft(value);setSaved(value);setPending(null);setConflict(false);setAutoBlocked(false);setManualRequired(false);},[]);
  function update(patch:Partial<IssueDraft>) {
    if(action.current || pending || sessionInvalid || recovery || draft?.project_archived)return;
    setDraft(value=>value?{...value,...patch}:value);setAutoBlocked(false);
  }
  function discardChanges() {
    if(action.current || compositionActive.current || pending || conflict || recovery || sessionInvalid || !saved)return;
    accept(saved);setMessage("已放弃本次未保存修改，恢复到最近保存的版本。");
  }
  const save=useCallback(async(automatic=false,retry=false)=>{
    if(!draft || draft.project_archived || action.current || compositionActive.current || sessionInvalid || conflict || recovery || (pending&&!retry) || (!dirty&&!pending) || automatic&&manualRequired)return;
    const lifetime=active.current;action.current=true;setBusy("save");setMessage("");
    const requestId=pending?.requestId || createRequestKey();
    const command=pending || {requestId,body:JSON.stringify({...issueInput(draft),request_id:requestId,autosave:automatic})};
    // Persist the fixed command before sending. Reload must query the receipt,
    // rather than create a new request that can create another planned item.
    setPending(command);
    try {sessionStorage.setItem(key,JSON.stringify({version:1,owner,issueId,at:Date.now(),draft:issueInput(draft),pending:command} satisfies Recovery));}catch{setStorageError(true);}
    try {
      const next=await request<IssueDraft>(endpoint,{method:"PUT",body:command.body});
      if(lifetime?.signal.aborted)return;
      if(next.request_found && !next.is_current_revision){setPending(null);setSaved(next);setConflict(true);setMessage("原保存已完成，但此后已有新的修订。请比较后决定保留哪份输入。");}
      else{accept(next);setMessage(automatic?"草稿已自动保存。":"草稿已保存。");}
    } catch(reason) {
      if(lifetime?.signal.aborted)return;
      setAutoBlocked(true);
      if(reason instanceof PrivateOwnerVerificationError){setMessage("暂时无法核对原登录账户。请恢复同一账户后查询这次保存。");}
      else if(reason instanceof ApiRequestError && reason.status>0 && reason.status<500){setPending(null);setConflict(reason.status===409);setMessage(`${reason.message} 当前输入已保留。`);}
      else setMessage("暂时无法确认保存结果，当前输入已保留。请先查询这次保存，再决定重试。");
    } finally {if(active.current===lifetime){action.current=false;if(!lifetime?.signal.aborted)setBusy("");}}
  },[draft,sessionInvalid,conflict,recovery,pending,dirty,key,owner,issueId,request,endpoint,accept,manualRequired]);
  useEffect(()=>{
    if(composing || !autosave || !dirty || busy || pending || conflict || recovery || autoBlocked || fullPreview || sessionInvalid || manualRequired)return;
    const timer=window.setTimeout(()=>{void save(true);},10000);
    return ()=>window.clearTimeout(timer);
  },[autosave,dirty,busy,pending,conflict,recovery,autoBlocked,fullPreview,sessionInvalid,manualRequired,composing,save]);
  async function lookup() {
    if(!pending || action.current)return;
    const lifetime=active.current;action.current=true;setBusy("lookup");
    try {
      const next=await request<IssueDraft>(`${endpoint}?request_id=${encodeURIComponent(pending.requestId)}`);
      if(lifetime?.signal.aborted)return;
      if(next.request_found){
        if(next.is_current_revision){accept(next);setMessage("已查询，原保存已完成。");}
        else{setPending(null);setSaved(next);setConflict(true);setMessage("原保存已完成，此后已有新的修订。请比较后继续。");}
      }else setMessage("尚未查到这次保存。可以再次查询，或重试原请求；不会重复建立计划书目。");
    }catch(reason){if(!lifetime?.signal.aborted)setMessage(reason instanceof Error?reason.message:"保存结果暂时无法查询。");}
    finally{if(active.current===lifetime){action.current=false;if(!lifetime?.signal.aborted)setBusy("");}}
  }
  async function command(path:string, body:unknown, success:string) {
    if(action.current || compositionActive.current || !draft || dirty || pending || conflict || recovery || sessionInvalid)return;
    const lifetime=active.current;action.current=true;setBusy(path);setMessage("");
    try {const next=await request<IssueDraft>(endpoint+path,{method:"POST",body:JSON.stringify(body)});if(!lifetime?.signal.aborted){accept(next);setMessage(success);return true;}}
    catch(reason){if(!lifetime?.signal.aborted){setConflict(!(reason instanceof ApiRequestError) || reason.status===0 || reason.status===409 || reason.status>=500);setMessage(`${reason instanceof Error?reason.message:"操作结果待核对"} 请读取最新版本核对后继续。`);return false;}}
    finally{if(active.current===lifetime){action.current=false;if(!lifetime?.signal.aborted)setBusy("");}}
  }
  async function recheck() {
    if(!draft || action.current || compositionActive.current || pending || recovery || sessionInvalid)return;
    const lifetime=active.current;action.current=true;setBusy("preview");
    try {const next=await request<IssueDraft>(endpoint+"preview/",{method:"POST",body:JSON.stringify(issueInput(draft))});if(!lifetime?.signal.aborted){setDraft({...draft,body_blocks:next.body_blocks,body_source_problems:next.body_source_problems});setMessage(next.body_source_problems?.length?"有来源尚不满足公开条件，请核对下方提示。":"已重新核对当前来源。");}}
    catch(reason){if(!lifetime?.signal.aborted)setMessage(reason instanceof Error?reason.message:"来源核对失败，当前输入已保留。");}
    finally{if(active.current===lifetime){action.current=false;if(!lifetime?.signal.aborted)setBusy("");}}
  }
  function recoverLocal() {
    if(!recovery || !saved)return;
    setDraft(restoredDraft(saved,recovery.draft));setPending(recovery.pending);setRecovery(null);setAutoBlocked(true);
    setManualRequired(true);
    setConflict(!recovery.pending && recovery.draft.edit_version!==saved.edit_version);
    setMessage(recovery.pending?"已恢复未确认的保存，请先查询结果。":"已恢复本标签页输入；请重新核对来源并保存。");
  }
  function restoreHistory(value:IssueDraft) {
    if(action.current || compositionActive.current || dirty || pending || recovery || !saved)return;
    setDraft({...value,edit_version:saved.edit_version,restore_revision_id:value.viewed_revision_id});setAutoBlocked(true);
    setManualRequired(true);
    setMessage(`修订 ${value.viewed_revision} 已放入编辑区，明确保存后才成为新草稿。`);
  }
  async function auxiliary<T>(url:string, body:string, refresh=false):Promise<T> {
    if(action.current || compositionActive.current || dirty || pending || conflict || recovery || sessionInvalid)throw new ApiRequestError("请先保存并核对当前草稿，再处理助手建议。",409);
    const lifetime=active.current;action.current=true;setBusy("assistant");
    try {
      const result=await request<T>(url,{method:"POST",body});
      if(refresh){try{const next=await request<IssueDraft>(endpoint);if(!lifetime?.signal.aborted)accept(next);}catch(reason){throw new Error("助手操作已提交，但文章最新状态读取失败，请查询原操作后继续。",{cause:reason});}}
      return result;
    } finally {if(active.current===lifetime){action.current=false;if(!lifetime?.signal.aborted)setBusy("");}}
  }
  async function refreshAfterAssistance() {
    if(action.current||compositionActive.current||dirty||pending||conflict||recovery||sessionInvalid)throw new Error("当前文章还有输入或状态待核对，请先保留并核对，再查询助手操作。");
    const lifetime=active.current;action.current=true;setBusy("assistant-refresh");
    try{const next=await request<IssueDraft>(endpoint);if(lifetime?.signal.aborted)throw new DOMException("Session changed","AbortError");accept(next);}
    finally{if(active.current===lifetime){action.current=false;if(!lifetime?.signal.aborted)setBusy("");}}
  }
  return {draft,saved,dirty,busy,composing,setComposing,message,initialError,conflict,pending,recovery,autosave,storageError,sessionInvalid,
    disabled:Boolean(busy||pending||recovery||sessionInvalid),update,save,lookup,command,recheck,recoverLocal,restoreHistory,request,auxiliary,refreshAfterAssistance,discardChanges,
    setAutosave,retryLoad:()=>setAttempt(value=>value+1),discardRecovery:()=>{setRecovery(null);try{sessionStorage.removeItem(key);}catch{setStorageError(true);}},
    useRemote:accept,keepLocal:(remote:IssueDraft)=>{setSaved(remote);setDraft(value=>value?{...value,edit_version:remote.edit_version}:value);setConflict(false);setPending(null);setAutoBlocked(true);setManualRequired(true);},
  };
}
