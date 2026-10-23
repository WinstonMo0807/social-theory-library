"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Bold, Italic, Link2, List, ListOrdered, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { safeEditorialLink } from "@/components/public/issue-prose";
import type { IssueBlock, IssueTextMark } from "@/lib/api/recommendation-issues.types";
import styles from "./issue-editor.module.css";

type TextValue={text:string;text_marks:IssueTextMark[];text_style:NonNullable<IssueBlock["text_style"]>};
type Selection={start:number;end:number};
type Step={value:TextValue;selection:Selection};
const blockTags=new Set(["DIV","P","LI","UL","OL"]);
function orderedMarks(values:IssueTextMark[]) {
  const result:IssueTextMark[]=[];
  for(const value of [...values].sort((a,b)=>a.kind.localeCompare(b.kind)||(a.href||"").localeCompare(b.href||"")||a.start-b.start||a.end-b.end)) {
    const previous=result.at(-1);
    if(previous&&previous.kind===value.kind&&previous.href===value.href&&previous.end>=value.start)previous.end=Math.max(previous.end,value.end);
    else result.push({...value});
  }
  return result;
}
function textValue(block:IssueBlock):TextValue{return {text:block.text,text_marks:orderedMarks(block.text_marks||[]),text_style:block.text_style||"paragraph"};}
const signature=(value:TextValue)=>JSON.stringify(value);

/** Read a fixed text/mark model from the native editing surface. Neither HTML
 * nor pasted styles enter a draft. Positions use the same UTF-16 units as DOM. */
function inspect(root:HTMLElement) {
  let text="";const marks:IssueTextMark[]=[],positions=new Map<Node,number[]>(),leaves:Array<{node:Node;start:number;end:number}>=[];
  function walk(node:Node,active:Omit<IssueTextMark,"start"|"end">[]) {
    if(node.nodeType===Node.TEXT_NODE){const start=text.length;const value=node.textContent||"";positions.set(node,[start]);text+=value;leaves.push({node,start,end:text.length});for(const mark of active)if(value)marks.push({...mark,start,end:text.length});return;}
    if(!(node instanceof HTMLElement))return;
    if(node.tagName==="BR"){if(node.nextSibling || node.previousSibling&&!(node.previousSibling instanceof HTMLElement&&node.previousSibling.tagName==="BR"))text+="\n";positions.set(node,[text.length]);return;}
    const weight=node.style.fontWeight;
    const next=active.filter(mark=>!(mark.kind==="strong"&&(weight==="normal"||Number.parseInt(weight)<600))&&!(mark.kind==="em"&&node.style.fontStyle==="normal"));
    if(["B","STRONG"].includes(node.tagName)||["bold","bolder"].includes(weight)||Number.parseInt(weight)>=600)next.push({kind:"strong"});
    if(["I","EM"].includes(node.tagName)||node.style.fontStyle==="italic")next.push({kind:"em"});
    if(node.tagName==="A"&&safeEditorialLink(node.getAttribute("href")||""))next.push({kind:"link",href:node.getAttribute("href")!});
    const children=[...node.childNodes],boundaries:number[]=[];
    for(const [index,child] of children.entries()){
      const prior=children[index-1];
      if(index>0&&((child instanceof HTMLElement&&blockTags.has(child.tagName))||(prior instanceof HTMLElement&&blockTags.has(prior.tagName))))text+="\n";
      boundaries.push(text.length);walk(child,next);
    }
    boundaries.push(text.length);positions.set(node,boundaries);
  }
  walk(root,[]);
  const first=root.firstElementChild,onlyList=first&&["UL","OL"].includes(first.tagName)&&[...root.childNodes].every(node=>node===first||!node.textContent?.trim());
  const value:TextValue={text,text_marks:orderedMarks(marks),text_style:onlyList?(first.tagName==="OL"?"ordered":"unordered"):"paragraph"};
  function offset(node:Node,position:number){const values=positions.get(node);return values?node.nodeType===Node.TEXT_NODE?values[0]+Math.min(position,node.textContent?.length||0):values[Math.min(position,values.length-1)]:0;}
  function selection():Selection|null{const range=window.getSelection()?.rangeCount?window.getSelection()!.getRangeAt(0):null;return range&&root.contains(range.startContainer)&&root.contains(range.endContainer)?{start:offset(range.startContainer,range.startOffset),end:offset(range.endContainer,range.endOffset)}:null;}
  function select(selected:Selection){
    const range=document.createRange();
    function point(at:number):[Node,number]{const index=Math.max(0,Math.min(at,text.length)),leaf=leaves.find(row=>index>=row.start&&index<=row.end)||leaves.at(-1);return leaf?[leaf.node,Math.max(0,Math.min(index-leaf.start,leaf.end-leaf.start))]:[root,0];}
    range.setStart(...point(selected.start));range.setEnd(...point(selected.end));const current=window.getSelection();current?.removeAllRanges();current?.addRange(range);
  }
  return {value,selection,select};
}
function renderText(root:HTMLElement,value:TextValue) {
  const fragment=document.createDocumentFragment();
  function inline(parent:Node,from:number,to:number){
    const marks=value.text_marks.filter(mark=>mark.end>from&&mark.start<to),points=[...new Set([from,to,...marks.flatMap(mark=>[Math.max(from,mark.start),Math.min(to,mark.end)])])].sort((a,b)=>a-b);
    for(let index=0;index<points.length-1;index++){
      const start=points[index],end=points[index+1],active=marks.filter(mark=>mark.start<=start&&mark.end>=end);let node:Node=document.createTextNode(value.text.slice(start,end));
      for(const kind of ["strong","em","link"] as const){const mark=active.find(row=>row.kind===kind);if(mark&&(kind!=="link"||safeEditorialLink(mark.href||""))){const element=document.createElement(kind==="link"?"a":kind);if(kind==="link")element.setAttribute("href",mark.href!);element.appendChild(node);node=element;}}
      parent.appendChild(node);
    }
    if(from===to)parent.appendChild(document.createTextNode(""));
  }
  if(value.text_style==="paragraph")inline(fragment,0,value.text.length);
  else {const list=document.createElement(value.text_style==="ordered"?"ol":"ul");let offset=0;for(const line of value.text.split("\n")){const item=document.createElement("li");inline(item,offset,offset+line.length);list.appendChild(item);offset+=line.length+1;}fragment.appendChild(list);}
  root.replaceChildren(fragment);
}

export function IssueTextEditor({block,label,disabled=false,onChange,onComposition,maxLength}:{block:IssueBlock;label:string;disabled?:boolean;onChange:(patch:Partial<IssueBlock>)=>void;onComposition?:(value:boolean)=>void;maxLength?:number}) {
  const id=useId(),area=useRef<HTMLDivElement>(null),selection=useRef<Selection>({start:0,end:0}),composing=useRef(false);
  const undo=useRef<Step[]>([]),redo=useRef<Step[]>([]),last=useRef<TextValue|null>(null),restoreSelection=useRef(false);
  const [message,setMessage]=useState(""),[linkOpen,setLinkOpen]=useState(false),[href,setHref]=useState(""),[pressed,setPressed]=useState({strong:false,em:false});
  const [historySize,setHistorySize]=useState({undo:0,redo:0});
  const [redraw,setRedraw]=useState(0),painted=useRef(-1);
  const prose=!["heading","image","link"].includes(block.type)&&!(block.type==="analysis"&&block.style==="heading");
  const limit=maxLength??(["paragraph","heading","quote","link","image"].includes(block.type)?30000:6000);
  useLayoutEffect(()=>{
    const root=area.current;if(!root||composing.current)return;
    const expected=textValue(block),current=inspect(root),changed=painted.current!==redraw||signature(expected)!==signature(current.value)||Boolean(root.querySelector("ul,ol")&&expected.text_style==="paragraph");
    painted.current=redraw;
    if(last.current&&signature(last.current)!==signature(expected)){undo.current=[];redo.current=[];queueMicrotask(()=>setHistorySize({undo:0,redo:0}));}
    last.current=expected;
    const focus=document.activeElement===root,selected=restoreSelection.current?selection.current:current.selection();
    if(changed)renderText(root,expected);
    if((changed&&focus||restoreSelection.current)&&selected){root.focus({preventScroll:true});inspect(root).select(selected);}
    restoreSelection.current=false;
  },[block,redraw]);
  useEffect(()=>()=>onComposition?.(false),[onComposition]);
  function remember(){const root=area.current;if(!root)return;const current=inspect(root),selected=current.selection();if(!selected)return;selection.current=selected;setPressed({strong:current.value.text_marks.some(row=>row.kind==="strong"&&row.start<=selected.start&&row.end>=selected.end),em:current.value.text_marks.some(row=>row.kind==="em"&&row.start<=selected.start&&row.end>=selected.end)});}
  function publish(){
    if(!area.current||disabled||composing.current)return;
    const current=inspect(area.current),previous=last.current||textValue(block),previousSelection={...selection.current};const selected=current.selection();if(selected)selection.current=selected;
    setRedraw(value=>value+1);
    if(signature(current.value)!==signature(previous)){undo.current=[...undo.current.slice(-49),{value:previous,selection:previousSelection}];redo.current=[];last.current=current.value;onChange(current.value);setHistorySize({undo:undo.current.length,redo:0});}
    setMessage(current.value.text.length>limit||current.value.text_marks.length>200?`内容超过限制，请缩短到${limit}字以内，并保留不超过200处格式后保存。`:"");remember();
  }
  function format(patch:Partial<TextValue>){
    if(disabled||composing.current)return;
    const previous=last.current||textValue(block),next={...previous,...patch};if(signature(previous)===signature(next))return;
    undo.current=[...undo.current.slice(-49),{value:previous,selection:{...selection.current}}];redo.current=[];
    last.current=next;restoreSelection.current=true;onChange(next);setHistorySize({undo:undo.current.length,redo:0});setMessage("");
  }
  function history(direction:"undo"|"redo"){
    if(disabled||composing.current)return;const source=direction==="undo"?undo:redo,destination=direction==="undo"?redo:undo,step=source.current.at(-1);if(!step)return;
    source.current=source.current.slice(0,-1);destination.current=[...destination.current.slice(-49),{value:last.current||textValue(block),selection:{...selection.current}}];last.current=step.value;selection.current=step.selection;restoreSelection.current=true;onChange(step.value);setHistorySize({undo:undo.current.length,redo:redo.current.length});setMessage("");
  }
  function command(kind:string,value?:string){
    const root=area.current;if(!root||disabled||composing.current)return;
    const selected=selection.current;if(selected.start===selected.end&&kind!=="unlink"){setMessage("请先选择需要设置格式的文字。");return;}
    root.focus({preventScroll:true});inspect(root).select(selected);
    // Native formatting/input commands preserve browser IME behavior; only the
    // bounded text/marks result is retained. Undo is local to this block (50 steps).
    if(!document.execCommand(kind,false,value)){setMessage("此浏览器未完成这项编辑，请保留输入并使用文章预览核对。");return;}
    publish();inspect(root).select(selected);remember();
  }
  function style(value:NonNullable<IssueBlock["text_style"]>){
    // Each model line is exactly one list item, including blank lines. Avoid
    // native list conversion treating literal newlines as a single paragraph.
    if(prose)format({text_style:value});
  }
  function insertPlain(text:string){
    if(disabled||composing.current||!text)return;const root=area.current;if(!root)return;
    const current=inspect(root),selected=current.selection()||selection.current;root.focus({preventScroll:true});current.select(selected);
    if(current.value.text.length-(selected.end-selected.start)+text.length>limit){setMessage(`粘贴内容超过${limit}字限制，请分块整理；原输入已保留。`);return;}
    if(!document.execCommand("insertText",false,text.replace(/\r\n?/g,"\n"))){setMessage("浏览器未完成粘贴，原输入已保留。");return;}publish();
  }
  return <div className={styles.textEditor}><span id={`${id}-label`} className={styles.richLabel}>{label}</span><div className={styles.textToolbar} role="toolbar" aria-label={`${label}格式`}>
    <label><span className="sr-only">段落格式</span><select disabled={!prose||disabled} value={block.text_style||"paragraph"} onChange={event=>style(event.target.value as TextValue["text_style"])}><option value="paragraph">段落</option><option value="unordered">无序列表</option><option value="ordered">有序列表</option></select></label>
    <button type="button" disabled={disabled} aria-label="加粗所选文字" aria-pressed={pressed.strong} title="加粗 · Ctrl/⌘ B" onMouseDown={event=>event.preventDefault()} onClick={()=>command("bold")}><Bold size={15}/></button><button type="button" disabled={disabled} aria-label="斜体所选文字" aria-pressed={pressed.em} title="斜体 · Ctrl/⌘ I" onMouseDown={event=>event.preventDefault()} onClick={()=>command("italic")}><Italic size={15}/></button>
    <button type="button" disabled={disabled||block.type==="link"} aria-label="为所选文字添加链接" onClick={()=>{if(selection.current.start===selection.current.end){setMessage("请先选择需要链接的文字。");return;}setHref("");setLinkOpen(true);}}><Link2 size={15}/></button><button type="button" disabled={disabled||!prose} aria-label="切换无序列表" aria-pressed={block.text_style==="unordered"} onMouseDown={event=>event.preventDefault()} onClick={()=>style(block.text_style==="unordered"?"paragraph":"unordered")}><List size={15}/></button><button type="button" disabled={disabled||!prose} aria-label="切换有序列表" aria-pressed={block.text_style==="ordered"} onMouseDown={event=>event.preventDefault()} onClick={()=>style(block.text_style==="ordered"?"paragraph":"ordered")}><ListOrdered size={15}/></button><button type="button" disabled={disabled} onClick={()=>format({text_marks:[],text_style:"paragraph"})}>清除格式</button>
    <button type="button" disabled={disabled||!historySize.undo} onMouseDown={event=>event.preventDefault()} onClick={()=>history("undo")}>撤销</button><button type="button" disabled={disabled||!historySize.redo} onMouseDown={event=>event.preventDefault()} onClick={()=>history("redo")}>重做</button></div>
    <div ref={area} className={styles.richInput} role="textbox" aria-labelledby={`${id}-label`} aria-multiline="true" aria-readonly={disabled} contentEditable={!disabled} suppressContentEditableWarning tabIndex={disabled?-1:0} onInput={publish} onSelect={remember} onKeyUp={remember} onMouseUp={remember} onBlur={remember} onClick={event=>{if((event.target as HTMLElement).closest("a"))event.preventDefault();}}
      onCompositionStart={()=>{composing.current=true;onComposition?.(true);}} onCompositionEnd={()=>{composing.current=false;onComposition?.(false);publish();}}
      onBeforeInput={event=>{const type=(event.nativeEvent as InputEvent).inputType;if(type==="historyUndo"||type==="historyRedo"){event.preventDefault();history(type==="historyUndo"?"undo":"redo");}}}
      onKeyDown={event=>{if(composing.current||event.nativeEvent.isComposing)return;if(event.ctrlKey||event.metaKey){const key=event.key.toLowerCase();if(key==="z"||key==="y"){event.preventDefault();history(key==="y"||event.shiftKey?"redo":"undo");}else if(key==="b"||key==="i"){event.preventDefault();remember();command(key==="b"?"bold":"italic");}}}}
      onPaste={event=>{event.preventDefault();insertPlain(event.clipboardData.getData("text/plain"));}} onDrop={event=>{event.preventDefault();event.stopPropagation();insertPlain(event.dataTransfer.getData("text/plain"));}}/>
    <small>{block.text.length} / {limit} · 仅编辑本页文字，原材料保持只读</small>{message?<p role="status">{message}</p>:null}
    <Dialog open={linkOpen} onRequestClose={()=>setLinkOpen(false)} className={styles.dialog} aria-label="设置导读链接"><header><h2>设置导读链接</h2><button type="button" aria-label="关闭链接设置" onClick={()=>setLinkOpen(false)}><X size={18}/></button></header><label>链接地址<input type="url" maxLength={1500} value={href} onChange={event=>setHref(event.target.value)} placeholder="https:// 或本站路径"/></label><button type="button" disabled={disabled||!safeEditorialLink(href)} onClick={()=>{setLinkOpen(false);requestAnimationFrame(()=>command("createLink",href));}}>应用链接</button><button type="button" disabled={disabled} onClick={()=>{setLinkOpen(false);requestAnimationFrame(()=>command("unlink"));}}>移除所选文字的链接</button></Dialog>
  </div>;
}
