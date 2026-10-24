import { Fragment, type ReactNode } from "react";
import type { IssueBlock } from "@/lib/api/recommendation-issues.types";

export function safeEditorialLink(value:string) {
  if(value.length>1500 || /[\\\u0000-\u0020]/.test(value))return false;
  if(/^\/(?!\/)/.test(value))return true;
  try {const url=new URL(value);return ["http:","https:"].includes(url.protocol)&&Boolean(url.hostname);}catch{return false;}
}
/** Render only text and a fixed set of marks, never arbitrary stored HTML. */
export function IssueInline({block,from=0,to=block.text.length}:{block:IssueBlock;from?:number;to?:number}) {
  const marks=(block.text_marks || []).filter(mark=>Number.isInteger(mark.start)&&Number.isInteger(mark.end)&&mark.start>=0&&mark.end<=block.text.length&&mark.end>mark.start&&mark.end>from&&mark.start<to);
  const points=[...new Set([from,to,...marks.flatMap(mark=>[Math.max(from,mark.start),Math.min(to,mark.end)])])].sort((a,b)=>a-b);
  return <>{points.slice(0,-1).map((start,index)=>{
    const end=points[index+1],active=marks.filter(mark=>mark.start<=start&&mark.end>=end);
    let text:ReactNode=block.text.slice(start,end);
    if(active.some(mark=>mark.kind==="strong"))text=<strong>{text}</strong>;
    if(active.some(mark=>mark.kind==="em"))text=<em>{text}</em>;
    if(active.some(mark=>mark.kind==="underline"))text=<u>{text}</u>;
    const link=block.type!=="link"?active.find(mark=>mark.kind==="link"&&safeEditorialLink(mark.href || "")):undefined;
    if(link)text=<a href={link.href} rel="noopener noreferrer">{text}</a>;
    return <Fragment key={start}>{text}</Fragment>;
  })}</>;
}
export function IssueProse({block}:{block:IssueBlock}) {
  if(block.text_style==="quote") return <blockquote style={{whiteSpace:"pre-wrap"}}><IssueInline block={block}/></blockquote>;
  if(block.text_style==="ordered" || block.text_style==="unordered") {
    const Tag=block.text_style==="ordered"?"ol":"ul",lines=[];let offset=0;
    for(const line of block.text.split("\n")){lines.push({line,from:offset});offset+=line.length+1;}
    return <Tag>{lines.map(({line,from})=><li key={from}><IssueInline block={block} from={from} to={from+line.length}/></li>)}</Tag>;
  }
  return <p style={{whiteSpace:"pre-wrap"}}><IssueInline block={block}/></p>;
}
