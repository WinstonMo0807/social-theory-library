"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import type { ReaderManifestPayload } from "@/lib/api/public-catalog";
import type { IssueResolvedSource } from "@/lib/api/recommendation-issues.types";
import { adaptApiWork } from "@/lib/public-data-adapters";
import { usePublicSession } from "../public-session-provider";

const ReaderShell=dynamic(()=>import("../reader-shell").then(module=>module.ReaderShell),{ssr:false,loading:()=> <p role="status">正在准备原文阅读器…</p>});
export function EditorialReader({source,returnTo}:{source:IssueResolvedSource;returnTo:string}){
  const {state}=usePublicSession(),owner=state.status==="authenticated"?String(state.user?.id):"visitor";
  return <ReaderSource key={`${owner}:${source.id}:${source.document_revision_id}`} source={source} returnTo={returnTo}/>;
}
function ReaderSource({source,returnTo}:{source:IssueResolvedSource;returnTo:string}){
  const [manifest,setManifest]=useState<ReaderManifestPayload|null>(null),[error,setError]=useState(""),[attempt,setAttempt]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    void apiRequest<ReaderManifestPayload>(`/catalog/assets/${encodeURIComponent(source.asset_id || "")}/manifest/`,{cache:"no-store",signal:AbortSignal.any([controller.signal,AbortSignal.timeout(30000)])}).then(value=>{
      if(value.asset_id!==source.asset_id||value.document_revision_id!==source.document_revision_id||value.edition_id!==source.edition_id||value.work.edition?.id!==value.edition_id||value.work.edition?.readable_asset?.id!==source.asset_id)throw new Error("展项对应的原文版本已经变化，请返回文章重新核对。");
      if(!controller.signal.aborted)setManifest(value);
    }).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"原文暂不可用。");});
    return()=>controller.abort();
  },[source.asset_id,source.edition_id,source.document_revision_id,attempt]);
  if(error)return <section role="alert"><h2>这份原文暂不可用</h2><p>{error}</p><button onClick={()=>{setError("");setManifest(null);setAttempt(value=>value+1);}}>重新核对</button></section>;
  if(!manifest)return <p role="status">正在读取展项的准确版本、页码与目录…</p>;
  const requestedPage=Number(new URLSearchParams(window.location.search).get("page"));
  return <ReaderShell embedded work={{...adaptApiWork(manifest.work),pages:manifest.page_count}} documentRevisionId={manifest.document_revision_id || ""} requestedRevisionId={source.document_revision_id || ""}
    initialPage={Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : source.page_start || 1} initialQuery="" initialFocus="" initialPassage="" initialEvidence={source.type==="span"?source.id:""} returnTo={returnTo}
    outline={manifest.outline} relatedScholars={manifest.related_scholars.flatMap(row=>row.slug?[{...row,slug:row.slug}]:[])} relatedTheories={manifest.related_theories} relatedTopics={manifest.related_topics}/>;
}
