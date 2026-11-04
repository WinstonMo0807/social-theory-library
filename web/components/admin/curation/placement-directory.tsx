"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { useAdminSession, hasAdminCapability } from "@/lib/admin-session";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { PlacementPage } from "@/lib/api/curation-workspace.client";
import { usePlacementSelection } from "./placement-selection-session";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import styles from "./placement-workspace.module.css";

export const placementPageLabels: Record<Exclude<PlacementPage,"site">,string> = {issue:"特别策划",scholar:"学者",node:"理论与概念",topic:"主题",discipline:"学科",subdiscipline:"子学科",reading_path:"阅读路径",timeline_event:"时间线事件"};
export type PlacementDestination = {id:string;type:PlacementPage;title:string;status:string;edit_url:string};
type Directory = {count:number;next:string|null;previous:string|null;results:PlacementDestination[]};
export function PlacementDirectory() {
  const selection=usePlacementSelection();
  useUnsavedForm(selection.value.selected.length>0,false);
  const user = useAdminSession();
  return user ? <DirectoryBody key={user.id} owner={String(user.id)} metadata={hasAdminCapability(user,"can_edit_metadata")} authority={hasAdminCapability(user,"can_edit_draft_authority")}/> : <p>正在核对编辑账户…</p>;
}
export function PlacementTargetDirectory({onSelect}:{onSelect:(row:PlacementDestination)=>void}) {
  const user=useAdminSession();
  return user?<DirectoryBody owner={String(user.id)} metadata={hasAdminCapability(user,"can_edit_metadata")} authority={hasAdminCapability(user,"can_edit_draft_authority")} onSelect={onSelect}/>:<p>正在核对可编辑页面…</p>;
}
function DirectoryBody({owner,metadata,authority,onSelect}:{owner:string;metadata:boolean;authority:boolean;onSelect?:(row:PlacementDestination)=>void}) {
  const [kind,setKind] = useState<Exclude<PlacementPage,"site">>(metadata?"issue":"node"),[q,setQ]=useState(""),[search,setSearch]=useState(""),[page,setPage]=useState(1);
  const load = useCallback((url:string,signal:AbortSignal)=>apiRequest<Directory>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource = usePersistentWorkspace<Directory>(`/catalog/admin/content-placements/pages/?${new URLSearchParams({type:kind,q:search,page:String(page)})}`,owner,undefined,load);
  return <main className={styles.page}><header className={styles.heading}><div><p>内容 / 页面编排</p><h1>{onSelect?"选择目标页面":"内容编排"}</h1></div>{!onSelect?<Link href="/admin/about">首页与公共说明</Link>:null}</header><form className={styles.search} onSubmit={event=>{event.preventDefault();setSearch(q.trim());setPage(1);}}><label>页面类型<select value={kind} onChange={event=>{setKind(event.target.value as typeof kind);setPage(1);}}>{Object.entries(placementPageLabels).filter(([key])=>key==="issue"?metadata:authority).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>查找页面<input value={q} onChange={event=>setQ(event.target.value)} placeholder="输入页面名称"/></label><button>搜索</button></form>
    {resource.error?<p role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p>:!resource.data?<p role="status">正在读取现有页面…</p>:<><p>共 {resource.data.count} 个页面</p><div className={styles.directory}>{resource.data.results.map(row=><article key={row.id}><div><h2>{row.title}</h2><small>{({published:"页面已公开",draft:"页面草稿",approved:"事件已核实",archived:"已归档",withdrawn:"已撤回"} as Record<string,string>)[row.status] || "发布状态请在原页面核对"}</small></div>{onSelect?<button type="button" onClick={()=>onSelect(row)}>选择此页面</button>:<><Link href={`/admin/content/${row.type}/${row.id}`}>编排内容</Link><Link href={row.edit_url}>编辑页面资料</Link></>}</article>)}</div>{!resource.data.count?<p>当前条件下没有页面。请先在对应编辑器保存页面资料。</p>:null}<nav className={styles.actions} aria-label="页面目录分页"><button disabled={!resource.data.previous} onClick={()=>setPage(page-1)}>上一页</button><span>第 {page} 页</span><button disabled={!resource.data.next} onClick={()=>setPage(page+1)}>下一页</button></nav></>}
  </main>;
}
