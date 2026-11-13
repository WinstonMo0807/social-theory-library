"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowRight, ChevronDown, GitBranch, Minus, Plus, RotateCcw, X } from "lucide-react";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { ApiRequestError } from "@/lib/api";
import { withPrivateOwner, PrivateOwnerVerificationError } from "@/lib/api/private-owner";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { loadOpinionScope, type ScopeOption, type ScopePage } from "@/lib/api/opinion-entry.client";
import { cancelResearchTurn, createResearchProject, listResearchRecords, lookupResearchTurnRequest, sendResearchTurnCommand, type ProjectData, type QueryScope, type ResearchRecord, type ResearchTurnCommand, type ResolvedEvidence } from "@/lib/api/research.client";
import { researchEvidenceKey, researchEvidenceReference, researchScopeInput, researchScopeLabel, researchReaderHref } from "@/lib/api/research-evidence";
import type { DiscoveryFilters } from "@/lib/api/discovery.types";
import { ReaderGrip, useReaderFloatingLayout } from "@/components/reader/reader-floating-controls";
import { LoadingState } from "@/components/ui/loading-state";
import { SourceText } from "@/components/source-text";
import { useResearchProject } from "./use-research-project";
import { researchEvidenceLocation } from "./research-evidence-card";
import styles from "./search-research-dock.module.css";

type Props = { question: string; searchPhase?: 'idle'|'running'|'ready'|'empty'|'error'; filters?: DiscoveryFilters; filterLabel?: string; filterAvailable?: boolean; materials: ResolvedEvidence[]; seed?: { ref: ResolvedEvidence; serial: number }; onInspect?: (ref: ResolvedEvidence) => void };
const statusNames: Record<string,string>={queued:"已排队",running:"正在检索",completed:"已完成",partial:"部分完成",failed:"处理未完成",canceled:"已取消"};
const running=(status?:string)=>status==='running'||status==='queued';
const exactReference=(ref:ResolvedEvidence)=>({...researchEvidenceReference(ref),...(!ref.anchors?.length&&(ref.quote||ref.text)?{selected_text:ref.quote||ref.text}:{})});
const messageOf=(e:unknown)=>e instanceof Error?e.message:'请求未完成，请重试。';

export function SearchResearchDock(props: Props) {
  const {state:session,retry}=useSessionBootstrap(), owner=String(session.user?.id||'');
  if(session.status==='loading'||session.status==='unknown')return <div className={styles.sessionState}><LoadingState variant="compact">正在读取我的研究…</LoadingState></div>;
  if(session.status==='authenticated'&&owner)return <OwnedDock key={owner} {...props} owner={owner}/>;
  return <section className={styles.sessionState} aria-label="继续研究"><GitBranch size={18}/><strong>继续研究</strong>{session.status==='unauthenticated'?<a href={`/login?next=${encodeURIComponent(typeof location==='undefined'?'/explore/opinions':location.pathname+location.search)}`}>登录后保留问题与选材<ArrowRight size={16}/></a>:<><span>{session.message||'暂时无法读取研究状态'}</span><button type="button" onClick={retry}>重新读取</button></>}</section>;
}
function OwnedDock(props:Props&{owner:string}) {
  const region=useRef<HTMLElement>(null);
  const [open,setOpen]=useState(true),[projectId,setProjectId]=useState(''),[projects,setProjects]=useState<ResearchRecord<ProjectData>[]>([]);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[page,setPage]=useState(1),[more,setMore]=useState(false);
  const [title,setTitle]=useState(props.question.slice(0,240)||'新的研究'),[find,setFind]=useState('');
  const createAttempt=useRef<Parameters<typeof createResearchProject>[0]|null>(null), lock=useRef(false);
  const previousTitle=useRef(title);
  const phase=props.searchPhase||(props.question?'ready':'idle');
  useEffect(()=>{const next=props.question.slice(0,240)||'新的研究',previous=previousTitle.current;setTitle(old=>old===previous?next:old);previousTitle.current=next;setOpen(true);},[props.question]);
  useEffect(()=>{const id=new URLSearchParams(location.search).get('research');if(id&&/^[a-f0-9-]{36}$/i.test(id)){setProjectId(id);setOpen(true);}},[]);
  useEffect(()=>{if(!props.seed)return;setOpen(true);const frame=requestAnimationFrame(()=>region.current?.scrollIntoView({block:'start'}));return()=>cancelAnimationFrame(frame);},[props.seed]);
  useEffect(()=>{if(!open)return;const controller=new AbortController();void withPrivateOwner(props.owner,()=>listResearchRecords<ProjectData>('research-projects',page,controller.signal),controller.signal).then(data=>{if(!controller.signal.aborted){setProjects(old=>page===1?data.results:[...old,...data.results]);setMore(Boolean(data.next));}}).catch(reason=>{if(!controller.signal.aborted)setError(messageOf(reason));});return()=>controller.abort();},[open,page,props.owner]);
  function select(id:string){setProjectId(id);const url=new URL(location.href);if(id)url.searchParams.set('research',id);else url.searchParams.delete('research');history.replaceState(history.state,'',url);}
  async function create(){if(lock.current||!title.trim())return;lock.current=true;setBusy(true);setError('');
    const data=createAttempt.current||{request_id:createRequestKey(),expected_owner_id:Number(props.owner),title:title.trim(),question:props.question,scope:{kind:'filtered' as const,filters:props.filters||{}}};createAttempt.current=data;
    try{const next=await withPrivateOwner(props.owner,()=>createResearchProject(data));select(next.id);createAttempt.current=null;}
    catch(reason){setError(messageOf(reason));if(reason instanceof ApiRequestError&&!(reason instanceof PrivateOwnerVerificationError)&&[400,403,409,422].includes(reason.status))createAttempt.current=null;}
    finally{lock.current=false;setBusy(false);}}
  return <section ref={region} className={styles.workspace} aria-label="同页连续研究">
    {!open?<button type="button" className={styles.launch} onClick={()=>setOpen(true)}><GitBranch size={18}/>继续研究<ArrowRight size={17}/></button>:<>
      <div className={styles.projectBar}><strong><GitBranch size={17}/>继续研究</strong><label><span className="sr-only">我的研究</span><select aria-label="当前研究" disabled={busy} value={projectId} onChange={event=>select(event.target.value)}><option value="">新建或选择研究</option>{projectId&&!projects.some(row=>row.id===projectId)&&<option value={projectId}>当前研究</option>}{projects.filter(row=>!row.archived).map(row=><option key={row.id} value={row.id}>{row.data.title}</option>)}</select></label><button type="button" onClick={()=>setOpen(false)}>收起</button></div>
      <p className={styles.searchState} role="status">{phase==='running'?(props.materials.length?'正在检索，可先使用已找到的原文继续研究。':'正在检索，找到原文后可选择书籍或段落继续追问。'):phase==='idle'?'输入问题开始检索，或选择已有研究继续。':phase==='empty'?'本次未找到原文，可以调整问题或选择已有研究继续。':phase==='error'?'本次检索未完成，已有研究和选材仍保留。':props.materials.length?`本次已显示 ${props.materials.length} 段原文，可选入下一轮。`:'可限定当前作品，也可以选择其他书籍继续研究。'}</p>
      {error&&<p role="alert">{error}</p>}
      {projectId?<ResearchEditor key={projectId} {...props} id={projectId} onClose={()=>setOpen(false)}/>:<div className={styles.setup}>
        {(phase!=='idle'&&(phase!=='running'||props.materials.length>0)||props.seed)&&<div className={styles.createRow}><label><span className="sr-only">研究名称</span><input aria-label="研究名称" maxLength={240} value={title} disabled={busy||Boolean(createAttempt.current)} onChange={event=>setTitle(event.target.value)}/></label><button type="button" className="button" disabled={busy||!title.trim()} onClick={()=>void create()}><Plus size={17}/>{busy?'正在建立研究…':createAttempt.current?'重试原创建请求':'以此开始研究'}</button></div>}
        {(projects.length>0||more)&&<details className={styles.findProject}><summary>查找已有研究<ChevronDown size={15}/></summary><label><span className="sr-only">查找我的研究</span><input type="search" aria-label="查找我的研究" value={find} onChange={event=>setFind(event.target.value)}/></label><div className={styles.projectList}>{projects.filter(row=>!row.archived&&row.data.title.includes(find)).map(row=><button type="button" key={row.id} onClick={()=>select(row.id)}>{row.data.title}<ArrowRight size={15}/></button>)}</div>{more&&<button type="button" onClick={()=>setPage(p=>p+1)}>读取更多研究</button>}</details>}
      </div>}
    </>}
  </section>;
}

function ResearchEditor(props:Props&{id:string;owner:string;onClose:()=>void}) {
  const workspace=useResearchProject(props.id,true);
  if(!workspace.record)return <div role="status">{workspace.error?<><p>{workspace.error}</p><button onClick={workspace.refresh}>重新读取</button></>:<LoadingState>正在读取研究记录…</LoadingState>}</div>;
  return <ResearchEditorReady {...props} workspace={workspace}/>;
}
function ResearchEditorReady(props:Props&{id:string;owner:string;onClose:()=>void;workspace:ReturnType<typeof useResearchProject>}) {
  const workspace=props.workspace,{record,turns,pending,run,refresh}=workspace;
  const root=useRef<HTMLDivElement>(null),reset=useReaderFloatingLayout(root,`search:${props.owner}`,true);
  const [collapsed,setCollapsed]=useState(false),[question,setQuestion]=useState(''),[parent,setParent]=useState(''),[viewed,setViewed]=useState('');
  const [choice,setChoice]=useState('previous'),[context,setContext]=useState<ResolvedEvidence[]>(props.seed?[props.seed.ref]:[]),[bookRows,setBookRows]=useState<ScopeOption[]>([]),[passageQuery,setPassageQuery]=useState('');
  const [submission,setSubmission]=useState<ResearchTurnCommand|null>(null),[error,setError]=useState('');
  useUnsavedForm({question,unresolved:Boolean(submission)},{question:'',unresolved:false});
  useEffect(()=>{if(props.seed){setContext(old=>{if(old.some(row=>researchEvidenceKey(row)===researchEvidenceKey(props.seed!.ref)))return old;if(old.length>=20){setError('已选择 20 段，请先移除不需要的参考。');return old;}return [...old,props.seed!.ref];});setCollapsed(false);root.current?.scrollIntoView({block:'nearest'});}},[props.seed]);
  const parentTurn=turns.find(row=>row.id===parent)||turns.at(-1);
  const current=turns.find(row=>row.id===viewed)||turns.at(-1);
  const sources=[...props.materials,...(record?.data.selections||[]),...turns.flatMap(row=>[...(row.data.result_refs||[]),...(row.data.selected_refs||[])])];
  const options=Array.from(new Map([...sources,...context].map(row=>[researchEvidenceKey(row),row])).values());
  const scope:QueryScope=choice==='previous'?(parentTurn?.data.scope||{kind:'filtered',filters:props.filters||{}}):choice==='passages'?{kind:'passages',references:context.map(exactReference)}:choice==='works'?{kind:'works',filters:{work_ids:bookRows.map(row=>row.id)}}:choice==='saved'?{kind:'passages',references:(record?.data.selections||[]).map(researchEvidenceReference)}:choice==='filtered'?{kind:'filtered',filters:props.filters||{}}:{kind:'library'};
  const valid=scope.kind==='passages'?Boolean(scope.references?.length):scope.kind==='works'?Boolean(scope.filters?.work_ids?.length):scope.kind==='filtered'&&(!parentTurn||choice==='filtered')?props.filterAvailable!==false:true;
  const locked=pending||Boolean(submission)||turns.some(row=>running(row.status));
  async function send(command:ResearchTurnCommand){setError('');let nextId='';let rejected=false;const ok=await run(async()=>{try{const next=await sendResearchTurnCommand(command,props.owner);if(next.project_id!==props.id||next.request_id!==command.data.request_id)throw Error('原请求回执未能核对，请查询原请求。');nextId=next.id;}catch(reason){rejected=reason instanceof ApiRequestError&&!(reason instanceof PrivateOwnerVerificationError)&&reason.status>=400&&reason.status<500&&![408,429].includes(reason.status);throw reason;}},'本轮已保存，正在查找原文。');if(ok){setSubmission(null);setQuestion('');setParent(nextId);setViewed(nextId);setChoice('previous');}else if(rejected)setSubmission(null);}
  async function submit(){if(!record||locked||!valid||question.trim().length<2)return;const command:ResearchTurnCommand={projectId:props.id,data:{expected_revision:record.revision,request_id:createRequestKey(),question:question.trim(),scope:researchScopeInput(scope),mode:'search',...(parentTurn?{parent_id:parentTurn.id}:{}),context_refs:context.map(exactReference),return_context:{scope_labels:choice==="previous"?parentTurn?.data.return_context?.scope_labels:choice==="works"?bookRows.map(row=>row.title):undefined}}};setSubmission(command);await send(command);}
  async function lookup(){if(!submission)return;setError('');try{const found=await lookupResearchTurnRequest(props.id,submission.data.request_id,props.owner);if(found){setSubmission(null);setQuestion('');setParent(found.id);setViewed(found.id);refresh();}else setError('尚未查到原请求，可重试同一请求。');}catch(reason){setError(messageOf(reason));}}
  if(!record)return <div role="status">{workspace.error?<><p>{workspace.error}</p><button onClick={refresh}>重新读取</button></>:<LoadingState>正在读取研究记录…</LoadingState>}</div>;
  return <>
    <div className={styles.path}><details><summary><GitBranch size={16}/>研究路径 · {turns.length} 轮<ChevronDown size={15}/></summary><ol>{turns.map((turn,index)=><li key={turn.id}><button type="button" aria-current={current?.id===turn.id?'step':undefined} onClick={()=>setViewed(turn.id)}><b>{String(index+1).padStart(2,'0')}</b><span>{turn.data.question}<small>{statusNames[turn.status||'']||turn.status} · {researchScopeLabel(turn.data.scope)}{turn.parent_id&&turn.parent_id!==turns[index-1]?.id?` · 从第 ${turns.findIndex(row=>row.id===turn.parent_id)+1} 轮分支`:''}</small></span></button></li>)}</ol></details>
    {current&&<section className={styles.round}><header><h3>{current.data.question}</h3><button type="button" disabled={locked} onClick={()=>{setParent(current.id);setChoice('previous');setCollapsed(false);root.current?.scrollIntoView({block:'nearest'});}}>从这一轮继续</button></header><p role="status">{statusNames[current.status||'']||current.status}{current.error_code?' · 本轮未完成，已取得材料仍保留。':''}</p>
      <details><summary>本轮范围与选材</summary><p>{researchScopeLabel(current.data.scope)}</p>{Array.isArray(current.data.return_context?.scope_labels)?<p>{current.data.return_context.scope_labels.filter(value=>typeof value==='string').join('、')}</p>:Object.keys(current.data.scope.filters||{}).length>0?<p>已保留当时的 {Object.keys(current.data.scope.filters||{}).length} 组馆藏限制。</p>:null}{(current.data.scope.references||[]).map((ref,index)=><p key={index}>范围原文 {index+1} · PDF {ref.pdf_page||'原定位'}</p>)}{current.data.selected_refs?.length?current.data.selected_refs.map((ref,index)=><details key={researchEvidenceKey(ref)}><summary>参考 {index+1} · {ref.title||'来源待核对'} · {researchEvidenceLocation(ref)}</summary><SourceText text={ref.quote||''}/></details>):<p>未附加参考原文</p>}</details>
      {running(current.status)&&<button type="button" disabled={pending} onClick={()=>void run(()=>cancelResearchTurn(current.id),'本轮已取消，材料保留。')}>取消本轮</button>}
      <div className={styles.roundResults}>{(current.data.result_refs||[]).map((ref,index)=><article key={researchEvidenceKey(ref)}><header><h4>{ref.title||'来源待核对'}</h4><small>{researchEvidenceLocation(ref)}</small></header><SourceText text={ref.quote||ref.text||'原文暂不可用，请重新核对来源。'}/><footer>{researchReaderHref(ref,{projectId:props.id,turnId:current.id})&&<a className="button" href={researchReaderHref(ref,{projectId:props.id,turnId:current.id})}>在线阅读</a>}<button type="button" disabled={ref.source_status!=='available'} onClick={()=>props.onInspect?.(ref)}>引用</button><button type="button" disabled={context.length>=20||ref.source_status!=='available'||locked} onClick={()=>setContext(rows=>rows.some(row=>researchEvidenceKey(row)===researchEvidenceKey(ref))?rows:[...rows,ref])}>用于下一轮</button></footer></article>)}</div>
      {current.data.scope.kind==='passages'&&<p className={styles.muted}>本轮只保留所选原文，不扩大查找范围。</p>}
    </section>}
    </div>
    <div ref={root} className={styles.dock}><section className={styles.composer} data-reader-float="search-followup">
      <header className={styles.title}><ReaderGrip heading="继续追问" label="继续追问"/><strong className={styles.mobileHeading}>继续追问</strong><span>{parentTurn?`承接第 ${turns.indexOf(parentTurn)+1} 轮`:'新的问题'}</span><button type="button" aria-label="追问组件复位" onClick={reset}><RotateCcw size={17}/></button><button type="button" aria-label={collapsed?'展开追问':'收起追问'} onClick={()=>setCollapsed(value=>!value)}>{collapsed?<Plus size={17}/>:<Minus size={17}/>}</button><button type="button" aria-label="关闭追问" onClick={props.onClose}><X size={17}/></button></header>
      {!collapsed&&<div className={styles.body}><fieldset disabled={locked}><details><summary>本轮参考 · {context.length} 段<ChevronDown size={15}/></summary><input type="search" aria-label="查找可选原文" placeholder="查找原文或书名" value={passageQuery} onChange={event=>setPassageQuery(event.target.value)}/><div className={styles.options}>{options.filter(ref=>`${ref.title} ${ref.quote||ref.text||''}`.includes(passageQuery)).map(ref=>{const key=researchEvidenceKey(ref),checked=context.some(row=>researchEvidenceKey(row)===key);return <label key={key}><input type="checkbox" checked={checked} disabled={!checked&&(context.length>=20||ref.source_status!=='available')} onChange={event=>setContext(rows=>event.target.checked?[...rows,ref]:rows.filter(row=>researchEvidenceKey(row)!==key))}/><span>{ref.title||'来源待核对'}<small>{researchEvidenceLocation(ref)}</small><small><SourceText text={ref.quote||ref.text||''} compact/></small></span></label>;})}{!options.length&&<p>在检索结果中选择原文，或沿用研究已有选材。</p>}</div><small>最多参考 20 段；范围另行选择。</small></details>
      <label className={styles.question}>下一步想追问什么？<textarea value={question} onChange={event=>setQuestion(event.target.value)} maxLength={1200} rows={3} placeholder="沿着这些原文，继续你的问题…"/></label>
      <details className={styles.scope}><summary>{choice==='previous'?'沿用上轮':choice==='saved'?'本研究的选材':choice==='filtered'?(props.filterLabel||'当前筛选'):researchScopeLabel(scope)}<ChevronDown size={15}/></summary><div className={styles.choices}>{[['previous','沿用上轮'],['passages','仅所选原文'],['works','指定书籍'],['filtered',props.filterLabel||'当前筛选'],['saved','研究选材'],['library','全部馆藏']].map(([value,label])=><label key={value}><input type="radio" name={`scope-${props.id}`} value={value} checked={choice===value} onChange={()=>setChoice(value)}/>{label}</label>)}</div>{choice==='works'&&<BookPicker selected={bookRows} onChange={setBookRows}/>}<p>{scope.kind==='passages'?`限定 ${scope.references?.length||0} 段原文`:scope.kind==='works'?`限定 ${choice==='previous'?'上轮所选':bookRows.length+' 部'}作品`:choice==='previous'?'保留所承接轮次的范围':'使用当前选择的馆藏范围'}</p></details></fieldset>
      {(workspace.actionError||workspace.error||error)&&<p role="alert">{error||workspace.actionError||workspace.error}</p>}
      {submission?<div role="status"><p>原请求结果待核对，问题、范围和选材已固定。</p><button type="button" disabled={pending} onClick={()=>void lookup()}>查询原请求</button><button type="button" disabled={pending} onClick={()=>void send(submission)}>重试原请求</button></div>:<footer><small>{valid?'每轮记录保存到我的研究':'请先选择有效范围，不会自动扩大到全馆'}</small><button type="button" className="button" disabled={locked||!valid||question.trim().length<2} onClick={()=>void submit()}>{pending?'正在提交…':'继续研究'}<ArrowRight size={17}/></button></footer>}
      {workspace.notice&&<p role="status">{workspace.notice}</p>}{(workspace.pollPaused||workspace.error)&&<button type="button" onClick={refresh}>重新读取研究进度</button>}
      </div>}
    </section></div>
  </>;
}

function BookPicker({selected,onChange}:{selected:ScopeOption[];onChange:(rows:ScopeOption[])=>void}) {
  const [query,setQuery]=useState(''),[search,setSearch]=useState(''),[page,setPage]=useState(1),[data,setData]=useState<ScopePage|null>(null),[error,setError]=useState('');
  useEffect(()=>{const controller=new AbortController();setData(null);setError('');void loadOpinionScope('work',search,page,controller.signal).then(rows=>{if(!controller.signal.aborted)setData(rows);}).catch(reason=>{if(!controller.signal.aborted)setError(messageOf(reason));});return()=>controller.abort();},[search,page]);
  return <div className={styles.books}><div className={styles.find}><input type="search" placeholder="书名、作者或关键词" aria-label="查找限定书籍" value={query} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();setSearch(query.trim());setPage(1);}}}/><button type="button" onClick={()=>{setSearch(query.trim());setPage(1);}}>查找</button></div><div className={styles.selected}>{selected.map(row=><button type="button" key={row.id} onClick={()=>onChange(selected.filter(item=>item.id!==row.id))}>{row.title}<X size={12}/></button>)}</div>{error?<p role="alert">{error}</p>:!data?<LoadingState variant="compact">正在查找书籍…</LoadingState>:<><div className={styles.options}>{data.results.map(row=><label key={row.id}><input type="checkbox" checked={selected.some(item=>item.id===row.id)} disabled={selected.length>=30&&!selected.some(item=>item.id===row.id)} onChange={event=>onChange(event.target.checked?[...selected,row]:selected.filter(item=>item.id!==row.id))}/><span>{row.title}<small>{row.subtitle}</small></span></label>)}{!data.results.length&&<p>没有匹配的书籍</p>}</div><div className={styles.pages}><button type="button" disabled={page===1} onClick={()=>setPage(p=>p-1)}>上一页</button><span>{page}/{Math.max(1,data.total_pages)}</span><button type="button" disabled={page>=data.total_pages} onClick={()=>setPage(p=>p+1)}>下一页</button></div></>}</div>;
}
