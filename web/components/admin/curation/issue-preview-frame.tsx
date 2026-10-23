"use client";

import { useEffect, useState } from "react";
import { RecommendationIssueView } from "@/components/public/recommendation-issue-view";
import { SiteHeader } from "@/components/site-header";
import type { SiteConfig } from "@/lib/site-config";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useAdminSession } from "@/lib/admin-session";
import type { IssuePublicationReviewData } from "./issue-publication-review";

export function IssuePreviewFrame({issueId,version,config}:{issueId:string;version:string;config:SiteConfig}) {
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  return user?<OwnedIssuePreview key={`${user.id}:${epoch}:${issueId}:${version}`} owner={String(user.id)} issueId={issueId} version={version} config={config}/>:<p role="status">正在核对预览账户…</p>;
}

function OwnedIssuePreview({owner,issueId,version,config}:{owner:string;issueId:string;version:string;config:SiteConfig}) {
  const [data,setData]=useState<IssuePublicationReviewData|null>(null),[error,setError]=useState("");
  useEffect(()=>{if(!owner)return;const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(25000)]);
    void withPrivateOwner(owner,()=>apiRequest<IssuePublicationReviewData>(`/catalog/admin/recommendation-issues/${issueId}/preview/?review=true&edit_version=${encodeURIComponent(version)}`,{signal,headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),signal).then(value=>{if(!controller.signal.aborted)setData(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"预览读取失败。");});return()=>controller.abort();
  },[owner,issueId,version]);
  if(error)return <section role="alert"><h1>预览暂不可用</h1><p>{error}</p><p>请返回发布检查重新读取当前已保存版本。</p></section>;
  if(!data)return <p role="status">正在读取已保存稿…</p>;
  return <><SiteHeader config={config} preview/><RecommendationIssueView issue={data.reader_preview} preview/></>;
}
