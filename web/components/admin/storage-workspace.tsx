"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronRight, CircleAlert, Database, Download, FileCheck2, HardDrive, RefreshCw, ShieldCheck, X } from "lucide-react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import type { components } from "@/lib/api/generated/schema";
import { Dialog } from "@/components/ui/dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import styles from "./storage-workspace.module.css";
import { RestoreHistory } from "./restore-history";
import { StorageCleanup, StorageRetentionEditor } from "./storage-cleanup";

type Snapshot = components["schemas"]["StorageSnapshot"];
type Backup = components["schemas"]["BackupOutput"];
type Detail = components["schemas"]["BackupDetailOutput"];
type Verification = components["schemas"]["BackupVerificationOutput"];
type VerificationPage = components["schemas"]["VerificationHistoryPage"];
type Command = components["schemas"]["StorageCommandInputRequest"];
type Reply = components["schemas"]["StorageCommandOutput"];
type Receipt = components["schemas"]["StorageCommandReceipt"];
type Plan = components["schemas"]["RestorePlan"];
type Schedule = components["schemas"]["BackupScheduleOutput"];
type Intent = Omit<Command,"request_id">;
const base = "/distribution/storage/";
const tabs = [{id:"backups",label:"备份记录"},{id:"verifications",label:"校验结果"},{id:"rehearsals",label:"恢复演练"},{id:"failed",label:"失败记录"}];
const date = (value?:string|null) => value ? new Date(value).toLocaleString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}) : "尚无记录";
const bytes = (value:number|null|undefined) => {
  if(value===null||value===undefined)return "未采集";
  if(!value)return "0 B";
  const unit=Math.min(4,Math.floor(Math.log(value)/Math.log(1024)));
  return `${(value/1024**unit).toLocaleString("zh-CN",{maximumFractionDigits:unit?1:0})} ${["B","KB","MB","GB","TB"][unit]}`;
};
const tone = (status:string) => status==="completed"||status==="available"?"ready":status==="failed"||status==="unavailable"?"failed":status==="low_space"?"limited":"unknown";
const active = (status:string) => status==="queued"||status==="running";
const poll = (value:Snapshot) => value.backups.results.some(row=>active(row.status)&&!row.stalled)||value.verifications.some(row=>active(row.status)&&!row.stalled)?5000:null;

// Only non-secret command fields are retained, under the verified account's key.
function storedCommand(raw:string):Command {
  const value:unknown=JSON.parse(raw);
  if(!value||typeof value!=="object"||Array.isArray(value))throw Error("备份请求记录损坏，请保留本页并核对备份记录后再处理。");
  const row=value as Record<string,unknown>;
  const strings=["base_backup_id","expected_base_checksum","operation","request_id","retry_from_id","backup_id","expected_checksum","verification_id","scope","expected_version","cleanup_id","confirmation"];
  if(Object.entries(row).some(([key,item])=>strings.includes(key)?typeof item!=="string"||item.length>1000:["include_originals","include_indexes","index_only","enabled"].includes(key)?typeof item!=="boolean":["interval_hours","temporary_days"].includes(key)?typeof item!=="number"||!Number.isFinite(item):key==="first_run_at"?item!==null&&typeof item!=="string":key==="cleanup_items"?!Array.isArray(item)||item.length>100||item.some(id=>typeof id!=="string"||!/^[0-9a-f]{24}$/.test(id)):true)
    ||typeof row.request_id!=="string"||! /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(row.request_id)
    ||!["create_backup","verify_archive","restore_plan","close_stalled_verification","save_schedule","close_stalled_backup","save_retention","scan_cleanup","queue_cleanup","cancel_cleanup"].includes(String(row.operation)))throw Error("备份请求记录不完整，请先核对已有备份与计划，避免重复发起。");
  return row as Command;
}

function download(value:unknown,name:string) {
  const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:"application/json;charset=utf-8"}));
  const anchor=document.createElement("a");anchor.href=url;anchor.download=name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}

export function StorageWorkspace() {
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  if(!hasAdminCapability(user,"can_view_system_status"))return <div className="admin-panel"><h1>存储、备份与恢复准备</h1><p>当前账户没有查看运行状态的权限。</p></div>;
  return <Workspace key={`${user?.id}:${epoch}`} owner={String(user?.id||"")} />;
}

function Workspace({owner}:{owner:string}) {
  const [tab,setTab]=useState("backups"),[status,setStatus]=useState(""),[page,setPage]=useState(1),[asOf,setAsOf]=useState("");
  const [selected,setSelected]=useState(""),[showCreate,setShowCreate]=useState(false),[message,setMessage]=useState("");
  const [plan,setPlan]=useState<Plan|null>(null),[unresolved,setUnresolved]=useState<Command|null>(null);
  const [incrementalBase,setIncrementalBase]=useState<Backup|null>(null);
  const [schedule,setSchedule]=useState<Schedule|null>(null),[closeBackup,setCloseBackup]=useState<Backup|null>(null);
  const [showLocations,setShowLocations]=useState(false),[cleanupId,setCleanupId]=useState(""),[editRetention,setEditRetention]=useState<Snapshot["retention_policy"]|null>(null);
  const [recovering,setRecovering]=useState(false),[confirmCancel,setConfirmCancel]=useState(false);
  const [ready,setReady]=useState(false), recoveryKey=`stl-storage-command:${owner}`;
  const query=`${base}?page=${page}&status=${tab==="failed"?"failed":status}${asOf?`&as_of=${encodeURIComponent(asOf)}`:""}`;
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Snapshot>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Snapshot>(query,owner,poll,load);
  const lifecycle=useRef<AbortController|null>(null),busy=useRef(false),pending=useRef<Command|null>(null);
  useEffect(()=>{const controller=new AbortController();lifecycle.current=controller;
    queueMicrotask(()=>{if(controller.signal.aborted)return;try{const raw=sessionStorage.getItem(recoveryKey);pending.current=raw?storedCommand(raw):null;setUnresolved(pending.current);setReady(true);}catch(reason){setMessage(reason instanceof Error?reason.message:"浏览器不能读取原请求，请保留本页并核对备份记录。");}});
    return()=>controller.abort();},[recoveryKey]);
  const data=resource.data, primary=data?.locations[0], disabled=!ready||!data||resource.pending||!!unresolved;

  function clearCommand(){sessionStorage.removeItem(recoveryKey);pending.current=null;setUnresolved(null);}

  function applyReply(reply:Reply, values:Command) {
    if(reply.request_id!==values.request_id||reply.operation!==values.operation)throw Error("回执与原请求不一致，请保留编号并核对记录。");
    clearCommand();setConfirmCancel(false);setPage(1);setAsOf("");
    if(reply.cleanup_id){setCleanupId(reply.cleanup_id);setMessage(values.operation==="scan_cleanup"?"扫描清单已保存，尚未清理。":values.operation==="cancel_cleanup"?"停止请求已登记，请查看逐项结果。":"清理请求已登记，实际结果以逐项任务记录为准。");}
    else if(reply.retention_saved){setEditRetention(null);setMessage("保留规则已保存，没有自动删除；请重新扫描可清理项。");}
    else if(reply.restore_plan){setPlan(reply.restore_plan);setTab("rehearsals");setMessage("演练准备清单已生成，尚未执行恢复。");}
    else if(reply.schedule_saved){setSchedule(null);setMessage("备份计划已保存。实际执行结果将进入备份记录。");}
    else if(reply.backup){setIncrementalBase(null);setShowCreate(false);setCloseBackup(null);setSelected(reply.backup.id);setMessage(values.operation==="close_stalled_backup"?"超时备份记录已关闭，已有归档与原件保留。可在详情中重新发起备份。":"备份请求已登记；生成结果以任务记录为准。");}
    else{setMessage(values.operation==="close_stalled_verification"?"超时记录已关闭，归档保留。可另行发起校验。":"校验请求已登记，不会解压或覆盖现有文件。");}
  }

  async function recover(cancel=false) {
    const values=pending.current,controller=lifecycle.current;
    if(!ready||busy.current||!controller||controller.signal.aborted||!values)return;
    busy.current=true;setRecovering(true);setMessage("");
    try {
      const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
      const receipt=await withPrivateOwner(owner,()=>apiRequest<Receipt>(`${base}commands/${values.request_id}/`,{
        method:cancel?"POST":"GET",signal,cache:"no-store",headers:{"X-Editor-Owner":owner},
        ...(cancel?{body:JSON.stringify({action:"cancel_pending"})}:{})},getServerSessionCredential()),signal);
      if(controller.signal.aborted)return;
      if(receipt.request_id!==values.request_id||receipt.actor_id!==owner)throw Error("返回的记录不属于当前账户的原请求，请保留编号。");
      if(receipt.state==="cancelled") {clearCommand();setConfirmCancel(false);setMessage("原请求已取消。迟到请求不会执行；已有任务、归档与计划保持原结果。");}
      else if(receipt.result)applyReply(receipt.result,values);
      else throw Error("回执缺少操作结果，请保留编号并继续核对。");
      resource.reload();
    } catch(reason) {
      if(controller.signal.aborted)return;
      // A missing/rejected lookup says nothing about an earlier in-flight write.
      setMessage(reason instanceof Error?reason.message:"暂未查到结果，原请求编号仍保留。请稍后查询或取消尚未执行的请求。");
    } finally {if(!controller.signal.aborted){busy.current=false;setRecovering(false);}}
  }

  async function command(intent:Intent) {
    if(!ready||!data||busy.current||!lifecycle.current||lifecycle.current.signal.aborted||pending.current)return;
    const controller=lifecycle.current;
    const values=pending.current||{...intent,request_id:createRequestKey()};
    try{sessionStorage.setItem(recoveryKey,JSON.stringify(values));}catch{setMessage("浏览器不能保存原请求，尚未提交。请保留当前页面并恢复浏览器存储后重试。");return;}
    pending.current=values;busy.current=true;setMessage("");setUnresolved(values);
    let reply:Reply|undefined;
    try {
      const result=await resource.mutate(JSON.stringify(values),async(snapshot)=>{
        const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
        reply=await withPrivateOwner(owner,()=>apiRequest<Reply>(base+"commands/",{method:"POST",signal,cache:"no-store",headers:{"X-Editor-Owner":owner},body:JSON.stringify(values)},getServerSessionCredential()),signal);
        // A received command is authoritative even if the following list read fails.
        return snapshot;
      });
      if(controller.signal.aborted||!result||!reply)return;
      applyReply(reply,values);
    } catch(reason) {
      if(controller.signal.aborted)return;
      if(reason instanceof ApiRequestError&&!(reason instanceof PrivateOwnerVerificationError)&&[400,401,403,404,409,410,422].includes(reason.status)){try{clearCommand();}catch{setMessage("操作被拒绝，但原请求记录暂不能清除，请保留本页并恢复浏览器存储。");return;}}
      setMessage(reason instanceof Error?reason.message:"操作暂未确认，请使用原请求查回。");
    } finally {if(!controller.signal.aborted)busy.current=false;}
  }

  const selectTab=(id:string)=>{setTab(id);setPage(1);setAsOf("");};
  const refresh=()=>{setPage(1);setAsOf("");resource.reload();};
  const verify=(row:Backup)=>void command({operation:"verify_archive",backup_id:row.id,expected_checksum:row.checksum});
  const prepare=(row:Backup)=>void command({operation:"restore_plan",backup_id:row.id,expected_checksum:row.checksum});
  const closeStalled=(row:Verification)=>void command({operation:"close_stalled_verification",backup_id:row.backup_id,expected_checksum:row.expected_checksum,verification_id:row.id});

  const commandFeedback=<>{message?<p className={styles.message} role="status">{message}</p>:null}
    {unresolved&&!resource.pending?<div className={styles.notice} aria-busy={recovering}><CircleAlert size={18}/><p>上次操作尚未确认。原编号 {unresolved.request_id} 已保留。查询只读取结果；取消只拦住尚未登记的迟到请求，不能终止已登记的任务。</p><button type="button" disabled={!ready||recovering} onClick={()=>void recover()}>查回原请求</button><button type="button" disabled={!ready||recovering} onClick={()=>setConfirmCancel(true)}>取消未执行请求</button></div>:null}</>;

  return <main className={styles.page} aria-busy={resource.loading||resource.pending||recovering}>
    <div className={styles.breadcrumb}><Link href="/admin">系统</Link><ChevronRight size={12}/><Link href="/admin/processing/status">运行维护</Link><ChevronRight size={12}/><span>存储、备份与恢复准备</span></div>
    <header className={styles.title}><div><h1>存储、备份与恢复准备</h1><p>管理原件、衍生文件和备份，知道恢复是否经过验证。</p></div><div className={styles.actions}><small>上次更新：{date(data?.checked_at)}</small><button onClick={refresh} disabled={resource.pending||resource.loading}><RefreshCw size={15}/>刷新</button><button className={styles.primary} onClick={()=>setShowCreate(true)} disabled={!data?.permissions.can_backup||disabled}><Database size={15}/>发起备份</button></div></header>
    {resource.error?<div className={styles.alert} role="alert"><CircleAlert size={18}/><p>{resource.error}</p><button onClick={refresh}>重新读取第一页</button></div>:null}
    {commandFeedback}
    {resource.loading?<div className={styles.empty} role="status"><HardDrive size={28}/><p>正在读取存储用量与备份记录</p></div>:null}
    {data?<>
      {data.locations.some(row=>row.status!=="available")?<div className={styles.alert}><CircleAlert size={19}/><div><strong>{data.locations.some(row=>row.status==="low_space")?"部分存储空间不足":"部分存储暂不可读取"}</strong><p>{data.locations.filter(row=>row.status!=="available").map(row=>`${row.label}：${row.status==="low_space"?`可用 ${bytes(row.free_bytes)}`:"目录或访问权限待核对"}`).join("；")}</p></div><button onClick={()=>setShowLocations(true)}>查看存储详情</button></div>:null}
      <div className={styles.overview}>
        <section className={styles.panel}><header><h2>存储位置 / 用量</h2><button onClick={()=>setShowLocations(value=>!value)}>查看详情 <ChevronRight size={14}/></button></header><div className={styles.capacity}><span>馆藏所在卷</span><strong>{bytes(primary?.used_bytes)}</strong><span>/ {bytes(primary?.total_bytes)}</span></div><div className={styles.meterRow}><meter min={0} max={100} value={primary?.used_percent??0} aria-label={primary?.used_percent===null?"所在卷容量未采集":`所在卷已用 ${primary?.used_percent}%`}/><span>{primary?.used_percent===null?"—":`${primary?.used_percent}%`}</span></div><ul className={styles.categories}>{data.categories.map((row,index)=><li key={row.label}><i data-color={index}/><span>{row.label}</span><strong>{bytes(row.bytes)}</strong></li>)}</ul><p className={styles.hint}>{data.file_statistics_notice}</p></section>
        <section className={styles.panel}><header><h2>文件类型分布</h2><span>馆藏登记</span></header><div className={styles.fileTypes}><FileRing rows={data.file_types} total={data.catalog_file_bytes}/><ul className={styles.legend}>{data.file_types.map((row,index)=><li key={row.label}><i data-color={index}/><div><strong>{row.label}</strong><span>{bytes(row.bytes)} · {row.count.toLocaleString()} 个</span></div><small>{data.catalog_file_bytes?`${Math.round(row.bytes*100/data.catalog_file_bytes)}%`:"—"}</small></li>)}</ul></div></section>
        <section className={styles.panel}><header><h2>备份任务状态</h2><button onClick={()=>selectTab("backups")}>查看记录 <ChevronRight size={14}/></button></header>{data.schedule.plans.map((item,index)=><div className={styles.schedule} key={item.scope}>{index?<HardDrive size={19}/>:<Database size={19}/>}<div><strong>{item.label}</strong><p>{item.enabled?`每 ${item.interval_hours} 小时 · 下次 ${date(item.next_run_at)}`:"尚未启用定时计划"}</p>{item.last_error?<p role="status" data-tone="failed">{item.last_error}</p>:null}{item.last_job_id&&data.permissions.can_backup?<button onClick={()=>setSelected(item.last_job_id!)}>查看上次任务</button>:null}</div>{data.permissions.can_backup?<button disabled={disabled} onClick={()=>{if(item.scope==="incremental"&&!item.base_backup_id){setMessage("请先从已校验的全量原件备份详情选择增量基准。");selectTab("backups");}else setSchedule(item);}}>{item.enabled?"调整":"设置"}</button>:<span>{item.enabled?"已启用":"未启用"}</span>}</div>)}<p className={styles.hint}>{data.schedule.detail}{!data.index_backup_configured?" 索引导出共享目录尚未配置，索引计划可保存为停用。":null}</p><Link className={styles.textLink} href="/admin/distribution">查看分发与云存储配置 <ChevronRight size={13}/></Link></section>
      </div>
      {showLocations?<section className={styles.panel}><header><h2>存储位置状态</h2><button onClick={()=>setShowLocations(false)}>收起详情</button></header><div className={styles.tableScroll}><table><thead><tr><th>存储位置</th><th>容量</th><th>已用</th><th>可用</th><th>目录状态</th><th>访问权限</th></tr></thead><tbody>{data.locations.map(row=><tr key={row.id}><th>{row.label}</th><td>{bytes(row.total_bytes)}</td><td>{bytes(row.used_bytes)}</td><td>{bytes(row.free_bytes)}</td><td><span className={styles.status} data-tone={tone(row.status)}>{row.status==="available"?"目录可读":row.status==="low_space"?"空间不足":"暂不可读"}</span></td><td>{row.readable?"可读":"不可读"} / {row.writable?"具有写权限":"未确认写权限"}</td></tr>)}</tbody></table></div><p className={styles.hint}>容量来自所在卷；多个配置目录可能共用同一个卷，不能相加。未执行写入探测，云存储按原分发服务查看。</p></section>:null}
      <div className={styles.recordHeading}><nav className={styles.tabs} aria-label="备份与恢复记录">{tabs.map(item=><button key={item.id} aria-current={tab===item.id?"page":undefined} onClick={()=>selectTab(item.id)}>{item.label}</button>)}</nav><div className={styles.actions}>{tab==="backups"?<label className={styles.filter}>任务状态<select value={status} onChange={event=>{setStatus(event.target.value);setPage(1);setAsOf("");}}><option value="">全部任务</option><option value="queued">等待</option><option value="running">执行中</option><option value="completed">完成</option><option value="failed">失败</option></select></label>:null}{tab!=="verifications"&&tab!=="rehearsals"?<button onClick={()=>download({checked_at:data.checked_at,scope:tab==="backups"||tab==="failed"?`第 ${page} 页`:"当前显示记录",as_of:data.backups.as_of,records:data.backups.results},`stl-storage-${tab}.json`)}><Download size={14}/>导出当前记录</button>:null}</div></div>
      <div className={styles.notice}><CircleAlert size={17}/><strong>近期窗口内恢复演练：{!data.permissions.can_prepare_restore?"需要维护权限":data.rehearsals.length?date(data.rehearsals[0].checked_at):data.rehearsals_limited?"记录尚未完整核实":"尚无可核实记录"}</strong><button onClick={()=>selectTab("rehearsals")}>查看恢复演练 <ChevronRight size={14}/></button><p>备份生成后仍需校验，并在隔离环境中核对恢复结果。{data.rehearsals_limited?" 摘要只读取近期窗口，请进入恢复历史继续翻页；未核实记录不代表没有演练。":""}</p></div>
      {tab==="backups"||tab==="failed"?<><BackupTable rows={data.backups.results} canInspect={data.permissions.can_backup} onSelect={setSelected}/><div className={styles.pagination}><span>共 {data.backups.count} 条记录 · 第 {page} 页</span><button disabled={page<=1||resource.pending} onClick={()=>{setAsOf(data.backups.as_of);setPage(value=>value-1);}}>上一页</button><button disabled={page*data.backups.page_size>=data.backups.count||resource.pending} onClick={()=>{setAsOf(data.backups.as_of);setPage(value=>value+1);}}>下一页</button></div></>:tab==="verifications"?<VerificationHistory owner={owner} revision={data.checked_at} canOperate={data.permissions.can_verify} disabled={disabled} onSelect={setSelected} onCloseStalled={closeStalled}/>:<div>{data.permissions.can_prepare_restore?<RestoreHistory owner={owner} onExport={download}/>:<p className={styles.hint}>恢复记录与准备清单仅对具有备份维护权限的账户显示。</p>}{plan?<div className={styles.plan}><h3>隔离恢复准备清单</h3><p>{plan.archive_name}</p><span className={styles.status} data-tone={plan.ready_for_rehearsal?"ready":"limited"}>{plan.ready_for_rehearsal?"已存在归档校验记录":"请先校验归档"}</span><ol>{plan.requirements.map(text=><li key={text}>{text}</li>)}</ol><button onClick={()=>download(plan,`stl-restore-plan-${plan.backup_id}.json`)}><Download size={14}/>下载准备清单</button><p className={styles.hint}>当前只生成清单，未执行数据库或索引恢复。</p></div>:null}</div>}
      <div className={styles.bottom}><section className={styles.panel}><header><h2>数据保留规则</h2>{data.permissions.can_cleanup?<button type="button" disabled={disabled} onClick={()=>setEditRetention(data.retention_policy)}>编辑规则</button>:<ShieldCheck size={17}/>}</header><div className={styles.tableScroll}><table><thead><tr><th>数据类型</th><th>保留策略</th><th>说明</th></tr></thead><tbody>{data.retention.map(row=><tr key={row.label}><th>{row.label}</th><td>{row.policy}</td><td>{row.detail}</td></tr>)}<tr><th>上传导入临时文件</th><td>至少闲置 {data.retention_policy.temporary_days} 天</td><td>须扫描、核对永久原件及明确确认；不自动删除。</td></tr></tbody></table></div><p className={styles.hint}>读者私人内容沿原读者中心设置管理；维护页面不会改写本人偏好。</p></section><StorageCleanup key={cleanupId||data.cleanup.latest_id||"not-scanned"} owner={owner} id={cleanupId||data.cleanup.latest_id||""} revision={data.checked_at} disabled={disabled} canOperate={!!data.permissions.can_cleanup} feedback={commandFeedback} onCommand={values=>void command(values)}/></div>
    </>:null}
    {selected&&data?.permissions.can_backup?<BackupDetails onOpenBase={setSelected} onIncremental={row=>{setSelected("");setIncrementalBase(row);}} feedback={commandFeedback} key={selected} owner={owner} id={selected} revision={data.checked_at} disabled={disabled} onClose={()=>setSelected("")} onVerify={verify} onPrepare={row=>{setSelected("");prepare(row);}} onRetry={row=>void command({operation:"create_backup",include_originals:row.include_originals,include_indexes:row.include_indexes,index_only:row.index_only,retry_from_id:row.id,...(row.incremental_base_id?{base_backup_id:row.incremental_base_id,expected_base_checksum:row.incremental_base_checksum}: {})})} onCloseBackup={setCloseBackup} onCloseStalled={closeStalled}/>:null}
    {incrementalBase&&data?<IncrementalBackup value={incrementalBase} disabled={disabled} feedback={commandFeedback} onClose={()=>setIncrementalBase(null)} onCreate={()=>void command({operation:"create_backup",include_originals:true,base_backup_id:incrementalBase.id,expected_base_checksum:incrementalBase.checksum})} onSchedule={()=>{const original=data.schedule.plans.find(item=>item.scope==="incremental");if(original){setSchedule({...original,base_backup_id:incrementalBase.id,base_checksum:incrementalBase.checksum});setIncrementalBase(null);}}}/>:null}
    {showCreate?<CreateBackup indexConfigured={Boolean(data?.index_backup_configured)} feedback={commandFeedback} disabled={disabled} onClose={()=>setShowCreate(false)} onCreate={(include,indexes,indexOnly)=>void command({operation:"create_backup",include_originals:include,include_indexes:indexes,index_only:indexOnly})}/>:null}
    {closeBackup?<Dialog open className={styles.dialog} onRequestClose={()=>setCloseBackup(null)} aria-labelledby="close-backup-title"><header><h2 id="close-backup-title">关闭这条超时备份记录？</h2><button type="button" aria-label="返回备份详情" onClick={()=>setCloseBackup(null)}><X size={18}/></button></header>{commandFeedback}<p>{date(closeBackup.created_at)} · {closeBackup.scope}</p><p>已超过配置的任务时限。关闭记录不会直接终止工作进程；旧任务再有响应时不能登记成功，并清理它本次尚未接受的临时归档。已有备份和原件保留。</p><p>任务若刚刚完成，系统会保留完成结果并要求重新读取。关闭后可明确重新发起一份备份。</p><footer><button type="button" onClick={()=>setCloseBackup(null)}>保留记录</button><button type="button" className={styles.primary} disabled={disabled} onClick={()=>void command({operation:"close_stalled_backup",backup_id:closeBackup.id,expected_version:closeBackup.version})}>确认关闭超时记录</button></footer></Dialog>:null}
    {schedule?<ScheduleEditor indexConfigured={Boolean(data?.index_backup_configured)} key={`${schedule.scope}:${schedule.version}`} feedback={commandFeedback} value={schedule} disabled={disabled} onClose={()=>setSchedule(null)} onSave={values=>void command(values)}/>:null}
    {editRetention&&data?<StorageRetentionEditor policy={editRetention} disabled={disabled} onClose={()=>setEditRetention(null)} onCommand={values=>void command(values)} feedback={commandFeedback}/>:null}
    {confirmCancel&&unresolved?<Dialog open className={styles.dialog} onRequestClose={()=>setConfirmCancel(false)} aria-labelledby="cancel-storage-title"><header><h2 id="cancel-storage-title">取消尚未执行的请求？</h2><button type="button" aria-label="返回维护页面" onClick={()=>setConfirmCancel(false)}><X size={18}/></button></header><p>系统会先核对原编号。如果已经登记，将返回原结果；如果尚未登记，将阻止这条迟到请求执行。此操作不能中止正在运行的备份或校验。</p><p role="status">{message}</p><footer><button type="button" onClick={()=>setConfirmCancel(false)}>继续等待</button><button type="button" className={styles.primary} disabled={!ready||recovering} onClick={()=>void recover(true)}>确认取消未执行请求</button></footer></Dialog>:null}
  </main>;
}

function FileRing({rows,total}:{rows:Snapshot["file_types"];total:number}) {
  let offset=0;
  const segments=rows.map((row,index)=>{const start=offset,length=total?row.bytes*100/total:0;offset+=length;return <circle key={row.label} cx="60" cy="60" r="46" pathLength="100" fill="none" strokeWidth="17" strokeDasharray={`${length} ${100-length}`} strokeDashoffset={-start} data-color={index}/>;});
  return <div className={styles.ring}><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r="46" fill="none" strokeWidth="17" className={styles.ringTrack}/><g transform="rotate(-90 60 60)">{total?segments:null}</g></svg><div><strong>{bytes(total)}</strong><span>登记文件</span></div></div>;
}

function BackupTable({rows,canInspect,onSelect}:{rows:Backup[];canInspect:boolean;onSelect:(id:string)=>void}) {
  if(!rows.length)return <div className={styles.empty}><Database size={28}/><strong>暂无符合条件的备份记录</strong><p>已有文件不会自动算作备份；可按权限发起并查看实际任务结果。</p></div>;
  return <div className={styles.tableScroll}><table className={styles.backupTable}><thead><tr><th>开始时间</th><th>任务类型</th><th>备份内容</th><th>存储位置</th><th>大小</th><th>用时</th><th>状态</th><th>操作</th></tr></thead><tbody>{rows.map(row=><tr key={row.id} data-failed={row.status==="failed"||undefined}><td><time dateTime={row.started_at||row.created_at}>{date(row.started_at||row.created_at)}</time></td><td>归档备份</td><td>{row.scope}</td><td title={row.archive_name}>{row.location}</td><td>{bytes(row.archive_bytes)}</td><td>{row.duration_seconds===null?"—":`${row.duration_seconds} 秒`}</td><td><span className={styles.status} data-tone={row.stalled?"limited":tone(row.status)}>{row.status_label}</span></td><td>{canInspect?<button aria-label={`查看 ${date(row.created_at)} 的备份详情`} onClick={()=>onSelect(row.id)}>查看详情</button>:<span>仅查看状态</span>}</td></tr>)}</tbody></table></div>;
}

function VerificationList({rows,canOperate,disabled,onSelect,onCloseStalled}:{rows:Verification[];canOperate:boolean;disabled:boolean;onSelect:(id:string)=>void;onCloseStalled:(row:Verification)=>void}) {
  if(!rows.length)return <div className={styles.empty}><FileCheck2 size={28}/><strong>暂无归档校验记录</strong><p>备份生成和校验分别记录。选择已完成的备份后可以发起校验。</p></div>;
  return <div className={styles.tableScroll}><table><thead><tr><th>发起时间</th><th>校验状态</th><th>结果与下一步</th><th>操作</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{date(row.created_at)}</td><td><span className={styles.status} data-tone={row.stalled?"limited":tone(row.status)}>{row.status_label}</span></td><td>{row.error_message||row.detail||(row.stalled?"已超过任务时限，请关闭本条超时记录后再决定是否重新校验。":"归档只读校验等待完成。")}{row.status==="completed"?<small className={styles.block}>{row.database_verified?"数据库文件校验已完成。":"此记录未校验数据库。"}{row.index_verified?" 索引导出文件校验已完成。":""} 包含原件 {row.originals_verified} 个。未执行恢复。</small>:null}</td><td>{canOperate?<div className={styles.rowActions}><button onClick={()=>onSelect(row.backup_id)}>查看备份</button>{row.stalled?<button disabled={disabled} onClick={()=>onCloseStalled(row)}>关闭超时记录</button>:null}</div>:"仅查看状态"}</td></tr>)}</tbody></table></div>;
}


function VerificationHistory({owner,backupId,revision,canOperate,disabled,onSelect,onCloseStalled}:{owner:string;backupId?:string;revision:string;canOperate:boolean;disabled:boolean;onSelect:(id:string)=>void;onCloseStalled:(row:Verification)=>void}) {
  const [page,setPage]=useState(1),[status,setStatus]=useState(""),[asOf,setAsOf]=useState("");
  const params=new URLSearchParams({page:String(page),status});if(asOf)params.set("as_of",asOf);if(backupId)params.set("backup_id",backupId);
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<VerificationPage>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<VerificationPage>(`${base}verifications/?${params}`,owner,value=>value.results.some(row=>active(row.status)&&!row.stalled)?5000:null,load);
  const reload=resource.reload;
  useEffect(()=>reload(),[revision,reload]);
  const data=resource.data;
  const refresh=()=>{setPage(1);setAsOf("");reload();};
  return <section aria-label={backupId?"本份备份的全部校验记录":"全部归档校验记录"} aria-busy={resource.loading}>
    <div className={styles.historyTools}><label className={styles.filter}>校验状态<select value={status} onChange={event=>{setStatus(event.target.value);setPage(1);setAsOf("");}}><option value="">全部结果</option><option value="queued">等待</option><option value="running">执行中</option><option value="completed">完成</option><option value="failed">失败</option></select></label><button type="button" onClick={refresh}>读取最新记录</button><button type="button" disabled={!data||!!resource.error} onClick={()=>data&&download({as_of:data.as_of,status,backup_id:backupId||null,page:data.page,total:data.count,records:data.results},`stl-verifications-${page}.json`)}><Download size={14}/>导出本页</button></div>
    {resource.error?<div className={styles.alert} role="alert"><p>{resource.error}</p><button type="button" onClick={refresh}>返回第一页</button></div>:null}
    {resource.loading?<p role="status">正在读取校验记录…</p>:null}
    {data?<><VerificationList rows={data.results} canOperate={canOperate} disabled={disabled||!!resource.error} onSelect={onSelect} onCloseStalled={onCloseStalled}/><p className={styles.hint}>显示截至 {date(data.as_of)} 创建的记录，任务状态仍按当前进度更新；筛选结果变化时可重新读取第一页。</p><nav className={styles.pagination} aria-label="归档校验记录分页"><span>共 {data.count} 条 · 第 {data.page}/{data.total_pages} 页</span><button type="button" disabled={page<=1||resource.loading} onClick={()=>{setAsOf(data.as_of);setPage(value=>value-1);}}>上一页</button><button type="button" disabled={page>=data.total_pages||resource.loading} onClick={()=>{setAsOf(data.as_of);setPage(value=>value+1);}}>下一页</button></nav></>:null}
  </section>;
}

function BackupDetails({owner,id,revision,disabled,onClose,onVerify,onPrepare,onRetry,onCloseStalled,onCloseBackup,feedback,onIncremental,onOpenBase}:{onIncremental:(row:Backup)=>void;onOpenBase:(id:string)=>void;feedback:ReactNode;owner:string;id:string;revision:string;disabled:boolean;onClose:()=>void;onVerify:(row:Backup)=>void;onPrepare:(row:Backup)=>void;onRetry:(row:Backup)=>void;onCloseStalled:(row:Verification)=>void;onCloseBackup:(row:Backup)=>void}) {
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Detail>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Detail>(`${base}backups/${id}/`,owner,value=>active(value.backup.status)&&!value.backup.stalled||value.verifications.some(row=>active(row.status)&&!row.stalled)?5000:null,load);
  const reload=resource.reload;
  useEffect(()=>reload(),[revision,reload]);
  const row=resource.data?.backup;
  return <Dialog open className={styles.dialog} onRequestClose={onClose} aria-labelledby="backup-detail-title"><header><div><span>备份记录</span><h2 id="backup-detail-title">备份详情与恢复准备</h2></div><button aria-label="关闭备份详情" onClick={onClose}><X size={18}/></button></header>{feedback}{resource.error?<p role="alert">{resource.error}<button onClick={()=>resource.reload()}>重新读取</button></p>:null}{resource.loading?<p role="status">正在读取备份详情…</p>:null}{row?<><dl className={styles.details}><div><dt>状态</dt><dd><span className={styles.status} data-tone={row.stalled?"limited":tone(row.status)}>{row.status_label}</span></dd></div><div><dt>备份内容</dt><dd>{row.scope}</dd></div>{row.incremental_base_id?<div><dt>所需完整基准</dt><dd><button type="button" disabled={disabled} onClick={()=>onOpenBase(row.incremental_base_id!)}>查看基准备份</button><span className={styles.checksum}>{row.incremental_base_checksum}</span><p>两份归档必须同时保留；增量归档不能独立恢复全部原件。</p></dd></div>:null}{row.include_indexes?<div><dt>检索索引</dt><dd>{row.index_detail}{row.index_task_uid!==null?<p>导出任务编号：{row.index_task_uid}</p>:null}{row.index_export_unknown?<p role="status">导出响应未知，请先核对远端任务。本记录不会自动重发；确需另一次导出时请从发起备份新建任务。</p>:null}</dd></div>:null}<div><dt>数据库与清单</dt><dd>{row.consistency_detail||"此旧记录尚未登记共享快照证据，须在隔离恢复时核对。"}</dd></div><div><dt>归档文件</dt><dd>{row.archive_name}</dd></div><div><dt>归档大小</dt><dd>{bytes(row.archive_bytes)}</dd></div><div><dt>发起时间</dt><dd>{date(row.created_at)}</dd></div><div><dt>完成时间</dt><dd>{date(row.completed_at)}</dd></div><div><dt>归档身份</dt><dd className={styles.checksum}>{row.checksum||"尚未生成"}</dd></div></dl>{row.error_message?<div className={styles.alert}><CircleAlert size={18}/><p>{row.error_message}</p></div>:null}{resource.data?.technical_error?<details className={styles.technical}><summary>查看错误详情</summary><pre>{resource.data.technical_error}</pre></details>:null}{row.stalled?<p className={styles.notice}>此记录已超过配置的任务时限，执行结果尚未确认。先刷新详情；若仍未结束，可关闭超时记录后重新发起。</p>:null}<div className={styles.actions}>{row.stalled?<button type="button" disabled={disabled} onClick={()=>onCloseBackup(row)}>核对并关闭超时记录</button>:null}{row.status==="failed"?<button className={styles.primary} disabled={disabled||row.index_export_unknown} onClick={()=>onRetry(row)}>{row.include_indexes&&row.index_task_uid!==null?"继续核对原索引导出并重做归档":"重新发起备份"}</button>:null}{row.status==="completed"?<><button className={styles.primary} disabled={disabled||resource.data?.verifications.some(item=>active(item.status))} onClick={()=>onVerify(row)}><FileCheck2 size={15}/>校验归档</button><button disabled={disabled} onClick={()=>onPrepare(row)}>准备隔离恢复</button>{row.can_seed_incremental?<button type="button" disabled={disabled} onClick={()=>onIncremental(row)}>用作增量基准</button>:null}</>:null}<button onClick={()=>resource.reload()}>刷新详情</button></div><h3>归档校验记录</h3><VerificationHistory owner={owner} backupId={id} revision={revision} canOperate disabled={disabled} onSelect={()=>resource.reload()} onCloseStalled={onCloseStalled}/>{row.checksum?<RestoreHistory key={row.checksum} owner={owner} backupId={id} onExport={download}/>:<p className={styles.hint}>归档身份生成后可查看相应的恢复记录。</p>}</>:null}</Dialog>;
}

function CreateBackup({disabled,onClose,onCreate,feedback,indexConfigured}:{feedback:ReactNode;disabled:boolean;indexConfigured:boolean;onClose:()=>void;onCreate:(include:boolean,indexes:boolean,indexOnly:boolean)=>void}) {
  const [include,setInclude]=useState(false),[indexes,setIndexes]=useState(false),[indexOnly,setIndexOnly]=useState(false);
  return <Dialog open className={styles.dialog} onRequestClose={onClose} aria-labelledby="create-backup-title"><form onSubmit={event=>{event.preventDefault();onCreate(indexOnly?false:include,indexOnly||indexes,indexOnly);}}><header><div><span>创建备份任务</span><h2 id="create-backup-title">发起备份</h2></div><button type="button" aria-label="关闭备份设置" onClick={onClose}><X size={18}/></button></header>{feedback}<p>归档写入配置的 NAS 备份目录。已有归档、原件和活动索引保留。</p><label className={styles.checkbox}><input type="checkbox" checked={indexOnly} disabled={disabled||!indexConfigured} onChange={event=>setIndexOnly(event.target.checked)}/><span><strong>仅备份检索索引</strong><small>导出同一实例的全部索引，不含数据库、原件和模型。</small></span></label>{!indexOnly?<><label className={styles.checkbox}><input type="checkbox" checked={include} disabled={disabled} onChange={event=>setInclude(event.target.checked)}/><span><strong>数据库备份同时包含原始文件</strong><small>原件副本按现有校验身份核对；归档会增大。</small></span></label><label className={styles.checkbox}><input type="checkbox" checked={indexes} disabled={disabled||!indexConfigured} onChange={event=>setIndexes(event.target.checked)}/><span><strong>同时包含检索索引</strong><small>索引与数据库不共享事务时点，恢复后需核对代次、公开范围和私人权限。</small></span></label></>:null}{!indexConfigured?<p className={styles.notice}>索引导出共享目录尚未配置。数据库与原件备份仍可使用；配置挂载后才可选择索引。</p>:null}<p className={styles.hint}>归档可能包含账户、私人资料及索引配置，沿原维护权限保存，不提供公共下载。首次索引导出响应未知时不自动重发；另行新建可能产生第二份导出，已有文件保留。</p><footer><button type="button" onClick={onClose}>返回</button><button className={styles.primary} type="submit" disabled={disabled||((indexOnly||indexes)&&!indexConfigured)}><Database size={15}/>确认发起备份</button></footer></form></Dialog>;
}

function ScheduleEditor({value,disabled,onClose,onSave,feedback,indexConfigured}:{indexConfigured:boolean;feedback:ReactNode;value:Schedule;disabled:boolean;onClose:()=>void;onSave:(values:Intent)=>void}) {
  const [enabled,setEnabled]=useState(value.enabled),[hours,setHours]=useState(value.interval_hours),[indexes,setIndexes]=useState(value.include_indexes);
  const [initialFirst]=useState(()=>{
    const target=value.next_run_at?new Date(value.next_run_at):new Date(Date.now()+3600000);
    return new Date(target.getTime()-target.getTimezoneOffset()*60000).toISOString().slice(0,16);
  });
  const [first,setFirst]=useState(initialFirst),[discard,setDiscard]=useState(false);
  const dirty=enabled!==value.enabled||hours!==value.interval_hours||first!==initialFirst||indexes!==value.include_indexes;
  useUnsavedForm(dirty,false);
  function requestClose(){if(dirty)setDiscard(true);else onClose();}
  return <><Dialog open className={styles.dialog} onRequestClose={requestClose} aria-labelledby="backup-schedule-title"><form onSubmit={event=>{
    event.preventDefault();
    onSave({operation:"save_schedule",scope:value.scope as "database"|"originals"|"incremental"|"indexes",include_indexes:value.scope==="indexes"||indexes,...(value.scope==="incremental"&&value.base_backup_id?{base_backup_id:value.base_backup_id,expected_base_checksum:value.base_checksum}:{}),enabled,interval_hours:hours,first_run_at:enabled?new Date(first).toISOString():null,expected_version:value.version});
  }}><header><div><span>备份计划</span><h2 id="backup-schedule-title">{value.label}</h2>{value.scope==="incremental"?<p>每次保存完整数据库与相对基准变化的原件。基准 {value.base_backup_id||"尚未选择"} 必须长期保留；更换基准需从已校验全量备份详情重新选择。</p>:null}</div><button type="button" aria-label="关闭备份计划" onClick={requestClose}><X size={18}/></button></header>{feedback}<label className={styles.checkbox}><input type="checkbox" checked={enabled} disabled={disabled} onChange={event=>setEnabled(event.target.checked)}/><span><strong>启用定时备份</strong><small>由现有后台任务服务执行。上次任务未结束时不会叠加同一计划的任务。</small></span></label>{value.scope!=="indexes"?<label className={styles.checkbox}><input type="checkbox" checked={indexes} disabled={disabled||(!indexConfigured&&!indexes)} onChange={event=>setIndexes(event.target.checked)}/><span>每次同时包含检索索引。索引与数据库时点需在隔离恢复中核对。</span></label>:<p className={styles.hint}>此计划仅保存检索索引；数据库、原件和模型须分别备份。</p>}{!indexConfigured&&(value.scope==="indexes"||indexes)?<p role="status">索引导出共享目录未配置，目前可保存为停用计划。</p>:null}<div className={styles.scheduleFields}><label>执行间隔（小时）<input type="number" min={6} max={720} required value={hours} disabled={disabled} onChange={event=>setHours(Number(event.target.value))}/></label><label>首次执行时间（本地时区）<input type="datetime-local" value={first} required={enabled} disabled={disabled||!enabled} onChange={event=>setFirst(event.target.value)}/></label></div><p className={styles.hint}>最短间隔 6 小时，最长 30 天。每次生成归档，仍需单独校验和演练；增量归档须同时保留基准。索引备份失败或配置账户失去维护权限时计划暂停。重新启用会开始新的导出，旧任务和文件保留。</p><footer><button type="button" onClick={requestClose}>返回</button><button type="submit" className={styles.primary} disabled={disabled||(enabled&&(value.scope==="indexes"||indexes)&&!indexConfigured)}>保存计划</button></footer></form></Dialog>{discard?<Dialog open className={styles.dialog} onRequestClose={()=>setDiscard(false)} aria-label="备份计划尚未保存"><h2>保留未保存的备份计划？</h2><p>返回继续编辑会保留当前输入。放弃后已保存的计划仍按原规则执行，待定请求仍需核对。</p><footer><button type="button" onClick={()=>setDiscard(false)}>继续编辑</button><button type="button" onClick={onClose}>放弃本次编辑</button></footer></Dialog>:null}</>;
}


function IncrementalBackup({value,disabled,feedback,onClose,onCreate,onSchedule}:{value:Backup;disabled:boolean;feedback:ReactNode;onClose:()=>void;onCreate:()=>void;onSchedule:()=>void}) {
  const [confirmed,setConfirmed]=useState(false);
  return <Dialog open className={styles.dialog} onRequestClose={onClose} aria-labelledby="incremental-backup-title"><header><h2 id="incremental-backup-title">设置增量原件备份</h2><button type="button" aria-label="关闭增量备份" onClick={onClose}><X size={18}/></button></header>{feedback}<p>以 {date(value.created_at)} 的全量原件备份作为固定基准。后台会重新校验基准，再保存当前完整数据库，以及新增或变化的原件；不会删除基准、馆藏或旧归档。</p><dl className={styles.details}><div><dt>完整基准</dt><dd>{value.archive_name}</dd></div><div><dt>归档身份</dt><dd className={styles.checksum}>{value.checksum}</dd></div></dl><label className={styles.checkbox}><input type="checkbox" checked={confirmed} disabled={disabled} onChange={event=>setConfirmed(event.target.checked)}/><span>我已了解恢复全部原件时需要同时保留这份完整基准和新的增量归档。</span></label><footer><button type="button" disabled={disabled||!confirmed} onClick={onSchedule}>配置定时增量</button><button type="button" className={styles.primary} disabled={disabled||!confirmed} onClick={onCreate}>立即发起增量备份</button></footer></Dialog>;
}
