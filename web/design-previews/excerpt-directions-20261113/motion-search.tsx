import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ArrowDown, ArrowRight, BookOpen, Check, ChevronDown, CornerDownLeft, ListFilter, RotateCcw, Search, X } from "lucide-react";
import { submitSearchOnEnter } from "@/lib/search-submit-key";
import "./motion-search.css";

export const searchSchemes = [
  { id: "S1", name: "打开一本书", motion: "书页舒展 · 书脊亮起", navigator: "rail" },
  { id: "S2", name: "悬浮检索舱", motion: "搜索舱抬升 · 焦点扩展", navigator: "dropdown" },
  { id: "S3", name: "黑金扉页", motion: "黑金分幕 · 标识入场", navigator: "rail" },
  { id: "S4", name: "问题卡叠层", motion: "纸卡归位 · 输入层浮起", navigator: "strip" },
  { id: "S5", name: "原文长卷", motion: "金线铺开 · 字段展开", navigator: "dropdown" },
  { id: "S6", name: "从问题到原文", motion: "双栏接续 · 路径显现", navigator: "strip" },
] as const;
export type SearchScheme = typeof searchSchemes[number]["id"];
export type SearchMode = "original" | "viewpoint";
const headings = {
  S1: ["打开原文，\n找到那一句。", "翻开书，\n让问题深入。"],
  S2: ["让记得的文字，\n找到它的出处。", "一个问题，\n通向更多原文。"],
  S3: ["原文，\n就在这里。", "好的问题，\n值得回到原文。"],
  S4: ["把那句话，\n放回它的语境。", "把问题写下来，\n从原文开始。"],
  S5: ["循着文字，找到出处。", "循着问题，深入原文。"],
  S6: ["从一句话，\n回到一本书。", "从一个问题，\n读到不同解释。"],
};

export function MotionSearch({ scheme, mode, onMode, value, onChange, onSubmit }: {
  scheme: SearchScheme; mode: SearchMode; onMode: (mode: SearchMode) => void;
  value: string; onChange: (value: string) => void; onSubmit: () => void;
}) {
  const fieldId = useId(), input = useRef<HTMLTextAreaElement>(null);
  const [replay, setReplay] = useState(0), [submitted, setSubmitted] = useState(0);
  const viewpoint = mode === "viewpoint";
  const examples = viewpoint ? ["礼物交换如何形成社会关系？", "民族认同如何形成？", "社会秩序如何维持？"] : ["民族互利", "民族问题的四个层面", "社会运行"];
  const submit = (event: FormEvent) => { event.preventDefault(); if (value.trim().length < 2) return; setSubmitted(n => n + 1); onSubmit(); };
  return <section className="motion-search" data-scheme={scheme} data-mode={mode} key={`${scheme}-${replay}`} aria-label={`${scheme} 检索框`}>
    <div className="search-art" aria-hidden="true"><img src="/brand/stl-symbol-20261027.svg" alt=""/></div>
    <header className="motion-heading"><p>{viewpoint ? "观点检索" : "原文检索"}</p><h1>{headings[scheme][viewpoint ? 1 : 0]}</h1><p className="search-description">{viewpoint ? "带着你的问题，查找文献中的论述与解释。" : "输入关键词或记得的句子，定位原文及所在书页。"}</p></header>
    <div className="motion-composer"><form onSubmit={submit} className="motion-form">
      <div className="search-mode" role="group" aria-label="检索方式"><span className="mode-indicator" aria-hidden="true"/>{([["original", "原文检索"], ["viewpoint", "观点检索"]] as const).map(([id,label]) => <button type="button" key={id} aria-pressed={mode === id} onClick={() => onMode(id)}>{id === "original" ? <BookOpen size={16}/> : <Search size={16}/>}<span>{label}</span></button>)}</div>
      <label className="motion-label" htmlFor={fieldId}>{viewpoint ? "你想理解什么？" : "你想寻找哪段文字？"}</label>
      <div className="motion-input"><textarea id={fieldId} ref={input} value={value} onChange={e=>onChange(e.target.value)} aria-label={viewpoint ? "观点检索问题" : "原文检索文字"} rows={2} minLength={2} maxLength={500} required onKeyDown={submitSearchOnEnter} enterKeyHint="search" placeholder={viewpoint ? "例如：民族认同如何形成？" : "输入关键词，或粘贴一段原文…"}/>{value && <button type="button" className="icon" aria-label="清空检索内容" onClick={()=>{onChange("");input.current?.focus();}}><X size={18}/></button>}</div>
      <footer><span className="search-key"><CornerDownLeft size={15}/> 回车检索</span><span className="search-counter">{value.length}/500</span><button type="submit" className="search-submit" disabled={value.trim().length<2}>{viewpoint ? "查找相关原文" : "检索原文"}<ArrowRight size={20}/></button></footer>
      {submitted > 0 && <span key={submitted} className="submit-trace" aria-hidden="true"/>}
    </form><div className="motion-examples"><span>{viewpoint ? "试着问" : "试着找"}</span>{examples.map(example=><button type="button" key={example} onClick={()=>{onChange(example);input.current?.focus();}}>{example}<ArrowRight size={13}/></button>)}</div></div>
    <div className="search-destination"><span className="destination-rule"/><BookOpen size={25}/><strong>{viewpoint ? "在原文中比较解释" : "在书页中核对文字"}</strong><p>{viewpoint ? "保留出处，再展开你的研究。" : "书名、版本与页码一起保留。"}<br/>阅读 · 引用 · 笔记 · 研究</p><ArrowDown size={24}/></div>
    <button className="replay-motion" type="button" aria-label="重播检索框动效" onClick={()=>setReplay(n=>n+1)}><RotateCcw size={14}/><span>重播动效</span></button>
  </section>;
}

export function FilterDropdown({ title, options, selected, onChange }: {title: string; options: string[]; selected: string[]; onChange: (values: string[])=>void}) {
  const root = useRef<HTMLDetailsElement>(null), [query,setQuery]=useState("");
  useEffect(()=>{
    const outside=(event:PointerEvent)=>{if(root.current && !root.current.contains(event.target as Node))root.current.open=false;};
    const escape=(event:KeyboardEvent)=>{if(event.key==="Escape" && root.current?.open){root.current.open=false;root.current.querySelector("summary")?.focus();}};
    document.addEventListener("pointerdown",outside);document.addEventListener("keydown",escape);
    return()=>{document.removeEventListener("pointerdown",outside);document.removeEventListener("keydown",escape);};
  },[]);
  const matches=options.filter(option=>option.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  return <details className="filter-dropdown" ref={root} name="preview-search-filters"><summary>{title}{selected.length>0&&<b>{selected.length}</b>}<ChevronDown size={14}/></summary><div className="filter-popover"><label className="filter-search"><Search size={16}/><input aria-label={`搜索${title}`} placeholder={`搜索${title}…`} value={query} onChange={e=>setQuery(e.target.value)}/></label><div className="filter-options">{matches.length?matches.map(option=><label key={option}><input type="checkbox" checked={selected.includes(option)} onChange={e=>onChange(e.target.checked?[...selected,option]:selected.filter(v=>v!==option))}/><span>{option}</span>{selected.includes(option)&&<Check size={14}/>}</label>):<p>{options.length?"没有匹配项":"示例中没有可用选项"}</p>}</div>{selected.length>0&&<button className="quiet" onClick={()=>onChange([])}>清除此项</button>}</div></details>;
}

export function ResultJump({ presentation, rows, selected, onSelect, query, onQuery, onlySaved, onOnlySaved, saved }: {
  presentation:"rail"|"dropdown"|"strip"; rows:number[]; selected:number; onSelect:(index:number)=>void;
  query:string; onQuery:(value:string)=>void; onlySaved:boolean; onOnlySaved:(value:boolean)=>void; saved:number[];
}) {
  const [open,setOpen]=useState(false),root=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    const close=(e:PointerEvent)=>{if(root.current&&!root.current.contains(e.target as Node))setOpen(false);};
    const escape=(e:KeyboardEvent)=>{if(e.key==="Escape"&&open){setOpen(false);root.current?.querySelector<HTMLButtonElement>(".jump-disclosure")?.focus();}};
    document.addEventListener("pointerdown",close);document.addEventListener("keydown",escape);
    return()=>{document.removeEventListener("pointerdown",close);document.removeEventListener("keydown",escape);};
  },[open]);
  return <div className="result-jump" ref={root} data-presentation={presentation} data-open={open||undefined}>
    <button className="jump-disclosure" aria-expanded={open} onClick={()=>setOpen(v=>!v)}><ListFilter size={17}/><strong>结果快速跳转</strong><span>{rows.length} 段</span><ChevronDown size={16}/></button>
    <div className="jump-content"><header><h2>结果快速跳转 <span>{rows.length}</span></h2></header><div className="jump-tools"><label><Search size={16}/><input aria-label="在结果中检索" placeholder="在结果中检索…" value={query} onChange={e=>onQuery(e.target.value)}/>{query&&<button aria-label="清空结果内搜索" onClick={()=>onQuery("")}><X size={15}/></button>}</label><select aria-label="快速跳转范围" value={onlySaved?"saved":"all"} onChange={e=>onOnlySaved(e.target.value==="saved")}><option value="all">全部原文</option><option value="saved">已选用的原文（{saved.length}）</option></select></div>
      <nav aria-label="原文快速跳转">{rows.map(i=><button key={i} aria-current={selected===i?"true":undefined} onClick={()=>{onSelect(i);setOpen(false);}}><span className="jump-number">0{i+1}</span><span><strong>社会运行论及其发展</strong><span className="jump-topic">{i===0?"民族互利与民族认同":"民族问题的四个层面"}</span><small>李强、洪大用 · 2020<br/>书页 316 · PDF 330</small></span><ArrowRight size={15}/></button>)}</nav>{rows.length===0&&<p className="jump-empty">没有匹配的原文<button className="quiet" onClick={()=>{onQuery("");onOnlySaved(false);}}>清除跳转筛选</button></p>}
    </div>
  </div>;
}
