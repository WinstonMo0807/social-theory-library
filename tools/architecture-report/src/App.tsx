import React, {useState,useEffect,useRef,useLayoutEffect} from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {ArrowLeft,ArrowRight,ArrowUpRight,Play,Pause,RotateCcw,Maximize,Minimize,Download,FileCode2,X,Search,ChevronRight,BookOpen,Network,Layers,Workflow,Database,Palette,ListChecks,Check,CornerUpLeft,Image as ImageIcon,Film,Keyboard,ExternalLink} from 'lucide-react';
import {BrandImage} from '@/components/brand-image';
import {Button,Input} from '@/components/ui/controls';
import '@/styles/tokens/design.css';
import '@/styles/tokens/type-fonts.css';
import '@/styles/layout/brand-identity.css';
import architecture from '../data/architecture.json';
import {routes as routeInventory} from '../data/inventory.json';
import {layouts,type Position} from './layouts';
import './style.css';

type Evidence={file:string;line:number;anchor:string;sha256:string;note?:string};
type Node={id:string;name:string;type:string;summary:string;status:string;sources:Evidence[];children?:string[];routes?:string[];access?:string;statusNote?:string;screenshot?:string;action?:string;output?:string};
type Relation={from:string;to:string;kind:string;label:string;sources:Evidence[]};
const data=architecture as unknown as {meta:typeof architecture.meta;nodes:Node[];relations:Relation[];scenes:typeof architecture.scenes;statusLabels:Record<string,string>;runtime:typeof architecture.runtime};
const byId=Object.fromEntries(data.nodes.map(n=>[n.id,n]));
const icons=[Network,Layers,Workflow,Database,Palette,ListChecks];
const kindLabels:Record<string,string>={structure:'归属关系',navigation:'页面导航',data:'数据传递',call:'服务调用',reuse:'组件复用'};
const query=new URLSearchParams(location.search);
const initialScene=Math.max(0,data.scenes.findIndex(s=>s.id===query.get('scene')));
const capture=query.get('capture')==='1';
const recording=query.get('motion')==='1';
const initialPhase=Number(query.get('phase')??data.scenes[initialScene].phases.length-1);
const sourcesUnique=(sources:Evidence[])=>sources.filter((s,i,all)=>all.findIndex(x=>x.file===s.file&&x.line===s.line)===i);

function App(){
  const [sceneIndex,setSceneIndex]=useState(initialScene);
  const scene=data.scenes[sceneIndex];
  const [phase,setPhase]=useState(Math.max(0,Math.min(initialPhase,scene.phases.length-1)));
  const [playing,setPlaying]=useState(false);
  const [selected,setSelected]=useState<string|null>(null);
  const [trail,setTrail]=useState<string[]>([]);
  const [panel,setPanel]=useState<'routes'|'evidence'|'export'|'keys'|null>(null);
  const [filter,setFilter]=useState('');
  const [scale,setScale]=useState(1);
  const [fullscreen,setFullscreen]=useState(false);
  const [reduced,setReduced]=useState(matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [replay,setReplay]=useState(0);
  const [exporting,setExporting]=useState('');
  const [message,setMessage]=useState('');
  const appRef=useRef<HTMLDivElement>(null),stageRef=useRef<HTMLDivElement>(null),viewportRef=useRef<HTMLDivElement>(null),dialogRef=useRef<HTMLDialogElement>(null),lastFocus=useRef<HTMLElement|null>(null);
  const activeIds=new Set(scene.phases.slice(0,phase+1).flatMap(p=>p.ids));
  const selectedNode=selected?byId[selected]:null;
  const animationRef=useRef<Animation[]>([]);
  const wasPlaying=useRef(false),replayOnly=useRef(false);
  const closingButton=useRef<HTMLButtonElement>(null);
  function goScene(index:number){if(index<0||index>=data.scenes.length)return;const change=()=>{setSceneIndex(index);setPhase(0);setPlaying(false);setSelected(null);setTrail([]);setMessage('');};if(document.startViewTransition&&!reduced&&!capture)document.startViewTransition(()=>flushSync(change));else change();}
  function step(direction:number){setPlaying(false);setSelected(null);setTrail([]);if(phase+direction<0){if(sceneIndex>0){setSceneIndex(sceneIndex-1);setPhase(data.scenes[sceneIndex-1].phases.length-1);}}else if(phase+direction>=scene.phases.length){goScene(sceneIndex+1);}else setPhase(phase+direction);}
  function togglePlay(){replayOnly.current=false;if(selected){setSelected(null);setTrail([]);}if(playing){setPlaying(false);return;}if(phase===scene.phases.length-1)setPhase(0);setPlaying(true);}
  function replayCurrent(){replayOnly.current=true;setReplay(v=>v+1);setPlaying(true);}
  function focus(id:string){lastFocus.current=document.activeElement as HTMLElement;setPlaying(false);if(selected)setTrail(t=>[...t,selected]);setSelected(id);}
  function back(){if(trail.length){setSelected(trail.at(-1)!);setTrail(t=>t.slice(0,-1));}else{setSelected(null);requestAnimationFrame(()=>lastFocus.current?.focus());}}
  function resetFocus(){setSelected(null);setTrail([]);requestAnimationFrame(()=>lastFocus.current?.focus());}
  function openPanel(value:typeof panel){lastFocus.current=document.activeElement as HTMLElement;setPanel(value);setFilter('');setPlaying(false);}
  function closePanel(){setPanel(null);requestAnimationFrame(()=>lastFocus.current?.focus());}
  async function toggleFullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await appRef.current?.requestFullscreen();}catch{setMessage('此浏览器未允许全屏。请在 Edge 打开本地入口，或使用浏览器全屏键。');}}
  useEffect(()=>{const handler=()=>setFullscreen(Boolean(document.fullscreenElement));document.addEventListener('fullscreenchange',handler);return()=>document.removeEventListener('fullscreenchange',handler);},[]);
  useEffect(()=>{const m=matchMedia('(prefers-reduced-motion: reduce)');const handler=()=>{setReduced(m.matches);if(m.matches)setPlaying(false);};m.addEventListener('change',handler);return()=>m.removeEventListener('change',handler);},[]);
  useEffect(()=>{const handler=()=>{if(document.hidden)setPlaying(false);};document.addEventListener('visibilitychange',handler);return()=>document.removeEventListener('visibilitychange',handler);},[]);
  useLayoutEffect(()=>{const el=viewportRef.current;if(!el)return;const ro=new ResizeObserver(()=>{const r=el.getBoundingClientRect();setScale(Math.min(r.width/1600,r.height/900));});ro.observe(el);return()=>ro.disconnect();},[]);
  useEffect(()=>{if(!playing)return;const timer=setTimeout(()=>{if(replayOnly.current){setPlaying(false);replayOnly.current=false;}else if(phase<scene.phases.length-1)setPhase(p=>p+1);else setPlaying(false);},replayOnly.current?1400:3600);return()=>clearTimeout(timer);},[playing,phase,sceneIndex,replay]);
  useEffect(()=>{if(panel){dialogRef.current?.showModal();}else dialogRef.current?.close();},[panel]);
  useEffect(()=>{if(selected)closingButton.current?.focus();},[selected]);
  useEffect(()=>{const handle=(event:KeyboardEvent)=>{
    if(event.defaultPrevented||event.altKey||event.ctrlKey||event.metaKey||/INPUT|TEXTAREA|SELECT/.test((event.target as HTMLElement).tagName)||panel)return;
    if(event.key==='Escape'&&selected){resetFocus();return;}
    if(event.key==='ArrowRight'){event.preventDefault();step(1);}if(event.key==='ArrowLeft'){event.preventDefault();step(-1);}
    if(event.code==='Space'&&(event.target as HTMLElement).tagName!=='BUTTON'){event.preventDefault();togglePlay();}
    if(event.key.toLowerCase()==='r')replayCurrent();
    if(event.key.toLowerCase()==='f')void toggleFullscreen();
    if(/^[1-6]$/.test(event.key))goScene(Number(event.key)-1);
    if(event.key==='?')openPanel('keys');
  };document.addEventListener('keydown',handle);return()=>document.removeEventListener('keydown',handle);});
  useLayoutEffect(()=>{
    animationRef.current.forEach(a=>a.cancel());animationRef.current=[];
    if(reduced||(capture&&!recording))return;
    const elements=stageRef.current?.querySelectorAll<HTMLElement>('[data-enter]');
    elements?.forEach((el,i)=>{const a=el.animate([{opacity:0,transform:'translateY(10px)'},{opacity:1,transform:'translateY(0)'}],{duration:430,delay:Math.min(i*35,250),easing:'cubic-bezier(.22,1,.36,1)',fill:'backwards'});animationRef.current.push(a);});
    return()=>animationRef.current.forEach(a=>a.cancel());
  },[sceneIndex,replay,reduced]);
  useEffect(()=>{if(playing||wasPlaying.current)stageRef.current?.getAnimations({subtree:true}).forEach(a=>{if(playing)a.play();else a.pause();});wasPlaying.current=playing;},[playing]);
  useEffect(()=>{if(!capture)history.replaceState(null,'',`?scene=${scene.id}&phase=${phase}`);},[scene.id,phase]);

  async function download(kind:string){
    setExporting(kind);setMessage('');
    try{
      const response=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene:scene.id,phase,kind})});
      if(!response.ok)throw Error((await response.text()).slice(0,180));
      const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=`STL-${scene.id}-${kind==='video'?'demo.webm':'3840.png'}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);setMessage(kind==='video'?'当前场景的演示视频已导出。':'4K 画面已导出，可直接插入 PPT。');
    }catch(error){setMessage(`导出未完成：${(error as Error).message}。可使用 README 中的本地导出命令。`);}finally{setExporting('');}
  }
  const selectButton=(id:string,children:React.ReactNode,className='')=><button className={className} onClick={()=>focus(id)} aria-label={`查看${byId[id].name}`} data-node={id}>{children}</button>;
  function SourceList({sources}:{sources:Evidence[]}){return <ol className="source-list">{sourcesUnique(sources).map(s=><li key={s.file+':'+s.line}><code>{s.file}:{s.line}</code><p>{s.anchor}</p><small>{s.file.endsWith('.md')?'项目记录 · ':'源码 · '}SHA-256 {s.sha256.slice(0,16)}</small></li>)}</ol>;}
  function Diagram({positions}:{positions:Position[]}){
    const positionsById=Object.fromEntries(positions.map(p=>[p.id,p]));
    const edges=data.relations.filter(e=>positionsById[e.from]&&positionsById[e.to]);
    function route(e:Relation){const a=positionsById[e.from],b=positionsById[e.to];const aw=a.w||270,ah=a.h||130,bw=b.w||270,bh=b.h||130;const dx=b.x-a.x,dy=b.y-a.y;let x1,y1,x2,y2;
      if(scene.kind==='technology'){
        const paths:Record<string,string>={'api-postgres':'M374,99 H340 V175 H0 V650 H15','processing-files':'M159,338 V370 H333 V575 H397 V610','retrieval-index':'M874,338 V375 H518 V430'};
        const d=paths[e.from+'-'+e.to];if(d)return {d,x:0,y:0};
      }
      if(scene.kind==='design'&&e.from==='shells'&&['home','reader','admin'].includes(e.to)){
        const tx=b.x+bw/2;return {d:`M780,430 V535 H${tx} V575`,x:tx,y:563};
      }
      if(Math.abs(dx)>Math.abs(dy)*1.2){x1=a.x+(dx>0?aw:0);y1=a.y+ah/2;x2=b.x+(dx>0?0:bw);y2=b.y+bh/2;const mx=(x1+x2)/2;return {d:`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`,x:mx,y:(y1+y2)/2};}
      x1=a.x+aw/2;y1=a.y+(dy>0?ah:0);x2=b.x+bw/2;y2=b.y+(dy>0?0:bh);const my=(y1+y2)/2;return {d:`M${x1},${y1} C${x1},${my} ${x2},${my} ${x2},${y2}`,x:(x1+x2)/2,y:my};
    }
    return <div className={`diagram diagram-${scene.kind}`}>
      {scene.kind==='technology'&&<div className="layer-lines" aria-hidden="true">{['界面与业务','调度与检索','处理与投影','持久化与扩展'].map((n,i)=><span style={{top:[15,205,395,575][i]}} key={n}>{n}</span>)}</div>}
      <svg className="connectors" viewBox="0 0 1040 720" aria-label="模块之间的关系"><defs><marker id="arrow" markerWidth="7" markerHeight="7" refX="5.4" refY="3.5" orient="auto"><path d="M1,1 L5,3.5 L1,6" fill="none" stroke="currentColor" strokeWidth="1.2"/></marker></defs>
        {edges.map((e,i)=>{const p=route(e),active=activeIds.has(e.from)&&activeIds.has(e.to);return <g key={e.from+e.to} className={`edge ${e.kind} ${active?'active':''}`}><title>{byId[e.from].name} → {byId[e.to].name}：{e.label}（{kindLabels[e.kind]}）</title><path d={p.d} markerEnd={e.kind==='structure'||e.kind==='reuse'?undefined:'url(#arrow)'}/>{active&&['call','data'].includes(e.kind)&&<path className="flow" d={p.d}/>}<text x={p.x} y={scene.kind==='workflow'&&e.kind==='navigation'?p.y-100:scene.kind==='workflow'&&e.kind==='call'?p.y+112:p.y-10} textAnchor="middle">{scene.kind==='technology'?'':e.label==='产品职责'?'':e.label}</text></g>;})}
      </svg>
      {positions.map((p,i)=>{const n=byId[p.id],active=activeIds.has(p.id);return <button key={p.id} className={`map-node ${p.id==='stl'?'core':''} ${active?'revealed':'quiet'} ${n.status==='partial'?'conditional':''}`} style={{left:p.x,top:p.y,width:p.w||270,height:p.h||130,viewTransitionName:`node-${p.id}`}} onClick={()=>focus(p.id)} data-node={p.id} aria-label={`查看${n.name}`} data-enter>
        {p.id==='stl'?<><svg className="core-symbol" viewBox="12 17 230 154"><use href="/brand/stl-symbol-20261027.svg#mark"/></svg><strong>社会理论书库</strong><span>同一馆藏 · 同一证据身份</span></>:<><div className="node-title"><h3>{n.name}</h3><ArrowUpRight size={19}/></div>{scene.kind==='workflow'?<><p>{n.action||n.summary}</p><div className="node-output">{n.output||'人工判断 / 条件性生成'}</div></>:scene.kind==='technology'?<small>{n.type==='storage'?'数据存储':n.status==='partial'?'已接接口 · 待配置':'现有实现'}</small>:scene.kind==='design'?<p>{n.id==='brand'?'中文衬线标题 · 无衬线操作':n.id==='tokens'?'纸白 #F7F4EE · 炭黑 · 砂金':n.id==='controls'?'Button · Input · Dialog · Drawer':n.id==='shells'?'SiteHeader · AdminShell · ReaderShell':null}</p>:<p>{n.summary}</p>}{n.status==='partial'&&<span className="condition-dot" aria-label="存在未验证条件"/>}</>}
      </button>;})}
      {scene.kind==='workflow'&&<div className="workflow-evidence"><span>贯穿各步骤的证据身份</span><code>asset_id</code><span>文件</span><code>document_revision_id</code><span>修订</span><code>page / evidence</code><span>定位</span></div>}
      {scene.kind==='design'&&<><div className="swatches" aria-label="现有设计颜色"><i style={{background:'#f7f4ee'}}/><i style={{background:'#eeeae2'}}/><i style={{background:'#1b1b18'}}/><i style={{background:'#c4a164'}}/></div><div className="live-controls"><Button className="sample-primary" onClick={()=>setMessage('此为现有 Button 组件样例；未提交业务操作。')}>阅读原文 <ArrowUpRight size={16}/></Button><Input aria-label="共用输入组件样例" placeholder="查找书名或作者"/><span>真实共用控件</span></div></>}
    </div>;
  }
  function Sitemap(){const groups=[{title:'公开浏览',access:'无需登录',ids:['home','scholars','theories','topics','editorial']},{title:'探索与研究',access:'登录 / 本人数据',ids:['catalog-search','opinion','evidence','reader','projects','notes','plans','audit']},{title:'管理工作区',access:'按能力授权',ids:['intake','processing','publication','content','operations']}];return <div className="sitemap">{groups.map((group,i)=><section key={group.title} className="sitemap-group" data-enter><header><h3>{group.title}</h3><span>{group.access}</span></header><div className="sitemap-tree">{group.ids.map(id=>selectButton(id,<><strong>{byId[id].name}</strong><small>{byId[id].routes?.[0]||'/reader/[assetId]'}</small><ArrowUpRight size={16}/></>,`sitemap-node ${activeIds.has(id)?'':'quiet'}`))}</div></section>)}<div className="sitemap-nav"><ArrowRight size={18}/><span>观点检索</span><ChevronRight size={16}/><span>原文证据</span><ChevronRight size={16}/><span>PDF 阅读器</span><small>跨页面导航，有独立源码依据</small></div></div>;}
  function Status(){const groups=[{status:'verified',ids:['home','auth'],label:'定向验证',detail:'仅所列页面与门禁'},{status:'implemented',ids:['discovery','reader','projects','intake','publication','plans','outline'],label:'已实现，待验收',detail:'页面、接口或服务有证据'},{status:'partial',ids:['compare','relay','oauth'],label:'条件与缺口',detail:'已有部分单独保留'},{status:'planned',ids:['future'],label:'范围待定',detail:'不作为既成架构'}];return <div className="status-grid">{groups.map(g=><section key={g.status} className={`status-column status-${g.status}`} data-enter><span className="status-mark"/><h3>{g.label}</h3><p>{g.detail}</p>{g.ids.map(id=>selectButton(id,<><strong>{byId[id].name}</strong><ArrowUpRight size={16}/></>,`status-item ${activeIds.has(id)?'':'quiet'}`))}</section>)}<p className="status-boundary">状态是证据范围，不是全站完成度。当前快照包含未提交代码，生产切换仍需最终批准。</p></div>;}
  function Focus(){const n=selectedNode!;const related=data.relations.filter(e=>e.from===n.id||e.to===n.id);return <section className="focus-panel" aria-label={`${n.name}详情`}><div className="focus-top"><Button ref={closingButton} onClick={back} className="text-button"><ArrowLeft size={18}/>{trail.length?'返回上一层':'返回架构'}</Button><span>{data.statusLabels[n.status]}</span><Button onClick={resetFocus} aria-label="返回全局视图" className="icon-button"><X size={19}/></Button></div><div className="focus-body"><div><h2>{n.name}</h2><p className="focus-summary">{n.summary}</p>{n.access&&<div className="access-note">访问边界 <strong>{n.access}</strong></div>}<p className="evidence-note">{n.statusNote||'源码和引用关系已核对。完整业务及各界面状态仍待验收。'}</p>{n.routes&&<div className="route-tags">{n.routes.map(route=><code key={route}>{route}</code>)}</div>}{n.children?.length?<div className="child-list">{n.children.map(id=>selectButton(id,<><strong>{byId[id].name}</strong><span>{byId[id].summary}</span><ArrowRight size={18}/></>))}</div>:null}{n.screenshot&&<figure className="page-preview"><img src={`/screens/${n.screenshot}`} alt={`${n.name}本轮匿名只读截图`}/><figcaption>当前内网页面 · 本轮匿名只读截图</figcaption></figure>}{related.length>0&&<div className="related-list"><h3>直接关系</h3>{related.map((e,i)=><button key={i} onClick={()=>focus(e.from===n.id?e.to:e.from)}><span>{byId[e.from===n.id?e.to:e.from].name}</span><small>{kindLabels[e.kind]} · {e.label}</small><ChevronRight size={16}/></button>)}</div>}</div><aside className="focus-sources"><h3>实现与状态依据</h3><SourceList sources={n.sources}/><h3>关系依据</h3><SourceList sources={related.flatMap(e=>e.sources)}/></aside></div></section>;}
  return <div className={`report-app ${capture?'capture':''} ${recording?'recording':''} ${reduced?'reduced':''}`} ref={appRef}>
    {!capture&&<header className="app-toolbar"><span className="app-title">STL 架构展映 <span>内部汇报</span></span><nav aria-label="汇报工具"><Button onClick={()=>openPanel('routes')}><Layers size={16}/>路由索引</Button><Button onClick={()=>openPanel('evidence')}><FileCode2 size={16}/>来源</Button><Button onClick={()=>openPanel('export')}><Download size={16}/>导出</Button><Button onClick={toggleFullscreen} aria-label={fullscreen?'退出全屏':'全屏展示'}>{fullscreen?<Minimize size={17}/>:<Maximize size={17}/>}</Button></nav></header>}
    <div className="viewport" ref={viewportRef}><div className="stage-wrap" style={{width:1600*scale,height:900*scale}}><main className={`stage scene-${scene.kind} ${playing?'is-playing':''} ${selected?'has-selection':''}`} ref={stageRef} style={{transform:`scale(${scale})`}} data-scene={scene.id} data-phase={phase} data-playing={playing}>
      <header className="slide-header"><BrandImage/><span>STL 4.0 <i/> 架构与研究体验</span><time>{data.meta.snapshotDate}</time></header>
      <div className="slide-content" inert={selected ? true : undefined}><section className="story-rail"><div className="scene-number" aria-label={`场景 ${sceneIndex+1} / 6`}><span>{String(sceneIndex+1).padStart(2,'0')}</span><span>/ 06</span></div><h1 data-enter>{scene.title.split('\n').map((line,i)=><React.Fragment key={line}>{i>0&&<br/>}{line}</React.Fragment>)}</h1><p className="story-subtitle" data-enter>{scene.subtitle}</p><div className="phase-story" aria-live="polite"><span className="phase-count">{String(phase+1).padStart(2,'0')}<i/>{scene.phases.length} 段</span><h2>{scene.phases[phase].name}</h2><p>{scene.phases[phase].note}</p></div><div className="relationship-key">{(scene.kind==='overview'?['structure']:scene.kind==='workflow'?['navigation','data','reuse']:scene.kind==='design'?['reuse']:scene.kind==='technology'?['call','data']:[]).map(kind=><span key={kind}><i className={kind}/>{kindLabels[kind]}</span>)}</div></section>
      <div className="visual-field">{layouts[scene.kind]?<Diagram positions={layouts[scene.kind]}/>:scene.kind==='sitemap'?<Sitemap/>:<Status/>}</div></div>
      <footer className="slide-footer"><p>{scene.footnote}</p><span>Social Theory Library <i/> {scene.label}</span></footer>{selectedNode&&<Focus/>}
    </main></div></div>
    {!capture&&<><nav className="scene-nav" aria-label="场景导航">{data.scenes.map((s,i)=>{const Icon=icons[i];return <Button key={s.id} onClick={()=>goScene(i)} className={i===sceneIndex?'current':''} aria-current={i===sceneIndex?'step':undefined}><Icon size={17}/><span>{s.label}</span><small>{String(i+1).padStart(2,'0')}</small></Button>;})}</nav><footer className="transport"><div className="playback"><Button className="icon-button" aria-label="上一阶段" disabled={sceneIndex===0&&phase===0} onClick={()=>step(-1)}><ArrowLeft size={19}/></Button><Button className="play-button" aria-label={playing?'暂停':'播放'} onClick={togglePlay}>{playing?<Pause size={17}/>:<Play size={17}/>}<span>{playing?'暂停':'播放'}</span></Button><Button className="icon-button" aria-label="下一阶段" disabled={sceneIndex===data.scenes.length-1&&phase===scene.phases.length-1} onClick={()=>step(1)}><ArrowRight size={19}/></Button><Button className="icon-button" aria-label="重播当前阶段" onClick={replayCurrent}><RotateCcw size={18}/></Button></div><div className="phase-controls">{scene.phases.map((p,i)=><Button key={p.name} onClick={()=>{setPhase(i);setPlaying(false);resetFocus();}} className={i===phase?'current':''} aria-current={i===phase?'step':undefined}><span>{i+1}</span>{p.name}</Button>)}</div><div className="transport-end"><span>{reduced?'减少动态效果':'手动讲解 · 场景内播放'}</span><Button aria-label="键盘快捷键" className="icon-button" onClick={()=>openPanel('keys')}><Keyboard size={18}/></Button></div></footer></>}
    <div className="toast" role="status" hidden={!message}>{message}<Button onClick={()=>setMessage('')} aria-label="关闭提示"><X size={16}/></Button></div>
    <dialog ref={dialogRef} className={`report-dialog ${panel==='routes'?'wide':''}`} onCancel={e=>{e.preventDefault();closePanel();}}><header><h2>{{routes:'页面与源码索引',evidence:'这幅架构的依据',export:'把画面带进汇报',keys:'键盘操作'}[panel||'evidence']}</h2><Button className="icon-button" onClick={closePanel} aria-label="关闭面板"><X size={21}/></Button></header>
      {panel==='routes'&&<><p>实际提取 {data.meta.routeCount} 个页面文件。父级按 URL 路径归组；别名、预览与已暂停模块保留追溯。</p><label className="index-search"><Search size={18}/><Input autoFocus value={filter} onChange={e=>setFilter(e.target.value)} placeholder="搜索路径、分组或源码"/></label><div className="route-list">{routeInventory.filter(r=>(r.route+r.source+r.group).toLowerCase().includes(filter.toLowerCase())).map(r=><div key={r.route}><code>{r.route}</code><span>{r.group}{r.redirects.length?' · 重定向':''}</span><small>{r.source}</small><details><summary>直接引用 {r.imports.length} 个本地模块</summary>{r.imports.map(i=><code key={i}>{i}</code>)}</details></div>)}</div></>}
      {panel==='evidence'&&<><p className="dialog-lead">架构来自当前工作区，验证范围保持可见。</p><dl className="audit-metadata"><dt>快照</dt><dd>{data.meta.snapshotDate} · {data.meta.worktree}</dd><dt>代码基点</dt><dd><code>{data.meta.head.slice(0,12)}</code></dd><dt>方法</dt><dd>{data.meta.method}</dd><dt>实际读回</dt><dd>{data.runtime?.checks.map(c=><span key={c.route} className="runtime-row"><code>{c.route}</code><span>{c.status}{'finalPath'in c&&c.finalPath!==c.route?` → ${c.finalPath}`:''}</span></span>)}</dd><dt>范围限制</dt><dd>{data.runtime?.limits}</dd></dl><div className="data-downloads"><a href="/data/architecture.json" download>架构数据 JSON <Download size={16}/></a><a href="/data/evidence-index.csv" download>节点证据 CSV <Download size={16}/></a><a href="/data/inventory.json" download>路由与引用清单 <Download size={16}/></a></div></>}
      {panel==='export'&&<><p className="dialog-lead">当前场景 · {scene.label}</p><p>导出纯画面，不含播放器控件与节点详情。静态画面保留当前讲解阶段；视频从本场景第一段开始。</p><div className="export-options"><Button disabled={Boolean(exporting)} onClick={()=>download('png')}><ImageIcon size={28}/><strong>{exporting==='png'?'正在生成…':'4K PNG'}</strong><span>3840 × 2160 · 可插入 PPT</span><Download size={19}/></Button><Button disabled={Boolean(exporting)} onClick={()=>download('video')}><Film size={28}/><strong>{exporting==='video'?'正在录制…':'WebM 视频'}</strong><span>1920 × 1080 · 无音轨</span><Download size={19}/></Button></div><p className="export-note">视频使用本机 Edge 与 Playwright 录制；生成约需 15–25 秒，请保留当前窗口。</p></>}
      {panel==='keys'&&<div className="key-list">{[['← / →','上一阶段 / 下一阶段'],['Space','播放 / 暂停（按钮聚焦时执行按钮）'],['R','重新播放当前阶段'],['F','进入 / 退出全屏'],['1 – 6','直接切换场景'],['Esc','关闭面板或返回全局'],['Tab / Enter','选择与打开节点'],['?','显示此帮助']].map(([key,label])=><div key={key}><kbd>{key}</kbd><span>{label}</span></div>)}</div>}
    </dialog>
  </div>;
}
createRoot(document.getElementById('root')!).render(<App/>);
