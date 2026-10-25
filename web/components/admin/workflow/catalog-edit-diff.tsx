"use client";
import { X } from "lucide-react";
import { useState } from "react";
import { Dialog } from "@/components/ui/dialog";
import { WORKFLOW_STEP_LABELS, type DirtyFields, type WorkflowStepKey } from "./workflow-state";
import { asArray, asRecord, asString, type WorkflowDrafts } from "./workflow-types";
import { FILL_FIELD_LABELS } from "./field-assistant-control";
import styles from "./catalog-editor.module.css";

function display(value:unknown):string{if(value===null||value===undefined||value==="")return "未填写";if(Array.isArray(value))return value.map(display).join("；");if(typeof value==="object"){const row=asRecord(value);return asString(row.display_name||row.name||row.title||row.label||row.person_id||row.id)||Object.entries(row).filter(([,v])=>typeof v!=="object").map(([k,v])=>`${k}: ${String(v)}`).join("，");}return String(value);}
export function CatalogEditDiff({local,remote,dirty,onClose,onApply}:{local:WorkflowDrafts;remote:WorkflowDrafts;dirty:DirtyFields;onClose:()=>void;onApply:(choices:Record<string,boolean>,takeRemote:boolean)=>void}){
  const [choices,setChoices]=useState<Record<string,boolean>>({});
  const rows=(Object.keys(dirty) as WorkflowStepKey[]).flatMap(step=>asArray(dirty[step]).map(String).filter(field=>JSON.stringify(local[step][field])!==JSON.stringify(remote[step][field])).map(field=>({step,field,key:`${step}:${field}`,local:local[step][field],remote:remote[step][field]})));
  return <Dialog open onRequestClose={onClose} aria-label="多窗口修改冲突与差异" className={styles.diffDialog}><header><h2>多窗口修改冲突</h2><button type="button" className={styles.diffClose} aria-label="关闭差异核对" onClick={onClose}><X size={18}/></button><p>最新内容尚未替换当前输入。逐项选择后返回编辑，保存仍会再次核对版本。</p></header>{rows.length?<div className={styles.diffRows}><table><thead><tr><th>字段</th><th>服务器最新内容</th><th>本次未保存修改</th></tr></thead><tbody>{rows.map(row=><tr key={row.key}><th>{WORKFLOW_STEP_LABELS[row.step]}<small>{(FILL_FIELD_LABELS as Record<string,string>)[row.field]||({items:"责任者或关联条目",nodes:"知识条目",topics:"主题",disciplines:"学科",subdisciplines:"子学科"} as Record<string,string>)[row.field]||row.field}</small></th><td><label><input type="radio" name={row.key} checked={choices[row.key]===false} onChange={()=>setChoices({...choices,[row.key]:false})}/><span>{display(row.remote)}</span></label></td><td><label><input type="radio" name={row.key} checked={choices[row.key]!==false} onChange={()=>setChoices({...choices,[row.key]:true})}/><span>{display(row.local)}</span></label></td></tr>)}</tbody></table></div>:<p>当前未保存字段与服务器内容没有差异，可以读取最新版本继续。</p>}<footer><button onClick={onClose}>保留输入，返回编辑</button><button onClick={()=>onApply({},true)}>采用全部最新内容</button><button className={styles.primary} onClick={()=>onApply(choices,false)}>按所选内容合并</button></footer></Dialog>;
}
