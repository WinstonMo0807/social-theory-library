import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowLeft, ArrowRight, Play, Pause, RotateCcw, Maximize2, Minimize2, Download, X, Search, BookOpen, ScanText, Network, Library, ShieldCheck, Layers, FileText, Database, Workflow, SlidersHorizontal, ChevronRight, ExternalLink, Video, Square, Check, CircleHelp } from 'lucide-react';
import { BrandImage } from '../components/brand-image';
import { Button } from '../components/ui/controls';
import { Dialog } from '../components/ui/dialog';
import data from './architecture.json';
import { scenes, overview, technology, sitemapGroups, workflowSteps, type Placement } from './scenes';
import { exportFrame, download, recordPresentation } from './export';
import './style.css';

type Node = typeof data.nodes[number];
const byId = Object.fromEntries(data.nodes.map(n=>[n.id,n])) as Record<string,Node>;
const sources = data.sources as Record<string,{file:string,line:number,anchor:string,sha256:string,kind:string}>;
const icons:Record<string,React.ElementType>={stl:Library,discovery:Search,knowledge:Network,reader:BookOpen,research:ScanText,publishing:Layers,operations:SlidersHorizontal,web:Layers,django:Workflow,postgres:Database,redis:Workflow,meili:Search,'models-runtime':Network,'ocr-runtime':ScanText,files:Library};
const sceneIcons=[Network,Layers,ScanText,Database,SlidersHorizontal,Check];
const STAGE_MS=4200;

function SourceList({ids}:{ids:string[]}) { return <ul className="source-list">{ids.map(id=>{const r=sources[id];return <li key={id}><span>{r.kind==='record'?'项目记录':'源码依据'}</span><code>{r.file}:{r.line}</code><small>{r.anchor}</small></li>})}</ul> }

function Graph({layout,scene,stage,selected,onSelect}:{layout:Placement[],scene:string,stage:number,selected:string|null,onSelect:(id:string)=>void}) {
 const visibleIds=new Set(layout.map(p=>p.id));
 const edges=data.edges.filter(e=>visibleIds.has(e.source)&&visibleIds.has(e.target));
 const nodePositions=Object.fromEntries(layout.map(p=>[p.id,{...p,w:p.w??278,h:p.h??118}]));
 const related=new Set(selected?[selected,...data.edges.filter(e=>e.source===selected||e.target===selected).flatMap(e=>[e.source,e.target])]:[]);
 const focus=selected?nodePositions[selected]:null;
 const camera=focus?`translate(${230-(focus.x+focus.w/2)*.94}px, ${254-(focus.y+focus.h/2)*.94}px) scale(.94)`:'translate(0px, 0px) scale(1)';
 return <div className={`graph ${selected?'has-focus':''}`}>
  <div className="graph-camera" style={{transform:camera}}>
   <svg className="connections" viewBox="0 0 1200 500" aria-hidden="true">
    <defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 9 5 L 0 9" fill="none" stroke="currentColor" strokeWidth="1.3"/></marker></defs>
    {edges.map((e,i)=>{const a=nodePositions[e.source],b=nodePositions[e.target];const right=b.x>=a.x;let x1=right?a.x+a.w:a.x,x2=right?b.x:b.x+b.w,y1=a.y+a.h/2,y2=b.y+b.h/2;
      const d=`M${x1},${y1} C${x1+(x2-x1)*.52},${y1} ${x1+(x2-x1)*.48},${y2} ${x2},${y2}`;
      const active=stage>=Math.max(a.reveal??0,b.reveal??0);const dim=selected&&e.source!==selected&&e.target!==selected;
      return <g key={e.source+e.target} className={`edge edge-${e.type} ${active?'active':''} ${dim?'dim':''}`}><path className="edge-track" d={d}/><path className="edge-draw" d={d} pathLength="1" markerEnd={e.type==='contains'?undefined:'url(#arrow)'}/>{scene==='technology'&&active&&<text x={(x1+x2)/2} y={(y1+y2)/2-12} textAnchor="middle">{e.label}</text>}</g>;
    })}
   </svg>
   {layout.map(p=>{const n=byId[p.id];const Icon=icons[p.id]||FileText;const active=stage>=(p.reveal??0);const root=p.id==='stl';return <Button key={p.id} data-node={p.id} className={`graph-node ${root?'root-node':''} ${active?'revealed':''} ${selected===p.id?'selected':''} ${selected&&!related.has(p.id)?'dim':''}`} style={{transform:`translate(${p.x}px, ${p.y}px)`,width:p.w??278,height:p.h??118}} onClick={()=>onSelect(p.id)} aria-label={`查看${n.title}详情`}>
     {root?<><BrandImage/><span className="root-caption">内容、原文与研究共同连接</span></>:<><span className="node-top"><Icon size={21} strokeWidth={1.45}/><span>{n.type==='domain'?`${n.children.length} 个功能组`:n.type==='store'?'数据职责':'实现模块'}</span><ChevronRight size={15}/></span><strong>{n.title}</strong><span className="node-subtitle">{n.subtitle}</span></>}
    </Button>})}
  </div>
  {!selected&&<div className="graph-legend">{scene==='overview'?<><i className="legend-line belongs"/>功能归属<span>点击任一模块，展开内部结构</span></>:<><i className="legend-line"/>服务调用<i className="legend-line data-line"/>数据读写<span>箭头表示实际调用方向</span></>}</div>}
 </div>
}

function Details({id,onClose,onSelect}:{id:string,onClose:()=>void,onSelect:(id:string)=>void}) {
 const n=byId[id];return <aside className="details" aria-label={`${n.title}详情`}>
  <header><span>模块详情</span><Button autoFocus onClick={onClose} aria-label="返回全局视图"><X size={22}/></Button></header>
  <h2>{n.title}</h2><p className="detail-subtitle">{n.subtitle}</p>
  <span className={`status-pill ${n.status}`}>{data.statuses[n.status as keyof typeof data.statuses]}</span>
  <div className="detail-scroll">
   {n.children.length>0&&<div className="child-list">{n.children.map(child=><Button key={child} onClick={()=>onSelect(child)}><span>{byId[child].title}<small>{byId[child].subtitle}</small></span><ChevronRight size={17}/></Button>)}</div>}
   {n.note&&<p>{n.note}</p>}{n.boundary&&<p className="boundary"><ShieldCheck size={18}/>{n.boundary}</p>}
   {n.routes.length>0&&<div className="detail-routes">{n.routes.map(route=><code key={route}>{route}</code>)}</div>}
   <h3>可追溯依据</h3><SourceList ids={n.sources}/>
  </div>
 </aside>
}

function Sitemap({stage,onSelect,onInventory}:{stage:number,onSelect:(id:string)=>void,onInventory:()=>void}) {
 return <div className="sitemap-view"><div className="map-root"><BrandImage/><span>同一网站 · 分层授权</span><Button onClick={onInventory}>查看 {data.routes.length} 个路由文件 <ArrowRight size={16}/></Button></div><div className="sitemap-columns">{sitemapGroups.map((group,i)=><section key={group.title} className={`map-group ${stage>=group.reveal?'revealed':''}`}><div className="group-stem"/><header><span>{group.access}</span><h2>{group.title}</h2></header>{group.items.map(([name,route,id])=><Button key={name} onClick={()=>onSelect(id)}><strong>{name}</strong><small>{route}</small><ChevronRight size={16}/></Button>)}</section>)}</div><p className="canvas-footnote">分组表示使用与访问关系。完整清单同时保留兼容路由、预览路由及暂停模块，不将它们计作新的产品能力。</p></div>
}

function WorkflowScene({stage,onSelect}:{stage:number,onSelect:(id:string)=>void}) {
 const step=workflowSteps[stage];return <div className="workflow-view"><div className="flow-steps">{workflowSteps.map((s,i)=><React.Fragment key={s.id}>{i>0&&<div className={`flow-connector ${stage>=i?'active':''}`}><span>{workflowSteps[i-1].output}</span><div><i/></div></div>}<Button className={`flow-step ${stage>=i?'revealed':''} ${stage===i?'current':''}`} onClick={()=>onSelect(s.id)}><span className="flow-number">0{i+1}</span><h2>{s.title}</h2><p>{s.action}</p><small>{byId[s.id].title}</small></Button></React.Fragment>)}</div>
  <div className="flow-stage-detail"><div><span className="detail-kicker">当前交接</span><h2>{step.output}</h2><p>{scenes[2].notes[stage]}</p><Button className="text-button" onClick={()=>onSelect(step.id)}>展开模块与来源 <ArrowRight size={17}/></Button></div><div className="evidence-object"><div className="object-head"><FileText size={20}/><span>{stage<2?'原文证据的定位结构':'引用沿用同一原文身份'}</span></div>{[['作品与版本','Work · Edition'],['文档版本','DocumentRevision'],['原文位置','EvidenceSpan · PDF page'],['访问资格','当前来源与读者会话']].map(([name,value],i)=><div key={name} className={i<=stage?'active':''}><span>{name}</span><strong>{value}</strong></div>)}<small>结构示意，未放入任何虚构引文或私人资料。</small></div></div>
 </div>
}

function DesignScene({stage,onSelect}:{stage:number,onSelect:(id:string)=>void}) {
 return <div className="design-view"><section className="design-brand"><BrandImage/><div className="type-example"><span>字里行间，思想相连。</span><p>宋体标题 · 黑体正文与操作</p></div><div className="swatches">{[['#F7F4EE','纸白'],['#FFFFFF','内容白'],['#1B1B18','炭黑'],['#D6D1C7','暖灰'],['#CC9847','品牌金']].map(([hex,name])=><div key={hex}><i style={{background:hex}}/><span>{name}</span><small>{hex}</small></div>)}</div><Button className="text-button" onClick={()=>onSelect('design-tokens')}>查看品牌与设计变量 <ArrowRight size={16}/></Button></section>
  <section className={`design-components ${stage>=1?'revealed':''}`}><header><span>共用组件</span><h2>熟悉的操作，一致的反馈。</h2></header><div className="component-sample"><Button onClick={()=>onSelect('design-controls')} className="sample-primary">查看原文 <ArrowRight size={18}/></Button><Button onClick={()=>onSelect('design-controls')} className="sample-secondary">保存到研究</Button><div className="sample-search"><Search size={18}/><span>作品、学者、概念与主题</span></div><div className="sample-state"><Check size={16}/> 来源状态与操作反馈</div></div><div className="component-chain"><Button onClick={()=>onSelect('design-controls')}>基础控件</Button><ChevronRight size={16}/><Button onClick={()=>onSelect('design-shells')}>页头与工作框架</Button></div><small>按钮直接复用仓库 Button；品牌直接复用 BrandImage。</small></section>
  <section className={`design-pages ${stage>=2?'revealed':''}`}><div className="page-thumbnail"><img src="/site/home.png" alt="本次匿名访问的 STL 首页实拍" onError={e=>{e.currentTarget.hidden=true}}/></div><div><span>真实页面观察</span><h2>内容与界面，保持同一气质。</h2><p>公共浏览、原文阅读和管理工作台，基于各自任务组合共用组件。</p><Button className="text-button" onClick={()=>onSelect('design-pages')}>查看页面组合依据 <ArrowRight size={16}/></Button></div></section>
 </div>
}

function StatusScene({stage,onSelect}:{stage:number,onSelect:(id:string)=>void}) {
 const observed=data.runtime.filter(r=>r.status===200);return <div className="status-view"><section className="status-column verified"><span className="status-heading"><Check size={18}/>限定范围已验证</span><h2>本次实际观察</h2><p>匿名 GET、页面渲染与访问跳转</p><div className="observed-list">{observed.slice(0,7).map(r=><div key={r.route}><code>{r.route}</code><span>{r.destination==='/login'?'跳转登录':'页面已渲染'}</span></div>)}</div><small>不是检索、OCR 或私人研究全链验收。</small></section>
  <section className={`status-column ${stage>=1?'revealed':''}`}><span className="status-heading"><Layers size={18}/>已实现 · 待验收</span><h2>有代码，也有边界</h2><p>路由、组件、接口与数据结构可追溯</p>{['discovery','reader','research','outline'].map(id=><Button key={id} onClick={()=>onSelect(id)}><span>{byId[id].title}</span><ChevronRight size={17}/></Button>)}<small>项目记录的 206 个范围内视图仍为 B；文件数量不是可用性评分。</small></section>
  <section className={`status-column partial ${stage>=2?'revealed':''}`}><span className="status-heading"><CircleHelp size={18}/>部分实现 / 未闭环</span><h2>明确保留的缺口</h2><p>具体能力单独标记，不重开整个模块</p>{['private-ai','oauth'].map(id=><Button key={id} onClick={()=>onSelect(id)}><span>{byId[id].title}<small>{id==='outline'?'自动样本复核尚未完成':id==='private-ai'?'真实中转尚未配置与调用':'入口禁用，回调未实现'}</small></span><ChevronRight size={17}/></Button>)}<small>政策研究暂停；RAG / LLMWiki 方向未定。不展示为已交付能力。</small></section>
 </div>
}

function EvidenceDialog({open,onClose}:{open:boolean,onClose:()=>void}) {
 const [query,setQuery]=useState('');const [tab,setTab]=useState('nodes');
 const nodes=data.nodes.filter(n=>`${n.title} ${n.id} ${n.sources.map(s=>sources[s].file)}`.toLowerCase().includes(query.toLowerCase()));
 const routes=data.routes.filter(r=>`${r.route} ${r.file} ${r.group}`.toLowerCase().includes(query.toLowerCase()));
 return <Dialog open={open} onRequestClose={onClose} className="evidence-dialog" aria-labelledby="evidence-title"><header><div><span>可维护的架构快照</span><h2 id="evidence-title">每一个节点，都有出处。</h2></div><Button onClick={onClose} aria-label="关闭来源索引"><X/></Button></header><div className="evidence-tools"><div className="evidence-tabs"><Button aria-pressed={tab==='nodes'} onClick={()=>setTab('nodes')}>模块 {data.nodes.length}</Button><Button aria-pressed={tab==='routes'} onClick={()=>setTab('routes')}>路由 {data.routes.length}</Button></div><label><Search size={18}/><input placeholder="搜索模块、路径或源码" value={query} onChange={e=>setQuery(e.target.value)}/></label><a href="/architecture.json" download>JSON</a><a href="/evidence-index.csv" download>CSV</a></div><p className="evidence-scope">审计基于 {data.commit} 及当时未提交的工作区。每条源码保存行号与 SHA-256；更新脚本会检查锚点漂移。</p><div className="evidence-results">{tab==='nodes'?nodes.map(n=><article key={n.id}><header><h3>{n.title}</h3><span>{data.statuses[n.status as keyof typeof data.statuses]}</span></header><SourceList ids={n.sources}/></article>):routes.map(r=><article key={r.route}><header><code>{r.route}</code><span>{r.group}</span></header><code>{r.file}</code><p>直接引用：{r.imports.filter(s=>s.startsWith('@/components')).join('、')||'本路由无直接组件导入；参见源码及父级布局。'}</p></article>)}{(tab==='nodes'?nodes:routes).length===0&&<p>没有匹配的模块或路径。</p>}</div></Dialog>
}

function App(){
 const params=new URLSearchParams(location.search);const initial=Math.max(0,Math.min(5,Number(params.get('scene'))||0));
 const [scene,setScene]=useState(initial),[stage,setStage]=useState(Math.max(0,Math.min(scenes[initial].stages.length-1,Number(params.get('stage'))||0))),[playing,setPlaying]=useState(false),[selected,setSelected]=useState<string|null>(null),[indexOpen,setIndexOpen]=useState(false),[help,setHelp]=useState(false),[exportOpen,setExportOpen]=useState(false),[full,setFull]=useState(false),[busy,setBusy]=useState(''),[toast,setToast]=useState(''),[recording,setRecording]=useState(false),[scale,setScale]=useState(1),[replayKey,setReplayKey]=useState(0);
 const [reduced,setReduced]=useState(matchMedia('(prefers-reduced-motion: reduce)').matches);
 const viewport=useRef<HTMLDivElement>(null),frame=useRef<HTMLDivElement>(null),timer=useRef<ReturnType<typeof setTimeout>|null>(null),remaining=useRef(STAGE_MS),started=useRef(0),recorder=useRef<Awaited<ReturnType<typeof recordPresentation>>|null>(null);
 const s=scenes[scene];const maxStage=s.stages.length-1;
 function notify(message:string){setToast(message);}
 function selectNode(id:string){settleMotion();setSelected(id);setPlaying(false);}
 function settleMotion(){frame.current?.getAnimations({subtree:true}).forEach(a=>{try{a.finish()}catch{a.cancel()}});}
 function togglePlay(){if(reduced)return;if(playing){frame.current?.getAnimations({subtree:true}).forEach(a=>a.pause());setPlaying(false);}else{frame.current?.getAnimations({subtree:true}).forEach(a=>a.play());if(stage===maxStage){setStage(0);remaining.current=STAGE_MS;}setPlaying(true);}}
 function changeScene(next:number){settleMotion();setPlaying(false);setSelected(null);setStage(0);setScene(Math.max(0,Math.min(scenes.length-1,next)));remaining.current=STAGE_MS;}
 function next(){settleMotion();setPlaying(false);if(stage<maxStage)setStage(stage+1);else if(scene<scenes.length-1)changeScene(scene+1);}
 function prev(){settleMotion();setPlaying(false);if(stage>0)setStage(stage-1);else if(scene>0){setScene(scene-1);setStage(scenes[scene-1].stages.length-1);setSelected(null);}}
 function replay(){settleMotion();setSelected(null);remaining.current=STAGE_MS;setReplayKey(k=>k+1);setPlaying(false);}
 async function fullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await viewport.current?.requestFullscreen();}catch{notify('浏览器未允许全屏，请使用浏览器全屏功能。');}}
 async function exportImage(kind:'png'|'svg'){setExportOpen(false);setPlaying(false);setBusy(kind);try{await exportFrame(frame.current!,`STL-${s.id}`,kind);notify(kind==='png'?'3840 × 2160 图片已导出':'独立 SVG 画面已导出');}catch(e){notify(`导出未完成：${e instanceof Error?e.message:'请重试'}`);}finally{setBusy('');}}
 async function record(){setExportOpen(false);setPlaying(false);try{if(recording){recorder.current?.stop();return;}recorder.current=await recordPresentation(()=>{setRecording(false);notify('录制已结束，WebM 已保存。');});setRecording(true);notify('正在录制。请手动推进，完成后点击停止。');}catch(e){notify('录制未启动。请选择本展示标签页并允许共享。');}}
 useEffect(()=>{const mq=matchMedia('(prefers-reduced-motion: reduce)');const update=()=>{setReduced(mq.matches);if(mq.matches)setPlaying(false)};mq.addEventListener('change',update);return()=>mq.removeEventListener('change',update);},[]);
 useEffect(()=>{const update=()=>{const rect=viewport.current?.getBoundingClientRect();if(rect)setScale(Math.min(rect.width/1600,rect.height/900));};const observer=new ResizeObserver(update);if(viewport.current)observer.observe(viewport.current);update();return()=>observer.disconnect();},[]);
 useEffect(()=>{const fn=()=>setFull(Boolean(document.fullscreenElement));document.addEventListener('fullscreenchange',fn);return()=>document.removeEventListener('fullscreenchange',fn);},[]);
 useEffect(()=>{if(reduced)return;for(const el of frame.current?.querySelectorAll('.scene-intro,.scene-canvas')??[])el.animate([{opacity:.25,transform:'translateY(7px)'},{opacity:1,transform:'translateY(0)'}],{duration:260,easing:'cubic-bezier(.22,1,.36,1)'});},[scene,replayKey]);
 useEffect(()=>{remaining.current=STAGE_MS;},[scene,stage,replayKey]);
 useEffect(()=>{if(!playing||reduced||indexOpen||help||selected)return;started.current=performance.now();timer.current=setTimeout(()=>{remaining.current=STAGE_MS;if(stage<maxStage)setStage(v=>v+1);else setPlaying(false);},remaining.current);return()=>{if(timer.current)clearTimeout(timer.current);remaining.current=Math.max(100,remaining.current-(performance.now()-started.current));};},[playing,stage,scene,reduced,indexOpen,help,selected,replayKey]);
 useEffect(()=>{const fn=()=>{if(document.hidden)setPlaying(false)};document.addEventListener('visibilitychange',fn);return()=>document.removeEventListener('visibilitychange',fn);},[]);
 useEffect(()=>{if(!toast)return;const t=setTimeout(()=>setToast(''),4800);return()=>clearTimeout(t);},[toast]);
 useEffect(()=>{const fn=(e:KeyboardEvent)=>{if(e.ctrlKey||e.altKey||e.metaKey||e.target instanceof HTMLInputElement||e.target instanceof HTMLTextAreaElement)return;if(indexOpen||help)return;if(e.key==='Escape'){setSelected(null);setExportOpen(false);return;}if(e.key==='ArrowRight'){e.preventDefault();next();}if(e.key==='ArrowLeft'){e.preventDefault();prev();}if(e.code==='Space'&&!(e.target instanceof HTMLButtonElement)){e.preventDefault();togglePlay();}if(e.key.toLowerCase()==='f'){e.preventDefault();void fullscreen();}if(e.key.toLowerCase()==='r'){e.preventDefault();replay();}if(/^[1-6]$/.test(e.key))changeScene(Number(e.key)-1);};window.addEventListener('keydown',fn);return()=>window.removeEventListener('keydown',fn);});
 const graphScene=scene===0||scene===3;
 return <div className="viewport" ref={viewport}>
  <div ref={frame} className={`presentation ${playing?'playing':'paused'} ${reduced?'reduced':''}`} style={{transform:`translate(-50%,-50%) scale(${scale})`}} data-scene={s.id} data-stage={stage}>
   <header className="masthead"><BrandImage/><div className="presentation-title">架构映像 <span>STL 4.0</span></div><div className="header-actions no-export"><Button onClick={()=>{setIndexOpen(true);setPlaying(false)}}><FileText size={17}/>来源索引</Button><div className="export-anchor"><Button disabled={!!busy} aria-expanded={exportOpen} onClick={()=>setExportOpen(v=>!v)}><Download size={17}/>{busy?'正在导出':'导出'}<ChevronRight size={14}/></Button>{exportOpen&&<div className="export-menu"><Button onClick={()=>void exportImage('png')}>PNG <small>3840 × 2160 · PPT</small></Button><Button onClick={()=>void exportImage('svg')}>SVG <small>独立静态画面</small></Button><Button onClick={()=>void record()}>{recording?'停止录制':'录制演示'}<small>选择此标签页 · WebM</small></Button></div>}</div><Button aria-label={full?'退出全屏':'全屏展示'} onClick={()=>void fullscreen()}>{full?<Minimize2 size={19}/>:<Maximize2 size={19}/>}</Button></div></header>
   <aside className="scene-nav"><div className="nav-heading">探索书库的构成</div><nav aria-label="展示场景">{scenes.map((item,i)=>{const Icon=sceneIcons[i];return <Button key={item.id} aria-current={scene===i?'step':undefined} onClick={()=>changeScene(i)}><span className="scene-number">0{i+1}</span><Icon size={18}/><span>{item.name}</span>{scene===i&&<span className="nav-active"/>}</Button>})}</nav><div className="nav-bottom"><span className="live-dot"/>工作区架构快照<small>2026.11.06<br/>源码与实际页面为依据</small><Button className="no-export" onClick={()=>setHelp(true)}><CircleHelp size={16}/>演示操作</Button></div></aside>
   <main className={`main-scene ${selected?'with-details':''}`}><div className="scene-intro"><span className="scene-english">{s.english}</span><h1>{s.title}</h1><p>{s.intro}</p></div><div className="scene-canvas" key={replayKey}>
    {scene===0&&<Graph layout={overview} scene="overview" stage={stage} selected={selected&&overview.some(p=>p.id===selected)?selected:null} onSelect={selectNode}/>}
    {scene===1&&<Sitemap stage={stage} onSelect={selectNode} onInventory={()=>{setIndexOpen(true);setPlaying(false)}}/>}
    {scene===2&&<WorkflowScene stage={stage} onSelect={selectNode}/>}
    {scene===3&&<Graph layout={technology} scene="technology" stage={stage} selected={selected&&technology.some(p=>p.id===selected)?selected:null} onSelect={selectNode}/>}
    {scene===4&&<DesignScene stage={stage} onSelect={selectNode}/>}
    {scene===5&&<StatusScene stage={stage} onSelect={selectNode}/>}
    {selected&&<><div className={`detail-shade ${graphScene?'graph-shade':''}`} onClick={()=>setSelected(null)} aria-hidden="true"/><Details key={selected} id={selected} onClose={()=>setSelected(null)} onSelect={selectNode}/></>}
   </div><div className="speaker-note"><span>{String(stage+1).padStart(2,'0')} / {String(s.stages.length).padStart(2,'0')}</span><p>{s.notes[stage]}</p></div></main>
   <footer className="transport"><div className="transport-controls"><Button onClick={prev} disabled={scene===0&&stage===0} aria-label="上一阶段"><ArrowLeft size={20}/></Button><Button className="play-button" disabled={reduced} onClick={togglePlay} aria-label={playing?'暂停播放':'播放当前场景'}>{playing?<Pause size={17} fill="currentColor"/>:<Play size={17} fill="currentColor"/>}{playing?'暂停':'播放'}</Button><Button onClick={next} disabled={scene===5&&stage===maxStage} aria-label="下一阶段"><ArrowRight size={20}/></Button><Button onClick={replay} aria-label="重新播放当前阶段"><RotateCcw size={18}/></Button><span className="transport-divider"/><Button className="global-button" onClick={()=>{setSelected(null);setStage(maxStage);setPlaying(false)}}><Maximize2 size={16}/>返回全局</Button></div><div className="stage-nav" aria-label="当前场景阶段">{s.stages.map((label,i)=><Button key={label} aria-current={stage===i?'step':undefined} onClick={()=>{setPlaying(false);setStage(i);setSelected(null)}}><i className={i<=stage?'done':''}/><span>{label}</span></Button>)}</div><span className="scene-counter">{String(scene+1).padStart(2,'0')} <span>/ 06</span></span></footer>
   <div className="keyboard-note no-export">{reduced?'减少动态效果已开启 · 请手动切换阶段':'← → 推进　空格 播放 / 暂停　F 全屏　Esc 返回'}</div>
   {recording&&<Button className="recording-button no-export" onClick={()=>void record()}><Square size={14} fill="currentColor"/>停止录制</Button>}
   {toast&&<div className="toast no-export" role="status">{toast}</div>}
  </div>
  <EvidenceDialog open={indexOpen} onClose={()=>setIndexOpen(false)}/>
  <Dialog open={help} onRequestClose={()=>setHelp(false)} className="help-dialog" aria-labelledby="help-title"><header><h2 id="help-title">由你掌握讲解节奏。</h2><Button onClick={()=>setHelp(false)} aria-label="关闭操作说明"><X/></Button></header><p>默认停在当前阶段。播放只推进当前场景，最后一阶段自动停下，不跳到下一幕。</p><dl>{[['← / →','上一阶段 / 下一阶段'],['空格','播放 / 暂停（按钮聚焦时保留原生操作）'],['1–6','切换场景'],['F','进入 / 退出全屏'],['R','重播当前阶段'],['Esc','关闭详情或对话框'],['Tab / Enter','移动焦点 / 操作节点']].map(([a,b])=><div key={a}><dt>{a}</dt><dd>{b}</dd></div>)}</dl><p>PNG 导出为 3840 × 2160。录制时选择本标签页，再手动推进；停止后保存 WebM。减少动态效果开启时使用手动切换。</p></Dialog>
 </div>
}

createRoot(document.getElementById('root')!).render(<App/>);
