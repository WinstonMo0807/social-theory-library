"use client";

import { LoadingState } from "@/components/ui/loading-state";

import { useCallback, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { components } from "@/lib/api/generated/schema";
import styles from "./local-services.module.css";

type Page = components["schemas"]["LocalServiceHistoryPage"];
type Service = components["schemas"]["LocalService"];
const states = {available:"检查已返回",partial:"部分能力可用",offline:"离线",model_unloaded:"模型未加载",not_configured:"未配置",disabled:"未启用",quota_exhausted:"访问受限",untested:"未检查",stale:"记录已过期",changed:"配置已变化"};
export function LocalServiceHistory({owner,services,asOf}:{owner:string;services:Service[];asOf:string}) {
  const [page,setPage]=useState(1),[service,setService]=useState(""),[status,setStatus]=useState("");
  const params=new URLSearchParams({page:String(page),as_of:asOf});if(service)params.set("service_id",service);if(status)params.set("status",status);
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Page>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Page>(`/catalog/admin/local-services/history/?${params}`,owner,undefined,load);
  return <section className={styles.panel} aria-label="完整服务检查记录"><header><h2>检查与日志</h2><span>只读记录，不发起服务检查</span></header>
    <div className={styles.historyFilters}><label>服务<select data-stl-select value={service} onChange={event=>{setService(event.target.value);setPage(1);}}><option value="">全部服务，含已移除配置</option>{services.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}</select></label><label>记录结果<select data-stl-select value={status} onChange={event=>{setStatus(event.target.value);setPage(1);}}><option value="">全部结果</option>{Object.entries(states).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label></div>
    <p className={styles.hint}>记录范围截至 {new Date(asOf).toLocaleString("zh-CN")}。可用状态仍需核对当前配置和记录有效期。</p>
    {resource.error?<div className={styles.error} role="alert"><p>{resource.error}</p><button type="button" onClick={()=>{setPage(1);resource.reload();}}>重新读取第一页</button></div>:null}
    {resource.loading?<LoadingState role="status">正在读取检查历史…</LoadingState>:null}
    {resource.data?<><div className={styles.tableScroll}><table><thead><tr><th>时间</th><th>服务</th><th>结果</th><th>耗时</th><th>说明</th></tr></thead><tbody>{resource.data.results.map(row=><tr key={row.id}><td><time dateTime={row.checked_at}>{new Date(row.checked_at).toLocaleString("zh-CN")}</time></td><td>{services.find(service=>service.id===row.service_id)?.name||row.service_id}</td><td>{states[row.status as keyof typeof states]||"待核对"}</td><td>{row.latency_ms===null?"—":`${(row.latency_ms/1000).toFixed(1)} s`}</td><td>{row.detail}</td></tr>)}</tbody></table></div>{!resource.data.count?<p className={styles.empty}>当前筛选范围没有检查记录。</p>:null}
      <nav className={styles.historyPages} aria-label="服务检查历史分页"><button type="button" disabled={page<=1||resource.loading} onClick={()=>setPage(value=>value-1)}>上一页</button><span>第 {resource.data.page}/{resource.data.total_pages} 页 · 共 {resource.data.count} 条</span><button type="button" disabled={page>=resource.data.total_pages||resource.loading} onClick={()=>setPage(value=>value+1)}>下一页</button></nav></>:null}
  </section>;
}
