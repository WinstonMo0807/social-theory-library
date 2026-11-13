"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, BookOpen, Search, X } from "lucide-react";
import { submitSearchOnEnter } from "@/lib/search-submit-key";
import styles from "./s4-search.module.css";

export function S4SearchRoute({mode,initialQuery,href}:{mode:"original"|"viewpoint";initialQuery:string;href:string}) {
  const router=useRouter();
  return <S4Search mode={mode} initialQuery={initialQuery} onSearch={query=>{const url=new URL(href,location.origin);url.searchParams.set('q',query);url.searchParams.delete('page');router.push(url.pathname+'?'+url.searchParams);}}/>;
}

/** The accepted S4 surface; destinations keep their own filter contracts. */
export function S4Search({ mode, initialQuery = "", onSearch, children }: {
  mode: "original" | "viewpoint"; initialQuery?: string;
  onSearch: (query: string) => void; children?: React.ReactNode;
}) {
  const router = useRouter(), id = useId(), field = useRef<HTMLTextAreaElement>(null);
  const [value, setValue] = useState(initialQuery);
  const viewpoint = mode === "viewpoint";
  const examples = viewpoint ? ["礼物交换如何形成社会关系？", "民族认同如何形成？", "社会秩序如何维持？"] : ["民族互利", "社会运行", "地方社会"];
  function submit(event: FormEvent) { event.preventDefault(); if (value.trim().length >= 2) onSearch(value.trim()); }
  return <section className={styles.hero} data-mode={mode} aria-label="书库检索">
    <img className={styles.mark} src="/brand/stl-symbol-20261027.svg" alt=""/>
    <header><h1>{viewpoint ? "把问题写下来，从原文开始。" : "把那句话，放回它的语境。"}</h1><p>{viewpoint ? "带着你的问题，查找文献中的论述与解释。" : "输入题名、关键词或记得的句子，查找文献与原文。"}</p></header>
    <div className={styles.stack}><form onSubmit={submit} className={styles.form}>
      <nav className={styles.modes} aria-label="检索方式">{([['original','原文检索'],['viewpoint','观点检索']] as const).map(([key,label])=><button type="button" key={key} aria-pressed={mode===key} onClick={()=>{if(mode!==key)router.push(`/explore/${key==='original'?'original':'opinions'}?q=${encodeURIComponent(value)}`);}}>{key==='original'?<BookOpen size={19}/>:<Search size={19}/>}<span>{label}</span></button>)}</nav>
      <label htmlFor={id}>{viewpoint ? "你想理解什么？" : "你想寻找什么？"}</label>
      <div className={styles.input}><textarea id={id} ref={field} value={value} onChange={event=>setValue(event.target.value)} maxLength={500} minLength={2} required rows={2} placeholder={viewpoint?"例如：民族认同如何形成？":"输入关键词，或粘贴一段原文…"} onKeyDown={submitSearchOnEnter} enterKeyHint="search"/>{value&&<button type="button" aria-label="清空检索内容" onClick={()=>{setValue('');field.current?.focus();}}><X size={19}/></button>}</div>
      {children}<footer><small>回车检索 · Shift + 回车换行</small><span>{value.length}/500</span><button type="submit" className={styles.submit} disabled={value.trim().length<2}>{viewpoint?"查找相关原文":"检索原文"}<ArrowRight size={19}/></button></footer>
    </form></div>
    <div className={styles.examples}>{examples.map(example=><button type="button" key={example} onClick={()=>{setValue(example);field.current?.focus();}}>{example}<ArrowRight size={13}/></button>)}</div>
  </section>;
}
