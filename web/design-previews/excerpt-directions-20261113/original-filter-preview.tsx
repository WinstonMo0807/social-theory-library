import { useState, type FormEvent } from "react";
import { ChevronDown } from "lucide-react";
import { FilterDropdown } from "./motion-search";

export type OriginalPreviewFilters = { kind:string; from:string; to:string; fields:string[]; facets:Record<string,string[]> };
export const originalDefaults:OriginalPreviewFilters={kind:"全部馆藏",from:"",to:"",fields:["题名","作者","关键词","摘要"],facets:{}};

/** Layout study of CatalogFilterFields, using only the two screenshot passages. */
export function OriginalFilterPreview({value,onApply}:{value:OriginalPreviewFilters;onApply:(value:OriginalPreviewFilters)=>void}){
  const [draft,setDraft]=useState(value),[error,setError]=useState("");
  function submit(event:FormEvent){event.preventDefault();if(draft.from&&draft.to&&Number(draft.from)>Number(draft.to)){setError("起始年份不能晚于截止年份。");return;}if(!draft.fields.length){setError("至少选择一个检索字段。");return;}setError("");onApply(draft);}
  const facet=(title:string,options:string[])=><FilterDropdown key={title} title={title} options={options} selected={draft.facets[title]||[]} onChange={values=>setDraft(v=>({...v,facets:{...v.facets,[title]:values}}))}/>;
  return <aside className="original-filter-panel" aria-label="原文检索筛选"><form onSubmit={submit}>
    <header><h2>筛选结果</h2><button type="button" className="quiet" onClick={()=>{setDraft(originalDefaults);onApply(originalDefaults);setError("");}}>清除</button></header>
    <fieldset className="original-scope"><legend>匹配范围</legend>{["全部馆藏","图书","期刊论文","学位论文","研究报告"].map(label=><label key={label}><input type="radio" name="original-document-type" checked={draft.kind===label} onChange={()=>setDraft(v=>({...v,kind:label}))}/><span>{label}</span><small>{["全部馆藏","图书"].includes(label)?1:0}</small></label>)}</fieldset>
    <fieldset className="original-years"><legend>年份</legend><div><input type="number" min="1" max="9999" aria-label="起始年份" placeholder="起始年" value={draft.from} onChange={e=>setDraft(v=>({...v,from:e.target.value}))}/><span>至</span><input type="number" min="1" max="9999" aria-label="截止年份" placeholder="截止年" value={draft.to} onChange={e=>setDraft(v=>({...v,to:e.target.value}))}/></div></fieldset>
    <div className="original-facets">{facet("语言",["中文"])}{facet("主题",[])}{facet("理论流派",[])}{facet("可获取性",["在线阅读"])}</div>
    <details className="original-advanced" open><summary>高级筛选<ChevronDown size={16}/></summary><fieldset><legend>检索字段</legend>{["题名","作者","关键词","摘要","全文"].map(label=><label key={label}><input type="checkbox" checked={draft.fields.includes(label)} onChange={e=>setDraft(v=>({...v,fields:e.target.checked?[...v.fields,label]:v.fields.filter(f=>f!==label)}))}/>{label}</label>)}</fieldset><div className="original-facets">{facet("材料类型",["图书"])}{facet("作者",["李强","洪大用"])}{facet("文献标签",[])}</div></details>
    {error&&<p role="alert" className="original-filter-error">{error}</p>}<button className="button original-filter-apply" type="submit">应用筛选</button>
  </form></aside>;
}
