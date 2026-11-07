"use client";

import { ResearchSourceRegistryPanel } from "../research-source-registry";
import { AIRuntimeEditor } from "./ai-runtime-editor";
import { OcrRuntimeEditor } from "./ocr-runtime-editor";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { LocalServiceHistory } from "./local-service-history";
import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, ChevronRight, ChevronDown, CircleAlert, Clock3, FileText, Link2, Play, RefreshCw, SlidersHorizontal, Sparkles } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import styles from "./local-services.module.css";
import type { components } from "@/lib/api/generated/schema";

type CheckCommand=components["schemas"]["LocalServiceCheckInputRequest"];
type CheckReceipt=components["schemas"]["LocalServiceReceipt"];
const pendingKey=(owner:string)=>`stl-service-check:${owner}`;
function savedCheck(raw:string):CheckCommand{
  const value=JSON.parse(raw) as CheckCommand;
  if(!value||typeof value!=="object"||Object.keys(value).sort().join()!=="configuration_version,request_id,service_id"||! /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.request_id)||! /^[a-z][a-z0-9_-]{0,95}$/.test(value.service_id)||! /^[a-f0-9]{64}$/.test(value.configuration_version))throw Error("上次检查编号记录不完整，请保留本页并核对检查历史。");
  return value;
}

type Observation = components["schemas"]["LocalServiceObservation"];
type Service = components["schemas"]["LocalService"];
type Snapshot = components["schemas"]["LocalServicesSnapshot"];
const path = "/catalog/admin/local-services/";
const tabs = [{id:"overview",label:"服务总览"},{id:"services",label:"模型与服务"},{id:"history",label:"检查与日志"},{id:"configuration",label:"配置管理"}];
const icons = { parse:FileText, embedding:Link2, rerank:SlidersHorizontal, generation:Sparkles, metadata:BookOpen };
const labels:Record<string,string> = {available:"检查已返回",partial:"部分能力可用",offline:"离线",model_unloaded:"模型未加载",not_configured:"未配置",disabled:"未启用",quota_exhausted:"访问受限",untested:"未检查",stale:"记录已过期",changed:"配置已变化"};
const date = (value:string|null) => value ? new Date(value).toLocaleString("zh-CN",{month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}) : "尚无检查记录";
const tone = (state:string) => state === "available" ? "ready" : ["offline","not_configured"].includes(state) ? "failed" : ["partial","model_unloaded","quota_exhausted"].includes(state) ? "limited" : "unknown";

export function LocalServices() {
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  const selectedService=useSearchParams().get("service")||"";
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  if(!hasAdminCapability(user,"can_view_system_status")) return <div className="admin-panel"><h1>本地模型与服务状态</h1><p>当前账户没有查看运行状态的权限。</p></div>;
  return <LocalServicesWorkspace key={`${user?.id}:${epoch}:${selectedService}`} owner={String(user?.id||"")} initialService={selectedService} />;
}

function LocalServicesWorkspace({owner,initialService=""}:{owner:string;initialService?:string}) {
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Snapshot>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Snapshot>(path,owner,undefined,load);
  const [technical,setTechnical]=useState(false),[expandedService,setExpandedService]=useState(initialService),[configurationScope,setConfigurationScope]=useState("local");
  const [tab,setTab]=useState(initialService?"services":"overview"),[selected,setSelected]=useState(initialService),[checking,setChecking]=useState(""),[message,setMessage]=useState("");
  const lifecycle=useRef<AbortController|null>(null),busy=useRef(false),stop=useRef(false);
  useEffect(()=>{const controller=new AbortController();lifecycle.current=controller;return()=>controller.abort();},[]);
  const [unknown,setUnknown]=useState<CheckCommand|null>(null),[ready,setReady]=useState(false),[recordError,setRecordError]=useState("");
  const [reconciling,setReconciling]=useState(false),[cancelOpen,setCancelOpen]=useState(false);
  const original=useRef<CheckCommand|null>(null);
  const [configurationBusy,setConfigurationBusy]=useState(false);
  const [editingService,setEditingService]=useState<Service|null>(null);
  const liveService=useRef<Service|null>(null);
  const configurationChanged=useCallback((value:boolean)=>{setConfigurationBusy(value);setEditingService(previous=>value?(previous||liveService.current):null);},[]);
  const writeLocked=!!checking||!!unknown||!ready||reconciling||configurationBusy;
  useUnsavedForm(Boolean(unknown),false);
  useEffect(()=>{let alive=true;queueMicrotask(()=>{if(!alive)return;try{const raw=sessionStorage.getItem(pendingKey(owner));if(raw){const value=savedCheck(raw);original.current=value;setUnknown(value);}setReady(true);}catch(reason){setRecordError(reason instanceof Error?reason.message:"无法读取上次检查编号。");}});return()=>{alive=false;};},[owner]);
  function preserve(value:CheckCommand|null){if(value)sessionStorage.setItem(pendingKey(owner),JSON.stringify(value));else sessionStorage.removeItem(pendingKey(owner));original.current=value;setUnknown(value);}
  async function readReceipt(cancel=false){
    const value=original.current,controller=lifecycle.current;
    if(!value||busy.current||!controller||controller.signal.aborted)return;
    busy.current=true;setReconciling(true);setMessage("");
    try{
      const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(60000)]);
      const receipt=await withPrivateOwner(owner,()=>apiRequest<CheckReceipt>(`${path}receipts/${value.request_id}/`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner},...(cancel?{method:"POST",body:JSON.stringify({action:"cancel_pending"})}:{})},getServerSessionCredential()),signal);
      if(controller.signal.aborted)return;
      if(receipt.request_id!==value.request_id||receipt.actor_id!==owner)throw Error("操作结果与当前账户或原编号不一致，请保留记录。");
      if(receipt.state==="applied"){
        const result=receipt.observation;
        if(!result||result.id!==value.request_id||result.service_id!==value.service_id||result.configuration_version!==value.configuration_version)throw Error("原检查操作结果与已确认配置不一致，请保留编号并核对历史。");
        setMessage(`${cancel?"原检查已完成，取消不会撤销它。":"已查询原检查结果。"}${result.detail} 此结果对应原配置与检查时间。`);
      }else if(receipt.state==="cancelled")setMessage("此编号尚未执行的检查已取消，迟到请求不会调用服务。");
      else throw Error("原检查状态不能确认，请保留编号。");
      preserve(null);setCancelOpen(false);resource.reload();
    }catch(reason){if(!controller.signal.aborted)setMessage(reason instanceof Error?reason.message:"原检查尚未确认，请保留编号。");}
    finally{if(!controller.signal.aborted){busy.current=false;setReconciling(false);}}
  }
  const data=resource.data, services=data?.groups.flatMap(group=>group.services)||[];
  const liveCurrent=selected?services.find(service=>service.id===selected):services[0];
  const current=configurationBusy&&editingService?editingService:liveCurrent;
  const group=data?.groups.find(value=>value.id===current?.group);
  const select=(service?:Service)=>{if(service&&!configurationBusy){setSelected(service.id);setExpandedService(service.id);setTechnical(false);setTab("services");}};
  const compactServices=services.filter(service=>configurationScope==="external"?service.group==="metadata"||service.id==="remote-ocr":["ocr","discovery-embedding","discovery-reranker"].includes(service.id));
  const compactCurrent=configurationBusy&&editingService?editingService:compactServices.find(service=>service.id===selected)||compactServices[0];
  useEffect(()=>{liveService.current=(tab==="overview"?compactCurrent:liveCurrent)||null;},[tab,compactCurrent,liveCurrent]);

  async function check(items:Service[]) {
    if(busy.current||writeLocked||original.current||!lifecycle.current||lifecycle.current.signal.aborted)return;
    const allowed=items.filter(service=>service.can_check);
    if(!allowed.length)return;
    const controller=lifecycle.current;
    busy.current=true;stop.current=false;setMessage("");
    try {
      await resource.mutate(`service-check:${allowed.map(row=>row.id).join(",")}`,async()=>{
        for(const service of allowed) {
          if(stop.current||controller.signal.aborted)break;
          setChecking(service.id);
          const command:CheckCommand={request_id:createRequestKey(),service_id:service.id,configuration_version:service.configuration_version};
          preserve(command);
          const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(60000)]);
          const result=await withPrivateOwner(owner,()=>apiRequest<Observation>(path+"check/",{method:"POST",signal,cache:"no-store",headers:{"X-Editor-Owner":owner},
            body:JSON.stringify(command)},getServerSessionCredential()),signal);
          if(controller.signal.aborted)throw new DOMException("Session changed","AbortError");
          if(result.id!==command.request_id||result.service_id!==command.service_id||result.configuration_version!==command.configuration_version)throw Error("检查操作结果与原编号或配置不一致，请查询原结果。");
          preserve(null);
        }
        return load(path,AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]));
      });
      if(!controller.signal.aborted)setMessage(stop.current?"已停止后续检查，当前已发出的检查结果保留。":"检查记录已更新。模型与业务效果仍以正式验收为准。");
    } catch(reason) {
      if(!controller.signal.aborted)setMessage((reason instanceof Error?reason.message:"检查暂未完成。")+" 如有未确认编号，请先查询或取消；不会自动再次调用服务。");
    } finally {if(!controller.signal.aborted){busy.current=false;setChecking("");}}
  }


  return <main className={styles.page} aria-busy={resource.loading||resource.pending}>
    <div className={styles.breadcrumb}><Link href="/admin">首页</Link><ChevronRight size={12}/><Link href="/admin/processing/status">运行维护</Link><ChevronRight size={12}/><span>本地模型与服务状态</span></div>
    <header className={styles.title}><div><h1>本地模型与服务状态</h1></div><div className={styles.refresh}><small>最后检查：{date(data?.last_checked_at||null)}</small><button className={styles.recheck} disabled={writeLocked||resource.loading||resource.pending||!services.some(row=>row.can_check)} onClick={()=>void check(services)}><RefreshCw size={15}/>{checking?"检查进行中":"全部重新检查"}</button><button className={styles.refreshRecords} disabled={resource.loading||resource.pending||!!checking} onClick={()=>resource.reload()}>刷新记录</button></div></header>
    <nav className={styles.tabs} aria-label="服务维护栏目">{tabs.map(item=><button key={item.id} disabled={configurationBusy} aria-current={tab===item.id?"page":undefined} onClick={()=>{setTab(item.id);setTechnical(false);}}>{item.label}</button>)}</nav>
    {resource.error?<div className={styles.error} role="alert"><CircleAlert size={18}/><p>{resource.error}</p><button onClick={()=>resource.reload()}>重新读取</button></div>:null}
    {message?<p className={styles.message} role="status">{message}</p>:null}
    {recordError?<p className={styles.error} role="alert">{recordError}</p>:null}
    {unknown?<aside className={styles.notice}><CircleAlert size={18}/><div><strong>上次服务检查尚未确认</strong><p>服务标识 {unknown.service_id} · 请求编号 {unknown.request_id}</p><p>上次检查可能仍在运行。请先查看结果，或取消尚未开始的检查。</p><div className={styles.actions}><button disabled={!!checking||reconciling} onClick={()=>void readReceipt()}>查询原结果</button><button disabled={!!checking||reconciling} onClick={()=>setCancelOpen(true)}>取消未执行请求</button></div></div></aside>:null}
    <ConfirmDialog open={cancelOpen} title="取消尚未执行的服务检查" description="服务端会先查询原编号。已完成的检查保留原结果；尚未执行的检查将登记取消，迟到请求不会调用服务。" details={message?[message]:[]} confirmLabel={reconciling?"正在核对…":"取消未执行检查"} pending={reconciling} onCancel={()=>{if(!reconciling)setCancelOpen(false);}} onConfirm={()=>void readReceipt(true)}/>

    {data&&selected&&!current?<p className={styles.message} role="alert">原链接中的服务已不在当前配置中。请从服务列表重新选择，未自动改为检查其他服务。</p>:null}
    {resource.loading?<div className={styles.empty} role="status"><RefreshCw size={22}/><p>正在读取服务配置与已有检查记录</p></div>:null}
    {data?<>
      <section className={styles.metrics} aria-label="服务与任务概况">{[["services","配置服务"],["available","可使用"],["limited","受限"],["unavailable","不可用"],["waiting","等待任务"],["failed_24h","失败任务（近 24 小时）"]].map(([key,label])=><div key={key} data-tone={key==="available"?"ready":key==="limited"?"limited":key==="failed_24h"?"failed":undefined}><strong>{data.summary[key]??"—"}</strong><span>{label}</span></div>)}</section>
      {tab==="services"?<nav className={styles.detailTabs} aria-label="能力详情栏目"><button disabled={configurationBusy} aria-current={!technical?"page":undefined} onClick={()=>setTechnical(false)}>服务总览</button><button disabled={configurationBusy} aria-current={technical?"page":undefined} onClick={()=>setTechnical(true)}>技术配置</button><button disabled={configurationBusy} onClick={()=>setTab("history")}>检查与日志</button></nav>:null}
      {tab==="overview"||tab==="services"&&!technical?<>
        <section className={styles.services}><header className={styles.sectionHeader}><div><h2>服务状态</h2></div><div className={styles.actions}><button disabled={writeLocked||resource.pending||!services.some(row=>row.can_check)} onClick={()=>void check(services)}><Play size={13}/>{checking?"检查进行中":"检查全部服务"}</button>{checking?<button onClick={()=>{stop.current=true;setMessage("将在当前检查完成后停止后续检查。");}}>停止后续检查</button>:null}</div></header>
          <div className={styles.serviceTable}><div className={styles.tableHead}><span>能力</span><span>服务</span><span>状态</span><span>实际连接检查</span><span>任务积压</span><span>失败（24h）</span><span>受影响功能</span><span>操作</span></div>{data.groups.map(row=>{const Icon=icons[row.id as keyof typeof icons]||FileText;return <section className={styles.serviceRow} key={row.id}>
            <div className={styles.capability}><Icon size={21}/><div><strong>{row.label}</strong><small>{row.subtitle}</small></div></div>
            <div className={styles.identities}>{!row.services.length?<span>尚未配置此能力的服务</span>:null}{row.services.slice(0,2).map(service=><button key={service.id} disabled={configurationBusy} onClick={()=>select(service)}><span>{service.name}</span><small>{typeof service.observation?.identity?.revision==="string"?`${service.observation.identity.revision} · `:""}{service.scope}</small></button>)}{row.services.length>2?<button onClick={()=>select(row.services[0])}>另有 {row.services.length-2} 项配置</button>:null}</div>
            <span className={styles.status} data-tone={tone(row.status)}>{row.status_label}</span>
            <div className={styles.checkTime}>{date(row.services.map(service=>service.observation?.checked_at).filter((value):value is string=>!!value).sort().at(-1)||null)}<small>{row.services.find(service=>service.observation)?.observation?.detail||"尚未检查"}</small></div>
            <span className={styles.queueCount} title={row.task_notice}>{row.tasks?.waiting??"—"}</span><span className={styles.failedCount} title={row.task_notice}>{row.tasks?.failed_24h??"—"}</span>
            <p className={styles.affected}>{row.affected_features.join("、")}</p>
            <div className={styles.rowActions}><button disabled={writeLocked||resource.pending||!row.services.some(service=>service.can_check)} onClick={()=>void check(row.services)}>检查</button><button disabled={configurationBusy||!row.services.length} aria-label={`查看${row.label}详情`} onClick={()=>select(row.services[0])}><ChevronRight size={16}/></button></div>
          </section>;})}</div>
        </section>
        {tab==="overview"?<div className={styles.bottom}><ServiceHistory data={data} services={services} showAll={()=>{if(!configurationBusy)setTab("history");}} compact/><section className={styles.configurationCard}><nav className={styles.configurationTabs} aria-label="配置信息范围"><button disabled={configurationBusy} aria-current={configurationScope==="local"?"page":undefined} onClick={()=>setConfigurationScope("local")}>本地模型</button><button disabled={configurationBusy} aria-current={configurationScope==="external"?"page":undefined} onClick={()=>setConfigurationScope("external")}>外部服务</button><button disabled={configurationBusy} onClick={()=>setTab("configuration")}>系统参数</button></nav>{compactCurrent?<><label className={styles.configurationSelect}><span className="sr-only">查看服务配置</span><select aria-label="查看服务配置" value={compactCurrent.id} disabled={configurationBusy} onChange={event=>setSelected(event.target.value)}>{compactServices.map(service=><option key={service.id} value={service.id}>{service.name}</option>)}</select></label><ServiceDetails onBusyChange={configurationChanged} onSaved={resource.reload} service={compactCurrent} compact checking={checking} pending={resource.pending||writeLocked} onCheck={service=>void check([service])}/></>:<p className={styles.empty}>当前范围没有配置服务。</p>}</section></div>:<div className={`${styles.bottom} ${styles.expandedBottom}`}><section className={styles.serviceConfiguration}><header><h2>服务配置与技术详情</h2><button disabled={configurationBusy} onClick={()=>setExpandedService("")}>收起全部 <ChevronRight size={14}/></button></header>{services.map(service=>{const Icon=icons[service.group as keyof typeof icons]||FileText;return <details key={service.id} open={expandedService===service.id} className={styles.serviceAccordion}><summary onClick={event=>{event.preventDefault();if(!configurationBusy){setSelected(service.id);setExpandedService(value=>value===service.id?"":service.id);}}}><Icon size={16}/><strong>{data.groups.find(row=>row.id===service.group)?.label}</strong><span>{service.name}</span><span className={styles.status} data-tone={tone(service.status)}>{service.status_label}</span><ChevronDown size={14}/></summary>{expandedService===service.id?<ServiceDetails onBusyChange={configurationChanged} onSaved={resource.reload} service={service} checking={checking} pending={resource.pending||writeLocked} onCheck={row=>void check([row])}/>:null}</details>;})}</section><ServiceHistory data={data} services={services} showAll={()=>{if(!configurationBusy)setTab("history");}} compact/></div>}
      </>:tab==="history"?<LocalServiceHistory key={data.generated_at} owner={owner} services={services} asOf={data.generated_at}/>:tab==="services"?<div className={styles.serviceDetail}><aside aria-label="能力与服务">{data.groups.map(row=><section key={row.id}><h2>{row.label}</h2>{row.services.map(service=><button key={service.id} disabled={configurationBusy} aria-current={current?.id===service.id?"true":undefined} onClick={()=>setSelected(service.id)}><span>{service.name}</span><span className={styles.status} data-tone={tone(service.status)}>{service.status_label}</span></button>)}</section>)}</aside><div>{current?<ServiceDetails onBusyChange={configurationChanged} onSaved={resource.reload} service={current} checking={checking} pending={resource.pending||writeLocked} onCheck={service=>void check([service])}/>:null}{group?<p className={styles.hint}>受影响功能：{group.affected_features.join("、")}。同一能力下的配置分别记录，不会用其他服务的成功结果替代。</p>:null}</div></div>:<div className={styles.configuration}>{data.groups.map(row=><section className={styles.panel} key={row.id}><header><h2>{row.label}</h2><span>{row.services.length} 项配置</span></header>{row.services.map(service=><div className={styles.configurationRow} key={service.id}><div><strong>{service.name}</strong><p>{service.scope} · {service.status_label}</p></div>{service.can_configure?(["ocr","remote-ocr","generation-empty"].includes(service.id)||service.id.startsWith("metadata-")||service.id.startsWith("profile-"))?<button type="button" disabled={configurationBusy} onClick={()=>select(service)}>打开配置 <ChevronRight size={14}/></button>:service.config_url?<Link href={service.config_url}>打开原配置 <ChevronRight size={14}/></Link>:<span>随部署维护</span>:<span>仅查看</span>}</div>)}</section>)}</div>}
      <aside className={styles.notice}><CircleAlert size={18}/><strong>重要说明</strong><p>{data.notice}</p><Link href="/admin/processing/health">查看运行维护 <ChevronRight size={14}/></Link></aside>
      <p className={styles.hint}>任务统计来自现有处理队列；不展示读者私人任务内容。未检查、未启用和过期记录均不计为可用。</p>
    </>:null}
  </main>;
}

function ServiceHistory({data,services,showAll,compact=false}:{data:Snapshot|null;services:Service[];showAll:()=>void;compact?:boolean}) {
    const history=(data?.history||[]).slice(0,compact?5:40);
    return <section className={styles.panel} aria-labelledby={compact?"recent-checks":"all-checks"}>
      <header><h2 id={compact?"recent-checks":"all-checks"}>最近检查记录</h2>{compact?<button onClick={showAll}>查看全部 <ChevronRight size={14}/></button>:<span>最近保存的检查记录</span>}</header>
      {!history.length?<div className={styles.empty}><Clock3 size={22}/><p>尚未保存服务检查记录</p><span>配置存在并不表示服务已经检查。</span></div>:<div className={styles.tableScroll}><table><thead><tr><th>时间</th><th>服务</th><th>检查结果</th><th>耗时</th><th>说明</th></tr></thead><tbody>{history.map(item=><tr key={item.id}><td><time dateTime={item.checked_at}>{date(item.checked_at)}</time></td><td>{services.find(row=>row.id===item.service_id)?.name||item.service_id}</td><td><span className={styles.status} data-tone={tone(item.status)}>{labels[item.status]||"待核对"}</span></td><td>{item.latency_ms===null?"—":`${(item.latency_ms/1000).toFixed(1)} s`}</td><td>{item.detail}</td></tr>)}</tbody></table></div>}
    </section>;
  }

function ServiceDetails({service,compact=false,checking,pending,onCheck,onSaved,onBusyChange}:{service:Service;compact?:boolean;checking:string;pending:boolean;onCheck:(service:Service)=>void;onSaved:()=>void;onBusyChange:(value:boolean)=>void}) {
    const [editing,setEditing]=useState(false);
    const checked=service.observation;
    const identity=checked?.identity||{};
    return <section className={styles.panel}>
      <header><h2>{compact?"配置信息":service.name}</h2>{service.can_configure?(["ocr","remote-ocr","generation-empty"].includes(service.id)||service.id.startsWith("metadata-")||service.id.startsWith("profile-"))?<button type="button" disabled={pending||!!checking||editing} onClick={()=>setEditing(true)}>{editing?"配置已展开":"调整配置"}</button>:service.config_url?<Link href={service.config_url}>调整配置 <ChevronRight size={14}/></Link>:<span>随部署维护</span>:<span>仅查看</span>}</header>
      <div className={styles.detailHeading}>{compact?<strong>{service.name}</strong>:null}<span className={styles.status} data-tone={tone(service.status)}>{service.status_label}</span><small>{service.scope}</small></div>
      <dl className={styles.details}>{service.details.map(detail=><div key={detail.label}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}</dl>
      {checked?<div className={styles.observation} data-tone={tone(service.status)}><strong>{labels[checked.status]||"检查记录"}</strong><p>{checked.detail}</p><time dateTime={checked.checked_at}>{date(checked.checked_at)}</time>{["stale","changed"].includes(service.status)?<p>这条结果对应旧时间或旧配置，不能代表当前服务状态。</p>:null}</div>:<p className={styles.hint}>尚无这项服务的检查结果。</p>}
      {Object.keys(identity).length?<details className={styles.advanced}><summary>模型版本、设备与加载记录</summary><dl className={styles.details}>{Object.entries(identity).map(([key,value])=><div key={key}><dt>{{model:"模型",revision:"版本",artifact_id:"模型文件编号",loaded:"检查时仍驻留内存",inference_completed:"本次启动后已有推理记录",backend:"推理后端",runtime_version:"运行库版本",device:"服务报告的执行设备",threads:"推理线程数",batch_size:"批处理上限"}[key]||key}</dt><dd>{typeof value==="boolean"?value?"是":"否":String(value)}</dd></div>)}</dl><p className={styles.hint}>仅显示最近检查实际返回的字段。设备标签不是实时占用率；服务未返回内存、显存或配额时不估算。模型曾运行过，也可能已让出内存给其他能力。</p></details>:null}
      {editing&&service.can_configure&&["ocr","remote-ocr"].includes(service.id)?<OcrRuntimeEditor onSaved={onSaved} onBusyChange={onBusyChange}/>:null}
      {editing&&service.can_configure&&service.id.startsWith("metadata-")?<ResearchSourceRegistryPanel sourceKey={service.id.slice(9)} onSaved={onSaved} onBusyChange={onBusyChange}/>:null}
      {editing&&service.can_configure&&(service.id.startsWith("profile-")||service.id==="generation-empty")?<AIRuntimeEditor profileKey={service.id.startsWith("profile-")?service.id.slice(8):undefined} onSaved={onSaved} onBusyChange={onBusyChange}/>:null}
      {!compact?<div className={styles.detailActions}><button className={styles.primary} disabled={!service.can_check||!!checking||pending} onClick={()=>onCheck(service)}><Play size={14}/>{checking===service.id?"正在检查":"检查服务"}</button><p>{service.check_notice}</p></div>:null}
    </section>;
  }
