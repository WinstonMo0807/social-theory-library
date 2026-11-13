"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { isImeComposing } from "@/lib/search-submit-key";
import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { useCatalogCommand } from "../workflow/use-intake-command";
import { PrivateMediaImage } from "../media/media-crop";
import { Dialog } from "@/components/ui/dialog";
import styles from "./visual-review.module.css";

type Point = {x:number;y:number};
type Stroke = {color:"#B44C3D"|"#A17E42"|"#282724";points:Point[]};
type Viewport = {width:number;height:number;scroll_x:number;scroll_y:number};
type Draft = {review_id:string;atlas_id:string;path:string;viewport:Viewport;strokes:Stroke[];note:string;status:"open"|"resolved"};
type Entry = {page:string;id:string;module:string;title:string;route:string;start_path:string;route_kind:"page"|"dynamic"|"shared"|"excluded";implementation_status:string;visual_gaps:string};
type Saved = Draft & {version:string;saved_at:string};
type Directory = {owner_id:string;atlas:Entry[];count:number;page:number;page_size:number;results:Saved[];reference_available:boolean};
type Receipt = {owner_id:string;request_id:string;state:"applied"|"cancelled";next_url:string;review_id:string|null;version:string};
const BASE = "/catalog/admin/visual-review/";
const allowedQuery = new Set(["q","page","tab","view","status","type","section","scope","edition","edition_id","work","work_id","file_id","task_id","task_source","selection","item","review_work","review_file"]);
function localPath(value:string) {
  const url=new URL(value,window.location.origin);
  if(url.origin!==window.location.origin||/[\[\]\\]/.test(value)||url.pathname.startsWith("/api/")||url.pathname.startsWith("/admin/visual-review"))throw Error("请输入本站页面路径，并将 [id] 或 [slug] 换成对应编号。");
  for(const key of Array.from(url.searchParams.keys()))if(!allowedQuery.has(key))url.searchParams.delete(key);
  if(!/^#[a-zA-Z0-9_-]{1,100}$/.test(url.hash))url.hash="";
  return `${url.pathname}${url.search}${url.hash}`;
}
function newDraft(atlasId:string,path:string,viewport:Viewport):Draft{return{review_id:createRequestKey(),atlas_id:atlasId,path,viewport,strokes:[],note:"",status:"open"};}

export function VisualReviewWorkspace(){
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  return user?<Workspace key={`${user.id}:${epoch}`} owner={String(user.id)}/>:<LoadingState variant="screen" role="status">正在核对预览账户…</LoadingState>;
}

function Workspace({owner}:{owner:string}){
  const [page,setPage]=useState(1),[entryId,setEntryId]=useState(""),[pathInput,setPathInput]=useState("/home"),[path,setPath]=useState<string|null>("/home");
  const [referenceOpen,setReferenceOpen]=useState(false);
  const [size,setSize]=useState({width:1280,height:800}),[draft,setDraft]=useState<Draft|null>(null),[saved,setSaved]=useState<Draft|null>(null),[version,setVersion]=useState("0");
  const [drawing,setDrawing]=useState(false),[color,setColor]=useState<Stroke["color"]>("#B44C3D"),[active,setActive]=useState<Stroke|null>(null),[message,setMessage]=useState("");
  const frame=useRef<HTMLIFrameElement>(null),activeRef=useRef<Stroke|null>(null),lastSubmitted=useRef<Draft|null>(null),restore=useRef<Viewport|null>(null);
  const load=useCallback((url:string,signal:AbortSignal)=>apiRequest<Directory>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Directory>(`${BASE}?page=${page}`,owner,()=>null,load),data=resource.data;
  const command=useCatalogCommand<Draft & {expected_version:string},Receipt>(owner,BASE,`stl-visual-review:${owner}`);
  const entry=data?.atlas.find(row=>row.id===entryId)||data?.atlas[0],position=data?.atlas.findIndex(row=>row.id===entry?.id)??0;
  const dirty=useUnsavedForm(draft,saved),locked=command.busy||Boolean(command.recovery)||Boolean(active);
  function reset(row:Entry){if(dirty||locked)return;setEntryId(row.id);setPathInput(row.start_path);setPath(null);setDraft(null);setSaved(null);setVersion("0");setDrawing(false);restore.current=null;setMessage("");if(row.start_path&&row.route_kind!=="dynamic"){try{setPath(localPath(row.start_path));}catch{setMessage("此视图需要从对应业务入口打开。");}}}
  function navigate(){if(dirty||locked)return;try{const next=localPath(pathInput);setPath(next);setPathInput(next);setDraft(null);setSaved(null);setVersion("0");setDrawing(false);setMessage("");}catch(reason){setMessage(reason instanceof Error?reason.message:"页面路径无效。");}}
  function beginReview(){if(!entry||locked)return;try{const win=frame.current?.contentWindow;if(!win)throw Error("页面尚未准备好。");const current=localPath(win.location.href);const viewport={...size,scroll_x:Math.round(win.scrollX),scroll_y:Math.round(win.scrollY)};if(!draft){const value=newDraft(entry.id,current,viewport);setDraft(value);setSaved(value);}setDrawing(true);setMessage("");}catch{setMessage("无法读取当前页面，请确认内网预览已启动且页面仍在本站内。");}}
  function point(event:PointerEvent<SVGSVGElement>):Point{const rect=event.currentTarget.getBoundingClientRect();return{x:Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width)),y:Math.max(0,Math.min(1,(event.clientY-rect.top)/rect.height))};}
  function down(event:PointerEvent<SVGSVGElement>){if(!draft||locked||event.button!==0)return;if(draft.strokes.length>=80){setMessage("本条已达80笔，请保存后新建批注。");return;}event.preventDefault();event.currentTarget.setPointerCapture(event.pointerId);const value={color,points:[point(event)]};activeRef.current=value;setActive(value);}
  function move(event:PointerEvent<SVGSVGElement>){const value=activeRef.current;if(!value)return;if(value.points.length>=1500)return;const next=point(event),last=value.points.at(-1)!;if(Math.hypot((next.x-last.x)*size.width,(next.y-last.y)*size.height)<2)return;const changed={...value,points:[...value.points,next]};activeRef.current=changed;setActive(changed);}
  function finish(){const value=activeRef.current;if(value)setDraft(current=>current?{...current,strokes:[...current.strokes,value]}:current);activeRef.current=null;setActive(null);}
  async function accept(result:Receipt|null){if(!result)return;if(result.state==="applied"){setVersion(result.version);if(lastSubmitted.current){setSaved(lastSubmitted.current);setDraft(lastSubmitted.current);}setMessage("绘图与说明已保存到此账户。可以继续修改，或新建下一条批注。");}else setMessage("尚未执行的保存已停止，当前输入保留。");resource.reload();}
  async function save(){if(!draft||locked)return;lastSubmitted.current=draft;await accept(await command.send({...draft,expected_version:version}));}
  function openSaved(row:Saved){if(dirty||locked)return;const {version:revision,saved_at:unused,...value}=row;void unused;setDraft(value);setSaved(value);setVersion(revision);setEntryId(row.atlas_id);setPath(row.path);setPathInput(row.path);setSize({width:row.viewport.width,height:row.viewport.height});restore.current=row.viewport;setDrawing(true);try{if(frame.current?.contentWindow?.location.pathname===new URL(row.path,window.location.origin).pathname){frame.current.contentWindow.scrollTo(row.viewport.scroll_x,row.viewport.scroll_y);}}catch{setMessage("原页面需要重新读取，批注已保留。");}}
  function exportNote(){if(!draft)return;const blob=new Blob([JSON.stringify({...draft,version,reference_page:entry?.page,exported_at:new Date().toISOString()},null,2)],{type:"application/json"});const url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download=`stl-review-${draft.review_id}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function restorePosition(){if(!draft)return;try{frame.current?.contentWindow?.scrollTo(draft.viewport.scroll_x,draft.viewport.scroll_y);setMessage("已请求恢复批注保存时的位置；若页面内容有变化，请重新核对标记。");}catch{setMessage("当前页面无法恢复位置，请确认仍在本站。");}}
  const strokes=[...(draft?.strokes||[]),...(active?[active]:[])];
  return <main className={styles.root}>
    <header className={styles.heading}><div><p>上线前校订 · 仅当前账户</p><h1>预览与批注</h1></div><span>公网发布前保留最后确认</span></header>
    <p className={styles.intro}>打开页面后切换到绘图，可标记并保存修改意见。批注保留页面位置；页面内容会随数据更新。</p>
    {resource.error?<p role="alert" className={styles.notice}>{resource.error}<button onClick={resource.reload}>重新读取</button></p>:null}
    {data&&entry?<>
      <div className={styles.toolbar}><button disabled={dirty||locked||position<=0} onClick={()=>reset(data.atlas[position-1])}>上一张</button><label>终稿视图<select data-stl-select value={entry.id} disabled={dirty||locked} onChange={event=>reset(data.atlas.find(row=>row.id===event.target.value)!)}>{data.atlas.map(row=><option key={row.id} value={row.id}>{row.page} · {row.module} · {row.title}</option>)}</select></label><button disabled={dirty||locked||position>=data.atlas.length-1} onClick={()=>reset(data.atlas[position+1])}>下一张</button><span>{position+1} / {data.atlas.length}</span></div>
      <div className={styles.reviewGrid}><aside className={styles.reference}><h2>终稿第 {entry.page} 页</h2><p>{entry.title}</p>{data.reference_available?<><PrivateMediaImage owner={owner} path={`${BASE}references/${entry.page}/`} alt={`最终PDF第${entry.page}页：${entry.title}`}/><button onClick={()=>setReferenceOpen(true)}>放大查看原图</button></>:<p role="status">最终PDF尚未配置，暂不显示替代图。</p>}<section data-content-section><header data-section-heading>当前实施记录</header><p>{entry.implementation_status}</p><p>{entry.visual_gaps}</p></section></aside>
      <section className={styles.live}><h2>实际页面</h2><div className={styles.location}><label>本站路径<input value={pathInput} disabled={dirty||locked} onChange={event=>setPathInput(event.target.value)} onKeyDown={event=>{if(event.key==="Enter"&&!isImeComposing(event)){event.preventDefault();navigate();}}}/></label><button disabled={dirty||locked} onClick={navigate}>打开</button></div>
      {entry.route_kind==="dynamic"?<p className={styles.notice}>请填写材料编号，再打开页面。</p>:entry.route_kind==="shared"?<p className={styles.notice}>此图是共用弹层或流程。请从实际页面的相应按钮进入，再保存需要修改的位置。</p>:entry.route_kind==="excluded"?<p className={styles.notice}>此视图按已确定的 D010 决定排除，不开展检索质量评测，也不将其计为已完成页面。</p>:null}
      <div className={styles.toolbar}><label>视口<select data-stl-select value={`${size.width}x${size.height}`} disabled={dirty||locked||drawing} onChange={event=>{const [width,height]=event.target.value.split("x").map(Number);setSize({width,height});}}><option value="1280x800">桌面 1280 × 800</option><option value="1440x900">桌面 1440 × 900</option><option value="768x1024">平板 768 × 1024</option><option value="390x844">手机 390 × 844</option><option value="320x740">小屏 320 × 740</option></select></label><button aria-pressed={drawing} disabled={locked||!path} onClick={beginReview}>绘图与批注</button><button disabled={dirty||locked} onClick={()=>{setDrawing(false);setDraft(null);setSaved(null);setVersion("0");}}>继续交互 / 新批注</button>{draft?<button disabled={locked} onClick={restorePosition}>恢复标记位置</button>:null}</div>
      <div className={styles.frameScroll}><div className={styles.frame} style={{width:size.width,height:size.height}}>
        {path?<iframe ref={frame} title="页面交互预览" src={path} inert={drawing} sandbox="allow-same-origin allow-scripts allow-forms allow-downloads allow-popups" onLoad={()=>{if(restore.current){try{frame.current?.contentWindow?.scrollTo(restore.current.scroll_x,restore.current.scroll_y);restore.current=null;}catch{setMessage("保存位置暂不能恢复，请确认原页面可访问。");}}}}/>:<p className={styles.notice}>尚未打开对应页面。请选择实际业务入口后开始批注。</p>}
        {drawing?<svg className={styles.ink} viewBox={`0 0 ${size.width} ${size.height}`} aria-label="在页面上绘制修改标记；也可以使用下方文字说明" onPointerDown={down} onPointerMove={move} onPointerUp={finish} onPointerCancel={finish}>{strokes.map((stroke,index)=>stroke.points.length===1?<circle key={index} cx={stroke.points[0].x*size.width} cy={stroke.points[0].y*size.height} r={3} fill={stroke.color}/>:<polyline key={index} points={stroke.points.map(p=>`${p.x*size.width},${p.y*size.height}`).join(" ")} fill="none" stroke={stroke.color} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round"/>)}</svg>:null}
      </div></div></section></div>
      {draft?<section className={styles.editor}><div className={styles.toolbar}><h2>修改说明</h2><label>画笔<select data-stl-select value={color} disabled={locked} onChange={event=>setColor(event.target.value as Stroke["color"])}><option value="#B44C3D">朱红</option><option value="#A17E42">砂金</option><option value="#282724">炭黑</option></select></label><button disabled={locked||!draft.strokes.length} onClick={()=>setDraft({...draft,strokes:draft.strokes.slice(0,-1)})}>撤销最后一笔</button><span>{draft.strokes.length} 笔</span></div>
        <label>希望如何修改<textarea rows={4} maxLength={5000} value={draft.note} disabled={locked} onChange={event=>setDraft({...draft,note:event.target.value})} placeholder="例如：此处按钮应与参考图右侧对齐；点击后应保留当前筛选。"/></label>
        <div className={styles.toolbar}><label>处理状态<select data-stl-select value={draft.status} disabled={locked} onChange={event=>setDraft({...draft,status:event.target.value as Draft["status"]})}><option value="open">待修正</option><option value="resolved">已修正，待最终确认</option></select></label><button className={styles.primary} disabled={locked||!command.ready||!dirty||!draft.note.trim()&&!draft.strokes.length} onClick={()=>void save()}>保存批注</button><button onClick={exportNote}>导出此条批注</button><button disabled={locked||!dirty} onClick={()=>{setDraft(saved);setMessage("已恢复到本条上次保存的内容。");}}>撤销未保存修改</button></div>
      </section>:null}
      <p role="status" className={styles.message}>{message}{dirty?" 当前批注尚未保存，保存或撤销后可切换视图。":""}</p>{command.error?<p role="alert">{command.error}</p>:null}
      {command.recovery?<div className={styles.notice}><p>上次保存的操作结果尚未确认，请先查询原结果，避免重复记录。</p><div className={styles.toolbar}><button disabled={command.busy} onClick={()=>void command.lookup().then(accept)}>查询保存结果</button>{command.canRetry?<button disabled={command.busy} onClick={()=>void command.send().then(accept)}>重试原请求</button>:null}<button disabled={command.busy} onClick={()=>void command.lookup(true).then(accept)}>停止未执行保存</button></div></div>:null}
      <section className={styles.history}><h2>已保存批注 <span>{data.count}</span></h2>{data.results.length?<ol>{data.results.map(row=><li key={row.review_id}><div><strong>{row.atlas_id} · {row.status==="open"?"待修正":"已修正，待最终确认"}</strong><p>{row.note||`${row.strokes.length} 笔绘图标记`}</p><small>{row.path} · {row.viewport.width} × {row.viewport.height} · {new Date(row.saved_at).toLocaleString("zh-CN")}</small></div><button disabled={dirty||locked} onClick={()=>openSaved(row)}>打开批注</button></li>)}</ol>:<p>尚无保存记录。批注只属于当前账户，不进入公共页面或读者反馈。</p>}<div className={styles.toolbar}><button disabled={page<=1} onClick={()=>setPage(n=>n-1)}>上一页</button><span>第 {page} / {Math.max(1,Math.ceil(data.count/data.page_size))} 页</span><button disabled={page*data.page_size>=data.count} onClick={()=>setPage(n=>n+1)}>下一页</button></div></section>
      <Dialog open={referenceOpen} onRequestClose={()=>setReferenceOpen(false)} aria-labelledby="visual-reference-title" className={styles.referenceDialog}><header><h2 id="visual-reference-title">终稿第 {entry.page} 页 · {entry.title}</h2><button onClick={()=>setReferenceOpen(false)}>关闭原图</button></header>{referenceOpen?<PrivateMediaImage owner={owner} path={`${BASE}references/${entry.page}/`} alt={`最终PDF第${entry.page}页原图`}/>:null}</Dialog>
    </>:!resource.error?<LoadingState role="status">正在读取终稿视图与批注记录…</LoadingState>:null}
  </main>;
}
