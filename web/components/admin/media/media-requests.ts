"use client";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";

export async function ownedRequest<T>(owner:string,url:string,options:RequestInit={}){
  const signal=options.signal?AbortSignal.any([options.signal,AbortSignal.timeout(60000)]):AbortSignal.timeout(60000);
  return withPrivateOwner(owner,()=>apiRequest<T>(url,{...options,signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal);
}
export function useOwnedRead<T>(owner:string,url:string){
  const [attempt,setAttempt]=useState(0),[result,setResult]=useState<{key:string;data:T|null;error:string}|null>(null);const key=`${owner}:${url}:${attempt}`;
  useEffect(()=>{if(!url)return;const controller=new AbortController();void ownedRequest<T>(owner,url,{signal:controller.signal}).then(data=>{if(!controller.signal.aborted)setResult({key,data,error:""});}).catch(error=>{if(!controller.signal.aborted)setResult({key,data:null,error:error instanceof Error?error.message:"资料读取失败。"});});return()=>controller.abort();},[key,owner,url]);
  return {data:result?.key===key?result.data:null,error:result?.key===key?result.error:"",retry:()=>setAttempt(n=>n+1)};
}
