import { useId, useRef, useState, type FormEvent } from "react";
import { ArrowRight, BookOpen, Search, X } from "lucide-react";
import { submitSearchOnEnter } from "@/lib/search-submit-key";

export const queryCopy = [
  { name:"原文寻证", title:"从一个问题，读到原文。", description:"输入概念、问题或近似表述，查找馆内相关段落。", placeholder:"例如：礼物交换如何形成社会关系？", examples:["礼物交换如何形成社会关系？","民族认同如何形成？","社会秩序如何维持？"] },
  { name:"问题出发", title:"带着问题，重读经典。", description:"把你关心的现象写下来，从文献中寻找解释。", placeholder:"例如：为什么同样的制度，在不同地方产生不同结果？", examples:["为什么同样的制度产生不同结果？","市场如何改变乡村生活？","日常生活中的权力如何运作？"] },
  { name:"比较解释", title:"同一个问题，有哪些解释？", description:"查找不同文献中的论述，在原文中比较它们的联系与分歧。", placeholder:"例如：不同学者如何解释民族认同的形成？", examples:["不同学者如何解释民族认同？","礼物与商品有何不同？","阶级与地位如何影响社会分层？"] },
] as const;

export function QueryDirection({ direction, copyIndex, value, onChange, onSubmit }: {
  direction:"Q1"|"Q2"|"Q3"; copyIndex:number; value:string; onChange:(value:string)=>void; onSubmit:()=>void;
}) {
  const id=useId(), field=useRef<HTMLTextAreaElement>(null), copy=queryCopy[copyIndex];
  function submit(event:FormEvent) { event.preventDefault(); if(value.trim().length>=2) onSubmit(); }
  return <section className="query-direction" data-direction={direction} aria-label="观点检索">
    <header className="query-intro"><p>观点检索</p><h1>{copy.title}</h1><p>{copy.description}</p></header>
    <div className="query-compose">
      <form onSubmit={submit} className="query-sheet">
        <label htmlFor={id}><Search size={18}/><span>你想理解什么？</span></label>
        <div className="query-input"><textarea ref={field} id={id} name="q" aria-label="观点检索问题" value={value} onChange={e=>onChange(e.target.value)} placeholder={copy.placeholder} rows={direction==="Q2"?1:2} minLength={2} maxLength={500} required onKeyDown={submitSearchOnEnter} enterKeyHint="search"/>{value?<button type="button" className="icon" aria-label="清空问题" onClick={()=>{onChange("");field.current?.focus();}}><X size={17}/></button>:null}</div>
        <footer><span className="query-scope"><BookOpen size={16}/>馆内原文</span><span className="query-limit">{value.length}/500</span><button type="submit" className="button" disabled={value.trim().length<2}>查找原文<ArrowRight size={17}/></button></footer>
      </form>
      <div className="query-examples" aria-label="问题示例">{copy.examples.map(example=><button key={example} type="button" onClick={()=>{onChange(example);field.current?.focus();}}>{example}</button>)}</div>
    </div>
  </section>;
}

export function PreviewFacet({ title, options, selected, onChange }: {title:string;options:string[];selected:string[];onChange:(values:string[])=>void}) {
  // Local specimen values only; the live page uses its existing catalog facets.
  const [query,setQuery]=useState("");
  const matches=options.filter(option=>option.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  return <details className="facet"><summary><span>{title}{selected.length?` · ${selected.length}`:""}</span><span aria-hidden="true">⌄</span></summary>
    <label className="facet-search"><Search size={14}/><input type="search" aria-label={`搜索${title}`} placeholder={`搜索${title}`} value={query} onChange={event=>setQuery(event.target.value)}/></label>
    <div className="facet-values">{matches.map(option=><label key={option}><input type="checkbox" checked={selected.includes(option)} onChange={event=>onChange(event.target.checked?[...selected,option]:selected.filter(value=>value!==option))}/>{option}</label>)}{!matches.length?<p>{options.length?"没有匹配的选项":"当前示例没有可用选项"}</p>:null}</div>
  </details>;
}
