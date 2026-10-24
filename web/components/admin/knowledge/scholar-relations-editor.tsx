"use client";

import Link from "next/link";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { isEditorialConflict } from "@/lib/editorial-version";
import { useActionGuard } from "@/lib/use-action-guard";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { DraftConflict } from "@/components/admin/curation/draft-conflict";
import { ScholarRelationNetwork } from "@/components/scholar-relation-network";
import { relationArrow, scholarDirectionLabels, scholarRelationLabels, scholarRelationStatus, type ScholarRelation } from "@/lib/api/scholar-relations.types";
import type { Paginated } from "@/lib/api/pagination";
import { useScholarSave } from "./use-scholar-save";

export type ScholarRelationGuard = {dirty:boolean;pending:boolean;composing:boolean};
type Props = {scholarId:string;initialRelationId?:string;embedded?:boolean;detailOnly?:boolean;onGuardChange?:(value:ScholarRelationGuard)=>void;onSaved?:()=>void};
const newRelation = (scholarId:string):ScholarRelation => ({id:"",source_scholar:scholarId,target_scholar:"",source_name:"",target_name:"",relation_type:"influence",direction:"directed",summary:"",source:"",status:"draft",edit_version:""});

export function ScholarRelationsEditor(props:Props) {
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  return user?<RelationWorkspace key={`${user.id}:${epoch}:${props.scholarId}`} {...props} owner={String(user.id)}/>:<p role="status">正在核对编辑账户…</p>;
}

function RelationWorkspace({scholarId,initialRelationId,embedded=false,detailOnly=false,onGuardChange,onSaved,owner}:Props&{owner:string}) {
  const searchParams=useSearchParams(),user=useAdminSession(),command=useScholarSave(owner,"relation");
  const canEdit=hasAdminCapability(user,"can_edit_draft_authority"),canCreate=hasAdminCapability(user,"can_create_authority"),canPublish=hasAdminCapability(user,"can_publish_authority");
  const [selectedId,setSelectedId]=useState(initialRelationId??searchParams.get("relation")??""),loadedId=useRef("");
  const [draft,setDraft]=useState<ScholarRelation>(()=>newRelation(scholarId)),[saved,setSaved]=useState<ScholarRelation>(()=>newRelation(scholarId));
  const [profile,setProfile]=useState<{preferred_name:string;slug:string}|null>(null);
  const [collection,setCollection]=useState<Paginated<ScholarRelation>>({count:0,results:[]});
  const [page,setPage]=useState(1),[attempt,setAttempt]=useState(0),[loading,setLoading]=useState(true),[loadingRecord,setLoadingRecord]=useState(Boolean(selectedId));
  const [error,setError]=useState(""),[message,setMessage]=useState(""),[conflict,setConflict]=useState(false),[ime,setIme]=useState(false),composing=useRef(false);
  const dirty=useUnsavedForm(draft,saved),{pendingAction,startAction,finishAction}=useActionGuard(),busy=Boolean(pendingAction);
  useUnsavedForm(Boolean(command.recovery)||busy,false);
  const notifyGuard=useEffectEvent((value:ScholarRelationGuard)=>onGuardChange?.(value));
  useEffect(()=>{notifyGuard({dirty,pending:busy||Boolean(command.recovery),composing:ime});},[dirty,busy,command.recovery,command.ready,ime]);
  useEffect(()=>{
    const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    queueMicrotask(()=>{if(!controller.signal.aborted){setLoading(true);setError("");}});
    withPrivateOwner(owner,()=>Promise.all([
      apiRequest<Paginated<ScholarRelation>>(`/catalog/admin/scholar-relations/?scholar=${encodeURIComponent(scholarId)}&page=${page}`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),
      apiRequest<{preferred_name:string;slug:string}>(`/catalog/admin/scholars/${scholarId}/`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),
    ]),signal).then(([rows,scholar])=>{if(!controller.signal.aborted){setCollection(rows);setProfile(scholar);}}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"关系读取失败。");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[scholarId,page,attempt,owner]);
  useEffect(()=>{
    if(!selectedId||loadedId.current===selectedId)return;
    const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    queueMicrotask(()=>{if(!controller.signal.aborted){setLoadingRecord(true);setConflict(false);setError("");}});
    withPrivateOwner(owner,()=>apiRequest<ScholarRelation>(`/catalog/admin/scholar-relations/${selectedId}/?scholar=${encodeURIComponent(scholarId)}`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal).then(row=>{if(!controller.signal.aborted){loadedId.current=row.id;setDraft(row);setSaved(row);}}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"关系读取失败。");}).finally(()=>{if(!controller.signal.aborted)setLoadingRecord(false);});
    return()=>controller.abort();
  },[selectedId,attempt,owner,scholarId]);
  function rememberSelection(id:string){if(embedded)return;const url=new URL(window.location.href);if(id)url.searchParams.set("relation",id);else url.searchParams.delete("relation");window.history.replaceState(null,"",url.pathname+url.search);}
  function select(id:string){
    if(composing.current||busy||command.recovery||id&&id===selectedId)return;
    if(dirty&&!window.confirm("这条关系尚未保存，放弃当前输入并切换关系吗？"))return;
    setSelectedId(id);setLoadingRecord(Boolean(id));setMessage("");setConflict(false);
    if(!id){loadedId.current="";const empty=newRelation(scholarId);setDraft(empty);setSaved(empty);}
    rememberSelection(id);
  }
  function apply(row:ScholarRelation){loadedId.current=row.id;setDraft(row);setSaved(row);setSelectedId(row.id);setAttempt(value=>value+1);setConflict(false);rememberSelection(row.id);onSaved?.();}
  const live={...draft,id:draft.id||"current-input",source_name:draft.source_name||(draft.source_scholar===scholarId?profile?.preferred_name:"")||"第一位学者",target_name:draft.target_name||"第二位学者",has_unpublished_changes:dirty||draft.has_unpublished_changes};
  const rows=collection.results.filter(row=>row.id!==draft.id);if(draft.source_scholar&&draft.target_scholar)rows.push(live);
  const validEndpoints=Boolean(draft.source_scholar&&draft.target_scholar&&draft.source_scholar!==draft.target_scholar),hasEvidence=Boolean(draft.summary.trim()&&draft.source.trim());
  const editingReady=!loadingRecord&&(!selectedId||saved.id===selectedId);
  const locked=!canEdit||!command.ready||Boolean(command.recovery)||busy||!editingReady;
  const canPublishSaved=Boolean(saved.id&&!dirty&&hasEvidence&&canPublish&&(saved.status!=="published"||saved.has_unpublished_changes));
  async function act(operation:"save"|"publish"|"archive"|"retry") {
    if(composing.current||!canEdit||!editingReady||!command.ready||command.recovery&&operation!=="retry")return;
    if(operation==="save"&&(!validEndpoints||!draft.id&&!canCreate))return;
    if(operation==="save"&&embedded&&![draft.source_scholar,draft.target_scholar].includes(scholarId)){setError("页内关系至少一端须是当前学者，请核对来源与目标。");return;}
    if(operation==="publish"&&(!canPublishSaved||!window.confirm("发布这条已保存关系？两端学者页面将同时使用此方向、说明和来源。")))return;
    if(operation==="archive"&&(!canPublish||!saved.id||dirty||!window.confirm("撤下这条已公开关系？两端公开页面将同时移除，原内容和历史保留。")))return;
    if(!startAction(operation))return;
    setError("");setMessage("");setConflict(false);
    try {
      const payload=operation==="save"?{source_scholar:draft.source_scholar,target_scholar:draft.target_scholar,relation_type:draft.relation_type,direction:draft.direction,summary:draft.summary,source:draft.source,...(draft.id?{edit_version:saved.edit_version}:{})}:{edit_version:saved.edit_version};
      const suffix=operation==="publish"||operation==="archive"?`${saved.id}/${operation}/`:draft.id?`${draft.id}/`:"";
      const row=await command.save<ScholarRelation>(`/catalog/admin/scholar-relations/${suffix}`,JSON.stringify(payload),{},operation==="save"&&draft.id?"PUT":"POST");
      apply(row);setMessage(operation==="retry"?"已查回原操作，当前保存版本已重新读取。":operation==="save"?"关系草稿已保存，公开关系保持原版本。":operation==="publish"?"已发布到两端学者页面。":"已撤下公开关系，内容与历史仍保留。");
    }catch(reason){setError(reason instanceof Error?reason.message:"操作结果待核对，输入仍保留。");if(isEditorialConflict(reason))setConflict(true);}finally{finishAction(operation);}
  }
  async function recover(cancel=false){
    if(composing.current||!startAction("recover"))return;
    try {
      const receipt=await command.lookup(cancel);
      if(receipt?.exists&&receipt.relation_id){loadedId.current="";setSelectedId(receipt.relation_id);setLoadingRecord(true);rememberSelection(receipt.relation_id);setAttempt(value=>value+1);setMessage("已查回原操作，正在读取当前保存的关系。不会重复新建。");onSaved?.();}
      else if(receipt)setMessage(receipt.state==="cancelled"?"原操作已停止，当前输入保留。":"原操作已经完成，关系后来已移除，没有重复新建。");
    }catch(reason){setError(reason instanceof Error?reason.message:"原结果暂不可读，请重新读取关系列表。");}finally{finishAction("recover");}
  }
  return <div className="scholar-relations-editor" data-embedded={embedded} onCompositionStartCapture={()=>{composing.current=true;setIme(true);}} onCompositionEndCapture={()=>{composing.current=false;setIme(false);}}>
    {!detailOnly?<header className="v307-editor-heading"><div>{!embedded?<Link href={`/admin/scholars/${scholarId}?section=theory`}>返回学者编辑</Link>:null}<h2>{profile?.preferred_name||"学者"} · 学术关系</h2><p>明确两端、方向与出处；保存草稿与公开发布分别进行。</p></div><button type="button" className="button secondary" disabled={busy||ime||Boolean(command.recovery)||!canCreate} onClick={()=>select("")}>新建关系</button></header>:null}
    {error?<p className="form-message" role="alert">{error}<button type="button" disabled={busy||ime||dirty||Boolean(command.recovery)} onClick={()=>{loadedId.current="";setAttempt(value=>value+1);}}>重新读取</button></p>:null}{message?<p role="status">{message}</p>:null}
    {command.recovery?<aside role="status"><p>原操作结果尚未确认。请先查回或停止原请求，不能另建关系或重复发布。</p><button type="button" disabled={busy||ime} onClick={()=>void recover()}>查回原操作</button>{command.canRetry?<button type="button" disabled={busy||ime} onClick={()=>void act("retry")}>重试原操作</button>:null}<button type="button" disabled={busy||ime} onClick={()=>{if(window.confirm("停止尚未执行的原请求？已经完成的操作会返回原结果。"))void recover(true);}}>停止未执行请求</button></aside>:null}{command.error?<p role="alert">{command.error}</p>:null}
    <div className="scholar-relations-workspace"><aside className="fixed-editor-panel">{!detailOnly?<nav className="scholar-relation-index" aria-label="当前学者关系">{loading?<p>正在读取关系…</p>:collection.results.length?collection.results.map(row=><button type="button" key={row.id} disabled={busy||ime||Boolean(command.recovery)} aria-current={row.id===selectedId?"true":undefined} onClick={()=>select(row.id)}><strong>{row.source_name} {relationArrow(row.direction)} {row.target_name}</strong><small>{scholarRelationLabels[row.relation_type]} · {scholarRelationStatus(row)}</small></button>):<p>尚未建立规范关系，可从新建关系开始。</p>}
      {collection.count>24?<div><button type="button" disabled={page<=1||loading||dirty||busy||ime||Boolean(command.recovery)} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {page} 页 · 共 {collection.count} 项</span><button type="button" disabled={!collection.next||loading||dirty||busy||ime||Boolean(command.recovery)} onClick={()=>setPage(value=>value+1)}>下一页</button></div>:null}</nav>:null}
      <form className="fixed-editor-fields" onSubmit={event=>{event.preventDefault();event.stopPropagation();void act("save");}}><h3>{draft.id?"编辑当前关系":"新建关系"}</h3><p>{dirty?"有未保存输入":draft.id?scholarRelationStatus(draft):"填写两端学者"}</p>{loadingRecord?<p role="status">正在读取所选关系…</p>:null}
        <fieldset disabled={locked||!draft.id&&!canCreate}>
          <EntityPicker label="第一位学者" endpoint="/catalog/admin/scholars/" nameField="preferred_name" values={draft.source_scholar?[{id:draft.source_scholar,name:live.source_name}]:[]} onChange={values=>{const value=values.at(-1);setDraft({...draft,source_scholar:value?.id||"",source_name:value?.name||""});}}/>
          <EntityPicker label="第二位学者" endpoint="/catalog/admin/scholars/" nameField="preferred_name" values={draft.target_scholar?[{id:draft.target_scholar,name:live.target_name}]:[]} onChange={values=>{const value=values.at(-1);setDraft({...draft,target_scholar:value?.id||"",target_name:value?.name||""});}}/>
          <label>关系类型<select value={draft.relation_type} onChange={event=>setDraft({...draft,relation_type:event.target.value as ScholarRelation["relation_type"]})}>{Object.entries(scholarRelationLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
          <label>方向<select value={draft.direction} onChange={event=>setDraft({...draft,direction:event.target.value as ScholarRelation["direction"]})}>{Object.entries(scholarDirectionLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><p>{live.source_name} {relationArrow(draft.direction)} {live.target_name}</p>
          <label>关系说明<textarea rows={5} maxLength={6000} value={draft.summary} onChange={event=>setDraft({...draft,summary:event.target.value})}/></label><label>依据与来源<textarea rows={4} maxLength={6000} value={draft.source} onChange={event=>setDraft({...draft,source:event.target.value})}/></label>
          {!hasEvidence?<p>说明或来源尚不完整，可以保存草稿，暂不发布。</p>:null}{draft.source_scholar&&draft.source_scholar===draft.target_scholar?<p role="alert">关系两端须选择不同学者。</p>:null}<button type="submit" className="button" disabled={!validEndpoints||!dirty||ime}>{pendingAction==="save"?"正在保存…":"保存关系草稿"}</button>
        </fieldset>
        <button type="button" className="button secondary" disabled={locked||ime||!canPublishSaved} onClick={()=>void act("publish")}>发布已保存关系</button>{canPublish&&saved.id&&saved.status==="published"?<button type="button" className="button secondary" disabled={locked||ime||dirty} onClick={()=>void act("archive")}>撤下公开关系</button>:null}{!canPublish?<p>当前账号没有正式发布权限。</p>:null}
        {conflict&&saved.id&&!command.recovery?<DraftConflict endpoint={`/catalog/admin/scholar-relations/${saved.id}/`} local={draft} onUseRemote={row=>{setDraft(row);setSaved(row);setConflict(false);}} onKeepLocal={row=>{setSaved(row);setDraft(value=>({...value,edit_version:row.edit_version}));setConflict(false);}}/>:null}
      </form></aside>{!detailOnly?<section><p className="private-preview-label">{dirty?"当前输入预览，尚未保存。":"本页关系与已保存草稿。"}图中只显示当前分页；全部记录见列表分页。</p><ScholarRelationNetwork relations={rows} centerScholarId={scholarId} selectedId={live.id} onSelect={row=>{if(row.id!=="current-input")select(row.id);}}/></section>:null}
    </div>
  </div>;
}
