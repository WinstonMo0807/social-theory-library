"use client";

import { createContext, use, useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { editorialHeaders } from "@/lib/editorial-version";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { safeAdminHref } from "@/lib/admin-route-context";
import { Dialog } from "@/components/ui/dialog";
import type { KnowledgePreviewPayload } from "@/components/admin/preview/knowledge-page-preview";
import styles from "../curation/issue-publication.module.css";

type Saved = {id?:string;edit_version?:string;editorial_revision?:{id:string;status:string;target_type?:string;target_id?:string};[key:string]:unknown};
type Pending = {format:1;owner:string;objectType:string;objectId:string;phase:"prepare"|"publish";version:string;revisionId:string|null};
const targets:Record<string,{endpoint:string;type:string;field:string}>={
  scholar:{endpoint:"scholars",type:"scholar_profile",field:"editorial_status"},topic:{endpoint:"topics",type:"topic",field:"editorial_status"},
  discipline:{endpoint:"disciplines",type:"discipline",field:"editorial_status"},subdiscipline:{endpoint:"subdisciplines",type:"subdiscipline",field:"editorial_status"},
  reading_path:{endpoint:"theory-system/reading-paths",type:"reading_path",field:"status"},
  theory:{endpoint:"theory-system/nodes",type:"knowledge_node",field:"status"},concept:{endpoint:"theory-system/nodes",type:"knowledge_node",field:"status"},
  debate:{endpoint:"theory-system/nodes",type:"knowledge_node",field:"status"},research_problem:{endpoint:"theory-system/nodes",type:"knowledge_node",field:"status"},
};
const fields:Record<string,string>={canonical_name_zh:"名称",canonical_name_en:"原文名称",name:"名称",title:"标题",summary:"概述",definition:"定义",description:"内容说明",introduction:"导言",biography:"传记",short_description:"人物简介",core_questions:"核心问题",basic_propositions:"基本命题",items:"阅读条目",works:"关联馆藏",topics:"关联主题"};
const display=(value:unknown):string=>value==null||value===""?"未填写":typeof value==="string"?value:Array.isArray(value)?`${value.length} 项`:(typeof value==="number"||typeof value==="boolean")?String(value):"结构化内容，请核对完整预览";
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function validCommand(value:unknown,owner:string,objectType:string,objectId:string):value is Pending {
  if(!value||typeof value!=="object"||Array.isArray(value))return false;
  const command=value as Partial<Pending>;
  return command.format===1&&command.owner===owner&&command.objectType===objectType&&command.objectId===objectId&&uuid.test(objectId)&&typeof command.version==="string"&&/^[a-f0-9]{64}$/.test(command.version)&&(command.phase==="prepare"?command.revisionId===null:command.phase==="publish"&&typeof command.revisionId==="string"&&uuid.test(command.revisionId));
}
type Props={objectType:string;objectId:string;savedRecord:object;dirty:boolean;onPublished?:()=>void;onLockChange:(locked:boolean)=>void};
export const KnowledgePublicationContext=createContext<{locked:boolean;requestReview:()=>void}|null>(null);
export function KnowledgePublishEntry({disabled,onFallback}:{disabled:boolean;onFallback:()=>void}) {
  const publication=use(KnowledgePublicationContext);
  return <button type="button" className="button" disabled={disabled||Boolean(publication?.locked)} onClick={()=>publication?publication.requestReview():onFallback()}>进入发布前检查</button>;
}

export function KnowledgePublishControl(props:Props) {
  const owner=useAdminSession()?.id;
  return <PublishControl key={`${owner}:${props.objectType}:${props.objectId}`} {...props}/>;
}
function PublishControl({objectType,objectId,savedRecord,dirty,onPublished,onLockChange}:Props) {
  const user=useAdminSession(),owner=user?String(user.id):"",target=targets[objectType];
  const key=`stl:knowledge-publish:v1:${owner}:${objectType}:${objectId}`,endpoint=target?`/catalog/admin/${target.endpoint}/${objectId}/`:"";
  const savedVersion=(savedRecord as Saved).edit_version||"",canPublish=hasAdminCapability(user,"can_publish_authority");
  const lifetime=useRef<AbortController|null>(null),acting=useRef(false);
  const [review,setReview]=useState<{version:string;payload:KnowledgePreviewPayload;withdrawing:boolean}|null>(null),[open,setOpen]=useState(false),[confirmed,setConfirmed]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState(""),[pending,setPending]=useState<Pending|null>(null),[settledVersion,setSettledVersion]=useState("");
  const [hydrated,setHydrated]=useState(false),[recordProblem,setRecordProblem]=useState(false);
  const request=useCallback(async<T,>(url:string,init:RequestInit={}):Promise<T>=>{
    const signal=AbortSignal.any([lifetime.current!.signal,AbortSignal.timeout(30000)]);
    return withPrivateOwner(owner,()=>apiRequest<T>(url,{cache:"no-store",...init,signal,headers:{...init.headers,"X-Editor-Owner":owner}},getServerSessionCredential()),signal);
  },[owner]);
  useEffect(()=>{
    const controller=new AbortController();lifetime.current=controller;
    queueMicrotask(()=>{if(controller.signal.aborted)return;try{const value=JSON.parse(sessionStorage.getItem(key)||"null");if(value!==null){if(!validCommand(value,owner,objectType,objectId))throw Error();setPending(value);}}catch{setRecordProblem(true);setError("本标签页的发布记录暂不可读或与当前对象不符，请先核对原版本历史。");}finally{setHydrated(true);}});
    const unsubscribe=subscribeToSessionChanges(()=>{controller.abort();setReview(null);setOpen(false);setPending(null);setError("账户已变化，请重新打开当前对象。");try{sessionStorage.removeItem(key);}catch{/* The server-side record is retained. */}});
    return()=>{controller.abort();unsubscribe();};
  },[key,owner,objectType,objectId]);
  useEffect(()=>{onLockChange(!hydrated||busy||Boolean(pending)||recordProblem);},[hydrated,busy,pending,recordProblem,onLockChange]);
  function persist(value:Pending){sessionStorage.setItem(key,JSON.stringify(value));setPending(value);}
  function clear(){sessionStorage.removeItem(key);setPending(null);setRecordProblem(false);}
  function refresh(){try{onPublished?.();}catch{setError("发布结果已记录，但编辑器刷新失败，请重新打开本对象。");}}
  async function inspect(){
    if(acting.current||!endpoint||!owner||dirty||!hydrated||pending||recordProblem||!canPublish||lifetime.current?.signal.aborted)return;
    acting.current=true;setBusy(true);setError("");setReview(null);setConfirmed(false);setOpen(true);
    try{
      const expected=editorialHeaders(savedRecord)["If-Match"];
      const [saved,payload]=await Promise.all([request<Saved>(endpoint),request<KnowledgePreviewPayload>(`/catalog/admin/knowledge-preview/${objectType}/${objectId}/?${new URLSearchParams({edit_version:expected})}`)]);
      if(saved.id!==objectId||payload.object_id!==objectId||payload.object_type!==objectType)throw Error("对象身份不一致，请返回列表重新打开。");
      if(saved.edit_version!==expected||payload.edit_version!==expected)throw Error("这条资料已变化，请刷新编辑器后再检查。当前输入保留。");
      const current=await request<Saved>(endpoint);
      if(current.id!==objectId||current.edit_version!==expected)throw Error("检查期间内容已变化，请刷新编辑器后重新核对。");
      if(!payload.perspective.available)throw Error("当前保存内容暂不能预览，请先处理预览问题。");
      if(typeof saved[target.field]!=="string")throw Error("保存状态不完整，请重新打开当前对象。");
      setReview({version:expected,payload,withdrawing:Boolean(saved.editorial_revision?.status==="draft"&&saved[target.field]!=="published")});
    }catch(reason){if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"发布检查暂不可用。");}
    finally{acting.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  async function send(command:Pending){
    if(acting.current||!target||!canPublish||lifetime.current?.signal.aborted)return;
    if(!validCommand(command,owner,objectType,objectId)){setRecordProblem(true);setError("暂存请求与当前对象不符，已停止发送，请核对历史后清除记录。");return;}
    if(!pending&&(dirty||!confirmed||!review||review.version!==savedVersion||command.version!==review.version))return;
    acting.current=true;setBusy(true);setError("");setMessage("");setOpen(false);
    let phase=command,stage:"storage"|"request"="storage";
    try{
      persist(phase);stage="request";
      if(phase.phase==="prepare"){
        const current=await request<Saved>(endpoint);
        if(current.id!==objectId||current.edit_version!==phase.version)throw Error("已保存版本发生变化，请核对原版本历史后重新检查。");
        // An existing immutable revision already contains the reviewed status,
        // including a withdrawal. Do not overwrite that intent with published.
        const saved=current.editorial_revision?.status==="draft"?current:await request<Saved>(endpoint,{method:"PATCH",headers:{"If-Match":phase.version},body:JSON.stringify({[target.field]:"published"})});
        if(saved.id!==objectId)throw Error("响应对象不一致，请核对发布历史。");
        if(saved.editorial_revision?.status==="draft"){
          const revision=saved.editorial_revision;
          if(!uuid.test(revision.id)||revision.target_id!==objectId||revision.target_type!==target.type)throw Error("返回的修订不属于当前对象，已停止后续发布。");
          phase={...phase,phase:"publish",revisionId:revision.id};stage="storage";persist(phase);stage="request";
        }else{
          // First publications may be committed by the canonical endpoint itself.
          const result=await request<Saved&Record<string,unknown>>(endpoint);
          if(result.id!==objectId||result[target.field]!=="published"||result.editorial_revision?.status==="draft")throw Error("保存已返回，但正式公开状态尚未确认，请核对历史。");
        }
      }
      if(phase.phase==="publish"){
        const revision=await request<{id:string;target_id:string;target_type:string;status:string}>(`/catalog/admin/editorial-revisions/${phase.revisionId}/`);
        if(revision.id!==phase.revisionId||revision.target_id!==objectId||revision.target_type!==target.type||!["draft","published"].includes(revision.status))throw Error("原修订已变化或不属于当前对象，请核对记录。");
        if(revision.status!=="published"){
          const result=await request<typeof revision>(`/catalog/admin/editorial-revisions/${phase.revisionId}/publish/`,{method:"POST",body:"{}"});
          if(result.id!==phase.revisionId||result.target_id!==objectId||result.target_type!==target.type||result.status!=="published")throw Error("原修订的发布回执不完整，请核对历史。");
        }
      }
      stage="storage";clear();setSettledVersion(savedVersion);setMessage("发布操作已确认。公开内容与后续检索处理请在原记录中继续核对。");refresh();
    }catch(reason){if(!lifetime.current?.signal.aborted){setPending(phase);setError(stage==="storage"?"浏览器无法更新发布记录。后续操作已停止，请保持本页并恢复存储后重试同一阶段。":reason instanceof ApiRequestError?reason.status>0&&reason.status<500?`${reason.message} 请先核对保存内容与版本历史，再决定是否继续原请求。`:"本次操作结果尚不能确认。请核对历史或重试原阶段，不要另建发布请求。":reason instanceof Error?reason.message:"本次操作结果尚不能确认，请核对原版本历史。");}}
    finally{acting.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  const preview=review?.payload,before=(preview?.perspectives.published.data||{}) as Record<string,unknown>,after=(preview?.perspective.data||{}) as Record<string,unknown>;
  const changes=Object.entries(fields).filter(([field])=>JSON.stringify(before[field])!==JSON.stringify(after[field])&&(before[field]!=null||after[field]!=null));
  const locked=dirty||busy||!canPublish||!hydrated||recordProblem||Boolean(pending)||!review||review.version!==savedVersion||Boolean(error);
  const previewLink=new URL(safeAdminHref(preview?.preview_routes.draft,`/admin/preview/knowledge/${objectType}/${objectId}`),"https://admin.invalid");
  if(review)previewLink.searchParams.set("edit_version",review.version);
  return <section className={`${styles.review} ${styles.panel}`} aria-label="知识对象发布">
    <header><h2>发布已保存内容</h2><button type="button" disabled={dirty||busy||!canPublish||!hydrated||recordProblem||Boolean(pending)||settledVersion===savedVersion||!target} onClick={()=>void inspect()}>发布前检查</button></header>
    <p>{dirty?"当前输入尚未保存，请先保存草稿。":!canPublish?"当前账户没有正式发布权限。":"先核对已保存版本、公开内容与授权，再确认发布。"}</p>
    {message?<p role="status">{message}</p>:null}{error?<p className={styles.warning} role="alert">{error}</p>:null}
    {pending||recordProblem?<section className={styles.warning}><h3>原发布操作待核对</h3><a href={`/admin/knowledge?selected_type=${encodeURIComponent(objectType)}&selected_id=${encodeURIComponent(objectId)}`} target="_blank" rel="noopener">打开原对象版本记录 ↗</a><p>{pending?.phase==="publish"?"已记录编辑修订，继续核对原修订的发布结果。":"请核对正式内容与版本历史，确认原请求是否已完成。"}</p>{pending&&!recordProblem?<button type="button" disabled={busy||!canPublish} onClick={()=>void send(pending)}>重试原阶段</button>:null}<button type="button" disabled={busy} onClick={()=>{if(window.confirm("已核对正式内容与版本历史，确定清除此标签页的待确认记录吗？这不会撤销服务端操作。")){try{clear();setSettledVersion(savedVersion);setError("");setMessage("待确认记录已清除，请刷新编辑器后重新检查。");refresh();}catch{setError("浏览器暂不能清除记录，请保持页面后重试。");}}}}>已核对，清除待确认记录</button></section>:null}
    <Dialog open={open} onRequestClose={()=>{if(!busy)setOpen(false);}} className={styles.dialog} aria-label="知识对象发布前检查"><h2>核对已保存版本</h2>{busy?<p role="status">正在读取当前保存内容与公开版本…</p>:null}{error?<p role="alert">{error}</p>:null}{preview?<><h3>{preview.label}</h3><p>下方摘要取自公开页面的数据，只列主要文本与条目变化。未列出的结构化内容请在完整预览中核对。</p><div className={styles.table} style={{maxHeight:"38vh",overflow:"auto"}}>{changes.length?<table><thead><tr><th>内容</th><th>当前公开</th><th>已保存</th></tr></thead><tbody>{changes.map(([field,label])=><tr key={field}><th>{label}</th><td>{display(before[field])}</td><td>{display(after[field])}</td></tr>)}</tbody></table>:<p>主要摘要字段没有变化，请核对完整预览与公开范围。</p>}</div>{preview.content_completeness?.unsupported_preview_fields?.length?<p className={styles.warning}>部分内容尚不能完整预览，请在编辑页核对：{preview.content_completeness.unsupported_preview_fields.join("、")}。</p>:null}<a href={`${previewLink.pathname}${previewLink.search}${previewLink.hash}`} target="_blank" rel="noopener">打开完整预览 ↗</a><p>{review?.withdrawing?"当前保存的是非公开状态。本次确认会按原修订撤回公开展示，不会自动改成已发布。":"公开给所有读者。关联对象和原文仍受各自发布状态与授权约束；确认不会恢复其他已撤回对象。"}</p><label><input type="checkbox" checked={confirmed} disabled={locked} onChange={event=>setConfirmed(event.target.checked)}/>已核对保存内容、公开范围与来源授权</label></>:null}<div className={styles.actions}><button type="button" disabled={busy} onClick={()=>setOpen(false)}>返回编辑</button><button type="button" className={styles.primary} disabled={locked||!confirmed} onClick={()=>void send({format:1,owner,objectType,objectId,phase:"prepare",version:review!.version,revisionId:null})}>{review?.withdrawing?"确认撤回公开展示":"确认发布"}</button></div></Dialog>
  </section>;
}
