"use client";

import { useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useActionGuard } from "@/lib/use-action-guard";
import type { ArticleComment, ArticleCommentPage } from "@/components/public/article-comments";

export function ArticleCommentReview({issueId,owner}:{issueId:string;owner:string}){
  const [page,setPage]=useState(1),[message,setMessage]=useState(""),[reason,setReason]=useState("");
  const endpoint=`/reading/article-comments/admin/${issueId}/`,resource=useApiResource<ArticleCommentPage>(`${endpoint}?page=${page}`,getServerSessionCredential(),owner);
  const {pendingAction,startAction,finishAction}=useActionGuard();
  async function decide(row:ArticleComment,status:"published"|"rejected"){
    if(!startAction(row.id))return;
    setMessage("");
    try{await withPrivateOwner(owner,()=>apiRequest<ArticleComment>(endpoint,{method:"POST",body:JSON.stringify({id:row.id,expected_revision:row.revision,status,reason})},getServerSessionCredential()));setMessage(status==="published"?"已公开这条评论。":"这条评论未公开；此前公开的内容已经撤下。");setReason("");}
    catch(error){setMessage(`${error instanceof Error?error.message:"审核结果未确认。"} 请重新读取当前状态后继续。`);}
    finally{resource.retry();finishAction(row.id);}
  }
  return <section className="admin-panel"><h2>文章评论审核</h2><p>只审核读者明确同意公开的署名与评论，不读取账户私人资料。旧版文章评论保留归属，不迁到新版。</p><label>本次审核说明<input maxLength={240} value={reason} onChange={event=>setReason(event.target.value)}/></label>{resource.error?<p role="alert">{resource.error} <button onClick={resource.retry}>重新读取</button></p>:null}{message?<p role="status">{message}</p>:null}{resource.loading?<p role="status">正在读取评论…</p>:null}
    {resource.data?.results.map(row=><article key={row.id}><h3>{row.byline} · {({pending:"待审核",published:"已公开",rejected:"未公开"})[row.status!]}</h3><p style={{whiteSpace:"pre-wrap"}}>{row.body}</p>{row.moderation_reason?<p>审核说明：{row.moderation_reason}</p>:null}<div><button disabled={Boolean(pendingAction)||row.status==="published"} onClick={()=>void decide(row,"published")}>核对后公开</button><button disabled={Boolean(pendingAction)||row.status==="rejected"} onClick={()=>void decide(row,"rejected")}>不公开 / 撤下</button></div></article>)}
    {resource.data?.count===0?<p>尚无读者提交的评论。</p>:null}<nav aria-label="评论审核分页"><button disabled={!resource.data?.previous||resource.loading||Boolean(pendingAction)} onClick={()=>setPage(page-1)}>上一页</button><span>第 {page} 页 · 共 {resource.data?.count ?? "—"} 条</span><button disabled={!resource.data?.next||resource.loading||Boolean(pendingAction)} onClick={()=>setPage(page+1)}>下一页</button></nav>
  </section>;
}
