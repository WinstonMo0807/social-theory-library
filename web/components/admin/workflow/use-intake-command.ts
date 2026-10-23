"use client";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { createRequestKey } from "@/lib/request-key";
export type IntakeChoice={mode:"use_edition"|"new_version"|"new_work";edition_id:string|null;candidate_version:string;document_type:string;title:string;note:string};
type Command={action:"save"|"defer"|"confirm";choice:IntakeChoice;expected_version:string;confirm?:boolean};
type Receipt={owner_id:string;request_id:string;state:"applied"|"cancelled";next_url:string};
export function useCatalogCommand<C extends object,R extends Receipt>(owner:string,path:string,key:string){
  const original=useRef<(C&{request_id:string})|null>(null),lifetime=useRef<AbortController|null>(null),sending=useRef(false);
  const [ready,setReady]=useState(false),[busy,setBusy]=useState(false),[recovery,setRecovery]=useState(""),[error,setError]=useState(""),[canRetry,setCanRetry]=useState(false);
  useEffect(()=>{const controller=new AbortController();lifetime.current=controller;queueMicrotask(()=>{if(controller.signal.aborted)return;try{setRecovery(sessionStorage.getItem(key)||"");setReady(true);}catch{setError("浏览器暂不能保存请求编号，请保留当前页面。");}});return()=>controller.abort();},[key]);
  function clear(){sessionStorage.removeItem(key);original.current=null;setRecovery("");setCanRetry(false);}
  async function request(url:string,options:RequestInit){const signal=AbortSignal.any([lifetime.current!.signal,AbortSignal.timeout(60000)]);return withPrivateOwner(owner,()=>apiRequest<R>(url,{...options,signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal);}
  function verify(result:Receipt,id:string){if(result.owner_id!==owner||result.request_id!==id||!["applied","cancelled"].includes(result.state))throw Error("操作回执与当前对象不匹配，请查回原记录。");}
  async function send(body?:C){if(!ready||sending.current||lifetime.current?.signal.aborted)return null;sending.current=true;setBusy(true);setError("");try{if(!original.current){if(!body||sessionStorage.getItem(key))throw Error("请先查回上次操作。");original.current={...body,request_id:createRequestKey()};sessionStorage.setItem(key,original.current.request_id);setRecovery(original.current.request_id);setCanRetry(true);}const result=await request(path,{method:"POST",body:JSON.stringify(original.current)});verify(result,original.current.request_id);clear();return result;}catch(reason){if(reason instanceof ApiRequestError&&!(reason instanceof PrivateOwnerVerificationError)&&[400,401,403,404,409].includes(reason.status))clear();if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"未收到结果，请查回原请求。");return null;}finally{sending.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}}
  async function lookup(cancel=false){if(!recovery||sending.current||lifetime.current?.signal.aborted)return null;sending.current=true;setBusy(true);setError("");try{const result=await request(`${path}commands/${recovery}/`,cancel?{method:"POST",body:JSON.stringify({action:"cancel_pending"})}:{});verify(result,recovery);clear();return result;}catch(reason){if(!lifetime.current?.signal.aborted)setError(reason instanceof Error?reason.message:"暂时无法读取回执。");return null;}finally{sending.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}}
  return {ready,busy,recovery,error,canRetry,send,lookup};
}
export function useIntakeCommand(owner:string,itemId:string){return useCatalogCommand<Command,Receipt>(owner,`/ingestion/items/${itemId}/confirmation/`,`stl-intake-command:${owner}:${itemId}`);}
