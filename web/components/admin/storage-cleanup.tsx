"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { ShieldCheck, X } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import type { components } from "@/lib/api/generated/schema";
import { Dialog } from "@/components/ui/dialog";
import styles from "./storage-workspace.module.css";

type Plan = components["schemas"]["CleanupPlanOutput"];
type Policy = components["schemas"]["StorageRetentionPolicy"];
type Intent = Omit<components["schemas"]["StorageCommandInputRequest"],"request_id">;
const size=(value:number)=>`${(value/1024/1024).toLocaleString("zh-CN",{maximumFractionDigits:2})} MiB`;
const outcomes:Record<string,string>={pending:"待处理",deleted:"已清理",protected:"继续保护",missing:"已不存在",failed:"未完成"};

export function StorageCleanup({owner,id,revision,disabled,canOperate,onCommand,feedback}:{owner:string;id:string;revision:string;disabled:boolean;canOperate:boolean;onCommand:(intent:Intent)=>void;feedback:ReactNode}) {
  const [selected,setSelected]=useState<string[]>([]),[confirm,setConfirm]=useState(false),[stop,setStop]=useState(false),[phrase,setPhrase]=useState("");
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Plan>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Plan>(id&&canOperate?`/distribution/storage/cleanup/${id}/`:"",owner,value=>["queued","running"].includes(value.status)&&!value.stalled?3000:null,load);
  const reload=resource.reload;
  useEffect(()=>reload(),[revision,reload]);
  const plan=resource.data, selection=plan?.rows.filter(row=>selected.includes(row.id))||[];
  const actionable=plan?.status==="scanned"&&!plan.stale&&plan.execution_supported;
  const expected=`清理 ${selection.length} 个临时文件`;
  const controlsDisabled=disabled||resource.loading||!!resource.error||!canOperate;
  return <section className={`${styles.panel} ${styles.cleanupPanel}`} aria-label="清理衍生缓存"><header><h2>清理衍生缓存</h2><button type="button" disabled={disabled||!canOperate} onClick={()=>onCommand({operation:"scan_cleanup"})}>扫描可清理项</button></header>
    <p className={styles.hint}>只扫描已完成上传的专用临时目录。原件、阅读文件、OCR 成果、媒体历史、读者资料、模型与活动索引继续保护。</p>
    {!canOperate?<p className={styles.hint}>只有具有清理维护权限的账户可以查看和执行清单。</p>:!id?<div className={styles.protection}><ShieldCheck size={18}/><span>尚未扫描，不预估可释放容量。</span></div>:null}
    {resource.loading?<p role="status">正在读取清理清单…</p>:null}
    {resource.error?<div className={styles.alert} role="alert"><p>{resource.error}</p><button type="button" onClick={reload}>重新读取</button></div>:null}
    {plan?<><div className={styles.cleanupSummary}><strong>{plan.candidate_count} 项候选 · {size(plan.candidate_bytes)}</strong><span>{plan.status_label}</span></div><p className={styles.hint}>{plan.notice} 本次查看 {plan.examined_count} 个目录项，{plan.protected_count} 项未纳入。文件至少闲置 {plan.retention_days} 天。</p>
      {plan.limited?<p className={styles.notice}>本次达到扫描范围上限，不能据此判断其他文件是否可清理。清理后可另行扫描。</p>:null}
      {!plan.execution_supported?<p className={styles.notice}>当前环境可查看清单，但不支持保护式文件定位，不能执行删除。</p>:null}
      {plan.stale&&plan.status==="scanned"?<p className={styles.notice}>清单已超过一小时，请重新扫描后确认。</p>:null}
      {plan.stalled?<p className={styles.notice}>任务超过执行时限，结果待核对。可停止后续项目，再重新扫描；未登记结果不能当作从未删除。</p>:null}
      {plan.error_message?<p className={styles.alert} role="status">{plan.error_message}</p>:null}
      <details className={styles.cleanupDetails}><summary>查看影响详情 · {selection.length} 项已选</summary><p className={styles.hint}>{plan.scope} 确认后逐项完整校验永久原件；状态变化、文件缺失、权限不足会保留或跳过，不会扩大到其他目录。</p>
        {actionable&&plan.rows.length?<label className={styles.checkbox}><input type="checkbox" disabled={controlsDisabled} checked={selection.length===plan.rows.length} onChange={event=>setSelected(event.target.checked?plan.rows.map(row=>row.id):[])}/><span>选择本清单全部 {plan.rows.length} 项</span></label>:null}
        <div className={styles.cleanupRows}>{plan.rows.map(row=><label key={row.id} className={styles.cleanupRow}><input type="checkbox" disabled={controlsDisabled||!actionable} checked={actionable?selected.includes(row.id):plan.selected.includes(row.id)} onChange={event=>setSelected(previous=>event.target.checked?[...previous,row.id]:previous.filter(id=>id!==row.id))}/><span><strong>{row.label}</strong><small>{new Date(row.modified_at).toLocaleString("zh-CN")} · {size(row.bytes)} · {outcomes[row.outcome]||"待核对"}</small><small>{row.detail}</small></span></label>)}</div>
        {!plan.rows.length?<p className={styles.hint}>本次扫描范围没有满足保护条件的候选。</p>:null}
      </details>
      <div className={styles.cleanupSummary}><span>已选择 {selection.length} 项 · {size(selection.reduce((total,row)=>total+row.bytes,0))}</span><span>已清理 {plan.deleted_count} 项 · {size(plan.released_bytes)}</span></div>
      <p className={styles.hint}>大小按文件登记；所在卷实际可用空间以存储用量为准。不可撤回的清理只在本清单明确确认后执行。</p>
      <div className={styles.actions}><button type="button" onClick={reload}>刷新结果</button>{actionable?<button type="button" className={styles.primary} disabled={controlsDisabled||!selection.length} onClick={()=>{setPhrase("");setConfirm(true);}}>确认清理</button>:null}{["scanned","queued","running"].includes(plan.status)?<button type="button" disabled={controlsDisabled} onClick={()=>setStop(true)}>停止后续项目</button>:null}</div>
      {confirm&&actionable?<Dialog open className={styles.dialog} onRequestClose={()=>setConfirm(false)} aria-labelledby="cleanup-confirm-title"><header><h2 id="cleanup-confirm-title">确认清理所选临时文件</h2><button type="button" aria-label="关闭清理确认" onClick={()=>setConfirm(false)}><X size={18}/></button></header>{feedback}<p>本次选择 {selection.length} 项，共 {size(selection.reduce((total,row)=>total+row.bytes,0))}。每项删除前都会完整核对永久原件。原件、读者资料和阅读文件不在范围内。</p><p>已完成的删除不可撤回；可停止尚未处理的项目。清单在一小时后过期，期间变化的文件会保留。</p><label className={styles.confirmField}>输入 {expected}<input autoComplete="off" value={phrase} disabled={disabled} onChange={event=>setPhrase(event.target.value)}/></label><footer><button type="button" onClick={()=>setConfirm(false)}>返回核对</button><button type="button" className={styles.primary} disabled={controlsDisabled||phrase!==expected} onClick={()=>onCommand({operation:"queue_cleanup",cleanup_id:plan.id,expected_version:plan.version,cleanup_items:selection.map(row=>row.id),confirmation:phrase})}>确认并加入清理任务</button></footer></Dialog>:null}
      {stop&&["scanned","queued","running"].includes(plan.status)?<Dialog open className={styles.dialog} onRequestClose={()=>setStop(false)} aria-labelledby="cleanup-stop-title"><h2 id="cleanup-stop-title">停止后续清理？</h2>{feedback}<p>当前正在核对的项目处理结束后停止后续项目。已经完成的删除不会撤回，逐项结果继续保留。</p><footer><button type="button" onClick={()=>setStop(false)}>返回</button><button type="button" className={styles.primary} disabled={controlsDisabled} onClick={()=>onCommand({operation:"cancel_cleanup",cleanup_id:plan.id,expected_version:plan.version})}>确认停止后续项目</button></footer></Dialog>:null}
    </>:null}
  </section>;
}

export function StorageRetentionEditor({policy,disabled,onClose,onCommand,feedback}:{policy:Policy;disabled:boolean;onClose:()=>void;onCommand:(intent:Intent)=>void;feedback:ReactNode}) {
  const [days,setDays]=useState(String(policy.temporary_days)),[discard,setDiscard]=useState(false);
  const dirty=days!==String(policy.temporary_days);
  useUnsavedForm(dirty,false);
  const close=()=>dirty?setDiscard(true):onClose();
  return <><Dialog open className={styles.dialog} onRequestClose={close} aria-labelledby="storage-retention-title"><form onSubmit={event=>{event.preventDefault();if(!disabled)onCommand({operation:"save_retention",temporary_days:Number(days),expected_version:policy.version});}} onKeyDown={event=>{if(event.key==="Enter"&&event.nativeEvent.isComposing)event.preventDefault();}}><header><h2 id="storage-retention-title">编辑临时文件保留规则</h2><button type="button" aria-label="关闭保留规则" onClick={close}><X size={18}/></button></header>{feedback}<p>永久原件和历史版本始终保留；账户私人资料继续由读者中心管理。这里只调整已完成上传的遗留临时文件。</p><label className={styles.confirmField}>至少闲置天数<input type="number" min={7} max={3650} step={1} required disabled={disabled} value={days} onChange={event=>setDays(event.target.value)}/></label><p>{policy.detail} 修改后，已有未执行清单需要重新扫描。</p><footer><button type="button" onClick={close}>返回</button><button type="submit" className={styles.primary} disabled={disabled||!dirty}>保存规则</button></footer></form></Dialog>{discard?<Dialog open className={styles.dialog} onRequestClose={()=>setDiscard(false)} aria-label="保留规则尚未保存"><h2>保留当前编辑？</h2><p>继续编辑会保留输入。放弃不会改变已保存的保留规则。</p><footer><button type="button" onClick={()=>setDiscard(false)}>继续编辑</button><button type="button" onClick={onClose}>放弃本次编辑</button></footer></Dialog>:null}</>;
}
