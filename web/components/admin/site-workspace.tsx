"use client";
import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, BookOpen, Check, ChevronRight, GripVertical, Plus, X } from "lucide-react";
import { normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { useAdminSession } from "@/lib/admin-session";
import { SiteHeader } from "@/components/site-header";
import { SiteFooterView } from "@/components/public/site-footer-view";
import { HomePublicView, type HomeViewData } from "@/components/public/home-public-view";
import { AboutPublicView } from "@/components/public/about-public-view";
import { PreviewViewport } from "./curation/fixed-page-editor";
import { InlineMediaPicker } from "./curation/inline-media-picker";
import { ConfirmDialog } from "@/components/confirm-dialog";
import { Dialog } from "@/components/ui/dialog";
import { SiteHomePicker, type HomeChoice } from "./site-home-picker";
import { SiteTextFields, siteTextSections } from "./site-text-fields";
import { useSiteContent } from "./use-site-content";
import type { HomeArea, HomeCard, HomeLayoutPreview, HomeSlot } from "@/lib/api/home.types";
import type { SiteStats } from "@/lib/api/site.types";
import styles from "./site-content.module.css";

const areas:HomeArea[]=["featured","scholars","topics"];
const names={featured:"主页主推",scholars:"学者聚焦",topics:"探索主题"};
const groups={home:["home","brand","footer"],about:["about","about-why","about-feature-source","about-feature-reading","about-feature-knowledge"],usage:["about-process","about-open","about-copyright","about-privacy"],help:["about-notice"]};
type Props={home:HomeViewData;stats:SiteStats;fullPreview?:boolean};
export function SiteContentEditor(props:Props){
  const user=useAdminSession(),[epoch,setEpoch]=useState(0);
  useEffect(()=>subscribeToSessionChanges(()=>setEpoch(value=>value+1)),[]);
  if(!user||!["admin","superadmin"].includes(user.access_level||user.role))return <section className="admin-panel"><h1>首页编排、关于与公共说明</h1><p>当前账户没有网站内容管理权限。</p></section>;
  return <Workspace key={`${user.id}:${epoch}`} {...props} owner={String(user.id)}/>;
}

function Workspace({home,stats,owner,fullPreview=false}:Props&{owner:string}){
  const editor=useSiteContent(owner),{draft,setDraft,saved}=editor;
  const [group,setGroup]=useState<keyof typeof groups>("home"),[textSection,setTextSection]=useState("home"),[tab,setTab]=useState("settings");
  const [selection,setSelection]=useState<{area:HomeArea;id:string}|null>(null),[picker,setPicker]=useState<{area:HomeArea;replace?:string}|null>(null);
  const [cache,setCache]=useState<Record<string,HomeCard>>({}),[covers,setCovers]=useState<Record<string,string>>({});
  const [confirm,setConfirm]=useState<"publish"|"reset"|null>(null),[moreOpen,setMoreOpen]=useState(false),[previewOpen,setPreviewOpen]=useState(false),[small,setSmall]=useState(false),[mobileOpen,setMobileOpen]=useState(false);
  const dragging=useRef<{area:HomeArea;id:string}|null>(null);
  useEffect(()=>{const query=window.matchMedia("(max-width: 760px)");const update=()=>setSmall(query.matches);update();query.addEventListener("change",update);return()=>query.removeEventListener("change",update);},[]);
  const locked=editor.busy||!!editor.operation;
  function select(area:HomeArea,id:string){setSelection({area,id});setTab("settings");setMobileOpen(true);}
  function update(area:HomeArea,items:HomeSlot[]|null){setDraft(current=>current?{...current,home_layout:{...current.home_layout,[area]:items}}:current);}
  function move(area:HomeArea,id:string,position:number){if(!draft||locked)return;const items=[...(draft.home_layout[area]||[])],index=items.findIndex(row=>row.id===id);if(index<0||position<0||position>=items.length)return;items.splice(position,0,...items.splice(index,1));update(area,items);}
  function choose(choice:HomeChoice,destination=picker){if(!draft||!destination||locked)return;const id=destination.replace||crypto.randomUUID();const old=draft.home_layout[destination.area]||[];if(!destination.replace&&old.length>=5)return;
    if(old.some(row=>row.id!==id&&row.target.type===choice.target.type&&row.target.id===choice.target.id))return;
    const slot:HomeSlot={id,target:choice.target,title:"",description:"",cover_rendition_id:null,visible:true};
    update(destination.area,destination.replace?old.map(row=>row.id===id?slot:row):[...old,slot]);setCache(current=>({...current,[id]:{...choice.source,id}}));setCovers(current=>{const next={...current};delete next[id];return next;});select(destination.area,id);setPicker(null);
  }
  if(editor.blocked||(!editor.resource.data&&editor.resource.error))return <section className="admin-panel"><h1>首页编排、关于与公共说明</h1><p role="alert">{editor.message||editor.resource.error||"请重新核对当前账户。"}</p><button onClick={()=>window.location.reload()}>重新读取页面</button></section>;
  if(!draft)return <p role="status">正在读取网站内容…</p>;
  const layout=Object.fromEntries(areas.map(area=>[area,draft.home_layout[area]?.map(row=>{
    const original=saved?.home_layout[area]?.find(slot=>slot.id===row.id);
    const unsavedSource=!original||original.target.type!==row.target.type||original.target.id!==row.target.id;
    const latest=editor.resource.data?.edit_version===draft.edit_version?editor.resource.data.home_preview:draft.home_preview;
    const source=(unsavedSource?cache[row.id]:null)||latest[area]?.find(card=>card.id===row.id)||{id:row.id,title:"来源不可用",description:"请更换来源",href:"",image_url:"",label:"内容",available:false,visible:false};
    return {...source,id:row.id,title:row.title||(source.source_title??source.title),description:row.description||(source.source_description??source.description),visible:row.visible,image_url:row.cover_rendition_id?(covers[row.id]||`/api/catalog/admin/media/renditions/${row.cover_rendition_id}/file/`):(source.source_image_url??source.image_url)};
  })??null])) as HomeLayoutPreview;
  const selected=selection?draft.home_layout[selection.area]?.find(row=>row.id===selection.id):null;
  const card=selection?layout[selection.area]?.find(row=>row.id===selection.id):null;
  const patch=(values:Partial<HomeSlot>)=>{if(selected&&selection)update(selection.area,draft.home_layout[selection.area]!.map(row=>row.id===selected.id?{...row,...values}:row));};
  const preview=<div onClickCapture={event=>{if((event.target as Element).closest("a,button,input,form,select,textarea")){event.preventDefault();event.stopPropagation();}}} onSubmitCapture={event=>event.preventDefault()}><SiteHeader config={draft.config} preview/>{group==="home"?<HomePublicView {...home} config={draft.config} homeLayout={layout} preview/>:<AboutPublicView config={draft.config} stats={stats} about={{configured:draft.about_blocks.length>0,blocks:draft.about_blocks.filter(row=>row.visible)}}/>}<SiteFooterView config={draft.config} preview/></div>;
  const invalid=areas.flatMap(area=>layout[area]||[]).some(row=>row.visible&&!row.available);
  const history=<ol className={styles.history}>{draft.history.map(row=><li key={row.id}><strong>第 {row.revision} 版 · {{draft:"已保存草稿",published:"已发布",superseded:"已被新草稿替代",archived:"已归档"}[row.state]||row.state}</strong><p>{row.saved_by||"未记录编辑者"} · {new Date(row.saved_at).toLocaleString("zh-CN")}</p>{row.published_at?<p>{row.published_by||"管理员"} 发布于 {new Date(row.published_at).toLocaleString("zh-CN")}</p>:null}</li>)}{!draft.history.length?<li>暂无保存记录。</li>:null}</ol>;
  const detail=<><nav className={styles.tabs} aria-label="内容面板">{[["settings","内容设置"],["preview","页面预览"],["history","更新记录"]].map(([id,label])=><button key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    {tab==="preview"?<PreviewViewport>{preview}</PreviewViewport>:tab==="history"?history:group==="home"&&selected&&card?<fieldset disabled={locked} className={styles.fields}>
      {!card.available?<p role="alert" className={styles.warning}>来源已撤回或不可用。请更换来源或关闭首页显示后再发布。</p>:null}
      <label>标题 <span>{selected.title.length}/40</span><input maxLength={40} value={selected.title} placeholder={card.title} onChange={event=>patch({title:event.target.value})}/></label>
      <label>导语 <span>{selected.description.length}/80</span><textarea rows={4} maxLength={80} value={selected.description} placeholder={card.description} onChange={event=>patch({description:event.target.value})}/></label>
      <label>封面图</label><div className={styles.cover}>{card.image_url?<img src={normalizePublicResourceUrl(card.image_url)} alt="当前封面"/>:<div className={styles.imageMissing}><BookOpen size={28}/><p>尚未提供配图</p></div>}</div><small>建议比例 16:9。未设置时使用来源配图或留空。</small>
      <InlineMediaPicker selectedRenditionId={selected.cover_rendition_id} onSelect={(id,url)=>{patch({cover_rendition_id:id});setCovers(current=>({...current,[selected.id]:url}));}}/>{selected.cover_rendition_id?<button onClick={()=>patch({cover_rendition_id:null})}>使用来源配图</button>:null}
      <label>关联对象</label><div className={styles.related}><div><small>{card.label}</small><strong>{cache[selected.id]?.title||draft.home_preview[selection!.area]?.find(row=>row.id===selected.id)?.source_title||"已保存来源"}</strong></div><button onClick={()=>setPicker({area:selection!.area,replace:selected.id})}>更换</button>{card.href?<a href={card.href} target="_blank" rel="noopener noreferrer">打开 ↗</a>:null}</div>
      <p className={styles.meta}>来源状态：{card.available?"当前公开":"不可公开"}<br/>首页内容：{editor.dirty?"有未保存修改":draft.has_unpublished_changes?"已保存，尚未发布":"当前发布版本"}</p>
      <label className={styles.toggle}><input type="checkbox" checked={selected.visible} onChange={event=>patch({visible:event.target.checked})}/>在本页显示</label><small>仅改变本页位置，发布后生效，不改变来源对象的发布状态。</small>
      <footer><button className={styles.remove} onClick={()=>{update(selection!.area,draft.home_layout[selection!.area]!.filter(row=>row.id!==selected.id));setSelection(null);setMobileOpen(false);}}>从首页移除</button><button onClick={()=>setConfirm("reset")} disabled={!editor.dirty}>取消修改</button><button className={styles.primary} disabled={!editor.dirty} onClick={()=>void editor.persist()}>保存本页草稿</button></footer>
    </fieldset>:<SiteTextFields draft={draft} setDraft={setDraft} active={textSection} busy={locked}/>}</>;
  if(fullPreview)return <div className={styles.fullPreview}><p>已保存草稿预览 · 仅后台可见</p><nav className={styles.tabs}>{[["home","首页"],["about","关于与公共说明"]].map(([id,label])=><button key={id} onClick={()=>setGroup(id as keyof typeof groups)}>{label}</button>)}</nav>{preview}</div>;
  return <main className={styles.page}><div className={styles.toolbar}><span>内容 <ChevronRight size={12}/>页面编排 <ChevronRight size={12}/>首页与公共说明</span><div><small>{editor.dirty?"有未保存修改":draft.has_unpublished_changes?"已保存未发布":"当前发布版本"}</small><button disabled={locked} onClick={()=>setPreviewOpen(true)}>预览</button><button disabled={locked||!editor.dirty} onClick={()=>void editor.persist()}>保存草稿</button><button className={styles.primary} disabled={locked||editor.dirty||!draft.has_unpublished_changes||invalid} onClick={()=>setConfirm("publish")}>发布</button></div></div>
    <header className={styles.heading}><h1>首页编排、关于与公共说明</h1><p>管理读者看到的入口叙事与说明，从馆藏、专题、学者、主题中选择内容，调整顺序与导语。</p></header>
    {editor.message?<p role="status" className={styles.notice}>{editor.message}</p>:null}{editor.resource.error?<p role="alert">{editor.resource.error}<button onClick={editor.resource.reload}>重新读取</button></p>:null}
    {editor.operation?<div className={styles.warning} role="status"><p>原操作结果尚未确认，请查回后继续编辑。</p>{editor.operation.body?<button disabled={editor.busy} onClick={()=>void editor.persist()}>重试原请求</button>:null}<button disabled={editor.busy} onClick={()=>void editor.recover()}>查回原结果</button><button disabled={editor.busy} onClick={()=>void editor.recover(true)}>停止未执行的原请求</button></div>:null}
    {editor.conflict&&!editor.operation?<div className={styles.warning}><p>服务器已有新版本，当前输入仍保留。核对更新记录后选择处理方式。</p><button onClick={editor.useRemote}>采用服务器版本</button><button onClick={editor.keepLocal}>保留输入并采用新版本号</button></div>:null}
    <nav className={styles.tabs} aria-label="网站内容">{([["home","首页内容"],["about","关于我们"],["usage","使用说明"],["help","帮助与公告"]] as const).map(([id,label])=><button key={id} aria-pressed={group===id} disabled={locked} onClick={()=>{setGroup(id);setTextSection(groups[id][0]);setSelection(null);}}>{label}</button>)}</nav>
    <div className={styles.workspace}><section className={styles.directory}>{group==="home"?<>{areas.map((area,index)=><section key={area} className={styles.area}><header><div><h2><span>{index+1}</span>{names[area]}</h2><p>{area==="featured"?"设置首页重点内容，最多 5 个模块。":area==="scholars"?"从学者库选择展示内容，最多 5 位。":"从主题库选择展示内容，最多 5 个。"}</p></div><button disabled={locked||(draft.home_layout[area]?.length||0)>=5} onClick={()=>setPicker({area})}><Plus size={14}/>添加{area==="featured"?"模块":area==="scholars"?"学者":"主题"}</button></header>
      {draft.home_layout[area]===null?<div className={styles.empty}><p>当前沿用公开内容推荐。选择内容后使用本页编排。</p><button disabled={locked} onClick={()=>update(area,[])}>改为手动编排</button></div>:null}
      <div className={area==="featured"?styles.rows:styles.cards}>{(draft.home_layout[area]||[]).map((row,position)=>{const visual=layout[area]!.find(item=>item.id===row.id)!;return <article key={row.id} data-selected={selection?.id===row.id} draggable={!locked} onDragStart={event=>{dragging.current={area,id:row.id};event.dataTransfer.effectAllowed="move";event.dataTransfer.setData("text/plain",row.id);}} onDragEnd={()=>{dragging.current=null;}} onDragOver={event=>{if(dragging.current?.area===area)event.preventDefault();}} onDrop={event=>{event.preventDefault();if(dragging.current?.area===area)move(area,dragging.current.id,position);dragging.current=null;}}><button className={styles.select} disabled={locked} onClick={()=>select(area,row.id)}><GripVertical size={14}/>{visual.image_url?<img src={normalizePublicResourceUrl(visual.image_url)} alt=""/>:<span className={styles.thumb}><BookOpen size={22}/></span>}<span><strong>{visual.title}</strong><small>{visual.label} · {visual.available?row.visible?"在本页显示":"已关闭显示":"来源不可用"}</small></span>{area==="featured"?<ChevronRight size={14}/>:null}</button><div className={styles.order}><button aria-label={`上移${visual.title}`} disabled={locked||position===0} onClick={()=>move(area,row.id,position-1)}><ArrowUp size={12}/></button><button aria-label={`下移${visual.title}`} disabled={locked||position===draft.home_layout[area]!.length-1} onClick={()=>move(area,row.id,position+1)}><ArrowDown size={12}/></button></div></article>;})}</div>
      {draft.home_layout[area]?.length===0?<p className={styles.empty}>尚未添加内容。发布空栏目后，首页显示真实空态。</p>:null}{draft.home_layout[area]!==null?<button className={styles.textButton} disabled={locked} onClick={()=>{update(area,null);if(selection?.area===area)setSelection(null);}}>恢复公开推荐</button>:null}
    </section>)}<details className={styles.extra}><summary>馆头、品牌与页脚</summary>{groups.home.map(id=><button key={id} disabled={locked} onClick={()=>{setSelection(null);setTextSection(id);setTab("settings");setMobileOpen(true);}}>{siteTextSections.find(row=>row.id===id)?.label}</button>)}</details><details className={styles.extra} onToggle={event=>setMoreOpen(event.currentTarget.open)}><summary>更多内容（未上首页）</summary>{moreOpen?<SiteHomePicker owner={owner} area="featured" inline disabled={locked||(draft.home_layout.featured?.length||0)>=5} used={(draft.home_layout.featured||[]).map(row=>row.target)} onChoose={choice=>choose(choice,{area:"featured"})} onClose={()=>undefined}/>:null}{(draft.home_layout.featured?.length||0)>=5?<p>主页主推已满 5 项，请先移除条目或更换已有来源。</p>:null}</details></>:<nav className={styles.textSections} aria-label="公共说明模块">{groups[group].map(id=><button key={id} aria-current={textSection===id?"true":undefined} disabled={locked} onClick={()=>{setTextSection(id);setTab("settings");setMobileOpen(true);}}>{siteTextSections.find(row=>row.id===id)?.label}<ChevronRight size={14}/></button>)}</nav>}</section>
    {!small?<aside className={styles.detail}>{detail}</aside>:null}</div>
    {small?<Dialog open={mobileOpen} onRequestClose={()=>{if(!editor.busy)setMobileOpen(false);}} className={styles.mobileSheet} aria-label="编辑首页与公共说明"><header><strong>{selected?`编辑：${card?.title}`:siteTextSections.find(row=>row.id===textSection)?.label}</strong><button disabled={editor.busy} onClick={()=>setMobileOpen(false)} aria-label="收起编辑面板"><X size={18}/></button></header>{detail}</Dialog>:null}
    {picker?<SiteHomePicker owner={owner} area={picker.area} used={(draft.home_layout[picker.area]||[]).filter(row=>row.id!==picker.replace).map(row=>row.target)} onChoose={choose} onClose={()=>setPicker(null)}/>:null}
    <Dialog open={previewOpen} onRequestClose={()=>setPreviewOpen(false)} className={styles.previewDialog} aria-label="网站内容预览"><header><strong>{editor.dirty?"当前输入预览 · 尚未保存":"已保存内容预览"}</strong><button onClick={()=>setPreviewOpen(false)} aria-label="关闭预览"><X size={18}/></button></header><PreviewViewport>{preview}</PreviewViewport></Dialog>
    <ConfirmDialog open={confirm!==null} title={confirm==="publish"?"发布网站内容":"取消当前未保存修改"} description={confirm==="publish"?"发布首页编排、关于与公共说明。来源可见性会再次核对，来源对象及读者私人记录不会改变。":"恢复至本次打开或最近保存的版本，未保存的首页与公共说明输入会被放弃。"} confirmLabel={confirm==="publish"?"确认发布":"放弃未保存修改"} pending={editor.busy} onCancel={()=>setConfirm(null)} onConfirm={async()=>{if(confirm==="publish")await editor.persist(true);else if(saved){setDraft(saved);setCache({});setCovers({});}setConfirm(null);}}/>
    <p className={styles.footnote}><Check size={13}/>所有修改先保存为草稿，确认发布后才改变公开页面。</p>
  </main>;
}
