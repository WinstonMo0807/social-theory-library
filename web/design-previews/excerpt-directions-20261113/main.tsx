/// <reference types="vite/client" />
import { StrictMode, useCallback, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { ArrowLeftRight, ArrowRight, Bookmark, Check, Copy, FolderPlus, List, LayoutGrid, RotateCcw, Search, SlidersHorizontal, X, Quote, PencilLine, Highlighter, Underline, ChevronDown } from "lucide-react";
import { SourceExcerpt } from "@/components/source-excerpt";
import { SourceText } from "@/components/source-text";
import { ReaderContextMenu, ReaderGrip, useReaderFloatingLayout } from "@/components/reader/reader-floating-controls";
import { LoadingState } from "@/components/ui/loading-state";
import "./preview.css";

const passages = [
  "社会运行论及其发展\n\n316\n\n如果没有民族互利，则是不实在的。所以，也可简要地说，民族\n\n团结就是民族互利与民族认同的有机统一、相互促进。”①\n\n针对中国社会目前面对的民族问题的实际，郑先生指出：“民\n\n族问题的核心实际上就是利益和价值的关系问题，这两个方面的\n\n问题在不同的层面上有不同的表现形式，同时也具有不同的特征。",
  "概括起来，民族问题主要有四个层面：政治层面、经济层面、文\n\n化层面和社会层面。”②可见，郑先生不仅强调民族互利和民族认\n\n同是民族团结的基础，而且对此做了全面、深入而具体的思考和\n\n回答。在中国社会的快速转型中，不仅形成了一种市场化经济和\n\n市场化社会，国家及地方政府的运行也不可能脱离市场化的现实。",
];
const citation = "[责任者待核对]. 社会运行论及其发展[M]. [出版地待核对]: 中国人民大学出版社, 2020: 316.";
const titles = { A:"核对与引用", B:"连续精读", C:"材料比较" };

function App(){
  const [variant,setVariant]=useState<"A"|"B"|"C">("A");
  const [selected,setSelected]=useState(0),[grid,setGrid]=useState(false),[query,setQuery]=useState("民族认同与社会整合");
  const [filter,setFilter]=useState(false),[filterQuery,setFilterQuery]=useState(""),[onlyOcr,setOnlyOcr]=useState(false);
  const [tab,setTab]=useState("引用"),[draft,setDraft]=useState(""),[notes,setNotes]=useState<string[]>([]),[materials,setMaterials]=useState<number[]>([]);
  const [selection,setSelection]=useState(""),[status,setStatus]=useState(""),[manualCopy,setManualCopy]=useState(false),[mark,setMark]=useState(false);
  const [menu,setMenu]=useState<{x:number;y:number}|null>(null);
  const closeMenu=useCallback(()=>setMenu(null),[]);
  const [showComponents,setShowComponents]=useState(false),[operation,setOperation]=useState("ready"),[sort,setSort]=useState("页码顺序");
  const root=useRef<HTMLDivElement>(null);const reset=useReaderFloatingLayout(root,"excerpt-design-preview");
  const rows=sort==="页码顺序"?[0,1]:[1,0];
  function addMaterial(){setMaterials(value=>value.includes(selected)?value:[...value,selected]);setStatus("已加入本次预览选材");setTab("研究");}
  async function copyCitation(){try{await navigator.clipboard.writeText(citation);setStatus("引用格式已复制");setManualCopy(false);}catch{setManualCopy(true);setStatus("请在右侧选中文字复制");}}
  function choose(next:typeof variant){reset();setVariant(next);setStatus("");}
  return <div className="design-root" ref={root} data-variant={variant}>
    <header className="masthead"><a href="https://books.winstonmo.com/home" className="brand"><img src="/brand/stl-symbol-20261027.svg" alt=""/><span><b>Social Theory Library</b><strong>社会理论书库</strong></span></a><nav aria-label="设计版本">{(["A","B","C"] as const).map(v=><button key={v} aria-pressed={variant===v} onClick={()=>choose(v)}>{v}<span>{titles[v]}</span></button>)}</nav><button className="quiet" onClick={()=>{reset();setStatus("组件已恢复默认版式");}}><RotateCcw size={16}/>组件复位</button></header>
    <main><div className="page-heading"><div><p>书库检索</p><h1>{variant==="A"?"在原文中，找到依据。":variant==="B"?"让阅读，回到文字。":"并置原文，继续研究。"}</h1></div><button className="quiet" onClick={()=>setShowComponents(v=>!v)} aria-expanded={showComponents}><SlidersHorizontal size={16}/>组件与反馈</button></div>
    <form className="searchbar" onSubmit={event=>{event.preventDefault();setStatus(query.trim()?`本地演示：保留当前两段原文，查询词为“${query.trim()}”`:"请输入检索内容");}}><Search size={21}/><input aria-label="检索内容" value={query} onChange={e=>setQuery(e.target.value)}/><button type="button" className="icon" aria-label="清空检索" onClick={()=>setQuery("")}><X size={17}/></button><button className="button" type="submit">检索<ArrowRight size={17}/></button></form>
    <div className="result-toolbar"><div className="result-tabs"><strong>原文检索</strong><span>2 段截图原文 · 交互预览</span></div><div><button className="quiet mobile-filter" onClick={()=>setFilter(v=>!v)} aria-expanded={filter}><SlidersHorizontal size={16}/>筛选</button><label className="sort">排序 <select value={sort} onChange={e=>setSort(e.target.value)}><option>页码顺序</option><option>页码倒序</option></select></label><div className="view-toggle"><button aria-label="列表视图" aria-pressed={!grid} onClick={()=>setGrid(false)}><List size={18}/></button><button aria-label="网格视图" aria-pressed={grid} onClick={()=>setGrid(true)}><LayoutGrid size={18}/></button></div></div></div>
    <div className="workspace">
      <aside className={`navigation ${filter?"is-open":""}`} data-reader-float="filters"><ReaderGrip label="检索导航" heading={variant==="A"?"筛选结果":"原文导航"}/>{variant==="A"?<div className="filter-content"><h2>内容类型</h2><label className="check"><input type="checkbox" checked={onlyOcr} onChange={e=>setOnlyOcr(e.target.checked)}/>包含 OCR 原文<span>2</span></label>{["作者","理论流派","研究专题","文献标签"].map(title=><details className="facet" key={title}><summary>{title}<ChevronDown size={15}/></summary><label className="facet-search"><Search size={14}/><input placeholder={`搜索${title}`} aria-label={`搜索${title}`} value={filterQuery} onChange={e=>setFilterQuery(e.target.value)}/></label><p>{filterQuery?"没有匹配项":"当前示例暂无可筛选项"}</p></details>)}<button className="quiet" onClick={()=>{setOnlyOcr(false);setFilterQuery("");}}>清除筛选</button></div>:<div className="passage-nav">{rows.map(i=><button key={i} aria-pressed={selected===i} onClick={()=>setSelected(i)}><small>原文 0{i+1}</small><strong>社会运行论及其发展</strong><span>书页 316 · PDF 330</span><p>{i===0?"民族互利与民族认同":"民族问题的不同层面"}</p></button>)}</div>}</aside>
      <section className={`results ${grid?"is-grid":""}`} aria-label="原文结果">{(variant==="B"?[selected]:rows).map(i=><article className={`paper ${selected===i?"selected":""}`} key={i} data-mark={mark&&selected===i||undefined} onClick={()=>setSelected(i)}>
        <header className="paper-heading"><span className="number">0{i+1}</span><div><h2>社会运行论及其发展</h2><p>责任者待核对 · 中国人民大学出版社 · 2020</p></div><button className="icon" aria-label={`选用第${i+1}段原文`} aria-pressed={materials.includes(i)} onClick={e=>{e.stopPropagation();setSelected(i);setMaterials(value=>value.includes(i)?value.filter(n=>n!==i):[...value,i]);}}>{materials.includes(i)?<Check size={19}/>:<Bookmark size={19}/>}</button></header>
        <div className="source-area" onContextMenu={event=>{if(event.shiftKey)return;event.preventDefault();setSelected(i);setMenu({x:event.clientX,y:event.clientY});}} onMouseUp={()=>{const value=window.getSelection()?.toString().trim();if(value)setSelection(value);}}><SourceExcerpt text={passages[i]} label={variant==="C"?(i===0?"本段原文":"同页相邻原文"):"原文节选 · OCR"} location="书页 316 · PDF 330" marginalia={["社会运行论及其发展","316"]}/></div>
        <footer className="paper-actions"><button className="button" onClick={e=>{e.stopPropagation();setStatus("此为截图排版预览；正式页面沿用原阅读器定位链接。");}}>在线阅读<ArrowRight size={16}/></button><button className="quiet" onClick={()=>{setSelected(i);setVariant("B");}}>展开原文</button><button className="quiet" onClick={()=>{setTab("引用");setStatus(`右侧已定位原文 0${i+1} 的出处`);}}><Quote size={15}/>引用</button><button className="quiet" onClick={()=>{setTab("笔记");setSelection(passages[i]);}}><PencilLine size={15}/>笔记</button></footer>
      </article>)}</section>
      <aside className="inspector" data-reader-float="research"><ReaderGrip label="出处与研究" heading="出处与研究"/><div className="inspector-tabs" role="group" aria-label="侧栏内容">{["引用","笔记","研究"].map(name=><button key={name} aria-pressed={tab===name} onClick={()=>setTab(name)}>{name}{name==="笔记"&&notes.length?` ${notes.length}`:""}</button>)}</div><div className="inspector-body">
        <section className="location"><span>当前出处</span><strong>书页 316 <i/> PDF 330</strong><p>社会运行论及其发展</p></section>
        <section className="citation"><h2>GB/T 7714—2025</h2><p>{citation}</p><small>书目信息尚缺责任者、出版地，示例待核对。</small><button className="quiet" onClick={()=>void copyCitation()}><Copy size={15}/>复制引用格式</button>{manualCopy?<textarea aria-label="手动复制引用" value={citation} readOnly onFocus={e=>e.currentTarget.select()}/>:null}</section>
        {tab==="引用"?<section className="source-tools"><h2>从这里继续</h2><button onClick={()=>setVariant("B")}>核对上下文<ArrowRight size={16}/></button><button onClick={addMaterial}>加入研究选材<FolderPlus size={16}/></button><button onClick={()=>setVariant("C")}>并置两段原文<ArrowLeftRight size={16}/></button></section>:null}
        {tab==="笔记"?<section className="notes"><h2>我的笔记</h2>{selection?<details><summary>所选原文</summary><SourceText text={selection}/></details>:null}<textarea aria-label="笔记内容" placeholder="记下理解、问题与联系…" value={draft} onChange={e=>setDraft(e.target.value)}/><button className="button" disabled={!draft.trim()} onClick={()=>{setNotes(v=>[...v,draft.trim()]);setDraft("");setStatus("笔记已保存在本次预览");}}>保存笔记</button>{notes.map((note,i)=><article key={i}><p>{note}</p><button className="quiet" onClick={()=>setNotes(v=>v.filter((_,n)=>n!==i))}>删除</button></article>)}</section>:null}
        {tab==="研究"?<section className="materials"><h2>本次选材 · {materials.length}</h2>{materials.length?materials.map(i=><article key={i}><span>原文 0{i+1}<small>书页 316 · PDF 330</small></span><button className="icon" aria-label={`移除原文${i+1}`} onClick={()=>setMaterials(v=>v.filter(n=>n!==i))}><X size={16}/></button></article>):<p>选用原文后，会在这里保留出处。</p>}<button className="button" onClick={addMaterial}><FolderPlus size={16}/>加入当前原文</button></section>:null}
      </div></aside>
    </div>
    {selection?<div className="selection-tools" data-reader-float="selection"><ReaderGrip label="选段工具"/>{[["引用",Quote],["高亮",Highlighter],["划线",Underline],["笔记",PencilLine],["选材",FolderPlus]].map(([label,Icon])=>{const ToolIcon=Icon as typeof Quote;return <button key={String(label)} onClick={()=>{if(label==="引用")setTab("引用");else if(label==="笔记")setTab("笔记");else if(label==="选材")addMaterial();else {setMark(v=>!v);setStatus("当前原文已切换演示标记");}}}><ToolIcon size={17}/>{String(label)}</button>})}<button aria-label="关闭选段工具" onClick={()=>setSelection("")}><X size={16}/></button></div>:null}
    {showComponents?<section className="component-shelf"><header><h2>同一套组件，不同场景</h2><button className="icon" aria-label="关闭组件面板" onClick={()=>setShowComponents(false)}><X size={18}/></button></header><div className="component-grid"><section><h3>操作反馈</h3><div className="state-buttons"><button className="button" disabled={operation==="pending"} aria-busy={operation==="pending"} onClick={()=>{setOperation("pending");window.setTimeout(()=>setOperation("success"),800);}}>{operation==="pending"?"保存中…":operation==="success"?"已保存（演示）":"保存演示"}</button><button className="button secondary" onClick={()=>setOperation("error")}>查看失败状态</button><button className="button secondary" disabled>尚未选文</button></div>{operation==="error"?<p role="alert">未保存，内容仍保留。<button className="quiet" onClick={()=>setOperation("ready")}>重试</button></p>:null}</section><section><h3>局部加载</h3><LoadingState variant="compact">正在核对出处…</LoadingState></section><section><h3>组件规则</h3><p>短把手与整个标题区可拖动；支持方向键微调。窄屏回到文档流。右上角可复位。</p></section></div></section>:null}
    {menu?<ReaderContextMenu {...menu} close={closeMenu} pageLabel="书页 316 · PDF 330" actions={[{label:"查看引用格式",icon:<Quote size={17}/>,run:()=>setTab("引用")},{label:"添加笔记",icon:<PencilLine size={17}/>,run:()=>setTab("笔记")},{label:"加入当前选材",icon:<FolderPlus size={17}/>,run:addMaterial},{label:"并置原文",icon:<ArrowLeftRight size={17}/>,run:()=>setVariant("C"),group:true}]}/>:null}
    <p className="preview-note">设计与交互参考。原文来自用户截图，示例笔记、选材仅保存在本页；页面刷新后清空。</p></main>
    {status?<div className="notice" role="status"><span>{status}</span><button aria-label="关闭提示" onClick={()=>setStatus("")}><X size={16}/></button></div>:null}
  </div>;
}
const previewRoot = import.meta.hot?.data.root ?? createRoot(document.getElementById("root")!);
if (import.meta.hot) import.meta.hot.data.root = previewRoot;
previewRoot.render(<StrictMode><App/></StrictMode>);
