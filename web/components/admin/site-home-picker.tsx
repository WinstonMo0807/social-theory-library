"use client";
import { useCallback, useState } from "react";
import { X, BookOpen, Search } from "lucide-react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { Dialog } from "@/components/ui/dialog";
import type { HomeArea, HomeTarget, HomeCard } from "@/lib/api/home.types";
import { siteBase } from "./use-site-content";
import styles from "./site-content.module.css";
export type HomeChoice={target:HomeTarget;source:HomeCard};
type Page={count:number;page:number;total_pages:number;results:HomeChoice[]};
export function SiteHomePicker({owner,area,used,onChoose,onClose,inline=false,disabled=false}:{owner:string;area:HomeArea;used:HomeTarget[];onChoose:(choice:HomeChoice)=>void;onClose:()=>void;inline?:boolean;disabled?:boolean}){
  const [kind,setKind]=useState<HomeTarget["type"]>(area==="scholars"?"scholar":area==="topics"?"topic":"issue");
  const [input,setInput]=useState(""),[query,setQuery]=useState(""),[page,setPage]=useState(1);
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Page>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),[owner]);
  const resource=usePersistentWorkspace<Page>(`${siteBase}sources/?${new URLSearchParams({type:kind,q:query,page:String(page)})}`,owner,undefined,load);
  const content=<><header><h2>{inline?"更多内容（未上首页）":"选择已公开的内容"}</h2>{inline?null:<button onClick={onClose} aria-label="关闭内容选择"><X size={18}/></button>}</header>
    <p>引用已有来源，保存与发布首页时不会改变来源内容。</p>
    {area==="featured"?<nav className={styles.tabs} aria-label="来源类型">{(["issue","scholar","topic","edition"] as const).map(type=><button key={type} aria-pressed={kind===type} onClick={()=>{setKind(type);setPage(1);}}>{{issue:"特别策划",scholar:"学者",topic:"主题",edition:"馆藏"}[type]}</button>)}</nav>:null}
    <form className={styles.search} onSubmit={event=>{event.preventDefault();setQuery(input.trim());setPage(1);resource.reload();}}><Search size={16}/><input aria-label="搜索已公开内容" value={input} maxLength={200} onChange={event=>setInput(event.target.value)} placeholder="搜索标题或姓名…"/><button>查找</button></form>
    {resource.error?<p role="alert">{resource.error}<button onClick={resource.reload}>重新读取</button></p>:!resource.data?<p role="status">正在读取公开目录…</p>:<><ul className={styles.choices}>{resource.data.results.map(row=><li key={row.target.id}>{row.source.image_url?<img src={normalizePublicResourceUrl(row.source.image_url)} alt=""/>:<BookOpen size={28}/>}<div><strong>{row.source.title}</strong><p>{row.source.description}</p><small>{row.source.label} · 当前公开</small></div><button disabled={disabled||used.some(target=>target.type===row.target.type&&target.id===row.target.id)} onClick={()=>onChoose(row)}>{used.some(target=>target.type===row.target.type&&target.id===row.target.id)?"已添加":"选择"}</button></li>)}</ul>{!resource.data.results.length?<p className={styles.empty}>没有符合条件的已公开内容。可调整关键词，或先在原内容页完成发布。</p>:null}<nav className={styles.pagination} aria-label="来源分页"><button disabled={page<=1} onClick={()=>setPage(value=>value-1)}>上一页</button><span>{resource.data.page} / {resource.data.total_pages} · 共 {resource.data.count} 项</span><button disabled={page>=resource.data.total_pages} onClick={()=>setPage(value=>value+1)}>下一页</button></nav></>}
  </>;
  return inline?<section className={styles.inlinePicker} aria-label="更多公开内容">{content}</section>:<Dialog open onRequestClose={onClose} className={styles.picker} aria-label="选择已公开的内容">{content}</Dialog>;
}
