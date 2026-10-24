"use client";

import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, ChevronRight, CircleAlert, Clock3, FileText, Link2, Play, RefreshCw, SlidersHorizontal, Sparkles } from "lucide-react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { withPrivateOwner } from "@/lib/api/private-owner";
import styles from "./local-services.module.css";
import type { components } from "@/lib/api/generated/schema";

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
  const [tab,setTab]=useState(initialService?"services":"overview"),[selected,setSelected]=useState(initialService),[checking,setChecking]=useState(""),[message,setMessage]=useState("");
  const lifecycle=useRef<AbortController|null>(null),busy=useRef(false),stop=useRef(false),receipts=useRef(new Map<string,string>());
  useEffect(()=>{const controller=new AbortController();lifecycle.current=controller;return()=>controller.abort();},[]);
  const data=resource.data, services=data?.groups.flatMap(group=>group.services)||[];
  const current=selected?services.find(service=>service.id===selected):services[0];
  const group=data?.groups.find(value=>value.id===current?.group);
  const select=(service:Service)=>{setSelected(service.id);setTab("services");};

  async function check(items:Service[]) {
    if(busy.current||!lifecycle.current||lifecycle.current.signal.aborted)return;
    const allowed=items.filter(service=>service.can_check);
    if(!allowed.length)return;
    const controller=lifecycle.current;
    busy.current=true;stop.current=false;setMessage("");
    try {
      await resource.mutate(`service-check:${allowed.map(row=>row.id).join(",")}`,async()=>{
        for(const service of allowed) {
          if(stop.current||controller.signal.aborted)break;
          setChecking(service.id);
          const key=`${service.id}:${service.configuration_version}`;
          const requestId=receipts.current.get(key)||createRequestKey();receipts.current.set(key,requestId);
          const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(60000)]);
          await withPrivateOwner(owner,()=>apiRequest<Observation>(path+"check/",{method:"POST",signal,cache:"no-store",headers:{"X-Editor-Owner":owner},
            body:JSON.stringify({request_id:requestId,service_id:service.id,configuration_version:service.configuration_version})},getServerSessionCredential()),signal);
          receipts.current.delete(key);
        }
        return load(path,AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]));
      });
      if(!controller.signal.aborted)setMessage(stop.current?"已停止后续检查，当前已发出的检查结果保留。":"检查记录已更新。模型与业务效果仍以正式验收为准。");
    } catch(reason) {
      if(!controller.signal.aborted)setMessage((reason instanceof Error?reason.message:"检查暂未完成。")+" 可刷新最近检查记录；重试同一服务时会先核对本次请求。");
    } finally {if(!controller.signal.aborted){busy.current=false;setChecking("");}}
  }


  return <main className={styles.page} aria-busy={resource.loading||resource.pending}>
    <div className={styles.breadcrumb}><Link href="/admin">首页</Link><ChevronRight size={12}/><Link href="/admin/processing/status">运行维护</Link><ChevronRight size={12}/><span>本地模型与服务状态</span></div>
    <header className={styles.title}><div><h1>本地模型与服务状态</h1><p>了解知识解析、嵌入、重排、生成与外部元数据服务的可用性。</p></div><div className={styles.refresh}><small>最后检查：{date(data?.last_checked_at||null)}</small><button disabled={resource.loading||resource.pending||!!checking} onClick={()=>resource.reload()}><RefreshCw size={15}/>刷新检查记录</button></div></header>
    <nav className={styles.tabs} aria-label="服务维护栏目">{tabs.map(item=><button key={item.id} aria-current={tab===item.id?"page":undefined} onClick={()=>setTab(item.id)}>{item.label}</button>)}</nav>
    {resource.error?<div className={styles.error} role="alert"><CircleAlert size={18}/><p>{resource.error}</p><button onClick={()=>resource.reload()}>重新读取</button></div>:null}
    {message?<p className={styles.message} role="status">{message}</p>:null}
    {data&&selected&&!current?<p className={styles.message} role="alert">原链接中的服务已不在当前配置中。请从服务列表重新选择，未自动改为检查其他服务。</p>:null}
    {resource.loading?<div className={styles.empty} role="status"><RefreshCw size={22}/><p>正在读取服务配置与已有检查记录</p></div>:null}
    {data?<>
      <section className={styles.metrics} aria-label="服务与任务概况">{[["services","配置服务"],["available","可使用"],["limited","受限"],["unavailable","不可用"],["waiting","等待任务"],["failed_24h","失败任务（近 24 小时）"]].map(([key,label])=><div key={key} data-tone={key==="available"?"ready":key==="limited"?"limited":key==="failed_24h"?"failed":undefined}><strong>{data.summary[key]??"—"}</strong><span>{label}</span></div>)}</section>
      {tab==="overview"?<>
        <section className={styles.services}><header className={styles.sectionHeader}><div><h2>服务状态</h2><p>按能力查看真实配置及其最近检查记录。</p></div><div className={styles.actions}><button disabled={!!checking||resource.pending||!services.some(row=>row.can_check)} onClick={()=>void check(services)}><Play size={13}/>{checking?"检查进行中":"按权限检查全部服务"}</button>{checking?<button onClick={()=>{stop.current=true;setMessage("将在当前检查完成后停止后续检查。");}}>停止后续检查</button>:null}</div></header>
          <div className={styles.serviceTable}><div className={styles.tableHead}><span>能力</span><span>服务身份</span><span>状态</span><span>最近检查</span><span>任务积压</span><span>失败（24h）</span><span>受影响功能</span><span>操作</span></div>{data.groups.map(row=>{const Icon=icons[row.id as keyof typeof icons]||FileText;return <section className={styles.serviceRow} key={row.id}>
            <div className={styles.capability}><Icon size={21}/><div><strong>{row.label}</strong><small>{row.subtitle}</small></div></div>
            <div className={styles.identities}>{row.services.slice(0,2).map(service=><button key={service.id} onClick={()=>select(service)}><span>{service.name}</span><small>{service.scope}</small></button>)}{row.services.length>2?<button onClick={()=>select(row.services[0])}>另有 {row.services.length-2} 项配置</button>:null}</div>
            <span className={styles.status} data-tone={tone(row.status)}>{row.status_label}</span>
            <div className={styles.checkTime}>{date(row.services.map(service=>service.observation?.checked_at).filter((value):value is string=>!!value).sort().at(-1)||null)}</div>
            <span className={styles.queueCount} title={row.task_notice}>{row.tasks?.waiting??"—"}</span><span className={styles.failedCount} title={row.task_notice}>{row.tasks?.failed_24h??"—"}</span>
            <p className={styles.affected}>{row.affected_features.join("、")}</p>
            <div className={styles.rowActions}><button disabled={!!checking||resource.pending||!row.services.some(service=>service.can_check)} onClick={()=>void check(row.services)}>检查</button><button aria-label={`查看${row.label}详情`} onClick={()=>select(row.services[0])}><ChevronRight size={16}/></button></div>
          </section>;})}</div>
        </section>
        <div className={styles.bottom}><ServiceHistory data={data} services={services} showAll={()=>setTab("history")} compact/>{current?<ServiceDetails service={current} compact checking={checking} pending={resource.pending} onCheck={service=>void check([service])}/>:null}</div>
      </>:tab==="history"?<ServiceHistory data={data} services={services} showAll={()=>setTab("history")}/>:tab==="services"?<div className={styles.serviceDetail}><aside aria-label="能力与服务">{data.groups.map(row=><section key={row.id}><h2>{row.label}</h2>{row.services.map(service=><button key={service.id} aria-current={current?.id===service.id?"true":undefined} onClick={()=>setSelected(service.id)}><span>{service.name}</span><span className={styles.status} data-tone={tone(service.status)}>{service.status_label}</span></button>)}</section>)}</aside><div>{current?<ServiceDetails service={current} checking={checking} pending={resource.pending} onCheck={service=>void check([service])}/>:null}{group?<p className={styles.hint}>受影响功能：{group.affected_features.join("、")}。同一能力下的配置分别记录，不会用其他服务的成功结果替代。</p>:null}</div></div>:<div className={styles.configuration}>{data.groups.map(row=><section className={styles.panel} key={row.id}><header><h2>{row.label}</h2><span>{row.services.length} 项配置</span></header>{row.services.map(service=><div className={styles.configurationRow} key={service.id}><div><strong>{service.name}</strong><p>{service.scope} · {service.status_label}</p></div>{service.can_configure?<Link href={service.config_url}>打开原配置 <ChevronRight size={14}/></Link>:<span>仅查看</span>}</div>)}</section>)}</div>}
      <aside className={styles.notice}><CircleAlert size={18}/><strong>重要说明</strong><p>{data.notice}</p><Link href="/admin/processing/health">查看运行维护 <ChevronRight size={14}/></Link></aside>
      <p className={styles.hint}>任务统计来自现有处理队列；不展示读者私人任务内容。未检查、未启用和过期记录均不计为可用。</p>
    </>:null}
  </main>;
}

function ServiceHistory({data,services,showAll,compact=false}:{data:Snapshot|null;services:Service[];showAll:()=>void;compact?:boolean}) {
    const history=(data?.history||[]).slice(0,compact?5:40);
    return <section className={styles.panel} aria-labelledby={compact?"recent-checks":"all-checks"}>
      <header><h2 id={compact?"recent-checks":"all-checks"}>最近检查记录</h2>{compact?<button onClick={showAll}>查看全部 <ChevronRight size={14}/></button>:<span>保留最近 40 条显示</span>}</header>
      {!history.length?<div className={styles.empty}><Clock3 size={22}/><p>尚未保存服务检查记录</p><span>配置存在并不表示服务已经检查。</span></div>:<div className={styles.tableScroll}><table><thead><tr><th>时间</th><th>服务</th><th>检查结果</th><th>耗时</th>{!compact?<th>说明</th>:null}</tr></thead><tbody>{history.map(item=><tr key={item.id}><td><time dateTime={item.checked_at}>{date(item.checked_at)}</time></td><td>{services.find(row=>row.id===item.service_id)?.name||item.service_id}</td><td><span className={styles.status} data-tone={tone(item.status)}>{labels[item.status]||"待核对"}</span></td><td>{item.latency_ms===null?"—":`${(item.latency_ms/1000).toFixed(1)} s`}</td>{!compact?<td>{item.detail}</td>:null}</tr>)}</tbody></table></div>}
    </section>;
  }

function ServiceDetails({service,compact=false,checking,pending,onCheck}:{service:Service;compact?:boolean;checking:string;pending:boolean;onCheck:(service:Service)=>void}) {
    const checked=service.observation;
    const identity=checked?.identity||{};
    return <section className={styles.panel}>
      <header><h2>{compact?"配置信息":service.name}</h2>{service.can_configure?<Link href={service.config_url}>调整配置 <ChevronRight size={14}/></Link>:<span>仅查看</span>}</header>
      <div className={styles.detailHeading}><span className={styles.status} data-tone={tone(service.status)}>{service.status_label}</span><small>{service.scope}</small></div>
      <dl className={styles.details}>{service.details.map(detail=><div key={detail.label}><dt>{detail.label}</dt><dd>{detail.value}</dd></div>)}</dl>
      {checked?<div className={styles.observation} data-tone={tone(service.status)}><strong>{labels[checked.status]||"检查记录"}</strong><p>{checked.detail}</p><time dateTime={checked.checked_at}>{date(checked.checked_at)}</time>{["stale","changed"].includes(service.status)?<p>这条结果对应旧时间或旧配置，不能代表当前服务状态。</p>:null}</div>:<p className={styles.hint}>尚无这项服务的检查结果。</p>}
      {Object.keys(identity).length?<details className={styles.advanced}><summary>模型身份与加载记录</summary><dl className={styles.details}>{Object.entries(identity).map(([key,value])=><div key={key}><dt>{{model:"模型",revision:"版本",artifact_id:"模型文件身份",loaded:"检查时已加载",inference_completed:"本次启动后已有推理记录"}[key]||key}</dt><dd>{typeof value==="boolean"?value?"是":"否":String(value)}</dd></div>)}</dl></details>:null}
      {!compact?<div className={styles.detailActions}><button className={styles.primary} disabled={!service.can_check||!!checking||pending} onClick={()=>onCheck(service)}><Play size={14}/>{checking===service.id?"正在检查":"检查服务"}</button><p>{service.check_notice}</p></div>:null}
    </section>;
  }
