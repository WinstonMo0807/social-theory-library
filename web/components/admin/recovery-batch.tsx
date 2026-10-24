"use client";

import { useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./recovery-workspace.module.css";

type Detail=components["schemas"]["RecoveryDetail"];
type Command=components["schemas"]["RecoveryConfirmInputRequest"];
type Result=components["schemas"]["RecoveryResult"];
type Receipt=components["schemas"]["RecoveryReceipt"];
type Target={kind:string;object_id:string};
type Preview={target:Target;data:Detail|null;error:string};
const base="/catalog/admin/recycle/";
import type { RecoveryBatchState, RecoveryBatchItem as Item } from "./recovery-batch-state";

export function RecoveryBatch({owner,targets,initial,onPersist,onClose,onChanged}:{owner:string;targets:Target[];initial:RecoveryBatchState|null;onPersist:(value:RecoveryBatchState)=>void;onClose:()=>void;onChanged:()=>void}){
  const [batch,setBatch]=useState(initial),[previews,setPreviews]=useState<Preview[]>([]),[message,setMessage]=useState("");
  const [working,setWorking]=useState(false),[cancelOpen,setCancelOpen]=useState(false);
  const state=useRef(initial),lifecycle=useRef<AbortController|null>(null),busy=useRef(false),stop=useRef(false);
  useEffect(()=>{const controller=new AbortController();lifecycle.current=controller;return()=>{stop.current=true;controller.abort();};},[]);
  useUnsavedForm(Boolean(batch),false);
  function save(value:RecoveryBatchState){onPersist(value);state.current=value;setBatch(value);}
  function update(index:number,next:Item["state"]){const current=state.current;if(!current)throw Error("原批次记录不可用，请保留本页。");save({...current,items:current.items.map((item,position)=>position===index?{...item,state:next}:item)});}
  function signal(){return AbortSignal.any([lifecycle.current!.signal,AbortSignal.timeout(30000)]);}
  function live(){return Boolean(lifecycle.current&&!lifecycle.current.signal.aborted);}
  function failure(reason:unknown,fallback:string){
    if(!live())return;
    if(reason instanceof PrivateOwnerVerificationError||reason instanceof ApiRequestError&&[401,403,404,410].includes(reason.status))setPreviews([]);
    setMessage(reason instanceof Error?reason.message:fallback);
  }
  function validResult(result:Result,command:Command){
    if(result.request_id!==command.request_id||result.kind!==command.kind||result.object_id!==command.object_id||!result.restored||result.public_restored)throw Error("回执与原对象不一致，请保留原编号核对。");
  }
  async function readPreviews(){
    if(busy.current||!live())return;
    busy.current=true;stop.current=false;setWorking(true);setMessage("");setPreviews([]);
    const rows:Preview[]=[];
    try{
      for(const target of targets){
        if(stop.current||!live())break;
        const currentSignal=signal();
        try{
          const data=await withPrivateOwner(owner,()=>apiRequest<Detail>(`${base}${target.kind}/${target.object_id}/${state.current?"":"?check_files=true"}`,{signal:currentSignal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),currentSignal);
          if(!live())return;
          if(data.kind!==target.kind||data.object_id!==target.object_id)throw Error("预览身份与所选对象不一致。");
          rows.push({target,data,error:!data.can_restore?data.blockers.join(" ")||"当前状态或权限不允许恢复。":data.names.count?"存在同名对象，请回到单项详情比较并处理。":""});
        }catch(reason){if(!live())return;if(reason instanceof PrivateOwnerVerificationError||reason instanceof ApiRequestError&&[401,403,404,410].includes(reason.status)){setPreviews([]);setMessage("账户或对象可见性已变化，已清除本次预览。请重新核对访问权限。");return;}rows.push({target,data:null,error:reason instanceof Error?reason.message:"影响预览尚未完成。"});}
        setPreviews([...rows]);
      }
      if(live())setMessage(stop.current?"已停止读取，没有提交恢复。":state.current?"已读取当前对象名称，原确认范围和版本保持不变。":"请核对各项影响。受阻对象不会加入本次确认；所属对象仍在回收站时，需要先单独恢复所属对象。");
    }finally{if(live()){busy.current=false;setWorking(false);}}
  }
  async function submitRemaining(){
    if(busy.current||!state.current||!live()||state.current.items.some(item=>item.state==="pending"))return;
    busy.current=true;stop.current=false;setWorking(true);setMessage("");
    try{
      for(let index=0;index<state.current.items.length;index++){
        if(stop.current||!live())break;
        const item=state.current.items[index];if(item.state!=="ready")continue;
        // Persist uncertainty before sending. Reload can only look up this UUID.
        update(index,"pending");
        const currentSignal=signal();
        const result=await withPrivateOwner(owner,()=>apiRequest<Result>(base,{method:"POST",signal:currentSignal,cache:"no-store",headers:{"X-Editor-Owner":owner},body:JSON.stringify(item.command)},getServerSessionCredential()),currentSignal);
        if(!live())return;
        validResult(result,item.command);update(index,"applied");onChanged();
      }
      if(live())setMessage(stop.current?"已停止后续提交，当前已完成的恢复保留。":"本次已确认项目已处理，请核对逐项结果。恢复均保持未发布。");
    }catch(reason){failure(reason,"当前结果尚未确认，后续项目已暂停。请先查回原请求。");}
    finally{if(live()){busy.current=false;setWorking(false);}}
  }
  function confirm(){
    if(busy.current||state.current||previews.length!==targets.length)return;
    const eligible=previews.filter(row=>row.data&&!row.error);
    if(!eligible.length)return;
    try{save({version:1,items:eligible.map(row=>({state:"ready",command:{request_id:createRequestKey(),kind:row.data!.kind as Command["kind"],object_id:row.data!.object_id,expected_version:row.data!.version,confirmed:true}}))});}
    catch{setMessage("浏览器不能保存批量恢复记录，尚未提交。请恢复浏览器存储。");return;}
    void submitRemaining();
  }
  async function reconcile(cancel=false){
    if(busy.current||!state.current||!live())return;
    busy.current=true;stop.current=false;setWorking(true);setMessage("");
    try{
      const indices=state.current.items.map((item,index)=>({index,pending:item.state==="pending"})).sort((a,b)=>Number(b.pending)-Number(a.pending)).map(row=>row.index);
      for(const index of indices){
        if(stop.current||!live())break;
        const item=state.current.items[index];
        if(cancel?!["ready","pending"].includes(item.state):item.state!=="pending")continue;
        // Cancel also fences never-submitted UUIDs in copied tabs. One pending row at a time.
        if(item.state!=="pending")update(index,"pending");
        const currentSignal=signal();
        const receipt=await withPrivateOwner(owner,()=>apiRequest<Receipt>(`${base}receipts/${item.command.request_id}/`,{signal:currentSignal,cache:"no-store",headers:{"X-Editor-Owner":owner},...(cancel?{method:"POST",body:JSON.stringify({action:"cancel_pending"})}:{})},getServerSessionCredential()),currentSignal);
        if(!live())return;
        if(receipt.request_id!==item.command.request_id||receipt.actor_id!==owner)throw Error("回执与本次账户或原请求不一致。");
        if(receipt.state==="applied"&&receipt.result){validResult(receipt.result,item.command);update(index,"applied");}
        else if(receipt.state==="cancelled")update(index,"cancelled");
        else throw Error("原请求状态尚不能确认，请保留编号。");
        onChanged();
      }
      if(live()){setCancelOpen(false);setMessage(stop.current?"已暂停后续核对，尚未核对的项目仍保留。":cancel?"已核对并阻止尚未执行的剩余请求。已经完成的恢复不会撤销。":"原请求已查回。后续项目保持暂停，由你决定是否继续已确认项目。");}
    }catch(reason){failure(reason,"原请求仍待核对，未继续后续恢复。");}
    finally{if(live()){busy.current=false;setWorking(false);}}
  }
  const pending=batch?.items.find(item=>item.state==="pending"),remaining=batch?.items.filter(item=>["ready","pending"].includes(item.state)).length||0;
  const eligible=previews.filter(row=>row.data&&!row.error);
  function close(){if(working||remaining)return;try{onClose();}catch{setMessage("本地批次记录暂不能清除，请保留本页并恢复浏览器存储。");}}
  return <Dialog open className={styles.compareDialog} aria-labelledby="recovery-batch-title" onRequestClose={close}>
    <header className={styles.relatedTools}><h2 id="recovery-batch-title">批量恢复影响</h2><button disabled={working||remaining>0} onClick={close}>关闭</button></header>
    <p className={styles.hint}>仅处理明确选择的本页对象，最多20项。按顺序逐项提交，每项独立记录；停止或中断不会撤销已完成的恢复。本页关闭后不会继续发起下一项。</p>
    {message?<p className={styles.message} role="status">{message}</p>:null}
    {!batch?<><div className={styles.relatedTools}><span>已选 {targets.length} 项 · 已预览 {previews.length} 项</span><button disabled={working} onClick={()=>void readPreviews()}>读取恢复影响</button>{working?<button onClick={()=>{stop.current=true;setMessage("将在当前预览返回后停止。");}}>停止后续预览</button>:null}</div>
    <div className={styles.batchItems}>{previews.map(row=><article key={`${row.target.kind}:${row.target.object_id}`}><h3>{row.data?.title||`${row.target.kind} · ${row.target.object_id.slice(0,8)}`}</h3>{row.error?<p className={styles.error}>{row.error}</p>:<><p>{row.data?.notice}</p><p>关联摘要 {row.data?.dependency_count} 项{row.data?.dependencies_limited?"（还有其他关联，请在单项详情分页核对）":""}</p>{row.data?.storage.state==="checked"?<p>已核对 {row.data.storage.total} 份文件的存在与大小，不含内容完整性校验。</p>:null}</>}</article>)}</div>
    {previews.length===targets.length&&!working?<div className={styles.notice}><p>本次可恢复 {eligible.length} 项，另有 {targets.length-eligible.length} 项需单独处理。确认只恢复上述可恢复对象，保持未发布。</p></div>:null}
    <button className={styles.primary} disabled={working||previews.length!==targets.length||!eligible.length} onClick={confirm}>确认恢复 {eligible.length} 项（保持未发布）</button></>:<>
    {!previews.length?<button disabled={working} onClick={()=>void readPreviews()}>读取对象名称</button>:null}
    <div className={styles.batchItems}>{batch.items.map((item,index)=>{const preview=previews.find(row=>row.target.kind===item.command.kind&&row.target.object_id===item.command.object_id);return <article key={item.command.request_id}><strong>{index+1}. {preview?.data?.title||`${item.command.kind} · ${item.command.object_id}`}</strong><p>{({ready:"已确认，尚未提交",pending:"当前请求待核对，确认前不提交下一项",applied:"原回执确认已恢复，后续状态以对象最新记录为准",cancelled:"未执行请求已取消"})[item.state]}</p><small>请求编号 {item.command.request_id}</small></article>;})}</div>
    <div className={styles.relatedTools}>{working?<button onClick={()=>{stop.current=true;setMessage("已请求停止后续项目，当前请求仍需返回或查回结果。");}}>停止后续项目</button>:<>{pending?<button onClick={()=>void reconcile()}>查回当前原请求</button>:remaining?<button className={styles.primary} onClick={()=>void submitRemaining()}>继续已确认项目</button>:null}{remaining?<button onClick={()=>setCancelOpen(true)}>取消尚未执行的剩余项目</button>:<button className={styles.primary} onClick={close}>完成并返回列表</button>}</>}</div>
    <ConfirmDialog open={cancelOpen} title="取消剩余恢复请求" description="逐项查回原结果，阻止尚未执行的请求。已经完成的恢复保留，不会撤销。" details={[`仍需核对 ${remaining} 项。`,...(message?[message]:[])]} pending={working} confirmLabel={working?"正在核对…":"取消未执行项目"} onCancel={()=>{if(!working)setCancelOpen(false);}} onConfirm={()=>void reconcile(true)}/>
    </>}
  </Dialog>;
}
