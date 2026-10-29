"use client";
import { createRequestKey } from "../../lib/request-key";
import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner, PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { SiteContentDraft } from "@/lib/api/recommendation-issues.types";

export const siteBase = "/catalog/admin/site-content/";
type Operation = {id:string;action:"save"|"publish"|"restore";body?:string};
function retainedOperation(key:string):Operation|null{
  try{const raw=JSON.parse(sessionStorage.getItem(key)||"null");if(raw&&/^[0-9a-f-]{36}$/i.test(raw.id)&&["save","publish","restore"].includes(raw.action))return {id:raw.id,action:raw.action};}catch{/* No content is stored in browser persistence. */}
  return null;
}
const editable=(draft:SiteContentDraft|null)=>draft?{config:draft.config,about_blocks:draft.about_blocks,home_layout:draft.home_layout,edit_version:draft.edit_version}:null;
export function useSiteContent(owner:string) {
  const load = useCallback((path:string,signal:AbortSignal)=>apiRequest<SiteContentDraft>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource = usePersistentWorkspace<SiteContentDraft>(siteBase,owner,undefined,load);
  const key=`stl-site-command:${owner}`;
  const [local,setLocal]=useState<SiteContentDraft|null>(null),[baseline,setSaved]=useState<SiteContentDraft|null>(null);
  const draft=local??resource.data,saved=baseline??resource.data;
  const setDraft:Dispatch<SetStateAction<SiteContentDraft|null>>=value=>{setSaved(current=>current??resource.data);setLocal(current=>typeof value==="function"?value(current??resource.data):value);};
  const [operation,setOperation]=useState<Operation|null>(()=>retainedOperation(key)),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
  const [blocked,setBlocked]=useState(false);
  const pending=useRef<Operation|null>(operation),active=useRef<AbortController|null>(null),running=useRef(false);
  const dirty=JSON.stringify(editable(draft))!==JSON.stringify(editable(saved));
  useUnsavedForm({draft:editable(draft),operation:operation?.id??null},{draft:editable(saved),operation:null});
  useEffect(()=>{const controller=new AbortController();active.current=controller;return()=>controller.abort();},[key]);
  function remember(value:Operation|null){pending.current=value;setOperation(value);try{if(value)sessionStorage.setItem(key,JSON.stringify({id:value.id,action:value.action}));else sessionStorage.removeItem(key);}catch{/* Recovery remains available in this mounted editor. */}}
  async function request<T>(path:string,init:RequestInit){
    if(!active.current||active.current.signal.aborted)throw new DOMException("Session changed","AbortError");
    const signal=AbortSignal.any([active.current.signal,AbortSignal.timeout(30000)]);
    return withPrivateOwner(owner,()=>apiRequest<T>(path,{...init,signal,cache:"no-store",headers:{...init.headers,"X-Editor-Owner":owner}},getServerSessionCredential()),signal);
  }
  function failure(error:unknown,writing=false){
    if(active.current?.signal.aborted)return;
    const revoked=error instanceof PrivateOwnerVerificationError||error instanceof ApiRequestError&&[401,403].includes(error.status);
    if(revoked)setBlocked(true);
    if(writing&&!revoked&&error instanceof ApiRequestError&&error.status>=400&&error.status<500&&error.status!==408){remember(null);if(error.status===409)resource.reload();}
    setMessage(error instanceof Error?error.message:"请求未确认，请查询原结果。");
  }
  async function persist(publish=false, expectedFingerprint?:string, restore?:{revision_id:string;expected_fingerprint:string;reason:string}){
    if(running.current||!draft||blocked||((publish||restore)&&dirty))return;
    const original=pending.current;
    if(original&&!original.body){setMessage("请先查询上次操作，或停止尚未执行的原请求。");return;}
    const value=original||{id:createRequestKey(),action:restore?"restore" as const:publish?"publish" as const:"save" as const,body:JSON.stringify(restore?{...restore,edit_version:draft.edit_version,confirm:true}:publish?{edit_version:draft.edit_version,confirm:true,...(expectedFingerprint?{expected_fingerprint:expectedFingerprint}:{})}:{config:draft.config,about_blocks:draft.about_blocks,home_layout:draft.home_layout,edit_version:draft.edit_version})};
    remember(value);running.current=true;setBusy(true);setMessage("");
    try{const data=await request<SiteContentDraft>(`${siteBase}${value.action==="save"?"":`${value.action}/`}`,{method:value.action==="save"?"PUT":"POST",headers:{"Idempotency-Key":value.id},body:value.body});
      if(active.current?.signal.aborted)return;remember(null);setDraft(data);setSaved(data);resource.reload();setMessage(data.replayed?"已查询原操作；当前显示服务器最新内容。":value.action==="publish"?"网站内容已发布。":value.action==="restore"?"已从所选历史恢复为新草稿，当前公开内容保持原版本。请核对来源后再发布。":"已保存草稿，公开首页在确认发布后更新。");
      return true;
    }catch(error){failure(error,true);return false;}finally{running.current=false;if(!active.current?.signal.aborted)setBusy(false);}
  }
  async function recover(stop=false){
    if(running.current||!pending.current||blocked)return;
    running.current=true;setBusy(true);
    try{const row=await request<NonNullable<SiteContentDraft["receipt"]>>(`${siteBase}commands/${pending.current.id}/`,stop?{method:"POST",body:JSON.stringify({action:"cancel_pending"})}:{method:"GET"});
      if(active.current?.signal.aborted)return;
      if(row.actor_id!==owner||row.request_id!==pending.current?.id)throw new Error("操作结果与当前账户或原请求不一致，请保留页面并重新核对。");
      if(row.action!=="cancelled"){const data=await request<SiteContentDraft>(siteBase,{});setDraft(data);setSaved(data);}remember(null);resource.reload();setMessage(row.action==="cancelled"?"已停止原请求，未保存输入仍在当前页面。":"已找到原操作结果，已重新读取当前网站内容。");
    }catch(error){failure(error);if(error instanceof ApiRequestError&&error.status===404)setMessage("尚未找到完成操作结果。可以重试原请求，或停止尚未执行的原请求；这不代表操作已失败。");}
    finally{running.current=false;if(!active.current?.signal.aborted)setBusy(false);}
  }
  const remoteRevision=resource.data?.history[0],localRevision=draft?.history[0];
  const conflict=Boolean(resource.data&&draft&&resource.data.edit_version!==draft.edit_version&&(
    (remoteRevision?.revision||0)>(localRevision?.revision||0)||
    remoteRevision?.id===localRevision?.id&&remoteRevision?.state==="published"&&localRevision?.state==="draft"));
  function useRemote(){if(resource.data){setDraft(resource.data);setSaved(resource.data);setMessage("已采用服务器最新内容。");}}
  function keepLocal(){if(resource.data&&draft){setSaved(resource.data);setDraft({...draft,edit_version:resource.data.edit_version});setMessage("已保留当前输入，请核对差异后重新保存。");}}
  return {draft,setDraft,saved,dirty,busy,message,operation,blocked,resource,persist,recover,conflict,useRemote,keepLocal};
}
