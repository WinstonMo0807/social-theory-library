"use client";

import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowUpRight, FileText, History, RefreshCw, ChevronDown, ChevronRight, MoreHorizontal, Info } from "lucide-react";
import { ApiRequestError, apiRequest, getServerSessionCredential, normalizePublicResourceUrl, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import type { components } from "@/lib/api/generated/schema";
import type { CatalogPublication } from "@/lib/api/admin-collections";
import { publicationPresentation } from "@/lib/api/admin-collections";
import { PublicationDiff } from "./publication-diff";
import { PublicationRetryControl } from "./publication-retry-control";
import { Dialog } from "@/components/ui/dialog";
import styles from "./publication-ledger.module.css";
import { PublicationReview } from "./publication-review";
import { withAdminReturn } from "@/lib/admin-route-context";

type Revision = components["schemas"]["PublicationDeskRevision"];
export type PublicationDeskData = Omit<components["schemas"]["PublicationDesk"], "publication"> & {publication:CatalogPublication};
type Desk = PublicationDeskData;
type Pending = {version:1;owner:string;edition:string;kind:string;url:string;body:string;at:number};
const stateNames:Record<string,string>={preparing:"准备发布",active:"曾公开",superseded:"历史公开版",failed:"处理失败",withdrawn:"撤回记录",pending:"待处理",processing:"处理中",completed:"已完成",dead_letter:"需人工处理"};
const date=(value:string|null|undefined)=>value?new Date(value).toLocaleString("zh-CN"):"尚无记录";

function PublicationCover({editionId,request}:{editionId:string;request:<T>(url:string,init?:RequestInit)=>Promise<T>}) {
  const [image,setImage]=useState(""),[message,setMessage]=useState("正在读取封面");
  useEffect(()=>{const controller=new AbortController();void request<{image_url:string}>(`/catalog/admin/editions/${editionId}/cover/`,{signal:controller.signal}).then(value=>{if(!controller.signal.aborted){setImage(normalizePublicResourceUrl(value.image_url));setMessage("暂无可用封面");}}).catch(()=>{if(!controller.signal.aborted)setMessage("封面暂不可读");});return()=>controller.abort();},[editionId,request]);
  return image?<img src={image} alt="当前保存的馆藏封面" onError={()=>{setImage("");setMessage("封面已变化或暂不可读");}}/>:<div className={styles.noCover}><FileText size={30}/><span>{message}</span></div>;
}

export function PublicationLedger({editionId,backHref,onChanged,view="desk"}:{editionId:string;backHref:string;onChanged?:()=>void;view?:"desk"|"review"}) {
  const user=useAdminSession(),owner=user?String(user.id):"",key=`stl:publication-command:v1:${owner}:${editionId}`;
  const lifetime=useRef<AbortController|null>(null),acting=useRef(false);
  const [data,setData]=useState<Desk|null>(null),[error,setError]=useState(""),[loading,setLoading]=useState(true),[attempt,setAttempt]=useState(0);
  const [page,setPage]=useState(1),[impactPage,setImpactPage]=useState(1),[selected,setSelected]=useState(""),[tab,setTab]=useState("history");
  const [action,setAction]=useState<{kind:"publish"|"withdraw"|"restore";revision?:Revision;version:string;fingerprint:string}|null>(null),[reason,setReason]=useState(""),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(""),[pending,setPending]=useState<Pending|null>(null);
  const request=useCallback(async<T,>(url:string,init:RequestInit={}):Promise<T>=>{
    const signal=AbortSignal.any([lifetime.current!.signal,...(init.signal?[init.signal]:[]),AbortSignal.timeout(30000)]);
    return withPrivateOwner(owner,()=>apiRequest<T>(url,{...init,signal,headers:{...init.headers,"X-Editor-Owner":owner}},getServerSessionCredential()),signal);
  },[owner]);
  useEffect(()=>{
    const controller=new AbortController();lifetime.current=controller;
    queueMicrotask(()=>{if(controller.signal.aborted)return;try{const stored=JSON.parse(sessionStorage.getItem(key)||"null") as Pending|null;if(stored&&stored.version===1&&stored.owner===owner&&stored.edition===editionId&&Number.isFinite(stored.at)&&stored.at>0&&stored.at<8640000000000000&&typeof stored.body==="string"&&typeof stored.url==="string"&&["publish","withdraw","restore"].includes(stored.kind))setPending(stored);}catch{setMessage("未能读取本标签页操作记录，请先核对版本历史。");}});
    const unsubscribe=subscribeToSessionChanges(()=>{controller.abort();setData(null);setError("账户已变化，请重新进入发布台。");try{sessionStorage.removeItem(key);}catch{/* The original command is still in memory. */}});
    return()=>{controller.abort();unsubscribe();};
  },[key,owner,editionId]);
  useEffect(()=>{
    if(!owner)return;const controller=new AbortController();
    queueMicrotask(()=>{if(!controller.signal.aborted){setLoading(true);setError("");}});
    const query=new URLSearchParams({view:"review",page:String(page),impact_page:String(impactPage)});if(selected)query.set("revision",selected);
    void request<Desk>(`/catalog/admin/editions/${editionId}/publication/history/?${query}`,{signal:controller.signal}).then(value=>{if(value.edition_id!==editionId)throw Error("记录不属于选定版本，已停止显示。");if(!controller.signal.aborted)setData(value);}).catch(failure=>{if(!controller.signal.aborted)setError(failure instanceof Error?failure.message:"发布记录暂不可读。");}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});return()=>controller.abort();
  },[owner,editionId,page,impactPage,selected,attempt,request,view]);
  function clearPending(){setPending(null);try{sessionStorage.removeItem(key);}catch{setMessage("浏览器操作记录未能清除，重新打开时请核对历史。");}}
  async function send(command:Pending){
    if(acting.current||lifetime.current?.signal.aborted||!data)return;
    try{
      const body=JSON.parse(command.body),uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
      const expectedUrl=command.kind==="restore"?`/catalog/admin/editions/${editionId}/publication/rollback/`:`/catalog/admin/library/works/${data.work_id}/publication/?edition=${editionId}`;
      if(command.owner!==owner||command.edition!==editionId||command.url!==expectedUrl||!/^[0-9a-f]{64}$/.test(body.expected_version)||
        (command.kind==="restore"? !uuid.test(body.request_key)||!uuid.test(body.revision_id)||typeof body.reason!=="string":body.edition_id!==editionId||body.action!==command.kind||!/^[0-9a-f]{64}$/.test(body.prepared_fingerprint)))throw Error("invalid");
    }catch{setMessage("暂存请求与当前版本不一致，已停止发送。请核对记录后清除待确认状态。");return;}
    acting.current=true;setBusy(true);setMessage("");setPending(command);setAction(null);
    try{sessionStorage.setItem(key,JSON.stringify(command));}catch{setMessage("浏览器无法保留操作回执；本次未发送，请保持页面并恢复存储后重试。");acting.current=false;setBusy(false);return;}
    try{await request(command.url,{method:"POST",body:command.body});if(lifetime.current?.signal.aborted)return;clearPending();setReason("");setMessage(command.kind==="withdraw"?"撤回命令已确认，原文件与历史保留；索引退出状态请继续核对。":"命令已接受。请核对当前公开版本和后台处理结果，接受请求不代表所有处理已经完成。");setAttempt(n=>n+1);}
    catch(failure){if(!lifetime.current?.signal.aborted){if(!(failure instanceof PrivateOwnerVerificationError)&&failure instanceof ApiRequestError&&failure.status>0&&failure.status<500){clearPending();setMessage(`${failure.message} 已保存内容保留，请重新检查后继续。`);}else setMessage("暂时无法确认操作结果。请先刷新历史核对，或重试同一请求，不要重新提交另一份操作。");setAttempt(n=>n+1);}}
    finally{acting.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  function start(kind:"publish"|"withdraw"|"restore",revision?:Revision){if(!data)return;setAction({kind,revision,version:data.version,fingerprint:data.preparation.fingerprint});setReason("");setConfirmed(false);}
  function submit(){
    if(!data||!action||action.version!==data.version||action.fingerprint!==data.preparation.fingerprint||busy||pending||!confirmed||action.kind!=="publish"&&!reason.trim())return;
    const body=action.kind==="restore"?{revision_id:action.revision!.id,request_key:createRequestKey(),reason:reason.trim(),expected_version:data.version}:{action:action.kind,edition_id:editionId,prepared_fingerprint:data.preparation.fingerprint,expected_version:data.version,confirm_warnings:true,...(action.kind==="withdraw"?{reason:reason.trim()}:{} )};
    const url=action.kind==="restore"?`/catalog/admin/editions/${editionId}/publication/rollback/`:`/catalog/admin/library/works/${data.work_id}/publication/?edition=${editionId}`;
    void send({version:1,owner,edition:editionId,kind:action.kind,url,body:JSON.stringify(body),at:Date.now()});
  }
  const locked=busy||loading||Boolean(error)||Boolean(pending),canPublish=hasAdminCapability(user,"can_publish_work"),canWithdraw=hasAdminCapability(user,"can_withdraw_work");
  const status=publicationPresentation(data?.publication),current=data?.review?.current||data?.history.results.find(row=>row.is_current);
  const [collapsed,setCollapsed]=useState<Record<string,boolean>>({});
  const collapse=(key:string,label:string)=><button type="button" className={styles.collapse} aria-expanded={!collapsed[key]} aria-label={label} onClick={()=>setCollapsed(value=>({...value,[key]:!value[key]}))}><ChevronDown size={15}/></button>;
  const hasSavedChanges=Boolean(data?.preparation.changes.some(row=>row.change!=="unchanged"));
  const savedField=(name:string)=>data?.preparation.changes.find(row=>row.field===name)?.after_display||"";
  const impacts=data?<>{data.impacts.map(row=><article className={styles.impact} key={row.title}><FileText size={16}/><div><h3>{row.title}</h3><p>{row.detail}</p></div>{row.href?<Link href={row.href}>查看 <ChevronRight size={12}/></Link>:null}</article>)}<p className={styles.scopeNote}>{data.notice}</p></>:null;
  return <div className={styles.ledger} data-publication-view={view}>
    <nav className={styles.breadcrumb}><Link href={backHref} onClick={onChanged}><ArrowLeft size={14}/>{view==="review"?"返回原工作页":"返回发布列表"}</Link><span>内容 › 发布台{view==="review"?" › 发布前检查":""}</span></nav>
    <header className={styles.heading}><div><h1>{view==="review"?"发布前检查":"发布台、历史与撤回"}</h1><p>{view==="review"?`确认公开页、索引与 Reader 版本后，再发布当前草稿。${data?` ${data.preparation.blocking.length} 项阻断 · ${data.preparation.warnings.length} 项提醒`:""}`:"管理当前公开版本，知道变更会影响哪些读者页面。"}</p></div><button type="button" disabled={busy||loading} onClick={()=>setAttempt(n=>n+1)}><RefreshCw size={15}/>重新检查</button></header>
    {message?<p role="status" className={styles.notice}>{message}</p>:null}{pending?<section className={styles.warning}><h2>这次操作结果尚需核对</h2><p>请求保存于 {date(new Date(pending.at).toISOString())}。页面保留原请求，重试沿用相同内容与版本。</p><button type="button" disabled={busy||loading||!data||Boolean(error)} onClick={()=>void send(pending)}>重试原请求</button><button type="button" disabled={busy||loading} onClick={()=>{if(window.confirm("已核对最新版本与操作记录，确定清除本标签页的待确认记录吗？这不会撤销服务端操作。"))clearPending();}}>已核对结果，清除待确认记录</button></section>:null}
    {error?<p role="alert" className={styles.warning}>{error}<button type="button" onClick={()=>{setPage(1);setSelected("");setAttempt(n=>n+1);}}>返回第一页重试</button></p>:null}{loading?<p role="status">正在核对公开版本、历史与影响…</p>:null}
    {data&&!error&&view==="review"&&!loading?<PublicationReview key={`${data.version}:${data.checked_at}`} data={data} cover={<PublicationCover editionId={editionId} request={request}/>} locked={locked} canPublish={canPublish} onPublish={()=>start("publish")}/>:null}
    {data&&!error&&view==="desk"?<><section className={styles.object} aria-busy={loading} data-collapsed={collapsed.object||undefined}><div><header><h2>待发布对象</h2>{collapse("object","展开或收起待发布对象")}</header><div className={styles.book}><PublicationCover key={data.version} editionId={editionId} request={request}/><div><h3>{data.title}</h3><p>{data.authors||"责任者待确认"}</p>{savedField("publication_year")||savedField("publisher")?<p>{[savedField("publication_year"),savedField("publisher")].filter(Boolean).join(" · ")}</p>:null}<Link href={data.workbench_url}>查看详情 <ArrowUpRight size={13}/></Link></div></div></div><dl><dt>当前公开状态</dt><dd>{status.label}</dd><dt>当前公开修订</dt><dd>{current?`第 ${current.revision} 次发布` : data.publication.catalog_revision_active?"当前公开修订不在本页历史中":"尚无有效公开修订"}</dd><dt>最近保存</dt><dd>{date(data.review?.saved_at)}</dd><dt>历史记录</dt><dd>{data.history.count} 次</dd></dl><aside><h3>当前状态：<span className={styles.badge} data-state={hasSavedChanges?"draft":data.publication.public_state}>{hasSavedChanges?"已保存未发布":status.label}</span></h3><p>{data.publication.detail}</p><Link className={styles.primary} href={withAdminReturn(`/admin/publication/${editionId}?object=edition`,backHref)}>按授权发布</Link><button type="button" disabled={busy} onClick={()=>setTab("impact")}>检查影响范围</button><Link href={data.preview_url} target="_blank">真实公开样式预览 ↗</Link></aside></section>
    <nav className={styles.tabs} aria-label="发布记录视图">{[["history","版本历史"],["impact","影响范围"],["dependencies","引用依赖"]].map(([id,label])=><button type="button" key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    {tab==="history"?<section className={styles.panel} data-section="history"><div className={styles.table}><table><caption className="sr-only">正式发布修订记录</caption><thead><tr><th>版本</th><th>状态</th><th>发布说明</th><th>操作人 / 时间</th><th>操作</th></tr></thead><tbody>{hasSavedChanges?<tr data-draft="true"><th scope="row">已保存稿</th><td><span className={styles.badge} data-state="draft">已保存未发布</span></td><td>{data.review?.note||data.preparation.changes.filter(row=>row.change!=="unchanged").map(row=>row.label).join("、")}</td><td>{data.review?.saved_by||"未记录操作人"}<time>{date(data.review?.saved_at)}</time></td><td><div className={styles.actions}><Link className={styles.primary} href={withAdminReturn(`/admin/publication/${editionId}?object=edition`,backHref)}>按授权发布</Link><details className={styles.more}><summary aria-label="保存稿操作"><MoreHorizontal size={15}/></summary><div><Link href={data.workbench_url}>返回编辑</Link><Link href={data.preview_url} target="_blank">预览</Link></div></details></div></td></tr>:null}{data.history.results.map(row=><tr key={row.id} data-selected={selected===row.id||undefined}><th scope="row">第 {row.revision} 次</th><td><span className={styles.badge} data-state={row.is_current?"active":row.status}>{row.is_current?"当前公开":stateNames[row.status]||"状态待核对"}</span></td><td>{row.note||row.changed_fields.join("、")||"未填写说明"}</td><td>{row.created_by||"未记录操作人"}<time>{date(row.activated_at||row.created_at)}</time></td><td><div className={styles.actions}><button type="button" disabled={busy} onClick={()=>setSelected(row.id)}>查看 <ChevronRight size={12}/></button>{row.can_rollback?<button type="button" disabled={locked||!canPublish} onClick={()=>start("restore",row)}>恢复</button>:null}{row.is_current?<button type="button" disabled={locked||!canWithdraw} onClick={()=>start("withdraw")}>撤回</button>:null}</div></td></tr>)}</tbody></table></div>{!data.history.count?<p>尚无正式发布记录，已保存草稿仍在原编辑工作台。</p>:null}<nav className={styles.pagination} aria-label="版本历史分页"><button type="button" disabled={locked||page<=1} onClick={()=>setPage(n=>n-1)}>上一页</button><span>第 {data.history.page} / {data.history.pages} 页</span><button type="button" disabled={locked||page>=data.history.pages} onClick={()=>setPage(n=>n+1)}>下一页</button></nav></section>:null}
    {tab==="impact"?<section className={styles.panel}><h2>影响范围</h2>{impacts}</section>:null}
    {tab==="dependencies"?<section className={styles.panel}><h2>引用依赖与阅读记录</h2><p>{data.dependencies.notice}</p><p>馆藏证据 {data.dependencies.summary.catalog_evidence} 条 · 私人批注 {data.dependencies.summary.reader_annotations} 条 · 书签 {data.dependencies.summary.reader_bookmarks} 条 · 阅读位置 {data.dependencies.summary.reader_progress} 条</p><p>这里列出已建立的馆藏证据，暂不等同于所有文章的完整引用网络。</p>{data.dependencies.results.map(row=><article className={styles.impact} key={row.id}><div><h3>{row.title}</h3><p>PDF {row.file_page_index??"页码待核对"}{row.printed_page_label?` · 印刷页 ${row.printed_page_label}`:""}</p></div><Link href={row.href}>核对来源 ↗</Link></article>)}{!data.dependencies.count?<p>当前版本尚无已登记的馆藏证据。</p>:null}<nav className={styles.pagination} aria-label="引用依赖分页"><button type="button" disabled={locked||impactPage<=1} onClick={()=>setImpactPage(n=>n-1)}>上一页</button><span>共 {data.dependencies.count} 条</span><button type="button" disabled={locked||impactPage*data.dependencies.page_size>=data.dependencies.count} onClick={()=>setImpactPage(n=>n+1)}>下一页</button></nav></section>:null}
    {data.selected?<section className={styles.panel}><header><h2>历史修订 {data.selected.revision.revision}</h2><button type="button" onClick={()=>setSelected("")}>关闭历史对比</button></header><p>{data.selected.notice}</p><PublicationDiff value={{...data.preparation,changes:data.selected.changes}} showChecks={false} title="历史修订与当前公开版" afterLabel="选定历史修订"/></section>:null}
    <div className={styles.columns}><section className={styles.panel} data-collapsed={collapsed.diff||undefined}><header><h2>版本差异对比</h2>{collapse("diff","展开或收起版本差异")}</header><PublicationDiff value={data.preparation} compact showChecks={false}/><Link className={styles.fullDiff} href={withAdminReturn(`/admin/publication/${editionId}?object=edition`,backHref)}>查看完整对比 <ChevronRight size={13}/></Link></section><section className={styles.panel} data-collapsed={collapsed.impact||undefined}><header><h2>影响范围</h2><button type="button" disabled={busy||loading} onClick={()=>setAttempt(n=>n+1)}><RefreshCw size={13}/>重新检查</button>{collapse("impact","展开或收起影响范围")}</header><p className={styles.information}><Info size={14}/>将按本次保存内容更新以下关联位置。</p>{impacts}</section></div>
    <details className={styles.eventPanel} open={Boolean(data.events.some(row=>["failed","dead_letter"].includes(row.status)))}><summary>操作结果与状态 <ChevronDown size={14}/></summary><div>{data.events.map(row=><article className={styles.event} key={row.id} data-state={row.status}><History size={15}/><div><strong>{row.action} · 第 {row.revision} 次</strong><p>{stateNames[row.status]||"状态待核对"} · {row.actor||"系统"}</p><time>{date(row.processed_at||row.created_at)}</time><p>{row.detail}</p></div></article>)}{!data.events.length?<p>尚无发布任务记录。</p>:null}{data.events_limited?<p>这里只列最近 20 项任务，更多记录在原工作台核对。</p>:null}<PublicationRetryControl request={request} editionId={editionId} token={getServerSessionCredential()} disabled={locked} refreshKey={data.version} onCompleted={()=>setAttempt(n=>n+1)}/></div></details>
    {data.publication.public_state==="withdrawn"?<p className={styles.notice}>当前版本已撤回。若需重新公开，请核对当前草稿与授权后明确发布；历史回滚不会自动恢复已撤回的关联对象。</p>:null}</>:null}
    <Dialog open={Boolean(action)} onRequestClose={()=>setAction(null)} className={styles.dialog} aria-label="确认发布操作"><h2>{action?.kind==="withdraw"?"撤回当前公开版本":action?.kind==="restore"?`恢复第 ${action.revision?.revision} 次公开修订`:"发布已检查的保存版本"}</h2><p>{action?.kind==="withdraw"?"读者将不能访问此版本的公开内容，关联阅读与引用可能受影响。原文件和历史记录保留。":action?.kind==="restore"?"根据此历史内容创建新发布修订，保留当前草稿与原文件。处理完成前继续服务当前公开内容；其他已撤回对象不会一并恢复。":"保存内容将进入原发布流程。页面与索引分开核对，原公开内容在新修订生效前继续服务。"}</p>{action?.kind!=="publish"?<label>操作原因<textarea value={reason} maxLength={1000} onChange={event=>setReason(event.target.value)}/></label>:data?.preparation.warnings.length?<ul>{data.preparation.warnings.map(item=><li key={item}>{item}</li>)}</ul>:null}{action&&data&&(action.version!==data.version||action.fingerprint!==data.preparation.fingerprint)?<p role="alert">内容已经变化，请关闭确认并重新检查。</p>:null}<label className={styles.confirm}><input type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}/>已核对当前版本、授权、影响范围与提醒</label><div className={styles.actions}><button type="button" onClick={()=>setAction(null)}>返回核对</button><button type="button" className={styles.primary} disabled={locked||action?.version!==data?.version||action?.fingerprint!==data?.preparation.fingerprint||!confirmed||action?.kind!=="publish"&&!reason.trim()} onClick={submit}>确认{action?.kind==="withdraw"?"撤回":action?.kind==="restore"?"恢复":"发布"}</button></div></Dialog>
  </div>;
}
