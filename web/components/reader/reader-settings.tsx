"use client";

import { useEffect, useState } from "react";
import { SlidersHorizontal, X } from "lucide-react";
import { Dialog } from "../ui/dialog";

export type ReaderPreferences = { motion:"system"|"reduced"; outline:boolean; highlight:"gold"|"gray" };
export const defaultReaderPreferences:ReaderPreferences={motion:"system",outline:true,highlight:"gold"};
const key="stl4_reader_preferences";
export function useReaderPreferences(){
  const [preferences,setPreferences]=useState(defaultReaderPreferences),[loaded,setLoaded]=useState(false);
  useEffect(()=>{
    const load=()=>{
      let value:Partial<ReaderPreferences>={};
      try{value=JSON.parse(localStorage.getItem(key)||"{}");}catch{/* Unavailable browser storage retains usable defaults. */}
      setPreferences({motion:value?.motion==="reduced"?"reduced":"system",outline:value?.outline!==false,highlight:value?.highlight==="gray"?"gray":"gold"});setLoaded(true);
    };
    load();window.addEventListener("storage",load);return()=>window.removeEventListener("storage",load);
  },[]);
  function save(value:ReaderPreferences){localStorage.setItem(key,JSON.stringify(value));setPreferences(value);}
  return {preferences,loaded,save};
}
export function ReaderSettings({value,onSave}:{value:ReaderPreferences;onSave:(value:ReaderPreferences)=>void}){
  const [open,setOpen]=useState(false),[draft,setDraft]=useState(value),[error,setError]=useState(""),[section,setSection]=useState("preferences");
  return <><button type="button" onClick={()=>{setDraft(value);setError("");setSection("preferences");setOpen(true);}}><SlidersHorizontal size={16}/>阅读设置</button><Dialog open={open} onRequestClose={()=>setOpen(false)} className="reader-settings-dialog" aria-label="阅读设置"><header><h2>阅读设置</h2><button type="button" aria-label="关闭阅读设置" onClick={()=>setOpen(false)}><X size={18}/></button></header>
    <div className="reader-settings-body"><nav aria-label="设置栏目">{[["preferences","阅读偏好"],["display","显示设置"],["accessibility","辅助功能"]].map(([key,label])=><button key={key} type="button" aria-pressed={section===key} onClick={()=>setSection(key)}>{label}</button>)}</nav><section><fieldset hidden={section==="display"}><legend>页面动效</legend><p>减少界面中的动态效果，提供更稳定的阅读体验。</p><label><input type="radio" name="reader-motion" checked={draft.motion==="system"} onChange={()=>setDraft({...draft,motion:"system"})}/>默认（跟随系统）</label><label><input type="radio" name="reader-motion" checked={draft.motion==="reduced"} onChange={()=>setDraft({...draft,motion:"reduced"})}/>减少动态效果</label></fieldset><fieldset hidden={section==="accessibility"}><legend>其他设置</legend><label>默认展开目录<input type="checkbox" checked={draft.outline} onChange={event=>setDraft({...draft,outline:event.target.checked})}/></label><label>高亮颜色<select data-stl-select value={draft.highlight} onChange={event=>setDraft({...draft,highlight:event.target.value as ReaderPreferences["highlight"]})}><option value="gold">浅金色（默认）</option><option value="gray">暖灰色</option></select></label></fieldset><p>偏好保存在当前浏览器，不改变已经保存的笔记内容。</p></section></div>
    {error?<p role="alert">{error}</p>:null}<footer><button type="button" onClick={()=>setOpen(false)}>取消</button><button type="button" onClick={()=>{try{onSave(draft);setOpen(false);}catch{setError("浏览器未允许保存设置，请检查本机存储权限后重试。");}}}>保存设置</button></footer></Dialog></>;
}
