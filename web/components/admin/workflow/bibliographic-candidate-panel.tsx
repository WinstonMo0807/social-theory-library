"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, RefreshCw, Search, Undo2 } from "lucide-react";
import { apiRequest } from "@/lib/api";
import { FILL_FIELD_LABELS, type AssistedFieldFill } from "./field-assistant-control";

type Candidate = { id:string; source:string; source_label:string; source_url:string; fields:Record<string,unknown>; field_actions?:Record<string,Omit<AssistedFieldFill,"field_name">>; evidence:unknown[]; version_status:string; version_note:string };
type Result = {results:Candidate[]; locked_fields:string[]; confirmed_fields:string[]; sources:{key:string;state:string;message:string}[];context_fingerprint:string;external_requested:boolean};
const labels:Record<string,string> = {...FILL_FIELD_LABELS, authors:"作者署名",translators:"译者署名",isbn:"ISBN"};
const display=(value:unknown):string => Array.isArray(value) ? value.map(display).join("、") : value == null ? "" : typeof value === "object" ? JSON.stringify(value) : String(value);

export function BibliographicCandidatePanel({editionId,token,formContext,disabled,onFill,onUndo,pendingFields}:{
  editionId:string;token:string|null;formContext:Record<string,unknown>;disabled:boolean;
  onFill:(selection:AssistedFieldFill)=>void;onUndo:(field:string)=>void;pendingFields:string[];
}) {
  const current = useRef(formContext);
  useEffect(() => { current.current=formContext; }, [formContext]);
  const request = useRef<AbortController|null>(null);
  const [data,setData]=useState<Result|null>(null);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [expanded,setExpanded]=useState<string|null>(null);
  const anchorKey=JSON.stringify([formContext.title,formContext.authors,formContext.isbn,formContext.isbn10,formContext.isbn13,formContext.doi]);
  const [loadedAnchor,setLoadedAnchor]=useState("");
  const stale=Boolean(data && loadedAnchor!==anchorKey);
  const lookup=useCallback(async(external:boolean)=>{
    request.current?.abort();
    const controller=new AbortController();request.current=controller;
    const context=current.current;
    const fingerprint=JSON.stringify(context);
    setBusy(true);setMessage("");
    try {
      const result=await apiRequest<Result>("/catalog/admin/bibliographic-candidates/",{method:"POST",signal:controller.signal,body:JSON.stringify({edition_id:editionId,form_context:context,allow_external:external})},token);
      if(controller.signal.aborted)return;
      if(fingerprint!==JSON.stringify(current.current)){setMessage("查询期间书目输入已改变，结果未填入。请按当前内容重新查找。");return;}
      setData(result);setLoadedAnchor(JSON.stringify([context.title,context.authors,context.isbn,context.isbn10,context.isbn13,context.doi]));setMessage(result.results.length ? "候选不会自动覆盖当前填写，请核对具体出版版本。" : "未找到可匹配书目，可继续手工填写。");
    }catch(error){if(!controller.signal.aborted)setMessage(error instanceof Error ? error.message : "候选暂时无法读取，当前填写仍保留。");}
    finally{if(!controller.signal.aborted)setBusy(false);}
  },[editionId,token]);
  useEffect(()=>{const timer=window.setTimeout(()=>{setData(null);void lookup(false);},0);return()=>{window.clearTimeout(timer);request.current?.abort();};},[lookup]);
  const adopt=(candidate:Candidate,field:string)=>{
    const action=candidate.field_actions?.[field];
    if(stale || !action || !(field in FILL_FIELD_LABELS) || data?.locked_fields.includes(field))return;
    onFill({...action,field_name:field as AssistedFieldFill["field_name"]});
  };
  const fillEmpty=(candidate:Candidate)=>{
    if(stale)return;
    const fields=Object.keys(candidate.field_actions??{}).filter(field=>field in FILL_FIELD_LABELS && !data?.locked_fields.includes(field) && !display(current.current[field]).trim());
    fields.forEach(field=>adopt(candidate,field));
    setMessage(fields.length ? `已填入 ${fields.length} 个空字段，尚未保存；可以逐项撤销。` : "没有可填入的空字段。保留当前人工填写与锁定值。");
  };
  return <section className="bibliographic-candidates admin-panel" aria-label="整条书目候选">
    <header><div><h2>候选书目与版本</h2><p>先核对整条来源，再选择需要填入的字段。</p></div><div><button className="button secondary" type="button" disabled={disabled||busy} onClick={()=>void lookup(false)}><RefreshCw size={14}/>馆内候选</button><button className="button secondary" type="button" disabled={disabled||busy} onClick={()=>void lookup(true)}><Search size={14}/>查找免费来源</button></div></header>
    <p className="admin-help">页面打开和输入只使用本地资料；外部查询仅在你点击时进行，限已允许的免费来源。作者姓名须在作者区核对具体人物。</p>
    {busy?<p role="status"><LoaderCircle className="spin" size={15}/>正在读取候选…</p>:null}
    {message?<p role="status">{message}</p>:null}
    {stale?<p role="status">题名、作者或标识符已经改变，旧候选已停用。请按当前填写重新查找。</p>:null}
    {data?.sources.map(source=><p className={`bibliographic-source state-${source.state}`} key={source.key}><strong>{source.key}</strong><span>{source.message}</span></p>)}
    {data?.results.map(candidate=><article key={candidate.id} className="bibliographic-candidate"><div><small>{candidate.source_label||candidate.source}</small><h3>{display(candidate.fields.title)||"书目候选"}</h3><p>{[display(candidate.fields.authors),display(candidate.fields.publisher),display(candidate.fields.publication_year),display(candidate.fields.isbn13||candidate.fields.isbn)].filter(Boolean).join(" · ")}</p><p>{candidate.version_note}</p></div><div className="bibliographic-candidate-actions"><button type="button" className="button" disabled={disabled||busy||stale} onClick={()=>fillEmpty(candidate)}>仅填入空字段</button><button type="button" className="button secondary" aria-expanded={expanded===candidate.id} onClick={()=>setExpanded(expanded===candidate.id?null:candidate.id)}>逐项核对与来源</button></div>{expanded===candidate.id?<div className="bibliographic-field-comparison"><table><thead><tr><th>字段</th><th>当前填写</th><th>候选</th><th>决定</th></tr></thead><tbody>{Object.entries(candidate.fields).map(([field,value])=><tr key={field}><th>{labels[field]||field}</th><td>{display(formContext[field])||"尚未填写"}</td><td>{display(value)}</td><td>{data.locked_fields.includes(field)?<span>人工锁定</span>:candidate.field_actions?.[field]&&field in FILL_FIELD_LABELS?<button type="button" disabled={disabled||stale} onClick={()=>adopt(candidate,field)}>填入此项</button>:<span>核对后手工关联</span>}</td></tr>)}</tbody></table>{candidate.source_url&&/^https?:\/\//.test(candidate.source_url)?<a href={candidate.source_url} target="_blank" rel="noreferrer">打开来源页面 ↗</a>:<span>来源保存在当前候选记录中</span>}<p>未选择的字段保持现值；采用后仍需明确保存。</p></div>:null}</article>)}
    {pendingFields.filter(field=>!field.includes(":")).length?<div className="bibliographic-undo"><strong>本次已填入，尚未保存</strong>{pendingFields.filter(field=>!field.includes(":")).map(field=><button key={field} type="button" disabled={disabled} onClick={()=>onUndo(field)}><Undo2 size={13}/>{labels[field]||field}</button>)}</div>:null}
  </section>;
}
