"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArchiveRestore, BookOpen, Check, ChevronRight, CircleAlert, History, RefreshCw, Search, X } from "lucide-react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { ConfirmDialog } from "@/components/confirm-dialog";
import type { components } from "@/lib/api/generated/schema";
import styles from "./recovery-workspace.module.css";

type Directory=components["schemas"]["RecoveryDirectory"];
type Detail=components["schemas"]["RecoveryDetail"];
type Result=components["schemas"]["RecoveryResult"];
type Request=components["schemas"]["RecoveryConfirmInputRequest"];
type Target={kind:string;object_id:string};
const base="/catalog/admin/recycle/";
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
  const url=`${base}?page=${page}&search=${encodeURIComponent(search)}&kind=${kind}&state=${state}${since?`&since=${encodeURIComponent(since)}`:""}`;
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Directory>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Directory>(url,owner,undefined,load),data=resource.data;
  const reset=()=>{setPage(1);setSelected(null);};
  const choose=(target:Target)=>{if(!locked)setSelected(target);};
  return <main className={styles.page}>
    <div className={styles.breadcrumb}><Link href="/admin">首页</Link><ChevronRight size={12}/><Link href="/admin/processing/status">运行维护</Link><ChevronRight size={12}/><span>回收、变更历史与恢复</span></div>
    <header className={styles.title}><div><h1>回收、变更历史与恢复</h1><p>查看被删除或归档的对象，了解关联内容与变更记录，并在权限范围内恢复。</p></div><button onClick={()=>resource.reload()} disabled={locked||resource.loading}><RefreshCw size={15}/>刷新</button></header>
    <div className={styles.workspace} data-detail={!!selected}>
      <section className={styles.directory} aria-label="回收与归档对象">
        <nav className={styles.tabs} aria-label="回收记录范围">{[["","全部"],["deleted","已删除"],["archived","已归档"],["restored","其他变更"]].map(([key,label])=><button key={key} disabled={locked} aria-current={state===key?"page":undefined} onClick={()=>{setState(key);reset();}}>{label}<span>{data?(key?data.counts[key]||0:Object.values(data.counts).reduce((sum,count)=>sum+count,0)):"—"}</span></button>)}</nav>
        <form className={styles.filters} onSubmit={event=>{event.preventDefault();setSearch(input);reset();}}><label className={styles.search}><Search size={15}/><input aria-label="搜索回收内容名称" placeholder="搜索标题、名称…" value={input} disabled={locked} onChange={event=>setInput(event.target.value)}/><button type="submit" disabled={locked}>查找</button></label><label className={styles.filterLabel}>对象类型<select aria-label="对象类型" value={kind} disabled={locked} onChange={event=>{setKind(event.target.value);reset();}}><option value="">全部类型</option>{data?.kinds.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label><label className={styles.filterLabel}>时间<select aria-label="操作时间" value={period} disabled={locked} onChange={event=>{setPeriod(event.target.value);setSince(event.target.value?new Date(Date.now()-Number(event.target.value)*86400000).toISOString():"");reset();}}><option value="">全部时间</option><option value="7">近7天</option><option value="30">近30天</option><option value="90">近90天</option></select></label></form>
        {resource.error?<div className={styles.error} role="alert">{resource.error}<button onClick={()=>resource.reload()}>重新读取</button></div>:null}
        {resource.loading?<div className={styles.empty} role="status">正在读取回收和归档记录…</div>:null}
        {data?<><div className={styles.listHead}><span>标题与信息</span><span>类型</span><span>操作时间</span><span>操作人</span></div><div className={styles.list}>{data.results.map(row=><button className={styles.row} key={`${row.kind}:${row.object_id}`} aria-pressed={selected?.kind===row.kind&&selected.object_id===row.object_id} disabled={locked} onClick={()=>choose(row)}><span className={styles.marker}>{selected?.kind===row.kind&&selected.object_id===row.object_id?<Check size={12}/>:null}</span><span className={styles.objectIcon}><BookOpen size={22}/><small>{row.label}</small></span><span className={styles.objectTitle}><strong>{row.title}</strong><small>{row.label}</small></span><span className={styles.state} data-state={row.record_state}>{labels[row.record_state]||row.record_state}</span><time dateTime={row.changed_at}>{date(row.changed_at)}</time><span className={styles.actor}>{row.actor_name||"未记录"}</span><ChevronRight size={14} className={styles.rowArrow}/></button>)}</div>{!data.results.length?<div className={styles.empty}><ArchiveRestore size={27}/><strong>没有符合条件的记录</strong><p>可调整名称、类型或时间范围；没有内容时不会填入示例记录。</p></div>:null}<div className={styles.pagination}><span>共 {data.count} 条 · 每页 20 条</span><button disabled={page<=1||locked} onClick={()=>{setPage(value=>value-1);setSelected(null);}}>上一页</button><span>{page} / {Math.max(1,Math.ceil(data.count/data.page_size))}</span><button disabled={page*data.page_size>=data.count||locked} onClick={()=>{setPage(value=>value+1);setSelected(null);}}>下一页</button></div><p className={styles.hint}>{data.notice}</p></>:null}
      </section>
      {selected?<ObjectDetail key={`${selected.kind}:${selected.object_id}`} owner={owner} target={selected} onSelect={choose} onClose={()=>setSelected(null)} onLock={setLocked} onChanged={resource.reload}/>:<aside className={styles.emptyDetail}><ArchiveRestore size={30}/><h2>选择需要查看的对象</h2><p>在这里查看基本信息、保留的关联和恢复影响。</p></aside>}
    </div>
  </main>;
}

function ObjectDetail({owner,target,onSelect,onClose,onLock,onChanged}:{owner:string;target:Target;onSelect:(value:Target)=>void;onClose:()=>void;onLock:(value:boolean)=>void;onChanged:()=>void}){
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Detail>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Detail>(`${base}${target.kind}/${target.object_id}/`,owner,undefined,load);
  const [tab,setTab]=useState("basic"),[preview,setPreview]=useState<Detail|null>(null),[message,setMessage]=useState(""),[unknown,setUnknown]=useState<Request|null>(null);
  const lifecycle=useRef<AbortController|null>(null),pending=useRef<Request|null>(null),busy=useRef(false);
  useEffect(()=>{const controller=new AbortController();lifecycle.current=controller;return()=>controller.abort();},[]);
  const data=resource.data;
  async function restore(){
    if(busy.current||!lifecycle.current||(!preview&&!pending.current))return;
    const controller=lifecycle.current;
    const values=pending.current||{request_id:createRequestKey(),object_id:preview!.object_id,kind:preview!.kind as Request["kind"],expected_version:preview!.version,confirmed:true};
    pending.current=values;setUnknown(values);busy.current=true;onLock(true);setMessage("");
    try{
      let result:Result|undefined;
      const saved=await resource.mutate(JSON.stringify(values),async(snapshot)=>{
        const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
        result=await withPrivateOwner(owner,()=>apiRequest<Result>(base,{method:"POST",signal,cache:"no-store",headers:{"X-Editor-Owner":owner},body:JSON.stringify(values)},getServerSessionCredential()),signal);
        return snapshot;
      });
      if(controller.signal.aborted||!saved||!result)return;
      setMessage(result.detail);setPreview(null);pending.current=null;setUnknown(null);onLock(false);onChanged();
    }catch(reason){
      if(controller.signal.aborted)return;
      setPreview(null);
      setMessage(reason instanceof Error?reason.message:"恢复暂未确认，请查回原请求。");
      if(reason instanceof ApiRequestError&&reason.status>=400&&reason.status<500){pending.current=null;setUnknown(null);setPreview(null);onLock(false);}
    }finally{if(!controller.signal.aborted)busy.current=false;}
  }
  const disabled=resource.pending||!!unknown;
  return <aside className={styles.detail} aria-label="对象详情" aria-busy={resource.loading||resource.pending}>
    <button className={styles.closeDetail} onClick={onClose} disabled={disabled}><X size={16}/>关闭详情</button>
    {resource.error?<div className={styles.error} role="alert">{resource.error}<button onClick={()=>resource.reload()}>重新读取</button></div>:null}
    {resource.loading?<div className={styles.empty} role="status">正在读取对象与关联…</div>:null}
    {message?<p className={styles.message} role="status">{message}</p>:null}
    {unknown&&!resource.pending?<div className={styles.notice}><CircleAlert size={17}/><div><strong>原请求尚未确认</strong><p>保留同一编号查回，不会再次恢复后来重新删除的对象。</p><button onClick={()=>void restore()}>查回原请求</button></div></div>:null}
    {data?<><header className={styles.objectHeader}>{data.cover_url?<img src={data.cover_url} alt={`${data.title}封面`}/>:<div className={styles.detailIcon}><BookOpen size={34}/><span>{data.label}</span></div>}<div><h2>{data.title}</h2><p>{data.label}</p><span className={styles.state} data-state={data.record_state}>{labels[data.record_state]}</span><p>{date(data.changed_at)} · {data.operator}</p><button className={styles.primary} disabled={!data.can_restore||disabled} onClick={()=>setPreview(data)}>预览恢复影响</button></div></header><div className={styles.notice}><CircleAlert size={17}/><p>{data.notice}</p></div>
      <nav className={styles.tabs} aria-label="对象详情栏目">{[["basic","基本信息"],["dependencies",`关联依赖（${data.dependency_count}）`],["history",`变更历史（${data.history.length}）`]].map(([key,label])=><button key={key} aria-current={tab===key?"page":undefined} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      {data.blockers.length?<div className={styles.blockers}><CircleAlert size={18}/><div><strong>恢复前需要处理</strong><ul>{data.blockers.map(value=><li key={value}>{value}</li>)}</ul></div></div>:null}
      {tab==="basic"?<><dl className={styles.information}>{[["对象类型",data.label],["原位置",data.destination],["创建时间",date(data.created_at)],["最后修改",date(data.updated_at)],["操作时间",date(data.changed_at)],["操作人",data.operator],["操作原因",data.reason]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{label==="原位置"?<Link href={value}>前往原管理列表 <ChevronRight size={12}/></Link>:value}</dd></div>)}</dl><h3>关联依赖</h3><Dependencies data={data} disabled={disabled} onSelect={onSelect}/><h3>最近变更</h3><Changes rows={data.history.slice(0,4)}/></>:tab==="dependencies"?<Dependencies data={data} disabled={disabled} onSelect={onSelect}/>:<><p className={styles.hint}>显示最近30条原对象审计摘要，不含私人内容或原始操作载荷。</p><Changes rows={data.history}/></>}
      <Link className={styles.originalLink} href={data.destination}>查看原管理入口 <ChevronRight size={14}/></Link>
      <ConfirmDialog open={!!preview} title="确认恢复对象" description={preview?.notice||""} details={preview?[preview.title,`关联摘要：${preview.dependency_count} 项；其他已删除对象需单独恢复。`,...preview.blockers,...(message?[message]:[])]:[]} confirmLabel={resource.pending?"正在恢复…":"确认恢复（保持未发布）"} pending={resource.pending} onCancel={()=>{if(!unknown)setPreview(null);}} onConfirm={()=>void restore()}/>
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
