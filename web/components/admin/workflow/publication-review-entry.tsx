"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useAdminSession } from "@/lib/admin-session";
import { PublicationLedger } from "./publication-ledger";

export function PublicationReviewEntry({itemId,objectKind,backHref,view="review"}:{itemId:string;objectKind:string;backHref:string;view?:"desk"|"review"}) {
  const user=useAdminSession(),owner=user?String(user.id):"";
  const [edition,setEdition]=useState(""),[error,setError]=useState(""),[attempt,setAttempt]=useState(0);
  const valid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(itemId);
  useEffect(()=>{
    if(!owner||objectKind!=="upload"||!valid)return;
    const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    void withPrivateOwner(owner,()=>apiRequest<{context:{edition_id?:string|null}}>(`/catalog/admin/intake/${itemId}/`,{signal,headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),signal).then(value=>{
      if(controller.signal.aborted)return;
      if(!value.context.edition_id){setError("此收件尚未建立出版版本，请先返回收件完成编目。");return;}
      setEdition(value.context.edition_id);setError("");
    }).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"收件暂不可读。");});return()=>controller.abort();
  },[itemId,objectKind,owner,valid,attempt]);
  if(!valid||!["upload","edition"].includes(objectKind))return <section className="admin-page" role="alert"><h1>发布对象无效</h1><Link href={backHref}>返回原工作页</Link></section>;
  // Legacy paths denote UploadItem. Edition identity needs an explicit discriminator.
  const editionId=objectKind==="edition"?itemId:edition;
  if(editionId)return <PublicationLedger key={`${owner}:${editionId}`} editionId={editionId} backHref={backHref} view={view} />;
  return <section className="admin-page"><h1>发布前检查</h1><p role={error?"alert":"status"}>{error||"正在核对收件对应的出版版本…"}</p>{error?<button type="button" onClick={()=>setAttempt(n=>n+1)}>重新读取</button>:null}<Link href={`/admin/intake/${encodeURIComponent(itemId)}`}>返回收件编目</Link><Link href={backHref}>返回原工作页</Link></section>;
}
