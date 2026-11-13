"use client";

import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { LoadingState } from "@/components/ui/loading-state";
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
  return <section className="admin-panel comment-review-panel"><header><h2>评论审核</h2>{resource.data ? <span>{resource.data.count} 条</span> : null}</header><p className="workspace-help">仅审核读者同意公开的署名和评论。</p><section data-content-section className="workspace-note"><header data-section-heading>审核范围</header><p>账户私人资料不在审核范围内。旧版评论保留在原文章，不迁入新版。</p></section>{Boolean(resource.data?.results.length) ? <label className="workspace-field">审核说明<input maxLength={240} value={reason} placeholder="填写本次处理原因（选填）" onChange={event=>setReason(event.target.value)}/></label> : null}{resource.error?<p role="alert">{resource.error} <button onClick={resource.retry}>重新读取</button></p>:null}{message?<p role="status">{message}</p>:null}{resource.loading?<LoadingState variant="compact">正在读取评论…</LoadingState>:null}
    {resource.data?.results.map(row=><article key={row.id}><h3>{row.byline} · {({pending:"待审核",published:"已公开",rejected:"未公开"})[row.status!]}</h3><p style={{whiteSpace:"pre-wrap"}}>{row.body}</p>{row.moderation_reason?<p>审核说明：{row.moderation_reason}</p>:null}<div><button disabled={Boolean(pendingAction)||row.status==="published"} onClick={()=>void decide(row,"published")}>核对后公开</button><button disabled={Boolean(pendingAction)||row.status==="rejected"} onClick={()=>void decide(row,"rejected")}>不公开 / 撤下</button></div></article>)}
    {resource.data?.count===0&&!resource.loading?<CommentReviewEmpty />:null}{resource.data && (resource.data.count>0 || page>1) ? <nav className="workspace-pagination" aria-label="评论审核分页"><button disabled={!resource.data?.previous||resource.loading||Boolean(pendingAction)} onClick={()=>setPage(page-1)}>上一页</button><span>第 {page} 页 · 共 {resource.data.count} 条</span><button disabled={!resource.data?.next||resource.loading||Boolean(pendingAction)} onClick={()=>setPage(page+1)}>下一页</button></nav> : null}
  </section>;
}

export function CommentReviewEmpty() {
  return <div className="workspace-empty"><MessageSquare size={28} strokeWidth={1.3} aria-hidden="true" /><div><h3>暂无评论</h3><p>读者提交评论后，会显示在这里。</p></div></div>;
}
