import React, {useEffect, useRef, useState} from 'react';
import {Check, ChevronDown, Search, X} from 'lucide-react';
import {fold, type FacetOption} from './search-model';

export function FacetPicker({title, options, selected, onChange}: {
  title: string; options: FacetOption[]; selected: string[]; onChange: (values: string[]) => void;
}) {
  const [query,setQuery] = useState('');
  const [open,setOpen] = useState(false);
  const details = useRef<HTMLDetailsElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const found = options.filter(option => fold(option.label).includes(fold(query)));
  function close(restore = false) {
    if (details.current) details.current.open = false;
    if (restore) details.current?.querySelector('summary')?.focus();
  }
  useEffect(() => {
    if (!open) return;
    input.current?.focus({preventScroll:true});
    const outside = (event: PointerEvent) => {if (!details.current?.contains(event.target as Node)) close();};
    document.addEventListener('pointerdown',outside);
    return () => document.removeEventListener('pointerdown',outside);
  },[open]);
  const names = selected.map(value => options.find(option => option.value === value)?.label || value);
  return <section className="searchable-facet">
    <div className="facet-label"><h3>{title}</h3>{selected.length>0&&<button aria-label={`清除${title}筛选`} onClick={()=>onChange([])}>清除</button>}</div>
    <details ref={details} className="facet-picker" onToggle={event=>setOpen(event.currentTarget.open)} onKeyDown={event=>{if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close(true);}}}>
      <summary aria-label={`${title}筛选`} title={names.join('、')}><span>{names.length ? `${names[0]}${names.length>1?` 等 ${names.length} 项`:''}` : `全部${title==='出版时间'?'年份':title}`}</span><ChevronDown size={15}/></summary>
      <div className="facet-menu">
        <label className="facet-search"><Search size={15}/><input ref={input} type="search" aria-label={`搜索${title}`} placeholder={`搜索${title}…`} value={query} onChange={event=>setQuery(event.target.value)}/>{query&&<button aria-label={`清空${title}搜索`} onClick={()=>{setQuery('');input.current?.focus();}}><X size={14}/></button>}</label>
        <div className="facet-matches">{found.map(option=><label key={option.value} className={selected.includes(option.value)?'is-chosen':''}><input type="checkbox" checked={selected.includes(option.value)} onChange={()=>onChange(selected.includes(option.value)?selected.filter(value=>value!==option.value):[...selected,option.value])}/><span>{option.label}</span><small>{option.count}</small></label>)}
          {!found.length&&<p className="facet-empty">{options.length?'没有匹配选项':'当前资料没有可用选项'}</p>}
        </div>
        <div className="facet-menu-footer"><span>{selected.length?`已选 ${selected.length} 项`:`${found.length} 个选项`}</span><button onClick={()=>close(true)}><Check size={14}/>完成</button></div>
      </div>
    </details>
  </section>;
}
