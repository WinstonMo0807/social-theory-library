"use client";

import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { IssueBlock } from "@/lib/api/recommendation-issues.types";
import type { EvidenceCurationSource } from "@/lib/api/evidence-curation.types";
import { InlineMediaPicker } from "./inline-media-picker";

type Sources = { count:number;next:string|null;previous:string|null;results:EvidenceCurationSource[] };
function AddEvidence({ onAdd }: {onAdd:(block:IssueBlock)=>void}) {
  const [query,setQuery]=useState(""),[search,setSearch]=useState<string|null>(null),[page,setPage]=useState(1),[attempt,setAttempt]=useState(0);
  const [data,setData]=useState<Sources|null>(null),[error,setError]=useState("");
  useEffect(()=>{
    if(search===null)return;
    const controller=new AbortController();
    queueMicrotask(()=>{if(!controller.signal.aborted){setData(null);setError("");}});
    void apiRequest<Sources>(`/catalog/admin/evidence-curation/sources/?q=${encodeURIComponent(search)}&page=${page}`,{signal:controller.signal},getServerSessionCredential()).then(value=>{if(!controller.signal.aborted)setData(value);}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"原文读取失败。");});
    return()=>controller.abort();
  },[search,page,attempt]);
  return <details><summary>从现有馆藏加入准确原文</summary><label>查找原文文字<input value={query} onChange={event=>setQuery(event.target.value)}/></label><button type="button" onClick={()=>{setSearch(query.trim());setPage(1);}}>查找</button>
    {error?<p role="alert">{error}<button type="button" onClick={()=>setAttempt(value=>value+1)}>重新读取</button></p>:search!==null&&!data?<p role="status">正在读取…</p>:null}
    {data?<><p>第 {page} 页 · 下列仅显示可绑定文档修订的证据段，馆内摘录不会冒充原文证据。</p>{data.results.filter(row=>row.source_type==="span").map(row=><article key={row.id}><strong>{row.work_title} · {row.edition_label} · PDF {row.page_start}</strong><blockquote>{row.text}</blockquote><p>{row.public_eligible?"当前可公开":"尚未公开，发布文章前须完成来源上架"}</p><button type="button" onClick={()=>onAdd({id:crypto.randomUUID(),type:"evidence",text:"",target:{type:"span",id:row.id,document_revision_id:row.document_revision_id || undefined},resolved_sources:[{...row,type:"span",title:row.work_title,document_revision_id:row.document_revision_id || undefined,page_start:row.page_start || undefined}]})}>编入原文</button></article>)}{!data.results.some(row=>row.source_type==="span")?<p>这一页没有可绑定的证据段，可换关键词或继续翻页。</p>:null}<nav><button type="button" disabled={!data.previous} onClick={()=>setPage(value=>value-1)}>上一页</button><button type="button" disabled={!data.next} onClick={()=>setPage(value=>value+1)}>下一页</button></nav></>:null}
  </details>;
}
export function ArticleBodyFields({blocks,onChange}:{blocks:IssueBlock[];onChange:(blocks:IssueBlock[])=>void}) {
  function update(index:number,patch:Partial<IssueBlock>){onChange(blocks.map((row,i)=>i===index?{...row,...patch}:row));}
  function move(index:number,delta:number){const rows=[...blocks];[rows[index],rows[index+delta]]=[rows[index+delta],rows[index]];onChange(rows);}
  return <><p>小标题生成文章或展项目录。原文区块绑定准确文档修订；图片展项须保留来源和文字说明。</p>{blocks.map((block,index)=><section className="issue-block-editor" key={block.id||index}>
    <label>内容类型<select value={block.type} disabled={!["paragraph","heading","quote","link"].includes(block.type)} onChange={event=>update(index,{type:event.target.value as IssueBlock["type"]})}>{!["paragraph","heading","quote","link"].includes(block.type)?<option value={block.type}>{block.type==="image"?"图像展项":"结构化来源区块（保留原身份）"}</option>:null}<option value="paragraph">段落</option><option value="heading">小标题 / 展项分组</option><option value="quote">注明出处的引文</option><option value="link">链接</option></select></label>
    <textarea aria-label={`正文第${index+1}项`} rows={4} value={block.text} onChange={event=>update(index,{text:event.target.value})}/>
    {block.type==="quote"||block.type==="link"||block.type==="image"?<label>{block.type==="link"?"链接地址":"真实出处"}<input value={(block.type==="link"?block.url:block.source)||""} onChange={event=>update(index,{[block.type==="link"?"url":"source"]:event.target.value})}/></label>:null}
    {block.type==="image"?<><label>图像文字说明<textarea value={block.alt_text||""} onChange={event=>update(index,{alt_text:event.target.value})}/></label><InlineMediaPicker onSelect={(id,url)=>update(index,{image_rendition_id:id,image_url:url})}/>{block.image_rendition_id?<button type="button" onClick={()=>update(index,{image_rendition_id:null,image_url:""})}>保留资料，移除图片</button>:null}</>:null}
    {block.resolved_sources?.map(source=><p key={`${source.type}:${source.id}`}>已绑定 {source.title}{source.printed_label?` · 书页 ${source.printed_label}`:""}</p>)}
    <div><button type="button" disabled={!index} onClick={()=>move(index,-1)}>上移</button><button type="button" disabled={index===blocks.length-1} onClick={()=>move(index,1)}>下移</button><button type="button" onClick={()=>onChange(blocks.filter((_,i)=>i!==index))}>移除区块</button></div>
  </section>)}<button type="button" className="button secondary" onClick={()=>onChange([...blocks,{id:crypto.randomUUID(),type:"paragraph",text:""}])}>添加正文段落</button><button type="button" className="button secondary" onClick={()=>onChange([...blocks,{id:crypto.randomUUID(),type:"image",text:"",source:"",alt_text:"",image_rendition_id:null}])}>添加图像展项</button><AddEvidence onAdd={block=>onChange([...blocks,block])}/></>;
}
