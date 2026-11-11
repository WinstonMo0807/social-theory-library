import React, { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowDownWideNarrow, ArrowRight, BookOpen, Bookmark, Check, ChevronDown, Copy, ExternalLink, FileText, LayoutGrid, List, Quote, Search, SlidersHorizontal, Users, X } from 'lucide-react';
import './preview.css';

type Work = { id:string; title:string; author:string; year:string; topic:string; summary:string; href:string; reader:string; cover:string };
type Scholar = { title:string; href:string; summary:string; cover:string };
type Sample = { works:Work[]; scholars:Scholar[]; source:string; capturedAt:string };
type Direction = 'a'|'b'|'c';
const directions = {a:{title:'轻盈书房',description:'Apple Books · 空间与触感'},b:{title:'文献目录',description:'JSTOR · 清晰与秩序'},c:{title:'阅读工作台',description:'Semantic Scholar · 浏览与核对'}};
const external = {target:'_blank',rel:'noopener noreferrer'};
function Cover({work}:{work:Pick<Work,'title'|'author'|'cover'>}) {
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[work.cover]);
  return <div className="cover">{work.cover&&!failed?<img src={work.cover} alt={`${work.title}封面`} onError={()=>setFailed(true)}/>:<div className="cover-fallback"><span>社会理论书库</span><strong>{work.title}</strong><small>{work.author}</small><BookOpen size={28} strokeWidth={1}/></div>}</div>;
}
function Dialog({label,children,onClose,kind=''}:{label:string;children:React.ReactNode;onClose:()=>void;kind?:string}) {
  const ref=useRef<HTMLDialogElement>(null);
  useEffect(()=>{const d=ref.current!;const trigger=document.activeElement as HTMLElement|null;d.showModal();return()=>{d.close();requestAnimationFrame(()=>{if(trigger?.isConnected)trigger.focus({preventScroll:true});});};},[]);
  return <dialog ref={ref} className={`dialog ${kind}`} aria-label={label} onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===e.currentTarget)onClose();}}><div className="dialog-heading"><h2>{label}</h2><button className="icon-button" aria-label="关闭" onClick={onClose}><X/></button></div>{children}</dialog>;
}
function App({data}:{data:Sample}) {
  const initial=new URLSearchParams(location.search).get('v');
  const [direction,setDirection]=useState<Direction>(initial==='b'||initial==='c'?initial:'a');
  const [query,setQuery]=useState('');
  const [kind,setKind]=useState<'books'|'scholars'|'saved'>('books');
  const [authors,setAuthors]=useState<string[]>([]);
  const [period,setPeriod]=useState('all');
  const [sort,setSort]=useState('recent');
  const [view,setView]=useState<'grid'|'list'>('grid');
  const [saved,setSaved]=useState<string[]>([]);
  const [selected,setSelected]=useState(data.works[0]?.id||'');
  const [preview,setPreview]=useState<Work|null>(null);
  const [citation,setCitation]=useState<Work|null>(null);
  const [detailTab,setDetailTab]=useState('summary');
  const [filtersOpen,setFiltersOpen]=useState(false);
  const [toast,setToast]=useState('');
  const [showSources,setShowSources]=useState(false);
  const toastTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const searchRef=useRef<HTMLInputElement>(null);
  const filterGroupId=useId();
  function notify(text:string){setToast(text);if(toastTimer.current)clearTimeout(toastTimer.current);toastTimer.current=setTimeout(()=>setToast(''),2600);}
  function chooseDirection(value:Direction){setDirection(value);setPreview(null);setCitation(null);setFiltersOpen(false);history.replaceState(null,'',`?v=${value}`);}
  function save(work:Work){setSaved(old=>old.includes(work.id)?old.filter(x=>x!==work.id):[...old,work.id]);notify(saved.includes(work.id)?'已取消本地收藏':'已加入本地收藏');}
  function reset(){setAuthors([]);setPeriod('all');setQuery('');}
  const authorOptions=useMemo(()=>[...new Set(data.works.map(w=>w.author))].map(name=>({name,count:data.works.filter(w=>w.author===name).length})),[data]);
  const works=useMemo(()=>{
    const q=query.trim().toLocaleLowerCase();
    const rows=data.works.filter(w=>(kind!=='saved'||saved.includes(w.id))&&(!authors.length||authors.includes(w.author))&&(period==='all'||(period==='before'?+w.year<2000:+w.year>=2000))&&(!q||[w.title,w.author,w.summary,w.topic].join(' ').toLocaleLowerCase().includes(q)));
    return sort==='year'?[...rows].sort((a,b)=>+b.year-+a.year):sort==='title'?[...rows].sort((a,b)=>a.title.localeCompare(b.title,'zh-CN')):rows;
  },[data,query,authors,period,sort,kind,saved]);
  const scholars=data.scholars.filter(s=>[s.title,s.summary].join(' ').includes(query.trim()));
  const selectedWork=works.find(w=>w.id===selected)||works[0];
  const filterCount=authors.length+(period!=='all'?1:0);
  useEffect(()=>{function handler(e:KeyboardEvent){if(e.key==='/'&&!(e.target instanceof HTMLInputElement)&&!(e.target instanceof HTMLTextAreaElement)){e.preventDefault();searchRef.current?.focus();}}window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[]);
  function openPreview(work:Work){if(direction==='c'){setSelected(work.id);setDetailTab('summary');if(matchMedia('(max-width:1100px)').matches)setPreview(work);}else setPreview(work);}
  function openCitation(work:Work){if(direction==='c'&&!matchMedia('(max-width:1100px)').matches){setSelected(work.id);setDetailTab('citation');}else setCitation(work);}
  function citationText(w:Work){return `${w.author}. ${w.title}[M]. ${w.year}.`}
  async function copy(w:Work){try{await navigator.clipboard.writeText(citationText(w));notify('已复制简要书目信息');}catch{notify('复制未完成，请手动选取书目信息');}}
  function Citation({work}:{work:Work}){return <div className="citation-body"><p className="muted">简要书目信息</p><blockquote>{citationText(work)}</blockquote><p className="citation-note">依据当前列表中的作者、题名和年份。完整出版项与引用格式请在正式作品页核对。</p><div className="action-row"><button className="button primary" onClick={()=>copy(work)}><Copy size={16}/>复制书目信息</button><a className="button" href={`${work.href}#citation`} {...external}>完整引用<ExternalLink size={15}/></a></div></div>}
  function Actions({work,compact=false}:{work:Work;compact?:boolean}){return <div className={`actions ${compact?'compact':''}`}>
    {!compact&&work.reader&&<a className="button primary" href={work.reader} {...external}><BookOpen size={17}/>阅读 PDF</a>}
    <button className="button secondary" onClick={()=>openPreview(work)}><FileText size={16}/>预览</button>
    <button className="button secondary" onClick={()=>openCitation(work)}><Quote size={16}/>引用</button>
    <button className={`icon-button save ${saved.includes(work.id)?'saved':''}`} aria-label={`${saved.includes(work.id)?'取消收藏':'收藏'}《${work.title}》`} aria-pressed={saved.includes(work.id)} onClick={()=>save(work)}>{saved.includes(work.id)?<Check size={17}/>:<Bookmark size={17}/>}</button>
  </div>}
  function Details({work,modal=false}:{work:Work;modal?:boolean}){return <><div className="detail-identity"><Cover work={work}/><div><span className="muted">图书 · {work.year}</span><h2>{work.title}</h2><p>{work.author}</p></div></div><div className="detail-primary">{work.reader&&<a className="button primary" href={work.reader} {...external}><BookOpen size={18}/>阅读 PDF<ArrowRight size={16}/></a>}<button className="button" onClick={()=>save(work)}>{saved.includes(work.id)?<Check size={16}/>:<Bookmark size={16}/>} {saved.includes(work.id)?'已收藏':'收藏'}</button></div>
    {!modal&&<div className="detail-tabs" role="tablist" aria-label="作品资料"><button role="tab" aria-selected={detailTab==='summary'} onClick={()=>setDetailTab('summary')}>简介</button><button role="tab" aria-selected={detailTab==='citation'} onClick={()=>setDetailTab('citation')}>引用</button></div>}
    {detailTab==='citation'&&!modal?Citation({work}):<div className="detail-prose"><h3>关于这部作品</h3>{work.summary.split(/\n\s*\n/).filter(Boolean).map((p,i)=><p key={i}>{p}</p>)}<div className="detail-topic">{work.topic}</div><a className="text-link" href={work.href} {...external}>打开完整作品页<ExternalLink size={15}/></a></div>}</>}
  function Filters({mobile=false}={}){const periodGroup=`${filterGroupId}-${mobile?"mobile":"sidebar"}`;return <><div className="sidebar-heading"><h2><SlidersHorizontal size={17}/>筛选</h2><button className="text-button" onClick={reset} disabled={!filterCount&&!query}>重置</button></div>
    <div className="side-nav" aria-label="内容类型"><button className={kind==='books'?'current':''} onClick={()=>setKind('books')}><BookOpen size={18}/><span>图书</span><small>{data.works.length}</small></button><button className={kind==='scholars'?'current':''} onClick={()=>setKind('scholars')}><Users size={18}/><span>学者</span><small>{data.scholars.length}</small></button><button className={kind==='saved'?'current':''} onClick={()=>setKind('saved')}><Bookmark size={18}/><span>本地收藏</span><small>{saved.length}</small></button></div>
    {kind!=='scholars'&&<><details className="facet" open><summary>作者<ChevronDown size={15}/></summary><div className="facet-options">{authorOptions.map(({name,count})=><label key={name}><input type="checkbox" checked={authors.includes(name)} onChange={()=>setAuthors(a=>a.includes(name)?a.filter(x=>x!==name):[...a,name])}/><span>{name}</span><small>{count}</small></label>)}</div></details>
    <details className="facet" open><summary>出版时间<ChevronDown size={15}/></summary><div className="facet-options">{[['all','不限年份'],['after','2000 年及以后'],['before','2000 年以前']].map(([value,label])=><label key={value}><input name={periodGroup} type="radio" checked={period===value} onChange={()=>setPeriod(value)}/><span>{label}</span><small>{data.works.filter(w=>value==='all'||(value==='before'?+w.year<2000:+w.year>=2000)).length}</small></label>)}</div></details></>}
    <div className="sidebar-foot"><BookOpen size={18}/><p>回到作品，接近原文。</p><span>筛选即时生效</span></div></>}
  return <div className={`prototype direction-${direction}`}>
    <div className="preview-bar"><div className="preview-label"><span className="preview-dot"/>本地设计预览</div><nav aria-label="设计方案">{(['a','b','c'] as Direction[]).map(v=><button key={v} onClick={()=>chooseDirection(v)} aria-current={direction===v?'page':undefined}><b>{v.toUpperCase()}</b>{directions[v].title}</button>)}</nav><button className="reference-button" onClick={()=>setShowSources(true)}>设计参考<ExternalLink size={13}/></button></div>
    <header className="site-header"><a className="brand" href="https://books.winstonmo.com/home" {...external}><svg viewBox="12 17 230 154" aria-hidden="true"><use href="/brand/stl-symbol-20261027.svg#mark"/></svg><div><span>Social Theory Library</span><strong>社会理论书库</strong></div></a><nav aria-label="网站导航"><a className="active" href="#results">书库检索</a><a href="https://books.winstonmo.com/scholars" {...external}>学者</a><a href="https://books.winstonmo.com/theories" {...external}>理论流派</a><a href="https://books.winstonmo.com/topics" {...external}>主题</a></nav><span className="header-note">从问题出发，向原文求证</span></header>
    <div className="canvas"><section className="search-heading"><div><p className="section-label">书库检索</p><h1>{direction==='a'?'找到值得细读的作品':direction==='b'?'在文献中，展开问题。':'查找、浏览，继续阅读。'}</h1>{direction!=='c'&&<p className="intro">检索题名、作者与作品简介，让阅读从一条线索开始。</p>}</div><form className="search-box" role="search" onSubmit={e=>{e.preventDefault();searchRef.current?.blur();}}><Search size={21}/><input ref={searchRef} aria-label="搜索题名、作者或关键词" placeholder="搜索题名、作者或关键词" value={query} onChange={e=>setQuery(e.target.value)}/>{query?<button type="button" className="icon-button" aria-label="清空搜索" onClick={()=>setQuery('')}><X size={16}/></button>:<kbd>/</kbd>}<button className="search-submit" type="submit">搜索</button></form></section>
    <div className="workspace"><aside className="sidebar">{Filters()}</aside><main id="results" className="results">
    <div className="results-heading"><div><h2>{kind==='books'?'图书':kind==='scholars'?'学者':'本地收藏'}<span>{kind==='scholars'?scholars.length:works.length}</span></h2><span className="sample-note">{query?`“${query}”的匹配结果`:'当前公开资料样本'}</span></div><div className="toolbar"><button className="button mobile-filter" onClick={()=>setFiltersOpen(true)}><SlidersHorizontal size={16}/>筛选{filterCount>0&&<b>{filterCount}</b>}</button>{kind!=='scholars'&&<label className="sort"><ArrowDownWideNarrow size={16}/><select aria-label="排序方式" value={sort} onChange={e=>setSort(e.target.value)}><option value="recent">最新入库</option><option value="year">出版年份</option><option value="title">题名排序</option></select></label>}{direction==='a'&&kind!=='scholars'&&<div className="view-switch"><button aria-label="卡片视图" aria-pressed={view==='grid'} onClick={()=>setView('grid')}><LayoutGrid size={17}/></button><button aria-label="列表视图" aria-pressed={view==='list'} onClick={()=>setView('list')}><List size={18}/></button></div>}</div></div>
    {(filterCount>0||query)&&<div className="active-filters" aria-label="已选筛选">{authors.map(name=><button key={name} onClick={()=>setAuthors(a=>a.filter(x=>x!==name))}>{name}<X size={13}/></button>)}{period!=='all'&&<button onClick={()=>setPeriod('all')}>{period==='after'?'2000 年及以后':'2000 年以前'}<X size={13}/></button>}{query&&<button onClick={()=>setQuery('')}>{query}<X size={13}/></button>}<button className="clear-all" onClick={reset}>清除全部</button></div>}
    <div aria-live="polite" className="sr-only">找到{kind==='scholars'?scholars.length:works.length}条结果</div>
    {kind==='scholars'?<div className="scholar-list">{scholars.map(s=><article key={s.href}><img src={s.cover} alt={`${s.title}肖像`}/><div><h3>{s.title}</h3><p>{s.summary}</p><a className="button" href={s.href} {...external}>查看学者<ArrowRight size={16}/></a></div></article>)}</div>:<div className={`work-list ${view}`}>{works.map((work,i)=><article className={`work-card ${direction==='c'&&selectedWork?.id===work.id?'selected':''}`} key={work.id}>
      <button className="cover-button" onClick={()=>openPreview(work)} aria-label={`预览《${work.title}》`}><Cover work={work}/></button><div className="work-copy"><div className="work-topline"><span>{direction==='b'?String(i+1).padStart(2,'0'):'图书'}</span><span>{work.year}</span></div><h3><button onClick={()=>openPreview(work)}>{work.title}</button></h3><p className="author">{work.author}</p><p className="summary">{work.summary}</p><p className="topic">{work.topic}</p>{Actions({work,compact:direction==='c'})}</div></article>)}</div>}
    {(kind==='scholars'?scholars.length:works.length)===0&&<div className="empty"><Search size={30}/><h3>{kind==='saved'?'还没有收藏的作品':'没有匹配结果'}</h3><p>{kind==='saved'?'点击作品旁的书签，在这里集中查看。':'试试更短的关键词，或移除部分筛选条件。'}</p><button className="button" onClick={()=>{reset();if(kind==='saved')setKind('books')}}>{kind==='saved'?'浏览图书':'清除筛选'}</button></div>}
    <footer className="results-footer"><span>共 {kind==='scholars'?scholars.length:works.length} 条</span><span>样本内容来自已公开馆藏</span></footer>
    </main>{direction==='c'&&kind!=='scholars'&&selectedWork&&<aside className="detail-panel" aria-label="作品预览"><div className="detail-panel-heading"><span><FileText size={15}/>作品预览</span><span>无需离开结果</span></div>{Details({work:selectedWork})}</aside>}</div>
    <div className="prototype-note">本地样稿 · {data.works.length} 部图书、{data.scholars.length} 位学者 · 收藏仅在此页面演示；阅读链接打开正式书库。</div></div>
    {preview&&<Dialog label="作品预览" onClose={()=>setPreview(null)} kind="preview-dialog">{Details({work:preview,modal:true})}</Dialog>}
    {citation&&<Dialog label={`引用《${citation.title}》`} onClose={()=>setCitation(null)} kind="cite-dialog">{Citation({work:citation})}</Dialog>}
    {filtersOpen&&<Dialog label="筛选结果" onClose={()=>setFiltersOpen(false)} kind="filter-dialog">{Filters({mobile:true})}<button className="button primary filter-done" onClick={()=>setFiltersOpen(false)}>查看 {kind==='scholars'?scholars.length:works.length} 条结果<ArrowRight size={16}/></button></Dialog>}
    {showSources&&<Dialog label="三种检索体验" onClose={()=>setShowSources(false)} kind="sources-dialog"><div className="sources-content"><p>相同馆藏、相同筛选，不同的阅读节奏。</p><a href="https://www.apple.com/apple-books/" {...external}><b>A · 轻盈书房</b><span>参考 Apple Books 与 Apple HIG。清晰的侧栏、系统字体、柔和的内容层与即时按压反馈。</span><ExternalLink size={16}/></a><a href="https://support.jstor.org/hc/en-us/articles/4405598751255-Searching-Using-Filters-and-Facets" {...external}><b>B · 文献目录</b><span>参考 JSTOR 的筛选与结果组织。书名主导、摘要限宽、操作紧随内容。</span><ExternalLink size={16}/></a><a href="https://webflow.semanticscholar.org/product" {...external}><b>C · 阅读工作台</b><span>参考 Semantic Scholar 的浏览与引用操作，加入并排预览。选书时保留列表位置。</span><ExternalLink size={16}/></a><p>使用现有 React 和原生网页控件实现。借鉴 SwiftUI 的结构与反馈，无需更换技术栈。当前没有发布到公网。</p></div></Dialog>}
    {toast&&<div className="toast" role="status"><Check size={17}/>{toast}</div>}
  </div>;
}
fetch('/public-sample.json').then(r=>{if(!r.ok)throw new Error('资料样本读取失败');return r.json()}).then(data=>createRoot(document.getElementById('root')!).render(<App data={data}/>)).catch(()=>{document.getElementById('root')!.textContent='本地资料样本无法加载，请重新运行预览启动脚本。';});
