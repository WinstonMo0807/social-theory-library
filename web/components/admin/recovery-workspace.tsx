"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArchiveRestore, BookOpen, Check, ChevronRight, CircleAlert, History, RefreshCw, Search, X } from "lucide-react";
import { ApiRequestError, apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { Dialog } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./recovery-workspace.module.css";

type Directory=components["schemas"]["RecoveryDirectory"];
type Detail=components["schemas"]["RecoveryDetail"];
type Result=components["schemas"]["RecoveryResult"];
type Request=components["schemas"]["RecoveryConfirmInputRequest"];
type Target={kind:string;object_id:string};
const base="/catalog/admin/recycle/";
const requestKey=(owner:string)=>`stl-recovery-command:${owner}`;
function savedRestore(raw:string):Request{
  const value=JSON.parse(raw) as Request;
  const uuid=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
  if(!value||typeof value!=="object"||Object.keys(value).sort().join()!=="confirmed,expected_version,kind,object_id,request_id"||!uuid.test(value.request_id)||!uuid.test(value.object_id)||! /^[a-f0-9]{64}$/.test(value.expected_version)||typeof value.kind!=="string"||value.confirmed!==true)throw Error("原恢复请求记录不完整，请保留本页并核对对象变更历史。");
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
  const [period,setPeriod]=useState(""),[since,setSince]=useState(""),[page,setPage]=useState(1),[selected,setSelected]=useState<Target|null>(null),[locked,setLocked]=useState(false);
  const [operator,setOperator]=useState(""),[reason,setReason]=useState(""),[reasonQuery,setReasonQuery]=useState(""),[mobile,setMobile]=useState(false);
  useEffect(()=>{const media=window.matchMedia("(max-width:760px)"),update=()=>setMobile(media.matches);update();media.addEventListener("change",update);return()=>media.removeEventListener("change",update);},[]);
  const [original,setOriginal]=useState<Request|null>(null),[ready,setReady]=useState(false),[recoveryError,setRecoveryError]=useState("");
  useEffect(()=>{let alive=true;queueMicrotask(()=>{if(!alive)return;try{const raw=sessionStorage.getItem(requestKey(owner));if(raw){const value=savedRestore(raw);setOriginal(value);setSelected(value);setLocked(true);}setReady(true);}catch(reason){setRecoveryError(reason instanceof Error?reason.message:"不能读取原恢复请求，请保留本页。");}});return()=>{alive=false;};},[owner]);
  function preserve(value:Request|null){if(value)sessionStorage.setItem(requestKey(owner),JSON.stringify(value));else sessionStorage.removeItem(requestKey(owner));setOriginal(value);}
  const url=`${base}?page=${page}&search=${encodeURIComponent(search)}&kind=${kind}&state=${state}&operator=${encodeURIComponent(operator)}&reason=${encodeURIComponent(reasonQuery)}${since?`&since=${encodeURIComponent(since)}`:""}`;
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Directory>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Directory>(url,owner,undefined,load),data=resource.data;
  const reset=()=>{setPage(1);setSelected(null);};
  const choose=(target:Target)=>{if(ready&&!locked)setSelected(target);};
  const details=selected?<ObjectDetail key={`${selected.kind}:${selected.object_id}`} owner={owner} target={selected} initialCommand={original} preserve={preserve} onSelect={choose} onClose={()=>setSelected(null)} onLock={setLocked} onChanged={resource.reload}/>:null;
  return <main className={styles.page}>
    <div className={styles.breadcrumb}><Link href="/admin">首页</Link><ChevronRight size={12}/><Link href="/admin/processing/status">运行维护</Link><ChevronRight size={12}/><span>回收、变更历史与恢复</span></div>
    <header className={styles.title}><div><h1>回收、变更历史与恢复</h1><p>查看被删除或归档的对象，了解关联内容与变更记录，并在权限范围内恢复。</p></div><button onClick={()=>resource.reload()} disabled={locked||resource.loading}><RefreshCw size={15}/>刷新</button></header>
    {recoveryError?<p className={styles.error} role="alert">{recoveryError}</p>:null}
    <div className={styles.workspace} data-detail={!!selected}>
      <section className={styles.directory} aria-label="回收与归档对象">
        <nav className={styles.tabs} aria-label="回收记录范围">{[["","全部"],["deleted","已删除"],["archived","已归档"],["restored","其他变更"]].map(([key,label])=><button key={key} disabled={locked} aria-current={state===key?"page":undefined} onClick={()=>{setState(key);reset();}}>{label}<span>{data?(key?data.counts[key]||0:Object.values(data.counts).reduce((sum,count)=>sum+count,0)):"—"}</span></button>)}</nav>
        <form className={styles.filters} onSubmit={event=>{event.preventDefault();setSearch(input);setReasonQuery(reason);reset();}}><label className={styles.search}><Search size={15}/><input aria-label="搜索回收内容名称" placeholder="搜索标题、名称…" value={input} disabled={locked} onChange={event=>setInput(event.target.value)}/><button type="submit" disabled={locked}>查找</button></label><label className={styles.filterLabel}>对象类型<select aria-label="对象类型" value={kind} disabled={locked} onChange={event=>{setKind(event.target.value);reset();}}><option value="">全部类型</option>{data?.kinds.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label className={styles.filterLabel}>时间<select aria-label="操作时间" value={period} disabled={locked} onChange={event=>{setPeriod(event.target.value);setSince(event.target.value?new Date(Date.now()-Number(event.target.value)*86400000).toISOString():"");reset();}}><option value="">全部时间</option><option value="7">近7天</option><option value="30">近30天</option><option value="90">近90天</option></select></label><label className={styles.filterLabel}>操作人<select aria-label="操作人" value={operator} disabled={locked} onChange={event=>{setOperator(event.target.value);reset();}}><option value="">全部操作人</option>{data?.operators.map(row=><option key={row.id} value={row.id}>{row.label||"未填写姓名"}</option>)}</select></label><label className={styles.filterLabel}>操作原因<input aria-label="筛选操作原因" maxLength={200} value={reason} disabled={locked} onChange={event=>setReason(event.target.value)} placeholder="输入原因后查找"/></label></form>{data?.operators_limited?<p className={styles.hint}>操作人超过100位，请先缩小对象或时间范围。</p>:null}
        {resource.error?<div className={styles.error} role="alert">{resource.error}<button onClick={()=>resource.reload()}>重新读取</button></div>:null}
        {resource.loading?<div className={styles.empty} role="status">正在读取回收和归档记录…</div>:null}
        {data?<><div className={styles.listHead}><span>标题与信息</span><span>类型</span><span>操作时间</span><span>操作人</span><span>原因</span></div><div className={styles.list}>{data.results.map(row=><button className={styles.row} key={`${row.kind}:${row.object_id}`} aria-pressed={selected?.kind===row.kind&&selected.object_id===row.object_id} disabled={locked} onClick={()=>choose(row)}><span className={styles.marker}>{selected?.kind===row.kind&&selected.object_id===row.object_id?<Check size={12}/>:null}</span><span className={styles.objectIcon}>{row.cover_url?<img src={normalizePublicResourceUrl(row.cover_url)} alt={`${row.title}封面`} loading="lazy"/>:<><BookOpen size={22}/><small>{row.label}</small></>}</span><span className={styles.objectTitle}><strong>{row.title}</strong><small>{row.label}</small></span><span className={styles.state} data-state={row.record_state}>{labels[row.record_state]||row.record_state}</span><time dateTime={row.changed_at}>{date(row.changed_at)}</time><span className={styles.actor}>{row.actor_name||"未记录"}</span><span className={styles.rowReason}>{row.reason||"未记录"}</span><ChevronRight size={14} className={styles.rowArrow}/></button>)}</div>{!data.results.length?<div className={styles.empty}><ArchiveRestore size={27}/><strong>没有符合条件的记录</strong><p>可调整名称、类型或时间范围；没有内容时不会填入示例记录。</p></div>:null}<div className={styles.pagination}><span>共 {data.count} 条 · 每页 20 条</span><button disabled={page<=1||locked} onClick={()=>{setPage(value=>value-1);setSelected(null);}}>上一页</button><span>{page} / {Math.max(1,Math.ceil(data.count/data.page_size))}</span><button disabled={page*data.page_size>=data.count||locked} onClick={()=>{setPage(value=>value+1);setSelected(null);}}>下一页</button></div><p className={styles.hint}>{data.notice}</p></>:null}
      </section>
      {selected?mobile?<Dialog open className={styles.mobileDialog} onRequestClose={()=>{if(!locked)setSelected(null);}} aria-label="回收对象详情">{details}</Dialog>:details:<aside className={styles.emptyDetail}><ArchiveRestore size={30}/><h2>选择需要查看的对象</h2><p>在这里查看基本信息、保留的关联和恢复影响。</p></aside>}
    </div>
  </main>;
}

function ObjectDetail({owner,target,initialCommand,preserve,onSelect,onClose,onLock,onChanged}:{owner:string;target:Target;initialCommand:Request|null;preserve:(value:Request|null)=>void;onSelect:(value:Target)=>void;onClose:()=>void;onLock:(value:boolean)=>void;onChanged:()=>void}){
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Detail>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Detail>(`${base}${target.kind}/${target.object_id}/`,owner,undefined,load);
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
  async function restore(){
    if(busy.current||!lifecycle.current||lifecycle.current.signal.aborted||(!preview?.can_restore&&!pending.current))return;
    const controller=lifecycle.current;
    const values=pending.current||{request_id:createRequestKey(),object_id:preview!.object_id,kind:preview!.kind as Request["kind"],expected_version:preview!.version,confirmed:true};
    try{preserve(values);}catch{setMessage("浏览器不能保存原恢复请求，尚未提交。请保留本页并恢复浏览器存储后再继续。");return;}
    pending.current=values;setUnknown(values);busy.current=true;setSubmitting(true);onLock(true);setMessage("");
    try{
      const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
      const result=await withPrivateOwner(owner,()=>apiRequest<Result>(base,{method:"POST",signal,cache:"no-store",headers:{"X-Editor-Owner":owner},body:JSON.stringify(values)},getServerSessionCredential()),signal);
      if(controller.signal.aborted)return;
      if(result.request_id!==values.request_id||result.kind!==values.kind||result.object_id!==values.object_id)throw Error("恢复回执与原对象不一致，请保留原请求继续核对。");
      preserve(null);setMessage(result.detail);setPreview(null);pending.current=null;setUnknown(null);onLock(false);resource.reload();onChanged();
    }catch(reason){
      if(controller.signal.aborted)return;
      setPreview(null);
      setMessage(reason instanceof Error?reason.message:"恢复暂未确认，请查回原请求。");
      if(reason instanceof ApiRequestError&&!(reason instanceof PrivateOwnerVerificationError)&&[400,401,403,404,409,410,422].includes(reason.status)){try{preserve(null);pending.current=null;setUnknown(null);setPreview(null);onLock(false);}catch{setMessage("恢复被拒绝，但原请求暂不能清除，请保留本页并恢复浏览器存储。");}}
    }finally{if(!controller.signal.aborted){busy.current=false;setSubmitting(false);}}
  }
  const disabled=submitting||checking||!!unknown;
  return <aside className={styles.detail} aria-label="对象详情" aria-busy={resource.loading||submitting||checking}>
    <button className={styles.closeDetail} onClick={onClose} disabled={disabled}><X size={16}/>关闭详情</button>
    {resource.error?<div className={styles.error} role="alert">{resource.error}<button onClick={()=>resource.reload()}>重新读取</button></div>:null}
    {resource.loading?<div className={styles.empty} role="status">正在读取对象与关联…</div>:null}
    {message?<p className={styles.message} role="status">{message}</p>:null}
    {unknown&&!submitting?<div className={styles.notice}><CircleAlert size={17}/><div><strong>原请求尚未确认</strong><p>按原编号继续核对；未收到的请求会按原版本提交，已执行的请求只返回原记录。</p><button onClick={()=>void restore()}>按原编号核对并继续</button></div></div>:null}
    {data?<><header className={styles.objectHeader}>{data.cover_url?<img src={data.cover_url} alt={`${data.title}封面`}/>:<div className={styles.detailIcon}><BookOpen size={34}/><span>{data.label}</span></div>}<div><h2>{data.title}</h2><p>{data.label}</p><span className={styles.state} data-state={data.record_state}>{labels[data.record_state]}</span><p>{date(data.changed_at)} · {data.operator}</p><button className={styles.primary} disabled={!data.can_restore||disabled} onClick={()=>void previewRestore()}>{checking?"正在核对关联与文件…":"预览恢复影响"}</button></div></header><div className={styles.notice}><CircleAlert size={17}/><p>{data.notice}</p></div>
      <nav className={styles.tabs} aria-label="对象详情栏目">{[["basic","基本信息"],["dependencies",`关联依赖（${data.dependency_count}）`],["history",`变更历史（${data.history.length}）`]].map(([key,label])=><button key={key} aria-current={tab===key?"page":undefined} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      {data.blockers.length?<div className={styles.blockers}><CircleAlert size={18}/><div><strong>恢复前需要处理</strong><ul>{data.blockers.map(value=><li key={value}>{value}</li>)}</ul></div></div>:null}
      {tab==="basic"?<><dl className={styles.information}>{[["对象类型",data.label],["原位置",data.destination],["创建时间",date(data.created_at)],["最后修改",date(data.updated_at)],["操作时间",date(data.changed_at)],["操作人",data.operator],["操作原因",data.reason]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{label==="原位置"?<Link href={value}>前往原管理列表 <ChevronRight size={12}/></Link>:value}</dd></div>)}</dl><h3>关联依赖</h3><Dependencies data={data} disabled={disabled} onSelect={onSelect}/><h3>最近变更</h3><Changes rows={data.history.slice(0,4)}/></>:tab==="dependencies"?<Dependencies data={data} disabled={disabled} onSelect={onSelect}/>:<><p className={styles.hint}>显示最近30条原对象审计摘要，不含私人内容或原始操作载荷。</p><Changes rows={data.history}/></>}
      <Link className={styles.originalLink} href={data.destination}>查看原管理入口 <ChevronRight size={14}/></Link>
      <ConfirmDialog open={!!preview} title="确认恢复对象" description={preview?.notice||""} details={preview?[preview.title,`关联摘要：${preview.dependency_count} 项；其他已删除对象需单独恢复。`,...(preview.storage.state==="checked"?[`已核对 ${preview.storage.total} 份登记文件的存在与大小，不含内容完整性校验。`]:[]),...preview.blockers,...(message?[message]:[])]:[]} confirmLabel={submitting?"正在恢复…":"确认恢复（保持未发布）"} pending={submitting} onCancel={()=>{if(!unknown)setPreview(null);}} onConfirm={()=>void restore()}/>
    </>:null}
  </aside>;
}

function Dependencies({data,disabled,onSelect}:{data:Detail;disabled:boolean;onSelect:(value:Target)=>void}){
  return <><p className={styles.hint}>只列管理内容的对象关系，不展示读者笔记、私人书单或使用记录。</p>{data.dependencies.length?<div className={styles.dependencies}>{data.dependencies.map((row,index)=><div key={`${row.kind}:${row.object_id}:${index}`}><BookOpen size={16}/><div><strong>{row.name}</strong><small>{row.label} · {row.detail}</small></div><span className={styles.state} data-state={row.state}>{row.blocking?"需先恢复":labels[row.state]}</span>{row.state==="deleted"?<button disabled={disabled} onClick={()=>onSelect(row)}>查看</button>:<Link href={row.destination}>查看 <ChevronRight size={12}/></Link>}</div>)}</div>:<div className={styles.empty}><p>当前未列出可展示的管理对象关联。</p></div>}{data.dependencies_limited?<p className={styles.hint}>当前展示有界关联摘要。完整关系需回原管理入口核对。</p>:null}</>;
}

function Changes({rows}:{rows:Detail["history"]}){
  if(!rows.length)return <div className={styles.empty}><History size={20}/><p>尚无可展示的原对象变更记录。</p></div>;
  return <div className={styles.tableScroll}><table><thead><tr><th>时间</th><th>操作人</th><th>说明</th></tr></thead><tbody>{rows.map(row=><tr key={row.id}><td>{date(row.at)}</td><td>{row.actor}</td><td>{row.detail}</td></tr>)}</tbody></table></div>;
}
