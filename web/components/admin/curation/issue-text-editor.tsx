"use client";

import { useRef, useState } from "react";
import { Bold, Italic, Link2, List, ListOrdered, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { safeEditorialLink } from "@/components/public/issue-prose";
import type { IssueBlock, IssueTextMark } from "@/lib/api/recommendation-issues.types";
import styles from "./issue-editor.module.css";

/** Keep marks anchored around a single text edit; replaced characters inherit
 * the containing mark, while ranges entirely deleted are removed. */
export function editIssueMarks(before:string,after:string,marks:IssueTextMark[]) {
  let start=0,oldEnd=before.length,newEnd=after.length;
  while(start<oldEnd&&start<newEnd&&before[start]===after[start])start++;
  while(oldEnd>start&&newEnd>start&&before[oldEnd-1]===after[newEnd-1]){oldEnd--;newEnd--;}
  const insidePair=(text:string,position:number)=>position>0&&position<text.length&&/[\uD800-\uDBFF]/.test(text[position-1])&&/[\uDC00-\uDFFF]/.test(text[position]);
  if(insidePair(before,start)||insidePair(after,start))start--;
  while(insidePair(before,oldEnd)||insidePair(after,newEnd)){oldEnd++;newEnd++;}
  const delta=newEnd-oldEnd;
  return marks.flatMap(mark=>{
    if(mark.end<=start)return [mark];
    if(mark.start>=oldEnd)return [{...mark,start:mark.start+delta,end:mark.end+delta}];
    if(mark.kind==="link" && !(mark.start<=start&&mark.end>=oldEnd))return [
      ...(mark.start<start?[{...mark,end:start}]:[]),
      ...(mark.end>oldEnd?[{...mark,start:newEnd,end:mark.end+delta}]:[]),
    ];
    const left=Math.min(mark.start,start),right=mark.end>oldEnd?mark.end+delta:newEnd;
    return right>left?[{...mark,start:left,end:right}]:[];
  });
}
export function IssueTextEditor({block,label,onChange}:{block:IssueBlock;label:string;onChange:(patch:Partial<IssueBlock>)=>void}) {
  const area=useRef<HTMLTextAreaElement>(null),selection=useRef({start:0,end:0});
  const [message,setMessage]=useState(""),[linkOpen,setLinkOpen]=useState(false),[href,setHref]=useState("");
  const prose=!["heading","image","link"].includes(block.type)&&!(block.type==="analysis"&&block.style==="heading");
  function remember(){if(area.current)selection.current={start:area.current.selectionStart,end:area.current.selectionEnd};}
  function mark(kind:IssueTextMark["kind"],url?:string) {
    const {start,end}=selection.current;
    if(start===end){setMessage("请先选择需要设置格式的导读文字。");area.current?.focus();return;}
    const marks=block.text_marks || [],existing=marks.find(row=>row.kind===kind&&row.start===start&&row.end===end);
    if(marks.length>=200&&!existing){setMessage("本段已达到200处文字格式，请先移除不需要的格式。");return;}
    const next=marks.filter(row=>!(row.kind===kind&&(kind==="link"?row.start<end&&row.end>start:row.start===start&&row.end===end)));
    if(!existing || kind==="link")next.push({start,end,kind,...(url?{href:url}:{})});
    onChange({text_marks:next});setMessage("");
    requestAnimationFrame(()=>{area.current?.focus();area.current?.setSelectionRange(start,end);});
  }
  return <div className={styles.textEditor}><div className={styles.textToolbar} role="toolbar" aria-label={`${label}格式`}>
    <label><span className="sr-only">段落格式</span><select disabled={!prose} value={block.text_style || "paragraph"} onChange={event=>onChange({text_style:event.target.value as IssueBlock["text_style"]})}><option value="paragraph">段落</option><option value="unordered">无序列表</option><option value="ordered">有序列表</option></select></label>
    <button type="button" aria-label="加粗所选文字" title="加粗 · Ctrl/⌘ B" onClick={()=>mark("strong")}><Bold size={15}/></button><button type="button" aria-label="斜体所选文字" title="斜体 · Ctrl/⌘ I" onClick={()=>mark("em")}><Italic size={15}/></button><button type="button" aria-label="为所选文字添加链接" disabled={block.type==="link"} onClick={()=>{if(selection.current.start===selection.current.end){setMessage("请先选择需要链接的文字。");return;}setHref("");setLinkOpen(true);}}><Link2 size={15}/></button><button type="button" aria-label="切换无序列表" disabled={!prose} aria-pressed={block.text_style==="unordered"} onClick={()=>onChange({text_style:block.text_style==="unordered"?"paragraph":"unordered"})}><List size={15}/></button><button type="button" aria-label="切换有序列表" disabled={!prose} aria-pressed={block.text_style==="ordered"} onClick={()=>onChange({text_style:block.text_style==="ordered"?"paragraph":"ordered"})}><ListOrdered size={15}/></button><button type="button" disabled={!block.text_marks?.length} onClick={()=>onChange({text_marks:[],text_style:"paragraph"})}>清除格式</button></div>
    <label><span>{label}</span><textarea ref={area} rows={5} maxLength={["paragraph","heading","quote","link","image"].includes(block.type)?30000:6000} value={block.text} onSelect={remember} onKeyUp={remember} onMouseUp={remember} onKeyDown={event=>{if((event.ctrlKey||event.metaKey)&&["b","i"].includes(event.key.toLowerCase())){event.preventDefault();remember();mark(event.key.toLowerCase()==="b"?"strong":"em");}}} onChange={event=>{onChange({text:event.target.value,...(block.text_marks?.length?{text_marks:editIssueMarks(block.text,event.target.value,block.text_marks)}:{})});}}/></label>
    <small>已设置 {block.text_marks?.length || 0} 处文字格式 · 效果同步显示在文章预览</small>{message?<p role="status">{message}</p>:null}
    <Dialog open={linkOpen} onRequestClose={()=>setLinkOpen(false)} className={styles.dialog} aria-label="设置导读链接"><header><h2>设置导读链接</h2><button type="button" aria-label="关闭链接设置" onClick={()=>setLinkOpen(false)}><X size={18}/></button></header><label>链接地址<input type="url" maxLength={1500} value={href} onChange={event=>setHref(event.target.value)} placeholder="https:// 或本站路径"/></label><button type="button" disabled={!safeEditorialLink(href)} onClick={()=>{mark("link",href);setLinkOpen(false);}}>应用链接</button><button type="button" onClick={()=>{const {start,end}=selection.current;onChange({text_marks:block.text_marks?.filter(row=>row.kind!=="link" || row.start>=end || row.end<=start)});setLinkOpen(false);}}>移除所选文字的链接</button></Dialog>
  </div>;
}
