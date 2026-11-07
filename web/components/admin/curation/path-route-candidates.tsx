"use client";


import { LoadingState } from "@/components/ui/loading-state";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, normalizePublicResourceUrl } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { useScholarSave } from "../knowledge/use-scholar-save";
import type { PublicReadingPath } from "@/lib/api/reading-paths.types";
import styles from "../knowledge/path-editor.module.css";

type Summary = { id:string; title:string; summary:string; status:string; created_at:string; stages_count:number; items_count:number; method:string; gaps:string[]; edit_version:string; audience:string; learning_goal:string; review_note:string };
type Detail = Summary & { blockers:string[]; can_adopt:boolean; candidate_version:string; preview:PublicReadingPath|null; moves:{item_id:string;from_stage:string;to_stage:string;from_position:number;to_position:number}[] };
type Page = {count:number;page:number;total_pages:number;results:Summary[]};

export function PathRouteCandidates({ owner, pathId, version, blocked, onPending, onApplied }: {
  owner:string;pathId?:string;version:string;blocked:boolean;onPending:(value:boolean)=>void;onApplied:()=>Promise<void>;
}) {
  const command = useScholarSave(owner, "path_route");
  const [page,setPage]=useState(1),[retry,setRetry]=useState(0),[selected,setSelected]=useState("");
  const [result,setResult]=useState<{key:string;data:Page}|null>(null),[detail,setDetail]=useState<{key:string;data:Detail}|null>(null);
  const [error,setError]=useState(""),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  const acting=useRef(false),life=useRef<AbortController|null>(null);
  const listKey=JSON.stringify([owner,pathId,version,page,retry]),detailKey=JSON.stringify([listKey,selected]);
  const rows=result?.key===listKey?result.data:null,current=detail?.key===detailKey?detail.data:null;
  const route=pathId?`/catalog/admin/theory-system/reading-paths/${pathId}/routes/`:"";
  useEffect(()=>{const controller=new AbortController();life.current=controller;return()=>controller.abort();},[owner]);
  useEffect(()=>{onPending(busy||Boolean(command.recovery));return()=>onPending(false);},[busy,command.recovery,onPending]);
  const read=useCallback(<T,>(url:string,signal:AbortSignal)=>withPrivateOwner(owner,()=>apiRequest<T>(url,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),signal),[owner]);
  useEffect(()=>{
    if(!route)return;const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    void read<Page>(`${route}?page=${page}`,signal).then(data=>{if(!controller.signal.aborted)setResult({key:listKey,data});}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"候选暂不可读。");});
    return()=>controller.abort();
  },[route,page,listKey,read]);
  useEffect(()=>{
    if(!route||!selected)return;const controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(30000)]);
    void read<Detail>(`${route}${selected}/`,signal).then(data=>{if(!controller.signal.aborted)setDetail({key:detailKey,data});}).catch(reason=>{if(!controller.signal.aborted)setError(reason instanceof Error?reason.message:"候选详情暂不可读。");});
    return()=>controller.abort();
  },[route,selected,detailKey,read]);
  async function perform(operation:"generate"|"adopt"|"dismiss") {
    if(acting.current||!pathId||blocked||command.recovery||!command.ready)return;
    if(operation!=="generate"&&!current)return;
    if(operation==="adopt"&&!window.confirm(`采用“${current?.title}”的编排并保存为原路线草稿？阶段与材料顺序将调整，公开版本需另行确认发布。`))return;
    if(operation==="dismiss"&&!window.confirm("不采用这条候选？原路线与材料会保留。"))return;
    acting.current=true;setBusy(true);setError("");setMessage("");
    try {
      await command.save(route,JSON.stringify({operation,edit_version:version,...(current&&operation!=="generate"?{candidate_id:current.id,candidate_version:current.candidate_version}:{})}),{},"POST");
      if(operation==="adopt")await onApplied();
      if(!life.current?.signal.aborted){setRetry(value=>value+1);setPage(1);setSelected("");setMessage(operation==="adopt"?"候选已保存到原路线草稿，可继续阶段编排；公开页面尚未更新。":operation==="generate"?"候选已依据当前已选材料保存。请查看差异后决定。":"已记录不采用，原路线未改变。");}
    }catch(reason){if(!life.current?.signal.aborted)setError(reason instanceof Error?reason.message:"候选操作未确认，请查询原请求。");}
    finally{acting.current=false;if(!life.current?.signal.aborted)setBusy(false);}
  }
  async function recover(cancel=false){
    if(acting.current)return;acting.current=true;setBusy(true);
    try{const receipt=await command.lookup(cancel);if(!receipt)return;if(receipt.state==="applied"&&receipt.exists&&receipt.path_route_id===pathId)await onApplied();if(!life.current?.signal.aborted){setRetry(value=>value+1);setMessage(receipt.state==="cancelled"?"原请求已停止，路线未被此次请求修改。":"已查询原候选操作，请核对列表与当前草稿。");}}
    catch(reason){if(!life.current?.signal.aborted)setError(reason instanceof Error?reason.message:"原操作已找回，当前草稿暂不可读取。");}
    finally{acting.current=false;if(!life.current?.signal.aborted)setBusy(false);}
  }
  if(!pathId)return <p>先保存路线与所选材料，再生成整条候选编排。</p>;
  return <section className={styles.routes} aria-label="候选路线与质量检查"><header><div><h2>候选路线</h2><p>依据已选材料、明确先修关系和正式公开的主题馆藏，生成可比较的阶段安排。未推断难度、阅读量或额外学术关系。</p></div><button type="button" disabled={blocked||busy||Boolean(command.recovery)||!command.ready} onClick={()=>void perform("generate")}>{busy?"正在处理…":"重新生成候选"}</button></header>
    <p>每次最多编排40项材料，主题拓展最多补充12项选读。原阶段说明、问题和用时全部保留；缺少来源会说明原因，不推断书目或阅读难度。较长路线可继续手动编排。</p>
    {blocked?<p role="status">请先保存当前路线输入并核对未完成的操作。候选仍可查看。</p>:null}
    {error?<p role="alert">{error}<button type="button" onClick={()=>{setError("");setRetry(value=>value+1);}}>重新读取</button></p>:null}{message?<p role="status">{message}</p>:null}
    {command.error?<p role="alert">{command.error}</p>:null}{command.recovery?<div role="status"><p>原候选操作结果尚未确认。查询后再操作，可防止重复采用。</p><button type="button" disabled={busy} onClick={()=>void recover()}>查询原请求</button><button type="button" disabled={busy} onClick={()=>void recover(true)}>停止尚未执行的请求</button></div>:null}
    {rows?<><div className={styles.routeCards}>{rows.results.map(row=><article key={row.id} data-selected={selected===row.id}><header><h3>{row.title}</h3><small>{row.status==="pending"?"待人工核对":row.status==="adopted"?"已采用到草稿":row.status==="rejected"?"未采用":"稍后处理"}</small></header><p>{row.stages_count} 个阶段 · {row.items_count} 项材料</p><p>{row.summary}</p><p>{row.audience||"读者基础未填写"}</p>{row.gaps.length?<ul>{row.gaps.map(gap=><li key={gap}>{gap}</li>)}</ul>:null}{row.edit_version!==version&&row.status==="pending"?<p>原路线已变化，需重新生成。</p>:null}<button type="button" aria-expanded={selected===row.id} onClick={()=>{setError("");setSelected(row.id);}}>查看详情与差异</button></article>)}</div>{!rows.results.length?<p>尚无整条候选。保存材料后生成，空库不会补入示例书目。</p>:null}<nav aria-label="候选路线分页"><button type="button" disabled={page<=1||busy} onClick={()=>{setPage(value=>value-1);setSelected("");}}>上一页</button><span>第 {rows.page}/{rows.total_pages} 页 · 共 {rows.count} 条</span><button type="button" disabled={page>=rows.total_pages||busy} onClick={()=>{setPage(value=>value+1);setSelected("");}}>下一页</button></nav></>:!error?<LoadingState role="status">正在读取原路线候选…</LoadingState>:null}
    {selected&&!current&&!error?<LoadingState role="status">正在重新核对候选和当前来源…</LoadingState>:null}
    {current?<section className={styles.routeComparison} aria-label="候选详情"><header><h3>{current.title} · 与当前路线比较</h3><button type="button" onClick={()=>setSelected("")}>收起详情</button></header><p>{current.learning_goal||"原路线尚未填写学习目标。"}</p>{current.blockers.length?<div role="status"><strong>暂不能采用</strong><ul>{current.blockers.map(reason=><li key={reason}>{reason}</li>)}</ul></div>:<p>当前材料和先修结构满足采用条件；采用后仍需人工核对学习安排。</p>}
      {current.moves.length?<ul>{current.moves.map(move=><li key={move.item_id}>{current.preview?.items.find(item=>item.id===move.item_id)?.title||"原材料"}：{move.from_position ? `${move.from_stage} 第${move.from_position}项` : "新增选读"} → {move.to_stage} 第{move.to_position}项</li>)}</ul>:<p>材料顺序与阶段位置没有变化。</p>}
      {current.preview?.stages.map(stage=><details key={stage.id} open><summary>{stage.name} · {stage.items.length} 项</summary><p>{stage.description}</p><div className={styles.candidateMaterials}>{stage.items.map(item=><article key={item.id}>{item.cover_url?<img src={normalizePublicResourceUrl(item.cover_url)} alt=""/>:null}<div><strong>{item.title}</strong><small>{[item.authors.join("、"),item.publication_year,item.version_label].filter(Boolean).join(" · ")}</small><p>{item.learning_goal||item.reason||"阅读目标与理由尚未填写。"}</p><p>{item.source_notice}</p><small>{item.is_required?"必读":"选读"} · {item.dependencies?.length||0} 项关联</small></div></article>)}</div></details>)}
      <footer><button type="button" disabled={blocked||busy||Boolean(command.recovery)||!current.can_adopt} onClick={()=>void perform("adopt")}>采用此候选并开始编辑</button><button type="button" disabled={blocked||busy||Boolean(command.recovery)||current.status!=="pending"} onClick={()=>void perform("dismiss")}>不采用</button></footer><p>{current.review_note}</p>
    </section>:null}
  </section>;
}
