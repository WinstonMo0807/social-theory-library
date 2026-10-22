"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";

type Command = { owner:string;request_id:string;public_revision_id:string };
type Result = {owner_id:string;id:string|null;title:string;item_count:number;saved:boolean;receipt:{request_id:string}|null;notice:string};
export function SaveIssueList({ slug, revisionId }: { slug:string;revisionId?:string }) {
  const {state:session,retry}=useSessionBootstrap();
  const [message,setMessage]=useState(""),[pending,setPending]=useState(false),[command,setCommand]=useState<Command|null>(null),[result,setResult]=useState<Result|null>(null);
  const [messageOwner,setMessageOwner]=useState("");
  const busy=useRef(false),alive=useRef(true);
  useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
  useEffect(()=>{if(!command)return;const leave=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue="";};window.addEventListener("beforeunload",leave);return()=>window.removeEventListener("beforeunload",leave);},[command]);
  const owner=session.status==="authenticated"?String(session.user?.id||""):"";
  const currentResult=result?.owner_id===owner?result:null;
  async function act(lookup=false){
    if(busy.current||!revisionId||!owner)return;
    const original=command||{owner,request_id:crypto.randomUUID(),public_revision_id:revisionId};
    setMessageOwner(owner);
    if(original.owner!==owner){setMessage("登录账户已变化。请恢复原账户后核对这次保存，当前请求仍保留。");return;}
    busy.current=true;setPending(true);setCommand(original);setMessage("");
    const data={request_id:original.request_id,public_revision_id:original.public_revision_id};
    try{
      const endpoint=`/catalog/recommendation-issues/${encodeURIComponent(slug)}/save-list/`;
      const value=await withPrivateOwner(owner,()=>apiRequest<Result>(`${endpoint}${lookup?`?${new URLSearchParams(data)}`:""}`,{method:lookup?"GET":"POST",headers:{"X-Reader-Owner":owner},cache:"no-store",body:lookup?undefined:JSON.stringify(data)},getServerSessionCredential()));
      if(value.owner_id!==owner||value.receipt?.request_id!==original.request_id)throw new Error("保存回执未能对应当前账户和请求，请重新核对。");
      if(alive.current){setCommand(null);setResult(value);setMessage(value.saved?`已保存私人书单，共 ${value.item_count} 部作品。` : "原保存已完成，但书单后来被删除；本次核对没有重新创建书单。");}
    }catch(reason){if(alive.current){const rejected=!lookup && reason instanceof ApiRequestError && [400,409].includes(reason.status);if(rejected)setCommand(null);setMessage(`${reason instanceof Error?reason.message:"保存结果尚未确认。"}${rejected?" 本次保存未执行，请核对公开版本和隐私设置。":" 原请求已保留，请先核对结果。"}`);retry();}}
    finally{busy.current=false;if(alive.current)setPending(false);}
  }
  return <section className="issue-save-banner"><div><h2>保存本期书单</h2><p>将已公开作品另存为私人书单。原文版本、页码和笔记请从文章的引用与阅读入口保存。</p></div>
    {session.status==="authenticated"?<>{command?<><button type="button" className="button" disabled={pending} onClick={()=>void act(true)}>核对原保存结果</button><button type="button" disabled={pending} onClick={()=>void act()}>使用原请求重试</button></>:<button type="button" className="button" disabled={pending||!revisionId||Boolean(currentResult)} onClick={()=>void act()}>{pending?"正在保存…":currentResult?"本次保存已核对":"保存书单 ＋"}</button>}</>:<Link href={`/login?next=${encodeURIComponent(`/recommendations/${slug}`)}`}>登录后保存书单</Link>}
    {message && messageOwner===owner?<p role="status">{message}{currentResult?.saved?<Link href="/account/collections">打开我的书单</Link>:null}</p>:null}
  </section>;
}
