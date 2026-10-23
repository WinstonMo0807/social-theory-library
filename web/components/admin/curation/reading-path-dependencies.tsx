"use client";

import { useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";

export type PathDependency = { item_id:string; kind:"learning_order"|"theory_related"; reason:string };
export type DependencyMaterial = { id?:string; key:string; work_name:string; node_name:string; status:string };
export function PathDependencyEditor({ itemId, value, materials, onChange }: { itemId?:string; value:PathDependency[]; materials:DependencyMaterial[]; onChange:(value:PathDependency[])=>void }) {
  const [target,setTarget]=useState(""),[kind,setKind]=useState<PathDependency["kind"]>("learning_order");
  const available=materials.filter(row=>row.id&&row.id!==itemId&&row.status==="active");
  return <section aria-label="先修依赖与理论相关"><h3>先修依赖</h3><p>学习顺序要求先读对应材料；理论相关仅表达联系，不决定阅读顺序。</p>
    <ul>{value.map((row,index)=><li key={`${row.item_id}:${row.kind}`}><strong>{materials.find(item=>item.id===row.item_id)?.work_name||materials.find(item=>item.id===row.item_id)?.node_name||"原关联材料已移除"}</strong><span> · {row.kind==="learning_order"?"学习顺序":"理论相关"}</span><label>关系说明<input maxLength={1000} value={row.reason} onChange={event=>onChange(value.map((item,i)=>i===index?{...item,reason:event.target.value}:item))}/></label><button type="button" onClick={()=>onChange(value.filter((_,i)=>i!==index))}>移除关系</button></li>)}</ul>
    <div className="inline-fields"><label>选择路径中的材料<select value={target} onChange={event=>setTarget(event.target.value)}><option value="">请选择</option>{available.map(row=><option key={row.id} value={row.id}>{row.work_name||row.node_name||"未选定的材料"}</option>)}</select></label><label>关系类型<select value={kind} onChange={event=>setKind(event.target.value as PathDependency["kind"])}><option value="learning_order">学习顺序</option><option value="theory_related">理论相关</option></select></label></div>
    <button type="button" disabled={!itemId||!target||!available.some(row=>row.id===target)||value.length>=64||value.some(row=>row.item_id===target&&row.kind===kind)} onClick={()=>{onChange([...value,{item_id:target,kind,reason:""}]);setTarget("");}}>添加关系</button>
  </section>;
}

type Report = {material_count:number;active_count:number;relation_counts:Record<string,number>;dependencies_valid:boolean;problems:{code:string;item_ids:string[];detail:string}[];notice:string};
export function PathDependencyValidation({ owner,pathId,groups,materials,onSelect }: {owner:string;pathId?:string;groups:object[];materials:DependencyMaterial[];onSelect:(id:string)=>void}) {
  const [result,setResult]=useState<{key:string;data:Report}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState("");
  const life=useRef<AbortController|null>(null),body=JSON.stringify({path_id:pathId||null,stage_groups:groups});
  useEffect(()=>{const request=new AbortController();life.current=request;return()=>request.abort();},[owner]);
  const current=result?.key===body?result.data:null;
  async function inspect(){
    if(busy||!life.current||life.current.signal.aborted)return;setBusy(true);setError("");
    const signal=AbortSignal.any([life.current.signal,AbortSignal.timeout(30000)]);
    try {const data=await withPrivateOwner(owner,()=>apiRequest<Report>("/catalog/admin/theory-system/reading-paths/validate/",{method:"POST",body,signal,headers:{"X-Editor-Owner":owner},cache:"no-store"},getServerSessionCredential(),false),signal);setResult({key:body,data});}
    catch(reason){if(!life.current.signal.aborted)setError(reason instanceof Error?reason.message:"当前编排暂不可核对。");}finally{if(!life.current.signal.aborted)setBusy(false);}
  }
  const label=(id:string)=>materials.find(row=>row.id===id)?.work_name||materials.find(row=>row.id===id)?.node_name||"原材料";
  return <section aria-label="先修关系验证"><header><h3>先修关系验证</h3><button type="button" disabled={busy} onClick={()=>void inspect()}>{busy?"正在核对…":"核对本次编排"}</button></header>
    {!current?<p>{result?"编排已变化，请重新核对先修关系。":"保存前可核对材料身份、先修循环和阅读顺序。"}</p>:<><p>{current.dependencies_valid?"本次先修关系没有发现循环或顺序冲突。":"编排中还有需要处理的关系。"}</p><p>共 {current.material_count} 项材料 · 学习顺序 {current.relation_counts.learning_order} 条 · 理论相关 {current.relation_counts.theory_related} 条</p><ul>{current.problems.map((problem,index)=><li key={index}><strong>{problem.detail}</strong><div>{problem.item_ids.map((id,i)=><span key={`${id}:${i}`}>{i?" → ":""}<button type="button" data-path-navigation="true" data-preview-item-id={id} onClick={()=>onSelect(id)}>{label(id)}</button></span>)}</div></li>)}</ul><p>{current.notice}</p></>}{error?<p role="alert">{error}</p>:null}
  </section>;
}
