"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { ArrowUpRight, CheckCircle2, CircleAlert, Info, Monitor, Smartphone } from "lucide-react";
import type { PublicationDeskData } from "./publication-ledger";
import { withAdminReturn } from "@/lib/admin-route-context";
import styles from "./publication-review.module.css";

const date=(value:string|null|undefined)=>value?new Date(value).toLocaleString("zh-CN"):"尚无记录";
const changeNames={unchanged:"已关联",added:"新增",removed:"移除"};

function Section({number,title,children}:{number:number;title:string;children:ReactNode}) {
  return <section className={styles.section}><h2><span>{number}</span>{title}</h2>{children}</section>;
}

export function PublicationReview({data,cover,locked,canPublish,onPublish}:{data:PublicationDeskData;cover:ReactNode;locked:boolean;canPublish:boolean;onPublish:()=>void}) {
  const [device,setDevice]=useState("desktop"),[width,setWidth]=useState(390),[previewState,setPreviewState]=useState("loading");
  const container=useRef<HTMLDivElement|null>(null),iframe=useRef<HTMLIFrameElement|null>(null);
  const review=data.review,preparation=data.preparation;
  const path=`/admin/publication/${data.edition_id}?object=edition`;
  const editor=withAdminReturn(data.workbench_url,path);
  const frame=`${data.preview_url}?${new URLSearchParams({frame:"1",version:data.version,fingerprint:preparation.fingerprint,return_to:path})}`;
  useEffect(()=>{const node=container.current;if(!node)return;const observer=new ResizeObserver(entries=>setWidth(entries[0].contentRect.width));observer.observe(node);return()=>observer.disconnect();},[]);
  useEffect(()=>{
    const timer=window.setTimeout(()=>setPreviewState(value=>value==="loading"?"error":value),35000);
    function receive(event:MessageEvent){
      const value=event.data;
      if(event.origin===window.location.origin&&event.source===iframe.current?.contentWindow&&value?.type==="stl:publication-preview"&&value.editionId===data.edition_id&&value.version===data.version&&value.fingerprint===preparation.fingerprint){setPreviewState(value.ok?"ready":"error");window.clearTimeout(timer);}
    }
    window.addEventListener("message",receive);return()=>{window.clearTimeout(timer);window.removeEventListener("message",receive);};
  },[data.edition_id,data.version,preparation.fingerprint]);
  if(!review)return <p role="alert">未返回完整发布检查，请重新读取。</p>;
  const all=preparation.changes,fields=["title","authors","abstract","theories","topics","version_label"],main=all.filter(row=>fields.includes(row.field));
  const original=all.find(row=>row.field==="original_title"),kind=all.find(row=>row.field==="document_type");
  const extra=all.filter(row=>!fields.includes(row.field)&&row.change!=="unchanged"),frameWidth=device==="mobile"?390:1180,frameHeight=device==="mobile"?760:1100,scale=Math.min(1,width/frameWidth);
  const blockers=preparation.blocking.length;
  return <div className={styles.layout}>
    <main className={styles.main}>
      <Section number={1} title="发布对象"><div className={styles.object}><div className={styles.book}>{cover}<div><h3>{data.title}</h3>{original?.after_display?<p>{original.after_display}</p>:null}<p>{data.authors||"责任者待确认"}</p><div className={styles.tags}><span>{kind?.after_display||"馆藏"}</span>{review.relations.find(row=>row.field==="topics")?.items.filter(row=>row.change!=="removed").slice(0,2).map(row=><span key={row.id}>{row.label}</span>)}</div></div></div><div className={styles.current}><header><strong>当前公开页</strong>{data.publication.public_url?<a href={data.publication.public_url} target="_blank" rel="noopener">查看当前公开页 <ArrowUpRight size={14}/></a>:null}</header><p>当前公开修订：{review.current?`第 ${review.current.revision} 次发布`:"尚无有效公开修订"}</p><p>最后发布：{date(review.current?.activated_at)}</p></div></div></Section>
      <Section number={2} title="内容变化"><div className={styles.comparison}>{(["before","after"] as const).map(side=><section key={side}><header><h3>{side==="before"?"当前线上版本":"待发布草稿"}</h3><span>{side==="before"?(review.current?`第 ${review.current.revision} 次发布`:"尚未公开"):"已保存"}</span></header><dl>{main.map(row=><div key={row.field}><dt>{row.label}</dt><dd data-changed={side==="after"&&row.change!=="unchanged"||undefined}>{row[`${side}_display`]||"未填写"}</dd></div>)}<div><dt>文件页数</dt><dd data-changed={side==="after"&&review.page_count_after!==review.page_count_before||undefined}>{(side==="before"?review.page_count_before:review.page_count_after)??"无阅读文件"}</dd></div></dl></section>)}</div>{extra.length?<details className={styles.more}><summary>查看其余 {extra.length} 项变化</summary><dl>{extra.map(row=><div key={row.field}><dt>{row.label}</dt><dd><span>{row.before_display||"未填写"}</span><span aria-hidden="true"> → </span><mark>{row.after_display||"未填写"}</mark></dd></div>)}</dl></details>:null}</Section>
      <Section number={3} title="关联内容"><div className={styles.relations}>{review.relations.map(group=><section key={group.field}><h3>{group.title}（{group.count}）</h3><ul>{group.items.slice(0,4).map(row=><li key={row.id} data-change={row.change}><span aria-hidden="true">{row.change==="removed"?"−":row.change==="added"?"＋":"✓"}</span>{row.label}<small>（{changeNames[row.change]}）</small></li>)}</ul>{!group.items.length?<p>尚未关联</p>:null}{group.items.length>4?<details><summary>查看全部 {group.items.length} 项</summary><ul>{group.items.slice(4).map(row=><li key={row.id} data-change={row.change}>{row.label}（{changeNames[row.change]}）</li>)}</ul></details>:null}<Link href={withAdminReturn(data.workbench_url.replace(/#.*$/,group.field==="authors"?"#contributors":"#knowledge"),path)}>核对关联 →</Link></section>)}<section><h3>检索索引</h3><p>{data.publication.fulltext_ready?"当前公开全文已就绪":"当前公开全文未就绪"}</p><p>新发布内容由原任务更新。</p>{preparation.background_processing.length?<ul>{preparation.background_processing.map(row=><li key={row}>{row}</li>)}</ul>:null}<Link href={editor}>查看处理记录 →</Link></section></div></Section>
      <Section number={4} title="发布检查"><div className={styles.checks}>{review.checks.map(row=><article key={row.key}>{row.state==="ready"?<CheckCircle2 size={18}/>:row.state==="warning"?<CircleAlert size={18}/>:<Info size={18}/>}<div><h3>{row.title}</h3><p>{row.detail}</p><Link href={withAdminReturn(row.href,path)}>检查详情 →</Link></div></article>)}</div><div className={styles.checkDetails}>
        {blockers?<section role="alert"><h3>发布前必须处理 · {blockers} 项</h3><ul>{preparation.blocking.map(row=><li key={row}>{row}</li>)}</ul><Link href={editor}>返回编目处理 →</Link></section>:<p><CheckCircle2 size={15}/>本次检查没有阻断项，发布时会再次核验。</p>}
        {preparation.warnings.length?<details open><summary>仍需核对 · {preparation.warnings.length} 项提醒</summary><ul>{preparation.warnings.map(row=><li key={row}>{row}</li>)}</ul></details>:null}
      </div></Section>
      <Section number={5} title="版本记录"><dl className={styles.record}><div><dt>本稿保存者</dt><dd>{review.saved_by||"未记录"}</dd></div><div><dt>最近保存</dt><dd>{date(review.saved_at)}</dd></div><div><dt>变更说明</dt><dd>{review.note||"尚未填写说明"}</dd></div><div><dt>本次发布</dt><dd>确认后生成正式修订，实际序号与时间以发布记录为准。</dd></div></dl><Link href={`/admin/publication/${data.edition_id}?object=edition&view=history`}>查看版本历史 →</Link></Section>
    </main>
    <aside className={styles.preview}><header><h2>公开页预览（草稿）</h2><span>这是未发布预览</span></header><nav aria-label="草稿预览设备"><button type="button" aria-pressed={device==="desktop"} onClick={()=>setDevice("desktop")}><Monitor size={15}/>桌面端预览</button><button type="button" aria-pressed={device==="mobile"} onClick={()=>setDevice("mobile")}><Smartphone size={15}/>移动端预览</button></nav><div ref={container} className={styles.viewport} style={{height:frameHeight*scale}}><iframe ref={iframe} title="出版版本草稿预览" src={frame} style={{width:frameWidth,height:frameHeight,transform:`scale(${scale})`,marginLeft:Math.max(0,(width-frameWidth*scale)/2)}}/></div><a className={styles.previewLink} href={frame} target="_blank" rel="noopener">完整预览 <ArrowUpRight size={14}/></a>
      {previewState!=="ready"?<p className={styles.notice} role={previewState==="error"?"alert":"status"}>{previewState==="error"?"预览未能确认，请重新检查后继续。":"正在读取本次检查对应的草稿预览…"}</p>:null}
      <p className={styles.notice}>{blockers?`还有 ${blockers} 项必须处理，请完成后发布。`:!canPublish?"当前账户没有发布权限，可返回编辑。":preparation.warnings.length?`还有 ${preparation.warnings.length} 项提醒，请核对授权与公开范围。`:"请核对公开范围与预览，确认后发布。"}</p>
      <button type="button" className={styles.primary} disabled={locked||!canPublish||!preparation.can_publish||previewState!=="ready"} onClick={onPublish}>完成检查后发布 →</button><div className={styles.returnActions}><button type="button" disabled title="本页读取的内容已经保存">草稿已保存</button><Link href={editor}>返回编辑</Link></div>
    </aside>
  </div>;
}
