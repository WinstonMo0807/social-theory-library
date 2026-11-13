import { useEffect, useRef, useState } from "react";
import { ArrowRight, BookOpen, Check, ChevronDown, ChevronUp, GitBranch, Layers, Minus, RotateCcw, X } from "lucide-react";
import { ReaderGrip, useReaderFloatingLayout } from "@/components/reader/reader-floating-controls";
import { submitSearchOnEnter } from "@/lib/search-submit-key";
import type { SearchMode } from "./motion-search";
import "./research-followup.css";

type ScopeChoice = "previous" | "passages" | "works" | "filtered" | "saved" | "library";
type ScopeSnapshot = { label: string; detail: string; materials: number[]; books?: string[]; filters?: string[]; valid: boolean };
type PreviewTurn = { question: string; parent: number | null; scope: ScopeSnapshot; context: number[] };
const materialTitle = (index: number) => index === 0 ? "民族互利与民族认同" : "民族问题的四个层面";
const materialText = (index: number) => index === 0 ? "如果没有民族互利，则是不实在的。所以，也可简要地说，民族团结就是民族互利与民族认同的有机统一、相互促进。" : "概括起来，民族问题主要有四个层面：政治层面、经济层面、文化层面和社会层面。";
// Both book records are visible in the user's supplied screenshots. Only the first has excerpt samples here.
const books = [
  {id:"social-theory",title:"社会运行论及其发展",author:"李强、洪大用 主编",year:"2020",publisher:"中国人民大学出版社"},
  {id:"argonauts",title:"西太平洋上的航海者",author:"布罗尼斯拉夫·马林诺夫斯基",year:"2016",publisher:"商务印书馆"},
];
const sessionKey="stl-excerpt-research-preview-v2";
type DemoSession={version:2;rounds:PreviewTurn[];parent:number;question:string;context:number[];chosenBooks:string[];scope:ScopeChoice};
const materialIds=(value:unknown):value is number[]=>Array.isArray(value)&&value.every(id=>id===0||id===1);
function readSession():DemoSession|null{
  try{const value=JSON.parse(sessionStorage.getItem(sessionKey)||"null");
    if(value?.version!==2||!Array.isArray(value.rounds)||!value.rounds.length||!Number.isInteger(value.parent)||value.parent<0||value.parent>=value.rounds.length||typeof value.question!=="string"||!materialIds(value.context)||!Array.isArray(value.chosenBooks)||!value.chosenBooks.every((id:unknown)=>books.some(book=>book.id===id))||!scopeOptions.some(([id])=>id===value.scope))return null;
    if(!value.rounds.every((turn:PreviewTurn,index:number)=>typeof turn.question==="string"&&(turn.parent===null||Number.isInteger(turn.parent)&&turn.parent>=0&&turn.parent<index)&&materialIds(turn.context)&&turn.scope&&typeof turn.scope.label==="string"&&typeof turn.scope.detail==="string"&&typeof turn.scope.valid==="boolean"&&materialIds(turn.scope.materials)))return null;
    return value;
  }catch{return null;}
}
const scopeOptions: [ScopeChoice, string, string][] = [
  ["previous", "沿用上轮", "保留所承接轮次的范围"],
  ["passages", "仅所选原文", "只使用下方勾选的段落"],
  ["works", "指定书籍", "在所选书籍中继续查找"],
  ["filtered", "当前检索范围", "沿用本页已应用的筛选"],
  ["saved", "本研究的选材", "使用已经收集的原文"],
  ["library", "全部馆藏", "扩展至当前账号可访问的馆藏"],
];

export function ResearchFollowup({ open, onClose, selected, seed, saved, query, filters, mode }: {
  open: boolean; onClose: () => void; selected: number; seed: number; saved: number[];
  query: string; filters: string[]; mode: SearchMode;
}) {
  const root = useRef<HTMLDivElement>(null), scopeMenu = useRef<HTMLDetailsElement>(null);
  const reset = useReaderFloatingLayout(root, "excerpt-followup-docked-preview", true), restored = useRef(readSession());
  const [minimized, setMinimized] = useState(false), [question, setQuestion] = useState(restored.current?.question||"");
  const [context, setContext] = useState<number[]>(restored.current?.context||[selected]), [scope, setScope] = useState<ScopeChoice>(restored.current?.scope||"passages");
  const [chosenBooks, setChosenBooks] = useState<string[]>(restored.current?.chosenBooks||["social-theory"]), [bookQuery,setBookQuery]=useState(""), [passageQuery,setPassageQuery]=useState("");
  const [message, setMessage] = useState(""), [storageAvailable,setStorageAvailable]=useState(true);
  const [rounds, setRounds] = useState<PreviewTurn[]>(restored.current?.rounds||[{question: query, parent: null, context: [], scope: {label:"当前检索范围",detail:filters.join(" · "),filters:[...filters],materials:[],valid:true}}]);
  const [parent, setParent] = useState(restored.current?.parent||0), [inspected,setInspected]=useState<number|null>(null);
  // Preview history survives reload in this tab only; it never writes to the real research API.
  useEffect(()=>{try{sessionStorage.setItem(sessionKey,JSON.stringify({version:2,rounds,parent,question,context,chosenBooks,scope}));setStorageAvailable(true);}catch{setStorageAvailable(false);}},[rounds,parent,question,context,chosenBooks,scope]);
  useEffect(()=>{if(open)root.current?.scrollIntoView({block:"nearest",behavior:"instant"});},[open,seed]);
  useEffect(() => { if (seed) {setContext([selected]);setScope("passages");setMinimized(false);} }, [seed]); // selected only changes context when the reader explicitly asks about a passage.
  useEffect(() => {
    const outside = (event: PointerEvent) => {if(scopeMenu.current && !scopeMenu.current.contains(event.target as Node)) scopeMenu.current.open=false;};
    const escape = (event: KeyboardEvent) => {if(event.key==="Escape" && scopeMenu.current?.open){scopeMenu.current.open=false;scopeMenu.current.querySelector("summary")?.focus();}};
    document.addEventListener("pointerdown",outside);document.addEventListener("keydown",escape);
    return () => {document.removeEventListener("pointerdown",outside);document.removeEventListener("keydown",escape);};
  }, []);
  const currentScope: ScopeSnapshot = scope === "previous" ? rounds[parent].scope
    : scope === "passages" ? {label:`仅所选原文 · ${context.length} 段`,detail:"不自动扩展到整书或全馆",materials:[...context],valid:context.length>0}
    : scope === "works" ? {label:`指定书籍 · ${chosenBooks.length} 部`,detail:books.filter(book=>chosenBooks.includes(book.id)).map(book=>book.title).join("、"),books:[...chosenBooks],materials:[],valid:chosenBooks.length>0}
    : scope === "filtered" ? {label:"当前检索范围",detail:filters.join(" · "),filters:[...filters],materials:[],valid:true}
    : scope === "saved" ? {label:`本研究的选材 · ${saved.length} 段`,detail:"使用本次预览已选用的原文，不纳入笔记内容",materials:[...saved],valid:saved.length>0}
    : {label:"全部馆藏",detail:"扩展至当前账号可访问且可检索的馆藏",materials:[],valid:true};
  const canSubmit = question.trim().length >= 2 && currentScope.valid;
  const toggleContext = (index:number) => setContext(value=>value.includes(index)?value.filter(n=>n!==index):[...value,index]);
  const matchingBooks=books.filter(book=>`${book.title} ${book.author} ${book.year}`.includes(bookQuery.trim()));
  const matchingPassages=[0,1].filter(index=>`${materialTitle(index)} ${materialText(index)}`.includes(passageQuery.trim()));
  const inspectedTurn=inspected===null?null:rounds[inspected];
  return <div ref={root} className="followup-layer" data-mode={mode} data-open={open||undefined} data-collapsed={minimized||undefined}>
    {open && <section className="research-followup" data-reader-float="followup" data-minimized={minimized||undefined} role="region" aria-label="连续研究追问组件">
      <header className="followup-title"><ReaderGrip label="继续追问" heading="继续追问"/><h2>继续追问</h2><small>承接第 {parent+1} 轮</small><button type="button" aria-label="追问组件复位" title="恢复默认位置" onClick={reset}><RotateCcw size={17}/></button><button type="button" aria-label={minimized?"展开追问组件":"收起追问组件"} onClick={()=>setMinimized(v=>!v)}>{minimized?<ChevronUp size={18}/>:<Minus size={18}/>}</button><button type="button" aria-label="关闭追问组件" onClick={onClose}><X size={18}/></button></header>
      {!minimized && <div className="followup-body">
        <details className="research-path"><summary><GitBranch size={15}/><span>研究路径 · {rounds.length} 轮</span><ChevronDown size={15}/></summary><ol>{rounds.map((round,index)=><li key={index}><button type="button" aria-current={parent===index?"step":undefined} aria-label={`回看第${index+1}轮`} onClick={()=>setInspected(index)}><b>{String(index+1).padStart(2,"0")}</b><span>{round.question}<small>{round.parent!==null&&round.parent!==index-1?`从第 ${round.parent+1} 轮分支 · `:""}{round.scope.label} · 参考 {round.context.length} 段</small></span>{parent===index?<Check size={14}/>:<GitBranch size={14}/>}</button></li>)}</ol>{inspectedTurn&&<section className="turn-snapshot" aria-label={`第${inspected!+1}轮记录`}><header><strong>第 {inspected!+1} 轮</strong><button type="button" aria-label="收起轮次记录" onClick={()=>setInspected(null)}><X size={15}/></button></header><p>{inspectedTurn.question}</p><dl><dt>当时的范围</dt><dd>{inspectedTurn.scope.label}<small>{inspectedTurn.scope.detail}</small></dd><dt>本轮选材</dt><dd>{inspectedTurn.context.length?inspectedTurn.context.map(index=><details key={index}><summary>原文 0{index+1} · {materialTitle(index)}</summary><blockquote>{materialText(index)}</blockquote><small>社会运行论及其发展 · 书页 316 / PDF 330</small></details>):"未附加原文"}</dd></dl><button type="button" className="quiet" onClick={()=>{setParent(inspected!);setScope("previous");setMessage(`下一轮将承接第 ${inspected!+1} 轮；原记录保持不变。`);}}><GitBranch size={15}/>从这一轮继续</button></section>}</details>
        <div className="followup-context"><span>本轮参考</span>{context.length?context.map(index=><button type="button" className="context-chip" key={index} aria-label={`本轮不使用原文${index+1}`} onClick={()=>toggleContext(index)}>原文 0{index+1}<X size={13}/></button>):<small>未选择原文</small>}<details><summary>选择原文 <ChevronDown size={13}/></summary><div className="context-picker"><input type="search" aria-label="查找可选原文" placeholder="查找原文文字…" value={passageQuery} onChange={event=>setPassageQuery(event.target.value)}/>{matchingPassages.map(index=><label key={index}><input type="checkbox" checked={context.includes(index)} onChange={()=>toggleContext(index)}/><span>原文 0{index+1} · {materialTitle(index)}<small>{materialText(index)}</small><small>社会运行论及其发展 · 书页 316 / PDF 330</small></span></label>)}{!matchingPassages.length&&<p>没有匹配的示例原文</p>}</div></details></div>
        <form onSubmit={event=>{event.preventDefault();if(!canSubmit)return;setRounds(value=>[...value,{question:question.trim(),parent,context:[...context],scope:{...currentScope,materials:[...currentScope.materials]}}]);setParent(rounds.length);setQuestion("");setMessage("已记录本轮预览，未发起真实研究。可展开研究路径核对范围。");}}>
          <label className="followup-question-label" htmlFor="followup-question">继续追问</label><textarea id="followup-question" aria-label="继续追问的问题" placeholder="基于这些原文，继续提出你的问题…" value={question} onChange={event=>setQuestion(event.target.value)} onKeyDown={submitSearchOnEnter} minLength={2} maxLength={1200} rows={2} enterKeyHint="send" required/>
          <div className="followup-scope"><details ref={scopeMenu} className="scope-menu"><summary><Layers size={16}/><span>{scope==="previous"?`沿用第 ${parent+1} 轮 · `:""}{currentScope.label}</span><ChevronDown size={16}/></summary><div className="scope-popover"><h3>本轮查找范围</h3><div className="scope-choices">{scopeOptions.map(([key,title,description])=><label key={key} data-checked={scope===key||undefined}><input type="radio" name="followup-scope" value={key} checked={scope===key} onChange={()=>{setScope(key);setMessage("");}}/><span>{title}<small>{description}</small></span>{scope===key&&<Check size={15}/>}</label>)}</div><div className="scope-details">{scope==="passages"?<>{[0,1].map(index=><label key={index}><input type="checkbox" checked={context.includes(index)} onChange={()=>toggleContext(index)}/><span>原文 0{index+1} · {materialTitle(index)}<small>书页 316 / PDF 330</small></span></label>)}</>:scope==="works"?<><input className="book-search" type="search" aria-label="查找指定书籍" placeholder="书名、作者或年份…" value={bookQuery} onChange={event=>setBookQuery(event.target.value)}/>{matchingBooks.map(book=><label key={book.id}><input type="checkbox" checked={chosenBooks.includes(book.id)} onChange={event=>setChosenBooks(value=>event.target.checked?[...value,book.id]:value.filter(id=>id!==book.id))}/><BookOpen size={17}/><span>{book.title}<small>{book.author} · {book.year}</small><small>{book.publisher}</small></span></label>)}{!matchingBooks.length&&<p>没有匹配的示例书目</p>}</>:<p>{currentScope.detail}</p>}</div><footer><span>{!currentScope.valid?"请先选择可用材料":currentScope.label}</span><button type="button" className="button" onClick={()=>{if(scopeMenu.current)scopeMenu.current.open=false;}}>完成</button></footer></div></details><button className="button followup-send" type="submit" disabled={!canSubmit}>继续研究<ArrowRight size={17}/></button></div>
          <p className={`scope-caption ${currentScope.valid?"":"scope-invalid"}`} role={currentScope.valid?undefined:"alert"}>{currentScope.valid?currentScope.detail:"范围为空，请选择材料；不会自动扩大检索范围。"}</p>
        </form>
        <footer className="followup-footnote"><span>{storageAvailable?"本页签保留预览 · 不同步到账号":"浏览器无法保留预览，请先复制问题"}</span><span>{question?"草稿未发送":""}</span></footer>
        {message&&<p className="followup-feedback" role="status">{message}</p>}
      </div>}
    </section>}
  </div>;
}
