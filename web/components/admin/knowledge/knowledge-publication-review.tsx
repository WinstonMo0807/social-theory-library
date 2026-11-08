"use client";

import {useCallback,useEffect,useRef,useState} from "react";
import {useSearchParams} from "next/navigation";
import {AlertCircle,AlertTriangle,Info,Monitor,Smartphone,ExternalLink} from "lucide-react";
import {apiRequest,getServerSessionCredential,subscribeToSessionChanges} from "@/lib/api";
import {withPrivateOwner} from "@/lib/api/private-owner";
import {useAdminSession} from "@/lib/admin-session";
import {safeAdminHref} from "@/lib/admin-route-context";
import type {KnowledgePreviewPayload} from "../preview/knowledge-page-preview";
import {KnowledgePublishControl,knowledgePublicationTargets} from "./knowledge-publish-control";
import styles from "../curation/issue-publication.module.css";

const date=(value:string|undefined)=>value?new Date(value).toLocaleString("zh-CN"):"尚无记录";
const labels:Record<string,string>={name:"名称",title:"标题",canonical_name_zh:"中文名称",canonical_name_en:"原文名称",foreign_name:"原文名称",slug:"页面路径",description:"说明",summary:"概述",definition:"定义",introduction:"导言",person:"人物",preferred_name:"姓名",short_description:"人物简介",biography:"传记",affiliations:"机构",key_concerns:"研究关注",core_questions:"核心问题",basic_propositions:"基本命题",theoretical_boundary:"理论边界",start_year:"开始年份",end_year:"结束年份",period_label:"时期",direct_relations:"条目关系",representative_scholars:"代表学者",topic_links:"主题",subdiscipline_links:"子学科",curated_claims:"原文策展",core_viewpoint:"核心观点",major_criticism:"主要批评",major_response:"主要回应",debate_position:"争论立场",work_groups:"馆藏分组",works:"作品",scholars:"学者",topics:"主题",articles:"策划文章",paths:"阅读路径",evidence:"原文",questions:"问题",concepts:"概念",stages:"阶段",items:"条目",audience:"目标读者",learning_goal:"学习目标",formation_period:"形成时期",research_object:"研究对象",research_directions:"研究方向",methods:"研究方法",representative_issues:"代表议题",theories:"理论",curated:"人工编排",knowledge_nodes:"知识节点",text:"文字",quote:"引文",reason:"推荐理由",label:"名称",page:"页码",page_number:"页码",printed_page_label:"印刷页码",chapter_title:"章节",source_label:"出处",source_url:"出处链接",credit:"署名",license:"许可",rights:"使用说明",alt_text:"图片说明",hero_image:"主视觉",hero_media:"主视觉版本",cover_asset:"封面",cover_media:"封面版本",portrait:"肖像",portrait_media:"肖像版本",work_count:"作品数",scholar_count:"学者数",theory_count:"理论数",subdiscipline_count:"子学科数",topic_count:"主题数"};
function content(value:unknown,depth=0):string{
  if(value==null||value==="")return "未填写";
  if(typeof value==="boolean")return value?"是":"否";
  if(typeof value!=="object")return String(value);
  if(Array.isArray(value))return value.length?value.map((row,index)=>`${index+1}. ${content(row,depth+1)}`).join("\n"):"暂无条目";
  const rows=Object.entries(value).filter(([key])=>!(["id","created_at","updated_at","url","api_url","preview_url"].includes(key)||key.endsWith("_id")));
  if(!rows.length)return "无可展示文字，请核对完整预览";
  return rows.map(([key,row])=>`${labels[key]?labels[key]+"：":""}${content(row,depth+1)}`).join(depth?"\n":"\n\n");
}
type Saved={id:string;edit_version:string;[key:string]:unknown};
type Review={saved:Saved;payload:KnowledgePreviewPayload};
type FrameState="loading"|"ready"|"error";

function ReaderViewport({src,owner,objectType,objectId,version,pageId,device,onState}:{src:string;owner:string;objectType:string;objectId:string;version:string;pageId:string;device:string;onState:(state:FrameState)=>void}){
  const container=useRef<HTMLDivElement|null>(null),frame=useRef<HTMLIFrameElement|null>(null),[available,setAvailable]=useState(390);
  useEffect(()=>{const node=container.current;if(!node)return;const observer=new ResizeObserver(entries=>setAvailable(entries[0].contentRect.width));observer.observe(node);return()=>observer.disconnect();},[]);
  useEffect(()=>{
    const timer=window.setTimeout(()=>onState("error"),35000);
    function receive(event:MessageEvent){
      const value=event.data;
      if(event.origin!==window.location.origin||event.source!==frame.current?.contentWindow||value?.type!=="stl:knowledge-publication-preview"||value.owner!==owner||value.objectType!==objectType||value.objectId!==objectId||value.version!==version||value.pageId!==pageId)return;
      if(value.state==="loading"){onState("loading");return;}
      window.clearTimeout(timer);onState(value.ok&&value.state==="ready"?"ready":"error");
    }
    window.addEventListener("message",receive);return()=>{window.clearTimeout(timer);window.removeEventListener("message",receive);};
  },[owner,objectType,objectId,version,pageId,onState]);
  const width=device==="mobile"?390:1180,height=850,scale=Math.min(1,available/width);
  return <div className={styles.viewport} ref={container} style={{height:height*scale}}><iframe ref={frame} title="已保存内容的页面预览" src={src} data-device={device} style={{width,height,transform:`scale(${scale})`,marginLeft:Math.max(0,(available-width*scale)/2)}}/></div>;
}

export function KnowledgePublicationReview(props:{objectType:string;objectId:string}){
  const owner=useAdminSession()?.id,params=useSearchParams();
  return <ReviewPage key={`${owner}:${props.objectType}:${props.objectId}:${params.get("edit_version")||""}`} {...props}/>;
}
function ReviewPage({objectType,objectId}:{objectType:string;objectId:string}){
  const user=useAdminSession(),owner=user?String(user.id):"",params=useSearchParams(),target=knowledgePublicationTargets[objectType];
  const [data,setData]=useState<Review|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState(""),[attempt,setAttempt]=useState(0),[latest,setLatest]=useState(false);
  const [tab,setTab]=useState("preview"),[device,setDevice]=useState("desktop"),[pageId,setPageId]=useState("overview"),[unchanged,setUnchanged]=useState(false),[frameState,setFrameState]=useState<FrameState>("loading"),[locked,setLocked]=useState(true);
  const returnHref=safeAdminHref(params.get("return_to"),`/admin/knowledge?selected_type=${encodeURIComponent(objectType)}&selected_id=${encodeURIComponent(objectId)}`);
  const locate=(section:string)=>{const url=new URL(returnHref,"https://admin.invalid");url.searchParams.set("section",section);return `${url.pathname}${url.search}${url.hash}`;};
  const expected=latest?"":params.get("edit_version")||"";
  useEffect(()=>{
    const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    const request=<T,>(url:string)=>withPrivateOwner(owner,()=>apiRequest<T>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential()),signal);
    const unsubscribe=subscribeToSessionChanges(()=>{controller.abort();setData(null);setLoading(false);setError("账户已变化，请重新打开当前对象的发布检查。");setFrameState("error");});
    queueMicrotask(()=>{if(controller.signal.aborted)return;setData(null);setLoading(true);setError("");setFrameState("loading");});
    void (async()=>{
      if(!target||!owner)throw Error("当前对象不支持此发布检查，请返回原编辑页。");
      const endpoint=`/catalog/admin/${target.endpoint}/${objectId}/`,saved=await request<Saved>(endpoint);
      if(saved.id!==objectId||!/^[a-f0-9]{64}$/.test(saved.edit_version||""))throw Error("保存记录不完整，请返回编辑页核对。");
      if(expected&&saved.edit_version!==expected)throw Error("保存内容已变化。请核对最新保存版本后重新检查。");
      const payload=await request<KnowledgePreviewPayload>(`/catalog/admin/knowledge-preview/${objectType}/${objectId}/?${new URLSearchParams({edit_version:saved.edit_version,review:"1"})}`);
      const current=await request<Saved>(endpoint);
      if(payload.object_type!==objectType||payload.object_id!==objectId||payload.edit_version!==saved.edit_version||current.id!==objectId||current.edit_version!==saved.edit_version||!payload.publication_review)throw Error("检查期间版本发生变化或检查资料不完整，请重新读取。");
      if(!controller.signal.aborted)setData({saved,payload});
    })().catch(reason=>{if(!controller.signal.aborted){setData(null);setError(reason instanceof Error?reason.message:"发布检查暂不可用。");}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>{controller.abort();unsubscribe();};
  },[owner,target,objectType,objectId,expected,attempt]);
  const reload=useCallback(()=>{setData(null);setFrameState("loading");setLoading(true);setLatest(true);setAttempt(n=>n+1);},[]);
  const report=data?.payload.publication_review,version=data?.saved.edit_version||"";
  const frame=`/admin/preview/knowledge/${objectType}/${objectId}?${new URLSearchParams({frame:"1",edit_version:version,page:pageId,return_to:returnHref})}`;
  const blockedReason=loading?"正在读取保存版本与发布检查…":error?"检查未完成，请处理上方问题后重新读取。":!report?"完整检查资料尚未返回。":!report.has_draft?"当前没有待发布草稿。":report.blocking_count?`请先处理 ${report.blocking_count} 项发布阻断。`:frameState!=="ready"?frameState==="error"?"页面预览未能确认，请重新检查。":"请等待当前保存版本的页面预览完成。":"";
  const changes=report?.changes.filter(row=>unchanged||row.changed)||[];
  return <main className={styles.review}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><a href="/admin/knowledge">学者与知识</a><span>›</span><a href={returnHref}>页面编排</a><span>› 预览与发布</span></nav>
    <header className={styles.heading}><div><h1>预览与发布</h1></div><div className={styles.actions}><span>{report?.has_draft?"已保存未发布":"已保存版本"}</span><a href={returnHref}>返回编辑</a>{!locked?<a href={`/admin/publication/knowledge/${objectType}/${objectId}?${new URLSearchParams({return_to:returnHref})}`}>版本历史</a>:null}<button type="button" disabled={loading||locked} onClick={reload}>重新检查最新保存版本</button></div></header>
    <nav className={styles.tabs} aria-label="发布检查视图">{[["preview","页面预览"],["changes","版本变化"],["checks","发布检查"],["settings","发布设置"]].map(([key,label],index)=><button type="button" key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}><span>0{index+1}</span>{label}{key==="checks"&&report?`（${report.blocking_count}项阻断，${report.warning_count}项提醒）`:""}</button>)}</nav>
    {error?<p className={styles.warning} role="alert">{error} 已保存内容保留。</p>:null}{loading?<p role="status">正在读取已保存内容、公开版本与发布检查…</p>:null}
    <div className={styles.columns} data-tab={tab}>
      <section className={styles.panel} hidden={tab!=="preview"||!data}><header><div><h2>页面预览</h2><p>{data?.payload.label} · 当前保存版本</p></div><a href={frame} target="_blank" rel="noopener">在新标签页打开 <ExternalLink size={13}/></a></header>
        <nav className={styles.devices} aria-label="预览设备"><button type="button" aria-pressed={device==="desktop"} onClick={()=>setDevice("desktop")}><Monitor size={17}/>桌面端</button><button type="button" aria-pressed={device==="mobile"} onClick={()=>setDevice("mobile")}><Smartphone size={17}/>移动端</button></nav>
        {(data?.payload.public_control?.page_tree?.length||0)>1?<label>预览页面 <select data-stl-select value={pageId} disabled={locked} onChange={event=>{setFrameState("loading");setPageId(event.target.value);}}>{data?.payload.public_control?.page_tree?.filter(page=>page.preview?.supported!==false).map(page=><option key={page.page_id} value={page.page_id}>{page.display_name}</option>)}</select></label>:null}
        {data?<ReaderViewport key={`${frame}:${attempt}`} src={frame} owner={owner} objectType={objectType} objectId={objectId} version={version} pageId={pageId} device={device} onState={setFrameState}/>:null}
        {data&&frameState!=="ready"?<p role={frameState==="error"?"alert":"status"}>{frameState==="error"?"预览读取失败或超时，请重新检查。":"正在等待同一保存版本的预览…"}</p>:null}
        <p>预览中的读者操作已停用。页面和关联资料仍按各自公开规则展示。</p>
      </section>
      <aside>
        <section className={styles.panel} hidden={!report||!["preview","changes"].includes(tab)}><header><h2>版本对比{tab==="preview"?"摘要":""}</h2>{tab==="preview"?<button type="button" onClick={()=>setTab("changes")}>查看完整对比 →</button>:<label><input type="checkbox" checked={unchanged} onChange={event=>setUnchanged(event.target.checked)}/>显示未变化项</label>}</header><p>当前正式修订：{report?.current_revision||"尚无记录"} · 最近保存：{date(report?.saved_at)}</p><div className={styles.table}><table><caption className="sr-only">公开内容与已保存稿的页面字段对比</caption><thead><tr><th scope="col">对比项</th><th scope="col">当前公开版</th><th scope="col">已保存稿</th></tr></thead><tbody>{(tab==="preview"?changes.slice(0,4):changes).map(row=><tr key={row.key}><th scope="row">{row.label}<small>{row.changed?"有变化":"未变化"}</small></th><td>{tab==="preview"?content(row.before).slice(0,110):<pre>{content(row.before)}</pre>}</td><td data-changed={row.changed||undefined}>{tab==="preview"?content(row.after).slice(0,110):<pre>{content(row.after)}</pre>}</td></tr>)}</tbody></table></div>{!changes.length?<p>页面字段没有变化，可勾选显示未变化项继续核对。</p>:null}<p>这里只比较页面内容。来源和关系的变更请到各自编辑页核对。</p></section>
        <section className={styles.panel} hidden={!report||!["preview","checks"].includes(tab)}><header><h2>发布检查 <span>{report?.blocking_count}项阻断，{report?.warning_count}项提醒</span></h2><button type="button" onClick={()=>setTab("checks")}>全部展开 →</button></header>{report?.checks.map(row=>{const Icon=row.severity==="blocking"?AlertCircle:row.severity==="warning"?AlertTriangle:Info;return <article className={styles.check} key={row.code} data-severity={row.severity}><Icon size={18}/><div><h3>{row.title}</h3><p>{row.detail}</p></div><a href={locate(row.section)}>定位 →</a></article>;})}</section>
        <section className={styles.panel} hidden={!["preview","settings"].includes(tab)}><header><h2>发布设置</h2><a href={locate("publication")}>编辑</a></header><dl><dt>发布范围</dt><dd>{report?.withdrawing?"按保存的修订撤回公开展示":"公开（所有读者可见）"}</dd><dt>本次操作人</dt><dd>{report?.actor_label||"当前编辑账户"}</dd><dt>发布时间</dt><dd>确认后按原发布流程生效</dd><dt>最近保存</dt><dd>{date(report?.saved_at)}</dd><dt>检查时间</dt><dd>{date(report?.checked_at)}</dd></dl>
          <KnowledgePublishControl objectType={objectType} objectId={objectId} savedRecord={data?.saved||{}} dirty={false} onLockChange={setLocked} onPublished={reload} blockedReason={blockedReason} embedded/>
          <p>修改请返回编辑器保存。发布时会再次校验原修订；关联对象、原文和检索任务分别保持各自状态。</p>
        </section>
      </aside>
    </div>
  </main>;
}
