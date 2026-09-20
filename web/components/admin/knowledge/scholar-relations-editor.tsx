"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { isEditorialConflict } from "@/lib/editorial-version";
import { useActionGuard } from "@/lib/use-action-guard";
import { EntityPicker } from "@/components/admin/forms/workflow-fields";
import { DraftConflict } from "@/components/admin/curation/draft-conflict";
import { ScholarRelationNetwork } from "@/components/scholar-relation-network";
import { relationArrow, scholarDirectionLabels, scholarRelationLabels, scholarRelationStatus, type ScholarRelation } from "@/lib/api/scholar-relations.types";
import type { Paginated } from "@/lib/api/pagination";

const newRelation = (scholarId: string): ScholarRelation => ({id:"",source_scholar:scholarId,target_scholar:"",source_name:"",target_name:"",relation_type:"influence",direction:"directed",summary:"",source:"",status:"draft",edit_version:""});
export function ScholarRelationsEditor({scholarId}: {scholarId:string}) {
  const searchParams = useSearchParams();
  const user = useAdminSession();
  const canEdit = hasAdminCapability(user,"can_edit_draft_authority"), canPublish = hasAdminCapability(user,"can_publish_authority");
  const [selectedId,setSelectedId] = useState(searchParams.get("relation") || "");
  const loadedId = useRef("");
  const [draft,setDraft] = useState<ScholarRelation>(()=>newRelation(scholarId));
  const [saved,setSaved] = useState<ScholarRelation>(()=>newRelation(scholarId));
  const [profile,setProfile] = useState<{preferred_name:string;slug:string}|null>(null);
  const [collection,setCollection] = useState<Paginated<ScholarRelation>>({count:0,results:[]});
  const [page,setPage] = useState(1), [attempt,setAttempt] = useState(0);
  const [loading,setLoading] = useState(true), [loadingRecord,setLoadingRecord] = useState(false);
  const [error,setError] = useState(""), [message,setMessage] = useState(""), [conflict,setConflict] = useState(false);
  const dirty = useUnsavedForm(draft,saved);
  const {pendingAction,startAction,finishAction} = useActionGuard();
  const busy = Boolean(pendingAction);
  useEffect(()=>{
    const controller=new AbortController();
    queueMicrotask(()=>{if(!controller.signal.aborted){setLoading(true);setError("");}});
    Promise.all([apiRequest<Paginated<ScholarRelation>>(`/catalog/admin/scholar-relations/?scholar=${encodeURIComponent(scholarId)}&page=${page}`,{signal:controller.signal},getServerSessionCredential()),apiRequest<{preferred_name:string;slug:string}>(`/catalog/admin/scholars/${scholarId}/`,{signal:controller.signal},getServerSessionCredential())]).then(([rows,scholar])=>{if(!controller.signal.aborted){setCollection(rows);setProfile(scholar);}}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"关系读取失败。");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[scholarId,page,attempt]);
  useEffect(()=>{
    if(!selectedId || loadedId.current === selectedId)return;
    const controller=new AbortController();
    queueMicrotask(()=>{if(!controller.signal.aborted){setLoadingRecord(true);setConflict(false);setError("");}});
    apiRequest<ScholarRelation>(`/catalog/admin/scholar-relations/${selectedId}/`,{signal:controller.signal},getServerSessionCredential()).then(row=>{if(!controller.signal.aborted){loadedId.current=row.id;setDraft(row);setSaved(row);}}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"关系读取失败。");}).finally(()=>{if(!controller.signal.aborted)setLoadingRecord(false);});
    return()=>controller.abort();
  },[selectedId,attempt]);
  function select(id:string) {
    if(id && id===selectedId)return;
    if(busy || (dirty&&!window.confirm("这条关系尚未保存，放弃当前输入并切换关系吗？")))return;
    setSelectedId(id);setLoadingRecord(Boolean(id));setMessage("");setConflict(false);
    if(!id){loadedId.current="";setLoadingRecord(false);const empty=newRelation(scholarId);setDraft(empty);setSaved(empty);}
    const url=new URL(window.location.href);if(id)url.searchParams.set("relation",id);else url.searchParams.delete("relation");window.history.replaceState(null,"",url.pathname+url.search);
  }
  const live = {...draft,id:draft.id||"current-input",source_name:draft.source_name||(draft.source_scholar===scholarId?profile?.preferred_name:"")||"第一位学者",target_name:draft.target_name||"第二位学者",has_unpublished_changes:dirty||draft.has_unpublished_changes};
  const rows = collection.results.filter(row=>row.id!==draft.id);
  if(draft.source_scholar&&draft.target_scholar)rows.push(live);
  const validEndpoints = Boolean(draft.source_scholar&&draft.target_scholar&&draft.source_scholar!==draft.target_scholar);
  const hasEvidence = Boolean(draft.summary.trim()&&draft.source.trim());
  const canPublishSaved = Boolean(saved.id&&!dirty&&hasEvidence&&canPublish&&(saved.status!=="published"||saved.has_unpublished_changes));
  async function save() {
    if(!validEndpoints||!canEdit||!startAction("save-scholar-relation"))return;
    setError("");setMessage("");setConflict(false);
    try {
      const payload={source_scholar:draft.source_scholar,target_scholar:draft.target_scholar,relation_type:draft.relation_type,direction:draft.direction,summary:draft.summary,source:draft.source,...(draft.id?{edit_version:saved.edit_version}:{})};
      const row=await apiRequest<ScholarRelation>(`/catalog/admin/scholar-relations/${draft.id?`${draft.id}/`:""}`,{method:draft.id?"PUT":"POST",body:JSON.stringify(payload)},getServerSessionCredential());
      loadedId.current=row.id;setDraft(row);setSaved(row);setSelectedId(row.id);setAttempt(value=>value+1);setMessage("关系草稿已保存。正式发布前，两位学者的公开页面保持原有内容。");
      const url=new URL(window.location.href);url.searchParams.set("relation",row.id);window.history.replaceState(null,"",url.pathname+url.search);
    } catch(reason) {setError(reason instanceof Error?reason.message:"保存失败，输入仍保留。");if(isEditorialConflict(reason))setConflict(true);} finally {finishAction("save-scholar-relation");}
  }
  async function publish() {
    if(!canPublishSaved||!startAction("publish-scholar-relation"))return;
    setError("");setMessage("");
    try {
      const row=await apiRequest<ScholarRelation>(`/catalog/admin/scholar-relations/${saved.id}/publish/`,{method:"POST",body:JSON.stringify({edit_version:saved.edit_version})},getServerSessionCredential());
      setDraft(row);setSaved(row);setAttempt(value=>value+1);setMessage("这条关系已发布，两端学者页面使用同一关系与方向。");
    } catch(reason) {setError(reason instanceof Error?reason.message:"发布失败，草稿仍保留。");if(isEditorialConflict(reason))setConflict(true);} finally {finishAction("publish-scholar-relation");}
  }
  async function archive() {
    if(!canPublish||!saved.id||saved.status!=="published"||dirty||!window.confirm("撤下这条已公开关系？两端公开页面将同时移除，关系内容与历史会保留，之后仍可重新发布。")||!startAction("archive-scholar-relation"))return;
    setError("");setMessage("");
    try {
      const row=await apiRequest<ScholarRelation>(`/catalog/admin/scholar-relations/${saved.id}/archive/`,{method:"POST",body:JSON.stringify({edit_version:saved.edit_version})},getServerSessionCredential());
      setDraft(row);setSaved(row);setAttempt(value=>value+1);setMessage("已从两端公开页面撤下。内容与历史已保留，可继续编辑并重新发布。");
    } catch(reason) {setError(reason instanceof Error?reason.message:"撤下失败，当前内容仍保留。");if(isEditorialConflict(reason))setConflict(true);} finally {finishAction("archive-scholar-relation");}
  }
  return <div className="scholar-relations-editor"><header className="v307-editor-heading"><div><Link href={`/admin/scholars/${scholarId}?section=network`}>返回学者编辑</Link><h1>{profile?.preferred_name||"学者"} · 学术关系</h1><p>明确两端、方向与出处；一次编辑一条关系。原有历史阅读关联另行保留。</p></div><button type="button" className="button secondary" disabled={busy} onClick={()=>select("")}>新建关系</button></header>
    {error?<p className="form-message" role="alert">{error}<button type="button" disabled={busy} onClick={()=>setAttempt(value=>value+1)}>重试读取</button></p>:null}{message?<p role="status">{message}</p>:null}
    <div className="scholar-relations-workspace"><aside className="fixed-editor-panel"><nav className="scholar-relation-index" aria-label="当前学者关系">{loading?<p>正在读取关系…</p>:collection.results.length?collection.results.map(row=><button type="button" key={row.id} aria-current={row.id===selectedId?"true":undefined} onClick={()=>select(row.id)}><strong>{row.source_name} {relationArrow(row.direction)} {row.target_name}</strong><small>{scholarRelationLabels[row.relation_type]} · {scholarRelationStatus(row)}</small></button>):<p>尚未建立规范关系，可从新建关系开始。</p>}{collection.count>24?<div><button type="button" disabled={page<=1||loading||dirty||busy} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {page} 页</span><button type="button" disabled={!collection.next||loading||dirty||busy} onClick={()=>setPage(value=>value+1)}>下一页</button></div>:null}</nav>
      <form className="fixed-editor-fields" onSubmit={event=>{event.preventDefault();void save();}}><h2>{draft.id?"编辑当前关系":"新建关系"}</h2><p>{dirty?"有未保存输入":draft.id?"当前已保存关系":"填写两端学者"}</p>{loadingRecord?<p role="status">正在读取所选关系…</p>:null}<fieldset disabled={!canEdit||busy||loadingRecord}>
        <EntityPicker label="第一位学者" endpoint="/catalog/admin/scholars/" nameField="preferred_name" values={draft.source_scholar?[{id:draft.source_scholar,name:live.source_name}]:[]} onChange={values=>{const value=values.at(-1);setDraft({...draft,source_scholar:value?.id||"",source_name:value?.name||""});}}/>
        <EntityPicker label="第二位学者" endpoint="/catalog/admin/scholars/" nameField="preferred_name" values={draft.target_scholar?[{id:draft.target_scholar,name:live.target_name}]:[]} onChange={values=>{const value=values.at(-1);setDraft({...draft,target_scholar:value?.id||"",target_name:value?.name||""});}}/>
        <label>关系类型<select value={draft.relation_type} onChange={event=>setDraft({...draft,relation_type:event.target.value as ScholarRelation["relation_type"]})}>{Object.entries(scholarRelationLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
        <label>方向<select value={draft.direction} onChange={event=>setDraft({...draft,direction:event.target.value as ScholarRelation["direction"]})}>{Object.entries(scholarDirectionLabels).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><p>{live.source_name} {relationArrow(draft.direction)} {live.target_name}</p>
        <label>关系说明<textarea rows={5} value={draft.summary} onChange={event=>setDraft({...draft,summary:event.target.value})}/></label><label>依据与来源<textarea rows={4} value={draft.source} placeholder="填写可核对的文献、页码或其他依据" onChange={event=>setDraft({...draft,source:event.target.value})}/></label>
        {!hasEvidence?<p>说明或来源尚不完整，可以保存草稿，暂不发布。</p>:null}{draft.source_scholar&&draft.source_scholar===draft.target_scholar?<p role="alert">关系两端须选择不同学者。</p>:null}<button type="submit" className="button" disabled={!validEndpoints||!dirty}>{pendingAction==="save-scholar-relation"?"正在保存…":"保存关系草稿"}</button>
      </fieldset><button type="button" className="button secondary" disabled={!canPublishSaved||busy||loadingRecord} onClick={()=>void publish()}>{pendingAction==="publish-scholar-relation"?"正在发布…":"发布已保存关系"}</button>{canPublish&&saved.id&&saved.status==="published"?<button type="button" className="button secondary" disabled={dirty||busy||loadingRecord} onClick={()=>void archive()}>{pendingAction==="archive-scholar-relation"?"正在撤下…":"撤下公开关系"}</button>:null}{saved.status==="archived"?<p>这条关系已撤下，内容与历史仍保留。</p>:null}{!canPublish?<p>当前账号没有正式发布权限。</p>:null}
      {conflict&&saved.id?<DraftConflict endpoint={`/catalog/admin/scholar-relations/${saved.id}/`} local={draft} onUseRemote={row=>{setDraft(row);setSaved(row);setConflict(false);}} onKeepLocal={row=>{setSaved(row);setDraft(value=>({...value,edit_version:row.edit_version}));setConflict(false);}}/>:null}
      </form></aside><section><p className="private-preview-label">{dirty?"当前输入实时预览，尚未保存。":"当前关系及已保存草稿预览。"}</p><ScholarRelationNetwork relations={rows} centerScholarId={scholarId} selectedId={live.id} onSelect={row=>{if(row.id!=="current-input")select(row.id);}}/></section></div>
  </div>;
}
