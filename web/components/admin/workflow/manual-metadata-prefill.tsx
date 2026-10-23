"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import styles from "./manual-catalog.module.css";

export type ManualMetadataCandidate={id:string;token:string;source_label:string;source_url:string;version_note:string;fields:Record<string,unknown>};
export type ManualPrefill={token:string;fields:string[];previous:unknown;applied:unknown;label:string};
export const prefillKey=(field:string)=>["isbn10","isbn13"].includes(field)?"isbn":field;
export const prefillLabels:Record<string,string>={title:"题名",subtitle:"副题名",abstract:"简介",authors:"作者",translators:"译者",language:"语言",document_type:"材料类型",publisher:"出版社",publication_year:"出版年",publication_place:"出版地",version_label:"版次",isbn:"ISBN",isbn10:"ISBN-10",isbn13:"ISBN-13",doi:"DOI",journal_title:"期刊",volume:"卷",issue:"期",page_range:"起止页码"};
const display=(value:unknown):string=>Array.isArray(value)?value.map(display).join("、"):value==null?"":String(value);
type Result={owner_id:string;results:ManualMetadataCandidate[];sources:{key:string;state:string;message:string}[]};

export function ManualMetadataPrefill({owner,context,current,disabled,shared,prefills,onApply,onUndo,onDetach}:{
  owner:string;context:Record<string,unknown>;current:Record<string,unknown>;disabled:boolean;shared:boolean;
  prefills:Record<string,ManualPrefill>;onApply:(row:ManualMetadataCandidate,fields:string[])=>void;onUndo:(field:string)=>void;onDetach:()=>void;
}){
  const [data,setData]=useState<Result|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const request=useRef<AbortController|null>(null),latest=useRef(context);
  useLayoutEffect(()=>{latest.current=context;},[context]);
  useEffect(()=>()=>request.current?.abort(),[]);
  async function lookup(){
    request.current?.abort();const controller=new AbortController();request.current=controller;
    const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(60000)]),submitted=JSON.stringify(latest.current);
    setBusy(true);setError("");setData(null);
    try{
      const result=await withPrivateOwner(owner,()=>apiRequest<Result>("/catalog/admin/manual-catalog/candidates/",{method:"POST",headers:{"X-Editor-Owner":owner},cache:"no-store",signal,body:JSON.stringify({form_context:latest.current})},getServerSessionCredential(),false),signal);
      if(controller.signal.aborted)return;
      if(result.owner_id!==owner)throw Error("候选账户无法核对，请重新打开此页面。");
      if(submitted!==JSON.stringify(latest.current))throw Error("查询期间书目输入已改变，未使用旧结果。请按当前内容重新查找。");
      setData(result);
    }catch(reason){if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"候选暂不可用。填写已保留，可继续手工填写。")}
    finally{if(!controller.signal.aborted)setBusy(false);}
  }
  const canFill=(field:string)=>!disabled&&!busy&&!(shared&&["title","subtitle","abstract","language","document_type"].includes(field));
  const available=(row:ManualMetadataCandidate)=>Object.keys(row.fields).filter(field=>field in prefillLabels&&canFill(field));
  return <details className={styles.prefill}><summary>从书目来源预填 <small>逐项核对后采用</small></summary><p>点击后仅查询已允许的免费书目来源。不会上传文件，也不会自动新建人物；无结果时可继续手动填写。</p><button type="button" disabled={disabled||busy} onClick={()=>void lookup()}>{busy?"正在查询书目来源…":"查找元数据候选"}</button>
    {error?<p role="alert">{error} 当前填写仍保留。</p>:null}{data?.sources.map(row=><p key={row.key} role="status">{row.key} · {row.message}</p>)}
    {data&&!data.results.length?<p role="status">未找到可用的元数据候选，请手动填写并保存。</p>:null}
    {data?.results.map(row=><article key={row.id}><strong>{display(row.fields.title)||"书目来源"}</strong><small>{row.source_label} · {row.version_note}</small><button type="button" disabled={disabled||busy} onClick={()=>onApply(row,available(row).filter(field=>!display(current[prefillKey(field)]).trim()))}>仅填入空字段</button><details><summary>逐项核对来源与当前填写</summary><div className={styles.prefillScroll} tabIndex={0} role="region" aria-label="候选字段，可横向滚动"><table><thead><tr><th>字段</th><th>当前填写</th><th>候选</th><th>操作</th></tr></thead><tbody>{available(row).map(field=><tr key={field}><th>{prefillLabels[field]}</th><td>{display(current[prefillKey(field)])||"尚未填写"}</td><td>{display(row.fields[field])||"未提供"}</td><td><button type="button" disabled={!canFill(field)||row.fields[field]==null||row.fields[field]===""} onClick={()=>onApply(row,[field])}>填入此项</button></td></tr>)}</tbody></table></div></details>{/^https?:\/\//.test(row.source_url)?<a href={row.source_url} target="_blank" rel="noreferrer">查看原书目来源 ↗</a>:null}</article>)}
    {Object.keys(prefills).length?<div role="status"><p>以下来源将在保存时登记。作者和译者仍需逐人选择馆内身份或明确新建。</p>{Object.entries(prefills).map(([field,row])=><button type="button" key={field} disabled={disabled} onClick={()=>onUndo(field)}>撤销填入 · {prefillLabels[field]} · {row.label}</button>)}<button type="button" disabled={disabled} onClick={onDetach}>保留填写，移除本次预填来源</button></div>:null}
  </details>;
}
