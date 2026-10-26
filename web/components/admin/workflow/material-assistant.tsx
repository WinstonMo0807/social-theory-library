"use client";

import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Dialog, type DialogProps } from "@/components/ui/dialog";
import styles from "./material-assistant.module.css";
import { AssistantCommandNotice } from "./assistant-commands";
import { MaterialSourceRecord } from "./material-source-record";

type Field = {id:string;label:string;open:()=>void;status?:string};
const CandidateContext=createContext<{id:string;selected:string;disabled:boolean;select:(id:string)=>void}|null>(null);
export function MaterialCandidate({id,label,children}:{id:string;label:string;children:ReactNode}){
  const context=useContext(CandidateContext);
  return <article data-selected={context?.selected===id}><label className={styles.candidateSelector}><input type="radio" name={context?.id} checked={context?.selected===id} disabled={context?.disabled} onChange={()=>context?.select(id)} aria-label={`查看${label}的依据`}/></label>{children}</article>;
}
type Context = {fields:Field[];register:(field:Field)=>()=>void;mark:(id:string,status:string)=>void;preview?:ReactNode;dirty:boolean;disabled:boolean;save?:()=>void|Promise<boolean|void>};
const AssistantContext=createContext<Context|null>(null);
export function MaterialAssistantProvider({children,preview,dirty,disabled=false,save}:{children:ReactNode;preview?:ReactNode;dirty:boolean;disabled?:boolean;save?:Context["save"]}){
  const [fields,setFields]=useState<Field[]>([]);
  const register=useCallback((field:Field)=>{setFields(current=>[...current.filter(row=>row.id!==field.id),field]);return()=>setFields(current=>current.filter(row=>row.id!==field.id));},[]);
  const mark=useCallback((id:string,status:string)=>setFields(current=>current.map(row=>row.id===id?{...row,status}:row)),[]);
  const value=useMemo(()=>({fields,register,mark,preview,dirty,disabled,save}),[fields,register,mark,preview,dirty,disabled,save]);
  return <AssistantContext value={value}>{children}</AssistantContext>;
}
export function useMaterialField(label:string,open:()=>void){
  const id=useId(),context=useContext(AssistantContext),openRef=useRef(open),register=context?.register;
  useLayoutEffect(()=>{openRef.current=open;},[open]);
  useEffect(()=>register?.({id,label,open:()=>openRef.current()}),[id,label,register]);
  return {id,dirty:Boolean(context?.dirty),mark:(status:string)=>context?.mark(id,status)};
}
export function MaterialAssistantEntry({autoOpen=false}:{autoOpen?:boolean}){
  const context=useContext(AssistantContext),opened=useRef(false);
  useEffect(()=>{if(autoOpen&&!opened.current&&context?.fields.length&&!context.disabled){opened.current=true;context.fields[0].open();}},[autoOpen,context]);
  return context?.fields.length?<button className="material-assistant-entry" type="button" disabled={context.disabled} onClick={()=>context.fields[0].open()}>字段候选与材料助手</button>:null;
}
export type MaterialEvidence={category?:string;summary?:string;url?:string;locator?:{url?:string;page?:number;work_id?:string;edition_id?:string;asset_id?:string;title?:string}};
export type MaterialSource={id:string;label:string;evidence:MaterialEvidence[]};
export function ManualMaterialField({label,fields,onChange,sources=[]}:{label:string;fields:{key:string;label:string;value:string;type?:"number"|"text";multiline?:boolean}[];onChange:(key:string,value:string)=>void;sources?:MaterialSource[]}){
  const [open,setOpen]=useState(false),context=useContext(AssistantContext),field=useMaterialField(label,()=>setOpen(true));
  return <><button type="button" disabled={context?.disabled} onClick={()=>setOpen(true)}>核对{label}</button>{open?<MaterialAssistantDialog open fieldId={field.id} fieldLabel={label} sources={sources} onRequestClose={()=>setOpen(false)}><p>此字段尚无可直接采用的候选。请对照右侧已有来源填写，修改保留在当前草稿中。</p>{fields.map(row=><label key={row.key}><strong>{row.label}</strong>{row.multiline?<textarea rows={5} value={row.value} disabled={context?.disabled} onChange={event=>{onChange(row.key,event.target.value);field.mark("人工填写，待保存");}}/>:<input type={row.type||"text"} value={row.value} disabled={context?.disabled} onChange={event=>{onChange(row.key,event.target.value);field.mark("人工填写，待保存");}}/>}</label>)}</MaterialAssistantDialog>:null}</>;
}
export function materialSourceHref(value:string|undefined){if(!value)return "";if(/^\/(scholars|works|read|reader|topics|theories)\//.test(value)&&!value.includes("\\"))return value;try{const url=new URL(value);return ["https:","http:"].includes(url.protocol)&&!url.username&&!url.password?url.href:"";}catch{return "";}}
export function MaterialAssistantDialog({fieldId,fieldLabel,sources=[],children,className,onRequestClose,currentValue,onEditCurrent,refresh,...props}:DialogProps&{fieldId:string;fieldLabel:string;sources?:MaterialSource[];currentValue?:string;onEditCurrent?:(value:string)=>void;refresh?:()=>void}){
  const context=useContext(AssistantContext),[selected,setSelected]=useState(""),[evidenceIndex,setEvidenceIndex]=useState(0),[tab,setTab]=useState("sources"),[message,setMessage]=useState(""),[saving,setSaving]=useState(false),[editingCurrent,setEditingCurrent]=useState(false);
  const fields=context?.fields.length?context.fields:[{id:fieldId,label:fieldLabel,open:()=>{}}];
  const position=Math.max(0,fields.findIndex(row=>row.id===fieldId)),source=sources.find(row=>row.id===selected)||sources[0];
  const materials=sources.flatMap(row=>row.evidence.map((evidence,index)=>({source:row,evidence,index})));
  const disabled=Boolean(context?.disabled||saving||props["aria-busy"]);
  const processed=fields.filter(field=>Boolean(field.status)).length;
  function navigate(index:number){if(disabled||!fields[index]||fields[index].id===fieldId)return;onRequestClose?.();fields[index].open();}
  async function save(close=false){if(!context?.save||disabled)return;setSaving(true);setMessage("");try{const result=await context.save();if(result===false)setMessage("尚未确认保存，请返回编辑页处理提示。当前输入保留。");else if(close)onRequestClose?.();}catch(reason){setMessage(reason instanceof Error?reason.message:"保存尚未完成，输入仍保留。");}finally{setSaving(false);}}
  return <Dialog {...props} onRequestClose={disabled?undefined:onRequestClose} data-material-assistant data-origin-class={className} className={styles.workspace} aria-label="字段候选与材料助手">
    <header className={styles.header}><div><p>内容　›　页面编排　›　字段候选与材料助手</p><h1>字段候选与材料助手</h1><p>基于馆藏文献与已有资料，提供字段建议。请逐项核对、采用或修改后采用。</p></div><div className={styles.actions}>{refresh?<button type="button" disabled={disabled} onClick={refresh}>重新核对本字段</button>:null}<button type="button" disabled={disabled||position===0} onClick={()=>navigate(position-1)}>〈 上一个字段</button><small>{position+1} / {fields.length}</small><button type="button" disabled={disabled||position===fields.length-1} onClick={()=>navigate(position+1)}>下一个字段 〉</button><span>{context?.dirty?"● 未保存":"候选不会自动发布"}</span></div></header>
    <div className={styles.mobileNav}><span>{position+1} / {fields.length}</span><progress aria-label="本次已处理字段" max={fields.length} value={processed}/><button type="button" aria-label="上一个字段" disabled={disabled||position===0} onClick={()=>navigate(position-1)}>〈</button><button type="button" aria-label="下一个字段" disabled={disabled||position===fields.length-1} onClick={()=>navigate(position+1)}>〉</button></div>
    <div className={styles.columns}><nav className={styles.fields} aria-label="待核对字段"><h2>任务进度 <span>{processed} / {fields.length}</span></h2><progress aria-label="本次已处理字段" max={fields.length} value={processed}/>{fields.map((field,index)=><button key={field.id} type="button" disabled={disabled} aria-current={field.id===fieldId?"step":undefined} onClick={()=>navigate(index)}><span>{String(index+1).padStart(2,"0")}</span><strong>{field.label}<small>{field.status||"待核对"}</small></strong></button>)}</nav>
      <section className={styles.candidates} aria-label={`${fieldLabel}候选`}><h2><span>{String(position+1).padStart(2,"0")}</span>{fieldLabel}<small>{fields[position]?.status||"待处理"}</small></h2><p className={styles.fieldHelp}>请核对当前字段。可从候选中选择，或修改后采用。</p>{currentValue!==undefined?<section className={styles.currentValue}><h3>当前值 <small>（来自编辑页面）</small></h3><div>{editingCurrent&&onEditCurrent?<input aria-label={`修改当前${fieldLabel}`} value={currentValue} disabled={disabled} onChange={event=>{onEditCurrent(event.target.value);context?.mark(fieldId,"人工填写，待保存");}}/>:<output>{currentValue||"尚未填写"}</output>}{onEditCurrent?<button type="button" disabled={disabled} onClick={()=>setEditingCurrent(value=>!value)}>{editingCurrent?"完成编辑":"编辑"}</button>:null}</div></section>:null}<h3 className={styles.candidateTitle}>候选值 <small>（{sources.length}）</small></h3><CandidateContext value={{id:fieldId,selected:source?.id||"",disabled,select:id=>{setSelected(id);setEvidenceIndex(0);setTab("sources");}}}><div className={styles.legacy}>{children}</div></CandidateContext><details className={styles.relatedMaterials} open><summary>相关材料（{materials.length}）</summary>{materials.map(({source:row,evidence,index})=><button type="button" key={`${row.id}:${index}`} aria-pressed={source?.id===row.id&&evidenceIndex===index&&tab==="sources"} onClick={()=>{setSelected(row.id);setEvidenceIndex(index);setTab("sources");}}><strong>{evidence.locator?.title||evidence.category||row.label}</strong><small>{evidence.locator?.page?`PDF 第 ${evidence.locator.page} 页`:"来源片段"} · {row.label}</small></button>)}{!materials.length?<p>暂无可核对的材料，当前人工填写仍可保存。</p>:null}</details></section>
      <aside className={styles.aside}><nav className={styles.tabs} aria-label="核对依据"><button type="button" aria-pressed={tab==="sources"} onClick={()=>setTab("sources")}>相关材料</button><button type="button" aria-pressed={tab==="preview"} onClick={()=>setTab("preview")}>页面预览</button></nav>{tab==="sources"?<><h2>相关材料预览</h2>{sources.length?<><label>候选来源<select value={source?.id||""} onChange={event=>{setSelected(event.target.value);setEvidenceIndex(0);}}>{sources.map(row=><option key={row.id} value={row.id}>{row.label}</option>)}</select></label><h3>{source?.label}</h3>{source?.evidence.length?source.evidence.map((row,index)=>{const href=materialSourceHref(row.url||row.locator?.url);return <article key={index} data-selected={index===evidenceIndex}><button type="button" className={styles.evidenceSelect} onClick={()=>setEvidenceIndex(index)}>核对这段依据</button><strong>{row.category||"来源资料"}</strong>{row.locator?.page?<small>原文件第 {row.locator.page} 页</small>:null}<blockquote>{row.summary||"此来源未提供摘录，请核对原记录。"}</blockquote>{href?<a href={href} target="_blank" rel="noopener noreferrer">查看资料 ↗</a>:null}</article>}):<p>这项候选没有可显示的来源摘录，请保留人工判断。</p>}</>:<p>暂无可核对材料。可返回编辑页手工填写，不会生成示例资料。</p>}<MaterialSourceRecord evidence={source?.evidence[evidenceIndex]}/>{context?.preview?<details className={styles.relatedPreview}><summary>页面预览（节选）</summary><div className={styles.preview}>{context.preview}</div></details>:null}</>:<div className={styles.preview}>{context?.preview||<p>此入口没有页面预览，请返回原编辑页核对。</p>}</div>}</aside>
    </div><AssistantCommandNotice/>{message?<p role="alert">{message}</p>:null}<footer className={styles.footer}><button className={styles.returnButton} type="button" disabled={disabled} onClick={onRequestClose}>〈 返回编辑页面</button><span>{context?.dirty?"本页修改尚未保存":"候选不会自动发布"}</span>{context?.save?<><button type="button" disabled={disabled} onClick={()=>void save()}>{saving?"正在保存…":"保存草稿"}</button><button type="button" disabled={disabled} onClick={()=>void save(true)}>保存并返回主表</button></>:null}</footer>
  </Dialog>;
}
