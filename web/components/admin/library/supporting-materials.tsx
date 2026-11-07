"use client";

import { LoadingState } from "@/components/ui/loading-state";
import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useCatalogCommand } from "../workflow/use-intake-command";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import styles from "./supporting-materials.module.css";

type Fields={kind:"note"|"link";title:string;note:string;url:string};
type Row=Fields&{id:string;archived:boolean;updated_at:string};
type Workspace={owner_id:string;edition_id:string;version:string;results:Row[];count:number;page:number;pages:number};
type Command={expected_version:string;action:"create"|"update"|"archive"|"restore";material_id?:string;fields?:Fields};
type Receipt={owner_id:string;edition_id:string;request_id:string;state:"applied"|"cancelled";next_url:string;result:Row|null};
type Draft={id?:string;base:string;initial:Fields;fields:Fields};
const fieldsFor=(row:Fields):Fields=>({kind:row.kind,title:row.title,note:row.note,url:row.url});

export function SupportingMaterials({owner,editionId,canEdit,onUpload,expanded=false}:{owner:string;editionId:string;canEdit:boolean;onUpload:()=>void;expanded?:boolean}){
  const [page,setPage]=useState(1),[archived,setArchived]=useState(false),[draft,setDraft]=useState<Draft|null>(null),[message,setMessage]=useState("");
  const [confirm,setConfirm]=useState<Command|null>(null),[stop,setStop]=useState(false),[discard,setDiscard]=useState(false);
  const path=`/catalog/admin/editions/${editionId}/supporting-materials/`;
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Workspace>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Workspace>(`${path}?page=${page}&archived=${archived}`,owner,undefined,load);
  const state=resource.data?.edition_id===editionId?resource.data:null;
  const command=useCatalogCommand<Command,Receipt>(owner,path,`stl-supporting:${owner}:${editionId}`,value=>value.edition_id===editionId);
  const blocked=!canEdit||!command.ready||command.busy||Boolean(command.recovery)||!state;
  const dirty=Boolean(draft&&JSON.stringify(draft.fields)!==JSON.stringify(draft.initial));
  useUnsavedForm(dirty||Boolean(command.recovery),false);
  const changed=Boolean(draft&&state&&draft.base!==state.version),latest=state?.results.find(row=>row.id===draft?.id);
  function edit(row?:Row,kind:Fields["kind"]="note"){
    if(blocked||!state)return;
    const fields=row?fieldsFor(row):{kind,title:"",note:"",url:""};
    setDraft({id:row?.id,base:state.version,initial:fields,fields});setMessage("");
  }
  function close(){if(command.busy)return;if(dirty)setDiscard(true);else setDraft(null);}
  function received(value:Receipt,recovering=false){
    setConfirm(null);setStop(false);
    setMessage(value.state==="cancelled"?"尚未执行的请求已停止，当前填写保留。":recovering?"已查询原结果，没有重复操作。当前填写保留，请核对最新列表。":"补充材料已保存，仅管理可见。");
    if(!recovering&&value.state==="applied")setDraft(null);
    if(recovering&&value.state==="applied"&&value.result){const result=value.result;setDraft(current=>current&&current.fields.kind===result.kind?{...current,id:result.id,initial:fieldsFor(result)}:current);}
    resource.reload();
  }
  async function submit(body:Command){const result=await command.send(body);setConfirm(null);if(result)received(result);}
  async function recover(cancel=false,retry=false){const result=retry?await command.send():await command.lookup(cancel);if(result)received(result,true);}
  const feedback=<>{command.error?<p role="alert">{command.error}</p>:null}{message?<p role="status">{message}</p>:null}{command.recovery?<div className={styles.recovery}><p>有一项结果待核对，请先查询原请求。</p><button type="button" disabled={command.busy} onClick={()=>void recover()}>查询原结果</button>{command.canRetry?<button type="button" disabled={command.busy} onClick={()=>void recover(false,true)}>重试原请求</button>:null}<button type="button" disabled={command.busy} onClick={()=>setStop(true)}>停止尚未执行的请求</button></div>:null}</>;
  return <details className={styles.panel} id="supporting-materials" open={expanded||undefined}><summary>其他补充材料 </summary><p>补充说明和链接仅供管理编目核对。上传的原件保存在本版本的文件与历史中，是否生成或采用阅读副本另行决定。</p><div className={styles.actions}><button type="button" disabled={blocked} onClick={()=>edit()}>添加补充说明</button><button type="button" disabled={blocked} onClick={()=>edit(undefined,"link")}>添加相关链接</button><button type="button" disabled={blocked} onClick={onUpload}>上传补充原件</button><button type="button" disabled={resource.loading||command.busy} onClick={resource.reload}>刷新材料</button></div>{feedback}
    {resource.error?<p role="alert">{resource.error} <button type="button" onClick={resource.reload}>重新读取</button></p>:null}<label><input type="checkbox" checked={archived} disabled={command.busy||Boolean(draft)} onChange={event=>{setArchived(event.target.checked);setPage(1);}}/>查看已归档材料</label>
    {resource.loading&&!state?<LoadingState role="status">正在读取此版本的补充材料…</LoadingState>:null}{state&&!state.count?<p>本范围暂无补充说明或链接。已有文件仍保存在上方文件列表。</p>:null}
    {state?.results.map(row=><article key={row.id}><header><strong>{row.title}</strong><small>{row.kind==="note"?"补充说明":"相关链接"} · {row.archived?"已归档":"仅管理可见"}</small></header>{row.note?<p className={styles.note}>{row.note}</p>:null}{row.kind==="link"&&/^https?:\/\//.test(row.url)?<a href={row.url} target="_blank" rel="noreferrer">打开相关链接 ↗</a>:null}<div className={styles.actions}>{!row.archived?<button type="button" disabled={blocked} onClick={()=>edit(row)}>修改</button>:null}<button type="button" disabled={blocked} onClick={()=>setConfirm({action:row.archived?"restore":"archive",material_id:row.id,expected_version:state.version})}>{row.archived?"恢复":"归档"}</button></div></article>)}
    {state?<nav className={styles.actions} aria-label="补充材料分页"><button type="button" disabled={state.page<=1||resource.loading||Boolean(draft)} onClick={()=>setPage(state.page-1)}>上一页</button><span>共 {state.count} 项 · {state.page} / {state.pages}</span><button type="button" disabled={state.page>=state.pages||resource.loading||Boolean(draft)} onClick={()=>setPage(state.page+1)}>下一页</button></nav>:null}
    <Dialog open={Boolean(draft)} onRequestClose={close} className={styles.dialog} aria-label="编辑补充材料">{draft?<><h2>{draft.id?"修改":"添加"}{draft.fields.kind==="note"?"补充说明":"相关链接"}</h2><p>仅管理编目可见，不改动原件、阅读文件和公开页面。</p><form onSubmit={event=>{event.preventDefault();void submit({action:draft.id?"update":"create",material_id:draft.id,expected_version:draft.base,fields:draft.fields});}}><label>标题<input required maxLength={300} disabled={blocked} value={draft.fields.title} onChange={event=>setDraft({...draft,fields:{...draft.fields,title:event.target.value}})}/></label>{draft.fields.kind==="link"?<label>完整链接<input required type="url" maxLength={2000} disabled={blocked} value={draft.fields.url} onChange={event=>setDraft({...draft,fields:{...draft.fields,url:event.target.value}})}/></label>:null}<label>补充说明<textarea required={draft.fields.kind==="note"} maxLength={12000} rows={6} disabled={blocked} value={draft.fields.note} onChange={event=>setDraft({...draft,fields:{...draft.fields,note:event.target.value}})}/></label>{changed?<section className={styles.compare}><h3>材料列表已更新</h3>{latest?<><p>最新标题：{latest.title}</p><p className={styles.note}>{latest.note}</p><p>{latest.url}</p>{latest.archived?<p>此材料已被归档，请关闭窗口后先恢复。</p>:null}</>:<p>{draft.id?"本页未找到原材料，请先关闭窗口，在最新列表中重新核对。":"请核对最新列表是否已经存在同一材料。"}</p>}{(!draft.id||latest&&!latest.archived)?<button type="button" disabled={blocked} onClick={()=>setDraft({...draft,base:state!.version})}>已对照，保留本次填写继续</button>:null}</section>:null}{feedback}<footer className={styles.actions}><button type="button" disabled={command.busy} onClick={close}>取消</button><button type="submit" disabled={blocked||changed}>保存补充材料</button></footer></form></>:null}</Dialog>
    <ConfirmDialog open={Boolean(confirm)} title={confirm?.action==="restore"?"恢复这份补充材料？":"归档这份补充材料？"} description={`材料：${state?.results.find(row=>row.id===confirm?.material_id)?.title||"当前补充材料"}。只改变列表状态，内容与历史记录保留；原件、阅读文件与公开页面不变。`} confirmLabel={confirm?.action==="restore"?"确认恢复":"确认归档"} pending={command.busy} onCancel={()=>setConfirm(null)} onConfirm={async()=>{if(confirm)await submit(confirm);}}/>
    <ConfirmDialog open={stop} title="停止尚未执行的原请求？" description="已完成的操作返回原结果，不会撤销；尚未执行的请求停止后不能迟到写入。" details={command.error?[command.error]:[]} confirmLabel="核对并停止" pending={command.busy} onCancel={()=>setStop(false)} onConfirm={()=>recover(true)}/>
    <ConfirmDialog open={discard} title="放弃本次未保存的填写？" description="已保存的补充材料不变；待核对请求仍可从原编号查询。" confirmLabel="放弃填写" onCancel={()=>setDiscard(false)} onConfirm={()=>{setDiscard(false);setDraft(null);}}/>
  </details>;
}
