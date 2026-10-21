"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { usePublicSession } from "../public-session-provider";
import styles from "./editorial.module.css";

export type ArticleComment = {id:string;public_revision_id:string;byline:string;body:string;created_at:string;revision?:number;status?:"pending"|"published"|"rejected";moderation_reason?:string};
export type ArticleCommentPage = {owner_id?:string;count:number;page:number;total_pages:number;next:string|null;previous:string|null;results:ArticleComment[]};
type Submit = {request_id:string;public_revision_id:string;byline:string;body:string;confirm_public:true};
type Pending = {owner:string;submit:Submit} | {owner:string;remove:{id:string;expected_revision:number}};
const statusLabels={pending:"待审核",published:"已公开",rejected:"未公开"};

export function ArticleComments({issueId,revisionId,slug,onCount}:{issueId:string;revisionId:string;slug:string;onCount:(value:number|null)=>void}){
  const {state:session,retry:verifySession}=usePublicSession(),owner=session.status==="authenticated"?String(session.user?.id||""):"";
  const [page,setPage]=useState(1),[minePage,setMinePage]=useState(1),[attempt,setAttempt]=useState(0);
  const [publicResult,setPublicResult]=useState<{key:string;data:ArticleCommentPage|null;error:string}|null>(null);
  const [mineResult,setMineResult]=useState<{key:string;data:ArticleCommentPage|null;error:string}|null>(null);
  const [draft,setDraft]=useState({owner:"",byline:"",body:"",confirmed:false}),[pending,setPending]=useState<Pending|null>(null);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState({owner:"",text:""});
  const running=useRef(false),alive=useRef(true);
  const base=`/reading/article-comments/${issueId}/`,publicKey=`${issueId}:${revisionId}:${page}:${attempt}`,mineKey=`${owner}:${issueId}:${minePage}:${attempt}`;
  const shown=publicResult?.key===publicKey?publicResult:null,mine=mineResult?.key===mineKey?mineResult:null;
  const currentDraft=draft.owner===owner?draft:{owner,byline:"",body:"",confirmed:false};
  useUnsavedForm(Boolean(pending||draft.body||draft.byline),false);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useEffect(()=>{
    const controller=new AbortController();
    void apiRequest<ArticleCommentPage>(`/reading/article-comments/public/${issueId}/?page=${page}&page_size=12&public_revision_id=${revisionId}`,{cache:"no-store",signal:controller.signal}).then(
      data=>{if(!controller.signal.aborted){setPublicResult({key:publicKey,data,error:""});onCount(data.count);}},
      reason=>{if(!controller.signal.aborted){setPublicResult({key:publicKey,data:null,error:reason instanceof Error?reason.message:"评论读取失败。"});onCount(null);}});
    return()=>controller.abort();
  },[issueId,revisionId,page,publicKey,onCount]);
  useEffect(()=>{
    if(!owner)return;
    const controller=new AbortController();
    void withPrivateOwner(owner,()=>apiRequest<ArticleCommentPage>(`${base}?page=${minePage}&page_size=12`,{cache:"no-store",headers:{"X-Reader-Owner":owner},signal:controller.signal},getServerSessionCredential()),controller.signal).then(
      data=>{if(!controller.signal.aborted && data.owner_id===owner)setMineResult({key:mineKey,data,error:""});},
      reason=>{if(!controller.signal.aborted)setMineResult({key:mineKey,data:null,error:reason instanceof Error?reason.message:"本人评论读取失败。"});});
    return()=>controller.abort();
  },[owner,base,minePage,mineKey]);
  async function send(command:Pending,lookup=false){
    if(running.current)return;
    if(command.owner!==owner){setMessage({owner,text:"请恢复原账户后核对提交，原请求仍保留。"});return;}
    running.current=true;setBusy(true);setPending(command);setMessage({owner,text:""});
    try{
      if("submit" in command){
        const result=await withPrivateOwner(owner,()=>apiRequest<{owner_id:string;request_id:string;comment:ArticleComment|null;notice:string}>(lookup?`${base}requests/${command.submit.request_id}/`:base,
          {method:lookup?"GET":"POST",cache:"no-store",headers:{"X-Reader-Owner":owner},body:lookup?undefined:JSON.stringify(command.submit)},getServerSessionCredential()));
        if(result.owner_id!==owner||result.request_id!==command.submit.request_id)throw new Error("提交回执与当前账户不一致，请重新核对。");
        if(alive.current){setDraft({owner,body:"",byline:"",confirmed:false});setMessage({owner,text:result.notice});}
      }else{
        const result=await withPrivateOwner(owner,()=>apiRequest<{owner_id:string;deleted:boolean}>(`${base}${command.remove.id}/`,{method:"DELETE",headers:{"X-Reader-Owner":owner},body:JSON.stringify({expected_revision:command.remove.expected_revision})},getServerSessionCredential()));
        if(result.owner_id!==owner||!result.deleted)throw new Error("删除结果尚未确认，请核对原操作。");
        if(alive.current)setMessage({owner,text:"本人评论已删除，公开列表同步撤下。"});
      }
      if(alive.current){setPending(null);setAttempt(value=>value+1);}
    }catch(reason){if(alive.current){const rejected=!lookup&&reason instanceof ApiRequestError&&[400,409,429].includes(reason.status);if(rejected){setPending(null);setAttempt(value=>value+1);}setMessage({owner,text:`${reason instanceof Error?reason.message:"操作结果尚未确认。"}${rejected?" 当前输入已保留，请核对后重新操作。":" 原请求已保留，可核对结果或用原请求重试。"}`});verifySession();}}
    finally{running.current=false;if(alive.current)setBusy(false);}
  }
  function begin(){if(!owner||!currentDraft.confirmed||!currentDraft.byline.trim()||!currentDraft.body.trim())return;void send({owner,submit:{request_id:crypto.randomUUID(),public_revision_id:revisionId,byline:currentDraft.byline.trim(),body:currentDraft.body.trim(),confirm_public:true}});}
  function pager(data:ArticleCommentPage|null|undefined,current:number,change:(value:number)=>void,label:string){return data && (data.previous||data.next)?<nav aria-label={label}><button disabled={!data.previous} onClick={()=>change(current-1)}>上一页</button><span>第 {data.page} / {data.total_pages} 页</span><button disabled={!data.next} onClick={()=>change(current+1)}>下一页</button></nav>:null;}
  return <section id="article-comments" className={styles.comments}><header><h2>读者评论{shown?.data?`（${shown.data.count}）`:""}</h2><button type="button" onClick={()=>setAttempt(value=>value+1)}>刷新评论</button></header><p>此处展示当前文章版本经审核公开的评论。读者观点由本人署名，不代表馆藏原文或策划者结论。</p>
    {shown?.error?<p role="alert">{shown.error}</p>:shown?.data?shown.data.results.length?shown.data.results.map(row=><article key={row.id}><strong>{row.byline}</strong><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleDateString("zh-CN")}</time><p>{row.body}</p></article>):<p>当前版本还没有公开评论。</p>:<p role="status">正在读取公开评论…</p>}
    {pager(shown?.data,page,setPage,"公开评论分页")}
    {owner?<><h3>我的评论</h3>{mine?.error?<p role="alert">{mine.error}</p>:mine?.data?mine.data.results.map(row=><article key={row.id}><strong>{row.byline}</strong><span>{statusLabels[row.status!]}{row.public_revision_id!==revisionId?" · 针对旧版文章":""}</span><p>{row.body}</p>{row.moderation_reason?<p>审核说明：{row.moderation_reason}</p>:null}<button disabled={busy||Boolean(pending)} onClick={()=>{if(window.confirm("删除这条本人评论？已公开内容也会撤下。"))void send({owner,remove:{id:row.id,expected_revision:row.revision!}});}}>删除本人评论</button></article>):<p role="status">正在读取本人评论…</p>}{mine?.data?.count===0?<p>尚未提交评论。</p>:null}{pager(mine?.data,minePage,setMinePage,"本人评论分页")}
      <form onSubmit={event=>{event.preventDefault();begin();}}><fieldset disabled={busy||Boolean(pending)}><legend>提交评论</legend><label>公开署名<input required maxLength={80} value={currentDraft.byline} onChange={event=>setDraft({...currentDraft,byline:event.target.value})}/></label><label>评论内容<textarea required maxLength={3000} rows={5} value={currentDraft.body} onChange={event=>setDraft({...currentDraft,body:event.target.value})}/></label><label className={styles.commentConsent}><input type="checkbox" required checked={currentDraft.confirmed} onChange={event=>setDraft({...currentDraft,confirmed:event.target.checked})}/>我同意以上署名和评论经审核后公开，其他账户资料和私人笔记不会附带公开。</label><button type="submit" disabled={!currentDraft.confirmed}>提交审核</button></fieldset></form>
    </>:<p><Link href={`/login?next=${encodeURIComponent(`/recommendations/${slug}#article-comments`)}`}>登录后撰写评论</Link></p>}
    {pending?<div role="status"><p>有一项操作等待核对。{pending.owner!==owner?"请恢复提交时的账户。":""}</p>{"submit" in pending?<button disabled={busy||pending.owner!==owner} onClick={()=>void send(pending,true)}>核对原提交结果</button>:null}<button disabled={busy||pending.owner!==owner} onClick={()=>void send(pending)}>使用原请求重试</button></div>:null}
    {message.owner===owner&&message.text?<p role="status">{message.text}</p>:null}
  </section>;
}
