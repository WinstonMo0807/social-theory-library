"use client";

import { createRequestKey } from "../../../lib/request-key";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { PlacementSourcePicker } from "./placement-source-picker";
import { TimelineEvidenceImage } from "./timeline-evidence-image";
import styles from "./timeline-editor.module.css";

export type TimelineSourceRecord = { id: string; kind: "book"|"article"|"archive"|"other"; citation: string; locator: string; quote: string; status: "adopted"|"disputed"|"related"; asset_id: string|null; page: number|null; image_rendition_id?: string|null };
export type TimelineEditorialDetails = { sources: TimelineSourceRecord[]; time_note: string; conflict_note: string; editor_note: string; confirmed: boolean; duplicate_reason: string; primary_image_rendition_id?: string|null };
export const emptyTimelineDetails = (): TimelineEditorialDetails => ({ sources: [], time_note: "", conflict_note: "", editor_note: "", confirmed: false, duplicate_reason: "" });

export function TimelineSupplementalSources({ owner, value, onChange }: { owner: string; value: TimelineEditorialDetails; onChange: (value: TimelineEditorialDetails) => void }) {
  const [picking, setPicking] = useState("");
  const [expanded, setExpanded] = useState(() => new Set(value.sources.filter(row => !row.citation).map(row => row.id)));
  function addSource() {
    const id = createRequestKey();
    setExpanded(current => new Set([...current, id]));
    onChange({ ...value, confirmed: false, sources: [...value.sources, { id, kind: "book", citation: "", locator: "", quote: "", status: "related", asset_id: null, page: null }] });
  }
  const change = (id: string, patch: Partial<TimelineSourceRecord>) => onChange({ ...value, confirmed: false, sources: value.sources.map(row => row.id === id ? { ...row, ...patch } : row) });
  return <section className={styles.sources} aria-label="补充出处与来源分歧">
    <header><h3>补充出处</h3><button type="button" disabled={value.sources.length >= 20} onClick={addSource}>＋ 添加证据</button></header>
    {!value.sources.length ? <p>可添加相关研究或不同记载，保留各自出处。</p> : null}
    {value.sources.map((row,index) => <details key={row.id} open={expanded.has(row.id)} onToggle={event => {
      const open = event.currentTarget.open;
      setExpanded(current => {
        if (current.has(row.id) === open) return current;
        const next = new Set(current); if (open) next.add(row.id); else next.delete(row.id); return next;
      });
      if (!open) setPicking(current => current === row.id ? "" : current);
    }} className={styles.source}>
      <summary>证据 {index + 2} · {row.status === "disputed" ? "存疑" : row.status === "adopted" ? "辅助采用" : "相关研究"} · {row.citation || "待填写出处"}</summary>
      <label>来源类型<select value={row.kind} onChange={event => change(row.id,{kind:event.target.value as TimelineSourceRecord["kind"]})}><option value="book">图书</option><option value="article">论文</option><option value="archive">档案</option><option value="other">其他出处</option></select></label>
      <label>书目或来源信息<textarea required rows={2} maxLength={1000} value={row.citation} onChange={event => change(row.id,{citation:event.target.value})}/></label>
      <label>引用位置<input maxLength={240} value={row.locator} onChange={event => change(row.id,{locator:event.target.value})}/></label>
      <label>原文摘录<textarea rows={3} maxLength={4000} value={row.quote} onChange={event => change(row.id,{quote:event.target.value})}/></label>
      <label>核对结果<select value={row.status} onChange={event => change(row.id,{status:event.target.value as TimelineSourceRecord["status"]})}><option value="related">相关研究</option><option value="adopted">辅助采用</option><option value="disputed">存疑，保留分歧</option></select></label>
      <TimelineEvidenceImage key={`${owner}:${row.id}`} owner={owner} value={row.image_rendition_id} onChange={image_rendition_id => change(row.id, { image_rendition_id })} />
      <div className={styles.controls}><button type="button" onClick={() => setPicking(picking === row.id ? "" : row.id)}>{picking === row.id ? "收起选取" : "从馆藏选取原文"}</button>{row.asset_id ? <button type="button" onClick={() => change(row.id,{asset_id:null,page:null})}>移除文件关联</button> : null}<button type="button" onClick={() => onChange({...value,confirmed:false,sources:value.sources.filter(item => item.id !== row.id)})}>移除这条出处</button></div>
      {row.asset_id ? <p>已关联原文文件 · PDF 第 {row.page} 页。文件身份随记录保存。</p> : null}
      {picking === row.id ? <PlacementSourcePicker owner={owner} kind="span" onChoose={({source}) => { change(row.id,{citation:source.title,quote:String(source.text||""),asset_id:source.asset_id||null,page:source.asset_id && typeof source.page_start === "number" ? source.page_start : null,locator:source.page_start ? `PDF 第 ${source.page_start} 页` : ""}); setPicking(""); }}/>:null}
    </details>)}
    <label>来源分歧说明<textarea rows={3} maxLength={2000} value={value.conflict_note} onChange={event => onChange({...value,confirmed:false,conflict_note:event.target.value})} placeholder="记录不同说法及本次采用依据"/></label>
  </section>;
}

type SimilarInput = { title:string; event_type:string; start_year:number|null; work:string|null; scholar:string|null; exclude:string|null };
type SimilarResult = { count:number; truncated:boolean; results:{id:string;title:string;date_label:string;start_year:number|null;review_status:string}[] };
export function TimelineSimilarCheck({ owner, input, reason, onReason, onMerge, mergeDisabled }: { owner:string; input:SimilarInput; reason:string; onReason:(value:string)=>void; onMerge?:(id:string)=>void; mergeDisabled?:boolean }) {
  const [result,setResult]=useState<{key:string;data:SimilarResult}|null>(null), [error,setError]=useState(""),[busy,setBusy]=useState(false);
  const life=useRef<AbortController|null>(null);
  useEffect(()=>{const controller=new AbortController();life.current=controller;return()=>controller.abort();},[owner]);
  const key=JSON.stringify(input), visible=result?.key===key ? result.data : null;
  async function lookup() {
    if(busy)return; setBusy(true);setError("");
    if(!life.current||life.current.signal.aborted){setBusy(false);return;}
    const signal=AbortSignal.any([life.current.signal,AbortSignal.timeout(30000)]);
    try { const data=await withPrivateOwner(owner,()=>apiRequest<SimilarResult>("/catalog/admin/theory-timeline/similar/",{method:"POST",body:key,headers:{"X-Editor-Owner":owner},signal,cache:"no-store"},getServerSessionCredential(),false),signal);setResult({key,data}); }
    catch(reason){if(!life.current?.signal.aborted)setError(reason instanceof Error ? reason.message : "相似事件暂不可读取。");}finally{if(!life.current?.signal.aborted)setBusy(false);}
  }
  return <section className={styles.similar}><header><h3>相似事件</h3><button type="button" disabled={busy} onClick={()=>void lookup()}>{busy?"正在读取…":"核对已有事件"}</button></header>
    <p>按关联对象、事件类型与相近年份查找，由编辑确认是否为同一事件。</p>{error?<p role="alert">{error}</p>:null}
    {onMerge && (!input.exclude || mergeDisabled)?<p>先保存当前事件，再读取归并影响。未保存的输入不参与归并。</p>:null}
    {visible?<><p>{visible.count ? `找到 ${visible.count} 条可能相关的事件` : "没有符合当前条件的事件。"}{visible.truncated?"，先显示前 50 条。":""}</p><ul>{visible.results.map(row=><li key={row.id}><strong>{row.date_label||row.start_year||"时间待确认"} · {row.title}</strong><Link href={`/admin/theories/timeline?event=${row.id}`} target="_blank" rel="noopener noreferrer">打开原事件核对</Link>{onMerge?<button type="button" disabled={mergeDisabled || !input.exclude} onClick={()=>onMerge(row.id)}>查看归并影响</button>:null}</li>)}</ul>{visible.count?<label>保留为独立事件的说明<textarea rows={2} maxLength={2000} value={reason} onChange={event=>onReason(event.target.value)}/></label>:null}</>:null}
  </section>;
}
