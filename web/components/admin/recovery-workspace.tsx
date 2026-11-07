"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArchiveRestore, BookOpen, ChevronLeft, ChevronRight, CircleAlert, Funnel, History, RefreshCw, Search, X } from "lucide-react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./recovery-workspace.module.css";
import { RecoveryBatch } from "./recovery-batch";
import { RecoveryRestoreDialog } from "./recovery-restore-dialog";
import { parseRecoveryBatch, recoveryBatchKey, type RecoveryBatchState } from "./recovery-batch-state";

type Directory=components["schemas"]["RecoveryDirectory"];
type Detail=components["schemas"]["RecoveryDetail"];
type RelatedPage=components["schemas"]["RecoveryRelatedPage"];
type Result=components["schemas"]["RecoveryResult"];
type Receipt=components["schemas"]["RecoveryReceipt"];
type Request=components["schemas"]["RecoveryConfirmInputRequest"];
type Target={kind:string;object_id:string};
const base="/catalog/admin/recycle/";
const requestKey=(owner:string)=>`stl-recovery-command:${owner}`;
function savedRestore(raw:string):Request{
  const value=JSON.parse(raw) as Request;
  const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  if(!value||typeof value!=="object"||!["confirmed,expected_version,kind,object_id,request_id","confirmed,expected_version,keep_separate,kind,object_id,request_id"].includes(Object.keys(value).sort().join())||("keep_separate" in value&&typeof value.keep_separate!=="boolean")||!uuid.test(value.request_id)||!uuid.test(value.object_id)||! /^[a-f0-9]{64}$/.test(value.expected_version)||typeof value.kind!=="string"||value.confirmed!==true)throw Error("原恢复请求记录不完整，请保留本页并核对对象变更历史。");
  return value;
}
const labels:Record<string,string>={deleted:"已删除",archived:"已归档",restored:"已恢复",retained:"关联保留"};
const date=(value?:string|null)=>value?new Date(value).toLocaleString("zh-CN",{year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}):"未记录";

export function RecoveryWorkspace(){
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  if(!hasAdminCapability(user,"can_edit_metadata"))return <div className="admin-panel"><h1>回收、变更历史与恢复</h1><p>当前账户没有查看或恢复管理内容的权限。</p></div>;
  return <Workspace key={`${user?.id}:${epoch}`} owner={String(user?.id||"")}/>;
}

function Workspace({owner}:{owner:string}){
  const [state,setState]=useState(""),[kind,setKind]=useState(""),[search,setSearch]=useState(""),[input,setInput]=useState("");
  const [period,setPeriod]=useState(""),[since,setSince]=useState(""),[page,setPage]=useState(1),[pageSize,setPageSize]=useState(10),[filtersOpen,setFiltersOpen]=useState(false),[selected,setSelected]=useState<Target|null>(null),[singleLocked,setLocked]=useState(false);
  const [operator,setOperator]=useState(""),[reason,setReason]=useState(""),[reasonQuery,setReasonQuery]=useState(""),[mobile,setMobile]=useState(false);
  useEffect(()=>{const media=window.matchMedia("(max-width:760px)"),update=()=>setMobile(media.matches);update();media.addEventListener("change",update);return()=>media.removeEventListener("change",update);},[]);
  const [chosen,setChosen]=useState<Target[]>([]),[batchTargets,setBatchTargets]=useState<Target[]|null>(null),[batchSaved,setBatchSaved]=useState<RecoveryBatchState|null>(null),[batchOpen,setBatchOpen]=useState(false);
  const [original,setOriginal]=useState<Request|null>(null),[ready,setReady]=useState(false),[recoveryError,setRecoveryError]=useState("");
  useEffect(()=>{let alive=true;queueMicrotask(()=>{if(!alive)return;try{const raw=sessionStorage.getItem(requestKey(owner));if(raw){const value=savedRestore(raw);setOriginal(value);setSelected(value);setLocked(true);}const batchRaw=sessionStorage.getItem(recoveryBatchKey(owner));if(batchRaw){const saved=parseRecoveryBatch(batchRaw);setBatchSaved(saved);setBatchTargets(saved.items.map(item=>item.command));setBatchOpen(!raw);}setReady(true);}catch(reason){setRecoveryError(reason instanceof Error?reason.message:"不能读取原恢复请求，请保留本页。");}});return()=>{alive=false;};},[owner]);
  const locked=singleLocked||batchTargets!==null||!ready;
  function preserve(value:Request|null){if(value){const {request_id,kind,object_id,expected_version,confirmed}=value;sessionStorage.setItem(requestKey(owner),JSON.stringify({request_id,kind,object_id,expected_version,confirmed}));}else sessionStorage.removeItem(requestKey(owner));setOriginal(value);}
  const url=`${base}?page=${page}&page_size=${pageSize}&search=${encodeURIComponent(search)}&kind=${kind}&state=${state}&operator=${encodeURIComponent(operator)}&reason=${encodeURIComponent(reasonQuery)}${since?`&since=${encodeURIComponent(since)}`:""}`;
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Directory>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Directory>(url,owner,undefined,load),data=resource.data;
  const reset=()=>{setPage(1);setSelected(null);setChosen([]);};
  const choose=(target:Target)=>{if(ready&&!locked)setSelected(target);};
  const selectedRows=data?.results.filter(row=>row.record_state!=="restored"&&chosen.some(item=>item.kind===row.kind&&item.object_id===row.object_id))||[];
  const availableRows=data?.results.filter(row=>row.record_state!=="restored")||[];
  function toggle(target:Target,checked:boolean){setChosen(previous=>checked?[...previous.filter(item=>item.kind!==target.kind||item.object_id!==target.object_id),target].slice(0,20):previous.filter(item=>item.kind!==target.kind||item.object_id!==target.object_id));}
  function openBatch(){if(locked||!selectedRows.length)return;setBatchTargets(selectedRows.map(row=>({kind:row.kind,object_id:row.object_id})));setBatchOpen(true);setSelected(null);}
  function closeBatch(){sessionStorage.removeItem(recoveryBatchKey(owner));setBatchTargets(null);setBatchSaved(null);setBatchOpen(false);setChosen([]);resource.reload();}
  const details=selected?<ObjectDetail key={`${selected.kind}:${selected.object_id}`} owner={owner} target={selected} initialCommand={original} preserve={preserve} onSelect={choose} onClose={()=>setSelected(null)} onLock={setLocked} onChanged={resource.reload}/>:null;
  return <main className={styles.page}>
    <div className={styles.breadcrumb}><Link href="/admin">首页</Link><ChevronRight size={12}/><Link href="/admin/processing/status">运行维护</Link><ChevronRight size={12}/><span>回收、变更历史与恢复</span></div>

    {recoveryError?<p className={styles.error} role="alert">{recoveryError}</p>:null}
    {batchTargets&&!batchOpen?<div className={styles.notice}><p>有一批已确认的恢复记录尚待处理。</p><button disabled={singleLocked||!!original} onClick={()=>setBatchOpen(true)}>继续核对上次批量恢复</button></div>:null}
    <div className={styles.workspace} data-detail={!!selected}>
      <section className={styles.directory} aria-label="回收与归档对象">
    <header className={styles.title}><div><h1>回收、变更历史与恢复</h1></div><button aria-label="刷新回收与归档记录" className={styles.refresh} onClick={()=>{setChosen([]);resource.reload();}} disabled={locked||resource.loading}><RefreshCw size={15}/></button></header>
        <nav className={styles.tabs} aria-label="回收记录范围">{[["","全部"],["deleted","已删除"],["archived","已归档"],["restored","其他变更"]].map(([key,label])=><button key={key} disabled={locked} aria-current={state===key?"page":undefined} onClick={()=>{setState(key);reset();}}>{label}<span>{data?(key?data.counts[key]||0:Object.values(data.counts).reduce((sum,count)=>sum+count,0)):"—"}</span></button>)}</nav>
        <form className={styles.filters} data-open={filtersOpen} onSubmit={event=>{event.preventDefault();setSearch(input);setReasonQuery(reason);reset();}}><label className={styles.search}><button type="submit" aria-label="查找回收对象" disabled={locked}><Search size={15}/></button><input aria-label="搜索回收内容名称" placeholder="搜索标题、名称…" value={input} disabled={locked} onChange={event=>setInput(event.target.value)}/></label><button type="button" className={styles.mobileFilter} aria-label="展开或收起筛选" aria-expanded={filtersOpen} disabled={locked} onClick={()=>setFiltersOpen(value=>!value)}><Funnel size={17}/></button><label className={styles.filterLabel}><span>对象类型</span><select aria-label="对象类型" value={kind} disabled={locked} onChange={event=>{setKind(event.target.value);reset();}}><option value="">全部类型</option>{data?.kinds.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label className={styles.filterLabel}><span>时间</span><select aria-label="操作时间" value={period} disabled={locked} onChange={event=>{setPeriod(event.target.value);setSince(event.target.value?new Date(Date.now()-Number(event.target.value)*86400000).toISOString():"");reset();}}><option value="">时间</option><option value="7">近7天</option><option value="30">近30天</option><option value="90">近90天</option></select></label><label className={styles.filterLabel}><span>操作人</span><select aria-label="操作人" value={operator} disabled={locked} onChange={event=>{setOperator(event.target.value);reset();}}><option value="">操作者</option>{data?.operators.map(row=><option key={row.id} value={row.id}>{row.label||"未填写姓名"}</option>)}</select></label><label className={styles.filterLabel}><span>原因</span><input aria-label="筛选操作原因" maxLength={200} value={reason} disabled={locked} onChange={event=>setReason(event.target.value)} placeholder="原因" onBlur={()=>{if(reasonQuery!==reason){setReasonQuery(reason);reset();}}}/></label></form>{data?.operators_limited?<p className={styles.hint}>操作人超过100位，请先缩小对象或时间范围。</p>:null}
        {resource.error?<div className={styles.error} role="alert">{resource.error}<button onClick={()=>resource.reload()}>重新读取</button></div>:null}
        {resource.loading?<div className={styles.empty} role="status">正在读取回收和归档记录…</div>:null}
        {data?<><div className={styles.bulkTools} hidden={!selectedRows.length}><span>已选本页 {selectedRows.length} 项</span><button disabled={locked||!selectedRows.length} onClick={openBatch}>预览批量恢复影响</button></div><div className={styles.listHead}><span><input className={styles.checkbox} type="checkbox" aria-label="选择本页全部回收或归档对象" disabled={locked||!availableRows.length} checked={!!availableRows.length&&selectedRows.length===availableRows.length} onChange={event=>setChosen(event.target.checked?availableRows.map(row=>({kind:row.kind,object_id:row.object_id})):[])}/>标题与信息</span><span>类型</span><span>时间</span><span>操作人</span><span>原因</span></div><div className={styles.list}>{data.results.map(row=><div className={styles.row} key={`${row.kind}:${row.object_id}`} data-selected={selected?.kind===row.kind&&selected.object_id===row.object_id}><input className={styles.checkbox} type="checkbox" aria-label={`选择${row.title}`} disabled={locked||row.record_state==="restored"} checked={chosen.some(item=>item.kind===row.kind&&item.object_id===row.object_id)} onChange={event=>toggle({kind:row.kind,object_id:row.object_id},event.target.checked)}/><span className={styles.objectIcon}>{row.cover_url?<img src={normalizePublicResourceUrl(row.cover_url)} alt={`${row.title}封面`} loading="lazy"/>:<><BookOpen size={22}/><small>{row.label}</small></>}</span><button className={`${styles.objectTitle} ${styles.objectButton}`} aria-pressed={selected?.kind===row.kind&&selected.object_id===row.object_id} disabled={locked} onClick={()=>choose(row)}><strong>{row.title}</strong><small>{row.subtitle||row.label}</small></button><span className={styles.rowType}><span>{row.kind_label}</span><span className={styles.state} data-state={row.record_state}>{labels[row.record_state]||row.record_state}</span></span><time dateTime={row.changed_at}>{date(row.changed_at)}</time><span className={styles.actor}>{row.actor_name||"未记录"}</span><span className={styles.rowReason}>{row.reason||"未记录"}</span><ChevronRight size={14} className={styles.rowArrow}/></div>)}</div>{!data.results.length?<div className={styles.empty}><ArchiveRestore size={27}/><strong>没有符合条件的记录</strong><p>可调整名称、类型或时间范围；没有内容时不会填入示例记录。</p></div>:null}<div className={styles.pagination}><span>共 {data.count} 条</span><button aria-label="上一页" disabled={page<=1||locked} onClick={()=>{setPage(value=>value-1);setSelected(null);setChosen([]);}}><ChevronLeft size={14}/></button><span>{page} / {Math.max(1,Math.ceil(data.count/data.page_size))}</span><button aria-label="下一页" disabled={page*data.page_size>=data.count||locked} onClick={()=>{setPage(value=>value+1);setSelected(null);setChosen([]);}}><ChevronRight size={14}/></button><label className={styles.pageSize}>每页<select aria-label="每页条数" value={pageSize} disabled={locked} onChange={event=>{setPageSize(Number(event.target.value));reset();}}>{[10,20].map(size=><option key={size} value={size}>{size} 条</option>)}</select></label></div><p className={styles.hint}>{data.notice}</p></>:null}
      </section>
      {selected?mobile?<Dialog open className={styles.mobileDialog} onRequestClose={()=>{if(!locked)setSelected(null);}} aria-label="回收对象详情">{details}</Dialog>:details:<aside className={styles.emptyDetail}><ArchiveRestore size={30}/><h2>选择需要查看的对象</h2><p>在这里查看基本信息、保留的关联和恢复影响。</p></aside>}
    </div>
    {batchOpen&&batchTargets?<RecoveryBatch owner={owner} targets={batchTargets} initial={batchSaved} onPersist={value=>{sessionStorage.setItem(recoveryBatchKey(owner),JSON.stringify(value));setBatchSaved(value);}} onClose={closeBatch} onChanged={resource.reload}/>:null}
  </main>;
}

function ObjectDetail({owner,target,initialCommand,preserve,onSelect,onClose,onLock,onChanged}:{owner:string;target:Target;initialCommand:Request|null;preserve:(value:Request|null)=>void;onSelect:(value:Target)=>void;onClose:()=>void;onLock:(value:boolean)=>void;onChanged:()=>void}){
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Detail>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Detail>(`${base}${target.kind}/${target.object_id}/`,owner,undefined,load);
  const [comparison,setComparison]=useState(false),[cancelOpen,setCancelOpen]=useState(false);
  const [tab,setTab]=useState("basic"),[preview,setPreview]=useState<Detail|null>(null),[message,setMessage]=useState(""),[unknown,setUnknown]=useState<Request|null>(initialCommand),[submitting,setSubmitting]=useState(false),[checking,setChecking]=useState(false);
  const lifecycle=useRef<AbortController|null>(null),pending=useRef<Request|null>(initialCommand),busy=useRef(false);
  useEffect(()=>{const controller=new AbortController();lifecycle.current=controller;return()=>controller.abort();},[]);
  const data=resource.data;
  useUnsavedForm(Boolean(unknown),false);
  async function previewRestore(){
    if(busy.current||pending.current||!lifecycle.current||lifecycle.current.signal.aborted)return;
    const controller=lifecycle.current;
    busy.current=true;setChecking(true);onLock(true);setMessage("");
    try{
      const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
      const checked=await withPrivateOwner(owner,()=>apiRequest<Detail>(`${base}${target.kind}/${target.object_id}/?check_files=true`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),signal);
      if(controller.signal.aborted)return;
      if(checked.kind!==target.kind||checked.object_id!==target.object_id)throw Error("核对结果与当前对象不一致，请重新读取详情。");
      if(!checked.can_restore){setMessage(checked.blockers.join(" ")||"当前对象不能恢复，请重新读取详情并核对权限。");return;}
      setPreview(checked);
    }catch(reason){if(!controller.signal.aborted)setMessage(reason instanceof Error?reason.message:"关联与文件尚未核对完成，请稍后重试。");}
    finally{if(!controller.signal.aborted){busy.current=false;setChecking(false);onLock(false);}}
  }
  async function restore(rename?:Request["rename"],keepSeparate=false){
    if(busy.current||pending.current||!lifecycle.current||lifecycle.current.signal.aborted||!preview?.can_restore)return;
    const controller=lifecycle.current;
    const values:Request={request_id:createRequestKey(),object_id:preview!.object_id,kind:preview!.kind as Request["kind"],expected_version:preview!.version,confirmed:true,...(rename?{rename}:keepSeparate?{keep_separate:true}:{})};
    try{preserve(values);}catch{setMessage("浏览器不能保存原恢复请求，尚未提交。请保留本页并恢复浏览器存储后再继续。");return;}
    pending.current=values;setUnknown(values);busy.current=true;setSubmitting(true);onLock(true);setMessage("");
    try{
      const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
      const result=await withPrivateOwner(owner,()=>apiRequest<Result>(base,{method:"POST",signal,cache:"no-store",headers:{"X-Editor-Owner":owner},body:JSON.stringify(values)},getServerSessionCredential()),signal);
      if(controller.signal.aborted)return;
      if(result.request_id!==values.request_id||result.kind!==values.kind||result.object_id!==values.object_id)throw Error("恢复操作结果与原对象不一致，请保留原请求继续核对。");
      preserve(null);setMessage(result.detail);setPreview(null);pending.current=null;setUnknown(null);onLock(false);resource.reload();onChanged();
    }catch(reason){
      if(controller.signal.aborted)return;
      setPreview(null);
      setMessage(reason instanceof Error?reason.message:"恢复暂未确认，请查询原请求。");

    }finally{if(!controller.signal.aborted){busy.current=false;setSubmitting(false);}}
  }
  async function readReceipt(cancel=false){
    const values=pending.current,controller=lifecycle.current;
    if(!values||busy.current||!controller||controller.signal.aborted)return;
    busy.current=true;setSubmitting(true);setMessage("");
    try{
      const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
      const receipt=await withPrivateOwner(owner,()=>apiRequest<Receipt>(`${base}receipts/${values.request_id}/`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner},...(cancel?{method:"POST",body:JSON.stringify({action:"cancel_pending"})}:{})},getServerSessionCredential()),signal);
      if(controller.signal.aborted)return;
      if(receipt.request_id!==values.request_id||receipt.actor_id!==owner)throw Error("操作结果与当前账户或请求不一致，请保留原编号继续核对。");
      if(receipt.state==="applied"){
        const result=receipt.result;
        if(!result||result.request_id!==values.request_id||result.kind!==values.kind||result.object_id!==values.object_id||!result.restored||result.public_restored)throw Error("恢复操作结果与原对象不一致，请保留编号并核对历史。");
        preserve(null);setMessage(`${cancel?"原恢复已经完成，取消不会撤销它。":""}${result.detail}`);
      }else if(receipt.state==="cancelled"){
        preserve(null);setMessage("已阻止此编号尚未执行的恢复。迟到请求不会执行；原对象状态以最新详情为准。");
      }else throw Error("操作结果状态尚不能确认，请保留原编号。");
      pending.current=null;setUnknown(null);setPreview(null);setCancelOpen(false);onLock(false);resource.reload();onChanged();
    }catch(reason){if(!controller.signal.aborted)setMessage(reason instanceof Error?reason.message:"尚未查到可确认的操作结果，请保留原请求。");}
    finally{if(!controller.signal.aborted){busy.current=false;setSubmitting(false);}}
  }
  const disabled=submitting||checking||!!unknown;
  return <aside className={styles.detail} aria-label="对象详情" aria-busy={resource.loading||submitting||checking}>
    <button className={styles.closeDetail} onClick={onClose} disabled={disabled}><X size={16}/>关闭详情</button>
    {resource.error?<div className={styles.error} role="alert">{resource.error}<button onClick={()=>resource.reload()}>重新读取</button></div>:null}
    {resource.loading?<div className={styles.empty} role="status">正在读取对象与关联…</div>:null}
    {message?<p className={styles.message} role="status">{message}</p>:null}
    {unknown?<div className={styles.notice}><CircleAlert size={17}/><div><strong>原请求尚未确认</strong><p>查询只读取已登记结果，不再次提交恢复。查不到时，请求仍可能在途；可以取消尚未执行的原请求。</p><small>请求编号 {unknown.request_id}</small><div className={styles.relatedTools}><button disabled={submitting} onClick={()=>void readReceipt()}>{submitting?"正在处理原请求…":"查询原恢复结果"}</button><button disabled={submitting} onClick={()=>setCancelOpen(true)}>取消未执行请求</button></div></div></div>:null}
    <ConfirmDialog open={cancelOpen} title="取消尚未执行的恢复" description="服务端会先查询原结果。若恢复已完成，将返回原操作结果；若尚未执行，将阻止此编号之后到达的恢复请求。" details={["取消不会撤销已经完成的恢复，也不会删除原对象。",...(message?[message]:[])]} confirmLabel={submitting?"正在核对…":"取消未执行请求"} pending={submitting} onCancel={()=>{if(!submitting)setCancelOpen(false);}} onConfirm={()=>void readReceipt(true)}/>
    {data?<><header className={styles.objectHeader}>{data.cover_url?<img src={normalizePublicResourceUrl(data.cover_url)} alt={`${data.title}封面`}/>:<div className={styles.detailIcon}><BookOpen size={34}/><span>{data.label}</span></div>}<div><h2>{data.title}</h2><p>{[data.subtitle,data.kind_label].filter(Boolean).join(" ｜ ")}</p><span className={styles.state} data-state={data.record_state}>{labels[data.record_state]}</span><p>{date(data.changed_at)} · {data.operator}</p><p>原因：{data.reason}</p><button className={styles.primary} disabled={!data.can_restore||disabled} onClick={()=>void previewRestore()}>{checking?"正在核对关联与文件…":"预览恢复影响"}</button></div></header><div className={styles.notice}><CircleAlert size={17}/><p>{data.notice}</p></div>
      {data.names.count?<div className={styles.notice}><CircleAlert size={17}/><div><strong>另有 {data.names.count} 个同名对象</strong><p>同名可能是不同版本或身份。请先比较，恢复时保留各自内容与原身份。</p><button onClick={()=>setComparison(true)}>比较同名对象</button></div></div>:null}
      <nav className={styles.tabs} aria-label="对象详情栏目">{[["basic","基本信息"],["dependencies",`关联依赖（${data.dependency_count}）`],["history",`变更历史（${data.history_count}）`]].map(([key,label])=><button key={key} aria-current={tab===key?"page":undefined} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      {data.blockers.length?<div className={styles.blockers}><CircleAlert size={18}/><div><strong>恢复前需要处理</strong><ul>{data.blockers.map(value=><li key={value}>{value}</li>)}</ul></div></div>:null}
      {tab==="basic"?<><dl className={styles.information}>{[["对象类型",data.kind_label],["原位置",data.destination],["创建时间",date(data.created_at)],["最后修改",date(data.updated_at)],["操作时间",date(data.changed_at)],["操作人",data.operator],["操作原因",data.reason],...(data.description?[["对象说明",data.description]]:[])] .map(([label,value])=><div key={label}><dt>{label}</dt><dd>{label==="原位置"?<Link href={value}>前往原编辑入口 <ChevronRight size={12}/></Link>:value}</dd></div>)}</dl><h3>关联依赖</h3><Dependencies data={data} disabled={disabled} onSelect={onSelect}/><button onClick={()=>setTab("dependencies")}>分页查看关联对象</button><h3>最近变更</h3><Changes rows={data.history}/><button onClick={()=>setTab("history")}>查看全部变更记录（{data.history_count}）</button></>:<RelatedRecords key={`${tab}:${data.version}`} owner={owner} target={target} category={tab as RelatedCategory} disabled={disabled} onSelect={onSelect}/>}
      <Link className={styles.originalLink} href={data.destination}>查看原管理入口 <ChevronRight size={14}/></Link>
      <Dialog open={comparison} className={styles.compareDialog} aria-labelledby="recovery-comparison-title" onRequestClose={()=>setComparison(false)}>
        <header className={styles.relatedTools}><h2 id="recovery-comparison-title">同名对象比较</h2><button onClick={()=>setComparison(false)}><X size={15}/>关闭比较</button></header>
        <p className={styles.hint}>正在恢复：{data.title}。以下是当前未回收、未归档的同名管理对象。</p>
        {comparison?<RelatedRecords owner={owner} target={target} category="names" disabled={disabled} onSelect={onSelect}/>:null}
      </Dialog>
      <RecoveryRestoreDialog preview={preview} pending={submitting} message={message} onCancel={()=>{if(!unknown)setPreview(null);}} onConfirm={(rename,keepSeparate)=>void restore(rename,keepSeparate)}/>
    </>:null}
  </aside>;
}

function Dependencies({data,disabled,onSelect}:{data:Detail;disabled:boolean;onSelect:(value:Target)=>void}){
  return <><p className={styles.hint}>只列管理内容的对象关系，不展示读者笔记、私人书单或使用记录。</p>{data.dependencies.length?<div className={styles.dependencies}>{data.dependencies.map((row,index)=><div key={`${row.kind}:${row.object_id}:${index}`}><BookOpen size={16}/><div><strong>{row.name}</strong><small>{row.label} · {row.detail}</small><LinkedObjects row={row} disabled={disabled} onSelect={onSelect}/></div><span className={styles.state} data-state={row.state}>{row.blocking?"需先恢复":labels[row.state]}</span>{row.state==="deleted"?<button disabled={disabled} onClick={()=>onSelect(row)}>查看</button>:<Link href={row.destination}>查看 <ChevronRight size={12}/></Link>}</div>)}</div>:<div className={styles.empty}><p>当前未列出可展示的管理对象关联。</p></div>}{data.dependencies_limited?<p className={styles.hint}>这里是关联摘要，请切换到关联依赖栏目分页查看。</p>:null}</>;
}

function LinkedObjects({row,disabled,onSelect}:{row:Detail["dependencies"][number];disabled:boolean;onSelect:(value:Target)=>void}){
  if(!row.linked_objects?.length)return null;
  return <span className={styles.linkedObjects}>{row.linked_objects.map(item=><span key={`${item.kind}:${item.object_id}`}>{item.state==="deleted"||item.state==="archived"?<button disabled={disabled} onClick={()=>onSelect(item)}>{item.name} · {labels[item.state]}</button>:<Link href={item.destination} target="_blank" rel="noopener noreferrer">{item.name} · 查看关联 <ChevronRight size={11}/></Link>}</span>)}</span>;
}

function Changes({rows}:{rows:Detail["history"]}){
  if(!rows.length)return <div className={styles.empty}><History size={20}/><p>尚无可展示的原对象变更记录。</p></div>;
  return <div className={styles.tableScroll}><table><thead><tr><th>时间</th><th>操作</th><th>操作人</th><th>说明</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{date(row.at)}</td><td>{({"record.recycle":"删除","record.restore":"恢复","entity_archive":"归档","entity_restore":"恢复","recovery.confirmed":"恢复","recovery.renamed":"改名"} as Record<string,string>)[row.action]||"变更"}</td><td>{row.actor}</td><td>{row.detail}</td></tr>)}</tbody></table></div>;
}

type RelatedCategory="dependencies"|"history"|"names";
function RelatedRecords({owner,target,category,disabled,onSelect}:{owner:string;target:Target;category:RelatedCategory;disabled:boolean;onSelect:(value:Target)=>void}){
  const [page,setPage]=useState(1),[relation,setRelation]=useState(""),[asOf,setAsOf]=useState("");
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<RelatedPage>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const query=new URLSearchParams({category,page:String(page),relation});
  if(asOf)query.set("as_of",asOf);
  const resource=usePersistentWorkspace<RelatedPage>(`${base}${target.kind}/${target.object_id}/related/?${query}`,owner,undefined,load),data=resource.data;
  function refresh(){setPage(1);setAsOf("");resource.reload();}
  function move(next:number){if(!data)return;setAsOf(data.as_of);setRelation(data.relation);setPage(next);}
  return <section className={styles.related} aria-label={category==="history"?"完整变更记录":category==="names"?"同名对象比较":"关联对象分页"}>
    <div className={styles.relatedTools}>{category==="dependencies"&&data?.groups.length?<label>关联类型<select value={relation||data.relation} onChange={event=>{setRelation(event.target.value);setPage(1);setAsOf("");}}>{data.groups.map(group=><option key={group.id} value={group.id}>{group.label}（{group.count}）</option>)}</select></label>:null}<button onClick={refresh}><RefreshCw size={13}/>读取最新</button></div>
    {resource.error?<div className={styles.error} role="alert">{resource.error}<button onClick={refresh}>返回第一页重新读取</button></div>:null}
    {resource.loading?<LoadingState className={styles.hint} role="status">正在读取记录…</LoadingState>:null}
    {data?<><p className={styles.hint}>{data.notice}</p>{category==="history"?<Changes rows={data.history}/>:<div className={styles.dependencies}>{(category==="names"?data.names:data.dependencies).map((row,index)=><div key={`${row.kind}:${row.object_id}:${index}`}><BookOpen size={16}/><div><strong>{row.name}</strong><small>{row.label} · {row.detail}</small><LinkedObjects row={row} disabled={disabled} onSelect={onSelect}/><small>标识 {row.object_id.slice(0,8)}</small></div><span className={styles.state} data-state={row.state}>{row.blocking?"需先恢复":labels[row.state]}</span>{row.state==="deleted"||row.state==="archived"?<button disabled={disabled} onClick={()=>onSelect(row)}>查看</button>:<Link href={row.destination} target="_blank" rel="noopener noreferrer" aria-label={`新窗口查看${row.name}`}>查看 <ChevronRight size={12}/></Link>}</div>)}</div>}
    {!data.count&&category!=="history"?<div className={styles.empty}>此范围没有可展示的对象。</div>:null}
    <div className={styles.pagination}><span>共 {data.count} 条 · 每页 20 条</span><button disabled={data.page<=1} onClick={()=>move(data.page-1)}>上一页</button><span>{data.page} / {data.total_pages}</span><button disabled={data.page>=data.total_pages} onClick={()=>move(data.page+1)}>下一页</button></div>
    <p className={styles.hint}>{category==="history"?`记录创建上限 ${date(data.as_of)}；读取最新可查看之后的变更。`:"关联和同名对象按当前状态显示；其他管理员修改后，页数可能变化。恢复前会重新核对。"}</p></>:null}
  </section>;
}
