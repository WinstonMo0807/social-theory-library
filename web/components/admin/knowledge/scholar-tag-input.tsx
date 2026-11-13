"use client";

import { isImeComposing } from "@/lib/search-submit-key";
import { Plus, X } from "lucide-react";
import styles from "./scholar-editor.module.css";

/** Each edit updates the existing draft immediately; there is no second tag store. */
export function ScholarTagInput({label,value,onChange,addLabel="添加标签"}:{addLabel?:string;label:string;value:string[];onChange:(value:string[])=>void}) {
  return <div className={styles.tagInput}><span>{label}</span><div>{value.map((item,index)=><label key={index}><span className="sr-only">{label}第 {index+1} 项</span><input value={item} maxLength={240} size={Math.max(3,Math.min(18,item.length+1))} autoFocus={index===value.length-1&&!item} onChange={event=>onChange(value.map((row,at)=>at===index?event.target.value:row))} onKeyDown={event=>{if(event.key==="Enter"&&!isImeComposing(event)){event.preventDefault();if(item.trim())onChange([...value,""]);}}}/><button type="button" aria-label={"移除"+(item||label)} onClick={()=>onChange(value.filter((_,at)=>at!==index))}><X size={11}/></button></label>)}<button type="button" onClick={()=>onChange([...value,""])}><Plus size={12}/>{addLabel}</button></div></div>;
}
