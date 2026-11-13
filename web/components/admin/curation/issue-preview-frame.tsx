"use client";


import { LoadingState } from "@/components/ui/loading-state";
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
  return user?<OwnedIssuePreview key={`${user.id}:${epoch}:${issueId}:${version}`} owner={String(user.id)} issueId={issueId} version={version} config={config}/>:<LoadingState variant="screen" role="status">正在核对预览账户…</LoadingState>;
}

function OwnedIssuePreview({owner,issueId,version,config}:{owner:string;issueId:string;version:string;config:SiteConfig}) {
  const [data,setData]=useState<IssuePublicationReviewData|null>(null),[error,setError]=useState("");
  useEffect(()=>{if(!owner)return;const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(25000)]);
    void withPrivateOwner(owner,()=>apiRequest<IssuePublicationReviewData>(`/catalog/admin/recommendation-issues/${issueId}/preview/?review=true&edit_version=${encodeURIComponent(version)}`,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal).then(value=>{if(value.edit_version!==version||value.reader_preview.id!==issueId)throw Error("预览对象或保存版本不匹配，请重新检查。");if(!controller.signal.aborted)setData(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"预览读取失败。");});return()=>controller.abort();
  },[owner,issueId,version]);
  useEffect(()=>{
    let active=true;
    const report=(state=data&&!error?"ready":error?"error":"loading")=>window.parent.postMessage({type:"stl:issue-publication-preview",owner,issueId,version,state},window.location.origin);
    const paint=window.requestAnimationFrame(()=>{if(active)report();});
    const receive=(event:MessageEvent)=>{if(active&&event.origin===window.location.origin&&event.source===window.parent&&event.data?.type==="stl:issue-preview-probe")report();};
    const unsubscribe=subscribeToSessionChanges(()=>{active=false;report("error");});
    window.addEventListener("message",receive);
    return()=>{active=false;window.cancelAnimationFrame(paint);window.removeEventListener("message",receive);unsubscribe();};
  },[owner,issueId,version,data,error]);
  if(error)return <section role="alert"><h1>预览暂不可用</h1><p>{error}</p><p>请返回发布检查重新读取当前已保存版本。</p></section>;
  if(!data)return <LoadingState role="status">正在读取已保存稿…</LoadingState>;
  return <><SiteHeader config={config} preview/><RecommendationIssueView issue={data.reader_preview} preview/></>;
}
