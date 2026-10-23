"use client";

import { createRequestKey } from "../../../lib/request-key";
import {useCallback,useEffect,useRef,useState} from "react";
import {useSearchParams} from "next/navigation";
import {FileClock,RefreshCw} from "lucide-react";
import {apiRequest,ApiRequestError,getServerSessionCredential,subscribeToSessionChanges} from "@/lib/api";
import {PrivateOwnerVerificationError,withPrivateOwner} from "@/lib/api/private-owner";
import {useAdminSession} from "@/lib/admin-session";
import {safeAdminHref} from "@/lib/admin-route-context";
import {Dialog} from "@/components/ui/dialog";
import {knowledgePublicationTargets} from "./knowledge-publish-control";
import {PublicationRetryControl} from "../workflow/publication-retry-control";
import styles from "../workflow/publication-ledger.module.css";
import detail from "./knowledge-history.module.css";

type Row={id:string;revision:number;status:string;snapshot_public:boolean;matches_current:boolean;note:string;actor:string;created_at:string;published_at:string|null;can_restore:boolean};
type History={object_type:string;object_id:string;edit_version:string;title:string;status:string;is_public:boolean;has_draft:boolean;draft_id:string|null;can_withdraw:boolean;history:{count:number;page:number;pages:number;results:Row[]};selected:Row|null;changes:{field:string;label:string;before:unknown;after:unknown;changed:boolean}[];dependencies:{key:string;label:string;count:number}[];events:{id:string;actor:string;created_at:string;label:string;failures:string[];pending?:string[]}[];scope:string};
type Command={action:"withdraw"|"restore";request_key:string;expected_version:string;reason:string;source_revision_id?:string};
type Pending={format:1;owner:string;objectType:string;objectId:string;command:Command};
type Receipt={revision_id:string;revision:number;status:string;object_type:string;object_id:string;edit_version:string};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const labels:Record<string,string>={scholar:"学者",topic:"主题",discipline:"学科",subdiscipline:"子学科",reading_path:"阅读路径",theory:"理论",concept:"概念",debate:"学术争论",research_problem:"研究问题"};
const date=(value:string|null)=>value?new Date(value).toLocaleString("zh-CN"):"尚无记录";
function state(row:Row){return row.status==="draft"?"已保存未发布":row.status==="superseded"?"已替代的草稿":row.matches_current&&row.snapshot_public?"与当前公开内容一致":row.status==="published"?(row.snapshot_public?"历史公开修订":"撤回修订"):row.status;}
function text(value:unknown):string {return value==null||value===""?"未填写":typeof value==="object"?JSON.stringify(value,null,2):typeof value==="boolean"?value?"是":"否":String(value);}
function valid(value:unknown,owner:string,objectType:string,objectId:string):value is Pending {
  if(!value||typeof value!=="object")return false;
  const pending=value as Partial<Pending>,command=pending.command;
  return pending.format===1&&pending.owner===owner&&pending.objectType===objectType&&pending.objectId===objectId&&Boolean(command&&uuid.test(command.request_key)&&/^[a-f0-9]{64}$/.test(command.expected_version)&&typeof command.reason==="string"&&command.reason.trim().length&&command.reason.length<=400&&(command.action==="withdraw"?command.source_revision_id===undefined:command.action==="restore"&&typeof command.source_revision_id==="string"&&uuid.test(command.source_revision_id)));
}

export function KnowledgeHistory(props:{objectType:string;objectId:string}) {
  const owner=useAdminSession()?.id;
  return <HistoryWorkspace key={`${owner}:${props.objectType}:${props.objectId}`} {...props}/>;
}

function HistoryWorkspace({objectType,objectId}:{objectType:string;objectId:string}) {
  const user=useAdminSession(),owner=user?String(user.id):"",target=knowledgePublicationTargets[objectType],params=useSearchParams();
  const returnHref=safeAdminHref(params.get("return_to"),`/admin/knowledge?selected_type=${objectType}&selected_id=${objectId}&section=versions`);
  const endpoint=`/catalog/admin/knowledge-publications/${objectType}/${objectId}/history/`,key=`stl:knowledge-history:v1:${owner}:${objectType}:${objectId}`;
  const lifetime=useRef<AbortController|null>(null),acting=useRef(false);
  const [data,setData]=useState<History|null>(null),[page,setPage]=useState(1),[selected,setSelected]=useState(""),[refresh,setRefresh]=useState(0),[loading,setLoading]=useState(true),[error,setError]=useState(""),[message,setMessage]=useState("");
  const [tab,setTab]=useState("history"),[allFields,setAllFields]=useState(false),[busy,setBusy]=useState(false),[pending,setPending]=useState<Pending|null>(null),[hydrated,setHydrated]=useState(false),[recordProblem,setRecordProblem]=useState(false);
  const [confirm,setConfirm]=useState<{action:"withdraw"|"restore";source?:Row;version:string}|null>(null),[reason,setReason]=useState(""),[agreed,setAgreed]=useState(false);
  const [clearOpen,setClearOpen]=useState(false),[clearAgreed,setClearAgreed]=useState(false);
  const request=useCallback(async<T,>(url:string,init:RequestInit={}):Promise<T>=>{
    const signal=AbortSignal.any([lifetime.current!.signal,...(init.signal?[init.signal]:[]),AbortSignal.timeout(30000)]);
    return withPrivateOwner(owner,()=>apiRequest<T>(url,{cache:"no-store",...init,signal,headers:{...init.headers,"X-Editor-Owner":owner}},getServerSessionCredential()),signal);
  },[owner]);
  useEffect(()=>{
    const controller=new AbortController();lifetime.current=controller;
    queueMicrotask(()=>{if(controller.signal.aborted)return;try{const value:unknown=JSON.parse(sessionStorage.getItem(key)||"null");if(value!==null){if(!valid(value,owner,objectType,objectId))throw Error();setPending(value);}}catch{setRecordProblem(true);setError("本标签页原操作记录不可读，请先核对历史记录，当前不能发起新操作。");}finally{setHydrated(true);}});
    const unsubscribe=subscribeToSessionChanges(()=>{controller.abort();setData(null);setConfirm(null);setClearOpen(false);setPending(null);setError("账户已变化，请重新进入版本历史。");try{sessionStorage.removeItem(key);}catch{/* Server history remains authoritative. */}});
    return()=>{controller.abort();unsubscribe();};
  },[key,owner,objectType,objectId]);
  useEffect(()=>{
    if(!owner||!target||!uuid.test(objectId)){queueMicrotask(()=>{setLoading(false);setError("当前对象不支持此版本历史，请返回原编辑页。");});return;}
    const controller=new AbortController();
    queueMicrotask(()=>{if(!controller.signal.aborted){setData(null);setLoading(true);setError("");}});
    const query=new URLSearchParams({page:String(page)});if(selected)query.set("selected",selected);
    request<History>(`${endpoint}?${query}`,{signal:controller.signal}).then(value=>{if(value.object_type!==objectType||value.object_id!==objectId||!/^[a-f0-9]{64}$/.test(value.edit_version))throw Error("历史记录与当前对象不一致，请重新读取。");if(!controller.signal.aborted)setData(value);}).catch(cause=>{if(!controller.signal.aborted){setData(null);setError(cause instanceof Error?cause.message:"暂时无法读取历史记录。");}}).finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[owner,target,objectId,objectType,endpoint,page,selected,refresh,request]);
  const reload=useCallback(()=>{setData(null);setLoading(true);setConfirm(null);setRefresh(value=>value+1);},[setData,setLoading,setConfirm,setRefresh]);
  const locked=busy||Boolean(pending)||recordProblem||!hydrated||loading||!data;
  const reviewHref=`/admin/preview/knowledge/${objectType}/${objectId}?${new URLSearchParams({review:"1",edit_version:data?.edit_version||"",return_to:returnHref})}`;
  const changes=data?.changes.filter(row=>allFields||row.changed)||[];
  function begin(action:"withdraw"|"restore",source?:Row){if(locked||!data)return;setReason("");setAgreed(false);setConfirm({action,source,version:data.edit_version});}
  function clear(){sessionStorage.removeItem(key);setPending(null);}
  async function send(value:Pending,recover=false){
    if(acting.current||!valid(value,owner,objectType,objectId))return;
    acting.current=true;setBusy(true);setMessage("");setError("");
    try{
      if(!recover){sessionStorage.setItem(key,JSON.stringify(value));setPending(value);}
      const receipt=await request<Receipt>(endpoint,{method:"POST",body:JSON.stringify(value.command)});
      if(receipt.object_type!==objectType||receipt.object_id!==objectId||!uuid.test(receipt.revision_id))throw Error("原操作回执不完整，请重新核对。");
      clear();setConfirm(null);setSelected(receipt.revision_id);setPage(1);
      setMessage(receipt.status==="draft"?`第 ${receipt.revision} 版草稿已保存。请进入发布前检查后确认，公开内容尚未改变。`:`原操作对应第 ${receipt.revision} 版，${receipt.status==="published"?"已经处理":"已被后续修改替代"}。请核对当前记录。`);
      reload();
    }catch(cause){
      if(lifetime.current?.signal.aborted)return;
      if(cause instanceof ApiRequestError&&!(cause instanceof PrivateOwnerVerificationError)&&[400,403,404,409].includes(cause.status)){
        try{clear();}catch{setRecordProblem(true);}setConfirm(null);setData(null);
      }
      setError(cause instanceof Error?cause.message:"操作结果尚未确认，请核对原请求。");
    }finally{acting.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  async function submit(){if(!confirm||!agreed||!reason.trim()||locked||confirm.version!==data?.edit_version)return;await send({format:1,owner,objectType,objectId,command:{action:confirm.action,request_key:createRequestKey(),expected_version:confirm.version,reason:reason.trim(),...(confirm.source?{source_revision_id:confirm.source.id}:{})}});}
  async function clearConfirmed(){
    if(!clearAgreed||acting.current||!data)return;acting.current=true;setBusy(true);
    try{await request<History>(endpoint);clear();setRecordProblem(false);setClearOpen(false);setMessage("已清除本标签页记录。服务端修订保留，请重新核对后操作。");reload();}
    catch(cause){if(!lifetime.current?.signal.aborted)setError(cause instanceof Error?cause.message:"暂时不能核对原操作记录。");}
    finally{acting.current=false;if(!lifetime.current?.signal.aborted)setBusy(false);}
  }
  return <main className={styles.ledger}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><a href="/admin/knowledge">学者与知识</a><span>› 发布台 › 历史与撤回</span></nav>
    <header className={styles.heading}><div><h1>发布台、历史与撤回</h1><p>管理当前公开内容，核对历史修订与关联记录。</p></div><button type="button" disabled={busy||loading} onClick={reload}><RefreshCw size={15}/>重新读取</button></header>
    {error?<p role="alert" className={styles.warning}>{error}</p>:null}{message?<p role="status" className={styles.notice}>{message}</p>:null}
    {pending?<section className={styles.warning}><h2>原操作结果待核对</h2><p>本标签页保留了原请求。重试将核对同一回执，不会自动公开或生成第二份草稿。</p><button disabled={busy} type="button" onClick={()=>void send(pending,true)}>核对原请求</button></section>:null}
    {recordProblem?<p role="alert" className={styles.warning}>本标签页记录不可用。请在历史中核对最新草稿和操作人。</p>:null}
    {pending||recordProblem?<button type="button" disabled={busy||loading||!data} onClick={()=>{setClearAgreed(false);setClearOpen(true);}}>已核对历史，清除本标签页记录</button>:null}
    {loading?<p role="status">正在读取保存版本与历史记录…</p>:null}
    {data?<>
      <section className={styles.object}><div><h2>当前对象</h2><div className={styles.book}><div className={styles.noCover}><FileClock size={30}/><span>{labels[objectType]}</span></div><div><h3>{data.title}</h3><p>{labels[objectType]} · 共享知识对象</p><a href={returnHref}>返回编辑 →</a></div></div></div>
        <dl><dt>当前公开</dt><dd>{data.is_public?"读者可见":"未公开或已撤回"}</dd><dt>保存状态</dt><dd>{data.has_draft?"有未发布修改":"暂无独立编辑草稿"}</dd><dt>历史记录</dt><dd>{data.history.count} 份修订</dd></dl>
        <aside><h3>{data.has_draft?"已保存，尚未发布":data.is_public?"当前已公开":"当前未公开"}</h3><p>草稿与公开内容分别管理。撤回或恢复先保存新修订，再核对页面并确认发布。</p>{!locked?<a className={styles.primary} href={reviewHref}>进入发布前检查 →</a>:null}<button type="button" onClick={()=>setTab("impact")}>检查影响范围</button></aside>
      </section>
      <nav className={styles.tabs} aria-label="历史工作台视图">{[["history","版本历史"],["impact","影响范围"],["dependencies","引用依赖"]].map(([key,label])=><button type="button" key={key} aria-pressed={tab===key} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      <section className={styles.panel} hidden={tab!=="history"}><header><h2>历史修订记录</h2></header><div className={styles.table}><table><caption className="sr-only">保存与发布修订</caption><thead><tr><th>版本</th><th>状态</th><th>说明</th><th>操作人 / 时间</th><th>操作</th></tr></thead><tbody>{data.history.results.map(row=><tr key={row.id} data-selected={row.id===data.selected?.id||undefined}><th scope="row">第 {row.revision} 版</th><td><span className={styles.badge}>{state(row)}</span></td><td>{row.note||"未填写说明"}</td><td>{row.actor}<time>{date(row.published_at||row.created_at)}</time></td><td><div className={styles.actions}><button type="button" disabled={busy} onClick={()=>{setData(null);setSelected(row.id);setLoading(true);setRefresh(n=>n+1);}}>查看对比</button>{row.can_restore?<button type="button" disabled={locked} onClick={()=>begin("restore",row)}>恢复</button>:null}</div></td></tr>)}</tbody></table></div>{!data.history.count?<p>尚无独立修订记录。当前保存内容仍保留；不会补造历史版本。</p>:null}<div className={styles.pagination}><button disabled={busy||page<=1} onClick={()=>setPage(n=>n-1)}>上一页</button><span>第 {page} / {data.history.pages} 页</span><button disabled={busy||page>=data.history.pages} onClick={()=>setPage(n=>n+1)}>下一页</button></div></section>
      <div className={styles.columns}>
        <section className={styles.panel} hidden={tab!=="history"}><header><h2>版本差异对比</h2><label><input type="checkbox" checked={allFields} onChange={event=>setAllFields(event.target.checked)}/>显示未变化字段</label></header><p>当前正式内容 → {data.selected?`第 ${data.selected.revision} 版保存内容`:"当前保存内容"}</p>{changes.map(row=><details key={row.field} className={detail.change}><summary>{row.label} · {row.changed?"有变化":"未变化"}</summary><div className={detail.values}><div><h3>当前正式内容</h3><pre>{text(row.before)}</pre></div><div><h3>所选修订内容</h3><pre>{text(row.after)}</pre></div></div></details>)}{!changes.length?<p>本次对比范围内没有字段差异。</p>:null}<p>{data.scope}</p></section>
        <section className={styles.panel} hidden={tab==="dependencies"}><header><h2>影响范围</h2><button type="button" disabled={busy||loading} onClick={reload}>重新检查</button></header><article className={styles.impact}><div><h3>{labels[objectType]}页面</h3><p>确认发布后更新本对象公开内容。撤回后关联页面将按各自可见性规则处理该对象。</p></div></article><article className={styles.impact}><div><h3>关联资料与私人记录</h3><p>恢复不会自动恢复其他已撤回对象，不覆盖原始文件或读者私人记录。下方数量只表示已存关联，需要到各来源核对具体展示。</p></div><button type="button" onClick={()=>setTab("dependencies")}>查看依赖</button></article>{data.has_draft?<p className={styles.notice}>已有未发布修改。请先处理原草稿，当前不能另建撤回或恢复草稿。</p>:null}</section>
      </div>
      <section className={styles.panel} hidden={tab!=="dependencies"}><h2>关联依赖</h2><p>{data.scope}</p>{data.dependencies.length?data.dependencies.map(row=><div className={styles.impact} key={row.key}><span>{row.label}</span><strong>{row.count} 条</strong></div>):<p>未发现现有反向关联记录。</p>}</section>
      <div className={styles.columns}><section className={styles.panel}><h2>撤回与恢复版本</h2><p>撤回将影响本对象的公开展示。历史恢复保留原修订，并生成需要重新检查的草稿。</p><div className={styles.actions}><button type="button" disabled={locked||!data.can_withdraw} onClick={()=>begin("withdraw")}>撤回当前公开内容</button><button type="button" disabled={locked||!data.selected?.can_restore} onClick={()=>begin("restore",data.selected!)}>恢复所选历史版本</button></div></section>
      <section className={styles.panel}><h2>操作结果与状态</h2>{target?<PublicationRetryControl objectTarget={{objectType:target.type,objectId}} token={null} request={request} onCompleted={reload} disabled={locked} refreshKey={data.edit_version}/>:null}{data.events.map(event=><article className={styles.event} key={event.id}><FileClock size={16}/><div><strong>{event.label}</strong><p>{event.actor} · <time>{date(event.created_at)}</time></p>{event.failures.length?<p>待处理：{event.failures.join("、")}</p>:null}</div></article>)}{!data.events.length?<p>尚无发布任务记录。</p>:<p>展示最近 {data.events.length} 条任务；修订历史可翻页查看。</p>}</section></div>
    </>:null}
    <Dialog open={Boolean(confirm)} onRequestClose={()=>{if(!busy)setConfirm(null);}} className={styles.dialog} aria-labelledby="knowledge-history-confirm"><h2 id="knowledge-history-confirm">{confirm?.action==="withdraw"?"确认建立撤回草稿":"确认恢复历史内容"}</h2><p>{confirm?.action==="withdraw"?"将保存撤回当前对象的草稿。完成发布前检查并明确确认后，才撤下公开展示。":`将第 ${confirm?.source?.revision} 版保存的内容恢复为新草稿。原历史与其他对象保持不变，请随后检查来源、图片和关联。`}</p><label>操作说明<textarea maxLength={400} value={reason} disabled={busy} onChange={event=>setReason(event.target.value)}/></label><label className={styles.confirm}><input type="checkbox" checked={agreed} disabled={busy} onChange={event=>setAgreed(event.target.checked)}/>已核对对象和版本，理解此操作先保存草稿</label>{error?<p role="alert">{error}</p>:null}<div className={styles.actions}><button disabled={busy} onClick={()=>setConfirm(null)}>取消</button><button className={styles.primary} disabled={locked||!agreed||!reason.trim()||confirm?.version!==data?.edit_version} onClick={()=>void submit()}>{busy?"正在保存…":"确认保存草稿"}</button></div></Dialog>
    <Dialog open={clearOpen} onRequestClose={()=>{if(!busy)setClearOpen(false);}} className={styles.dialog} aria-labelledby="knowledge-history-clear"><h2 id="knowledge-history-clear">核对原操作记录</h2><p>清除只影响此标签页的待确认记录，不会撤销服务端已保存或正在处理的操作。请先查看最新修订、操作人和说明。</p><label className={styles.confirm}><input type="checkbox" checked={clearAgreed} disabled={busy} onChange={event=>setClearAgreed(event.target.checked)}/>已核对服务端历史，确认清除此标签页记录</label>{error?<p role="alert">{error}</p>:null}<div className={styles.actions}><button disabled={busy} onClick={()=>setClearOpen(false)}>取消</button><button disabled={busy||!clearAgreed||!data} onClick={()=>void clearConfirmed()}>确认清除本地记录</button></div></Dialog>
  </main>;
}
