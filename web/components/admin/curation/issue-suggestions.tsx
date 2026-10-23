"use client";

import { createRequestKey } from "../../../lib/request-key";
import { useEffect, useRef, useState } from "react";
import { BookOpen, Lightbulb, RefreshCw, UserRound, X } from "lucide-react";
import { ApiRequestError } from "@/lib/api";
import { Dialog } from "@/components/ui/dialog";
import { EditorialImage } from "@/components/public/editorial-directory";
import { safeEditorialLink } from "@/components/public/issue-prose";
import type { IssueBlock, IssueResolvedSource, IssueSourceReference } from "@/lib/api/recommendation-issues.types";
import styles from "./issue-editor.module.css";

type Candidate={key:string;token:string;kind:"work"|"person"|"concept";target:IssueSourceReference;source:IssueResolvedSource&{image_url?:string};reason:string};
type Page={results:Candidate[];query:string;kind:string;batch:number;has_more:boolean;edit_version:string;checked_at:string;notice:string};
const labels={work:"补充书目",person:"相关人物",concept:"相关概念"};
export function IssueSuggestions({issueId,version,disabled,blocks,request,onInsert,onClose}:{issueId:string;version:string;disabled:boolean;blocks:IssueBlock[];request:<T>(url:string,init?:RequestInit)=>Promise<T>;onInsert:(block:IssueBlock)=>void;onClose:()=>void}) {
  const [query,setQuery]=useState(""),[search,setSearch]=useState(""),[kind,setKind]=useState("all"),[batch,setBatch]=useState(1),[attempt,setAttempt]=useState(0);
  const [page,setPage]=useState<Page|null>(null),[error,setError]=useState(""),[selected,setSelected]=useState<Candidate|null>(null),[busy,setBusy]=useState(""),[message,setMessage]=useState("");
  const [pending,setPending]=useState<{key:string;body:string}|null>(null);
  const inFlight=useRef(false),lifetime=useRef<AbortController|null>(null);
  const endpoint=`/catalog/admin/recommendation-issues/${issueId}/suggestions/`;
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;return()=>controller.abort();},[]);
  useEffect(()=>{
    const controller=new AbortController();queueMicrotask(()=>{if(!controller.signal.aborted){setPage(null);setError("");setSelected(null);}});
    void request<Page>(`${endpoint}?${new URLSearchParams({q:search,kind,batch:String(batch)})}`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted)setPage(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"材料建议暂时不可用。");});
    return()=>controller.abort();
  },[endpoint,search,kind,batch,attempt,version,request]);
  const stale=Boolean(page&&page.edit_version!==version);
  const included=(row:Candidate)=>blocks.some(block=>block.target?.type===row.target.type&&block.target.id===row.target.id&&block.target.edition_id===row.target.edition_id);
  function insert(row:Candidate) {
    if(disabled||stale||inFlight.current||included(row)||blocks.length>=150)return;
    onInsert({id:createRequestKey(),type:row.kind,text:"",target:row.target,resolved_sources:[row.source],source_status:"available"});
    setMessage(`已将“${row.source.title}”加入当前草稿，请补充导读并核对来源。`);setSelected(null);
  }
  async function dismiss(row:Candidate) {
    if(disabled||stale||inFlight.current || pending&&pending.key!==row.key)return;
    inFlight.current=true;setBusy(row.key);setMessage("");
    const command=pending || {key:row.key,body:JSON.stringify({request_id:createRequestKey(),token:row.token})};setPending(command);
    try {
      await request<{dismissed:boolean;key:string}>(endpoint,{method:"POST",body:command.body,signal:lifetime.current?.signal});
      if(lifetime.current?.signal.aborted)return;
      setPending(null);setPage(value=>value?{...value,results:value.results.filter(item=>item.key!==row.key)}:value);setSelected(null);setMessage("已放弃这条建议，当前正文保持原样。");
    } catch(reason) {
      if(lifetime.current?.signal.aborted)return;
      const definite=reason instanceof ApiRequestError&&reason.status>0&&reason.status<500;
      if(definite)setPending(null);
      setMessage(definite?(reason as Error).message:"暂时无法确认放弃结果，请重试同一条建议，或重新读取核对。");
    } finally {inFlight.current=false;if(!lifetime.current?.signal.aborted)setBusy("");}
  }
  const locked=disabled||Boolean(busy)||Boolean(pending);
  function refresh(){if(locked)return;setBatch(1);setAttempt(value=>value+1);}
  const sourceHref=selected?[selected.source.reader_url,selected.source.work_url,selected.source.href].find(href=>href&&safeEditorialLink(href)):undefined;
  return <section className={styles.suggestions} aria-label="智能材料建议">
    <header><h2>智能建议 <small>{page?`(${page.results.length})`:""}</small></h2><div><button type="button" disabled={locked||!page?.has_more} onClick={()=>setBatch(value=>value+1)}><RefreshCw size={13}/>换一批</button><button type="button" aria-label="收起材料建议" onClick={onClose}><X size={16}/></button></div></header>
    <p>根据已保存文章的关键词与标题查找公开资料。可自行调整查询；每条建议须单独核对和采用。</p>
    <div className={styles.sourceSearch}><label><span className="sr-only">材料建议关键词</span><input type="search" maxLength={200} placeholder={page?.query || "输入材料关键词…"} value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"){event.preventDefault();if(!locked){setSearch(query.trim());refresh();}}}}/></label><button type="button" disabled={locked} onClick={()=>{setSearch(query.trim());refresh();}}>查找建议</button></div>
    <nav aria-label="材料建议类型">{[["all","全部"],["work","书目"],["person","人物"],["concept","概念"]].map(([value,label])=><button type="button" key={value} disabled={locked} aria-pressed={kind===value} onClick={()=>{setKind(value);setBatch(1);}}>{label}</button>)}</nav>
    {message?<p role="status">{message}{pending&&!busy?<button type="button" onClick={()=>{setPending(null);setBatch(1);setAttempt(value=>value+1);}}>重新读取核对</button>:null}</p>:null}
    {error?<p role="alert">{error}<button type="button" onClick={refresh}>重试读取</button></p>:!page?<p role="status">正在查找公开材料…</p>:<>
      {stale?<p className={styles.warning} role="alert">文章已产生新修订，请先读取最新草稿并核对，再重新获取建议。</p>:null}
      <div className={styles.suggestionGrid}>{page.results.map(row=><article key={row.key}>
        <span className={styles.suggestionKind}>{labels[row.kind]}</span><div className={styles.suggestionTitle}>{row.source.image_url?<EditorialImage key={row.source.image_url} src={row.source.image_url} className={styles.materialImage} portrait={row.kind==="person"} retry/>:<span className={styles.materialIcon} aria-hidden="true">{row.kind==="work"?<BookOpen size={28}/>:row.kind==="person"?<UserRound size={28}/>:<Lightbulb size={28}/>}</span>}<div><h3>{row.source.title}</h3>{row.source.edition_label?<small>{row.source.edition_label}</small>:null}</div></div>
        {row.source.summary?<p>{row.source.summary}</p>:null}<p>{row.reason}</p><footer><button type="button" onClick={()=>setSelected(row)}>查看</button><button type="button" className={styles.adopt} disabled={locked||stale||included(row)||blocks.length>=150} onClick={()=>insert(row)}>{included(row)?"已在正文":"插入到文章"}</button></footer>
        <button type="button" className={styles.discard} disabled={disabled||stale||Boolean(busy)||Boolean(pending&&pending.key!==row.key)} onClick={()=>void dismiss(row)}>{busy===row.key?"正在确认…":pending?.key===row.key?"重试放弃":"放弃这条建议"}</button>
      </article>)}</div>
      {!page.results.length?<p className={styles.empty}>本批没有可用建议。可更换关键词或查看下一批。</p>:null}
      <footer><span>{page.notice} · 第 {page.batch} 批 · <time dateTime={page.checked_at}>{new Date(page.checked_at).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"})}</time>核对</span><button type="button" disabled={locked} onClick={refresh}>重新读取</button></footer>
    </>}
    <Dialog open={Boolean(selected)} onRequestClose={()=>setSelected(null)} className={styles.dialog} aria-label="材料建议详情">{selected?<><header><h2>{selected.source.title}</h2><button type="button" aria-label="关闭材料详情" onClick={()=>setSelected(null)}><X size={18}/></button></header><div className={styles.sourceReadOnly}><p>{selected.source.edition_label}</p>{selected.source.summary?<p>{selected.source.summary}</p>:null}{selected.source.text?<blockquote>{selected.source.text}</blockquote>:null}{sourceHref?<a href={sourceHref} target="_blank" rel="noopener noreferrer">打开资料原页 ↗</a>:<p>当前资料没有可打开的公开页面。</p>}</div><p>{selected.reason}</p><button type="button" disabled={locked||stale||included(selected)||blocks.length>=150} onClick={()=>insert(selected)}>{included(selected)?"已在正文":"插入到文章"}</button></>:null}</Dialog>
  </section>;
}
