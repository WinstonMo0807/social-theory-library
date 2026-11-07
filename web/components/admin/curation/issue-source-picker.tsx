"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useAdminSession } from "@/lib/admin-session";
import type { IssueResolvedSource, IssueSourceReference } from "@/lib/api/recommendation-issues.types";
import styles from "./issue-editor.module.css";

export type IssueSourceChoice = { target: IssueSourceReference; source: IssueResolvedSource };
type Page = {count:number;next:string|null;previous:string|null;results:IssueSourceChoice[]};
const kinds = [["span","原文"],["work","馆藏版本"],["person","人物"],["node","理论与概念"],["timeline","时间线"],["reading_path","阅读路径"]] as const;

export function IssueSourcePicker({issueId, type, conceptOnly=false, disabled=false, onChoose}: {issueId:string;type?:IssueSourceReference["type"];conceptOnly?:boolean;disabled?:boolean;onChoose:(value:IssueSourceChoice)=>void}) {
  const [kind,setKind]=useState<IssueSourceReference["type"]>(type || "span");
  const [query,setQuery]=useState(""),[search,setSearch]=useState(""),[page,setPage]=useState(1);
  const params=new URLSearchParams({type:kind,q:search,page:String(page)});
  if(conceptOnly)params.set("node_type","concept");
  const user=useAdminSession(),owner=user?String(user.id):null;
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Page>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner||""}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Page>(`/catalog/admin/recommendation-issues/${issueId}/sources/?${params}`,owner,undefined,load);
  return <section className={styles.sourcePicker} aria-label="选择材料">
    <div className={styles.sourceSearch}>{!type?<label><span className="sr-only">来源类型</span><select value={kind} onChange={event=>{setKind(event.target.value as IssueSourceReference["type"]);setPage(1);}}>{kinds.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>:null}
      <label><Search size={15}/><input type="search" maxLength={200} aria-label="查找来源" placeholder={kind==="span"?"查找原文文字…":"查找资料名称…"} value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"&&!event.nativeEvent.isComposing&&event.nativeEvent.keyCode!==229){event.preventDefault();setSearch(query.trim());setPage(1);}}}/></label><button type="button" onClick={()=>{setSearch(query.trim());setPage(1);}}>查找</button></div>
    <p>核对作品、准确版本和来源位置后加入。尚未公开的资料可留作草稿，发布时会重新核对。</p>
    {resource.loading?<LoadingState role="status">正在读取材料…</LoadingState>:resource.error?<p role="alert">{resource.error}<button type="button" onClick={resource.reload}>重试</button></p>:resource.data?<><p>共 {resource.data.count} 项 · 第 {page} 页</p><ul>{resource.data.results.map((row,index)=><li key={`${row.target.type}:${row.target.id}:${row.target.edition_id || index}`}><strong>{row.source.title}</strong>{row.source.edition_label?<p>{row.source.edition_label}</p>:null}{row.source.page_start?<small>PDF 第 {row.source.page_start} 页{row.source.printed_label?` · 印刷页 ${row.source.printed_label}`:""}</small>:null}{row.source.text?<blockquote>{row.source.text}</blockquote>:row.source.summary?<p>{row.source.summary}</p>:null}<small>{row.source.public_eligible?"当前可公开":"公开状态须在发布前核对"}</small><button type="button" disabled={disabled||!owner||Boolean(resource.error)} onClick={()=>{if(!disabled)onChoose(row);}}>使用这份材料</button></li>)}</ul>{!resource.data.results.length?<p>没有匹配的材料，可调整关键词或类型。</p>:null}<nav aria-label="材料分页"><button type="button" disabled={!resource.data.previous} onClick={()=>setPage(value=>value-1)}>上一页</button><button type="button" disabled={!resource.data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav></>:null}
  </section>;
}
