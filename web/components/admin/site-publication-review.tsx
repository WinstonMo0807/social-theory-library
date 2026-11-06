"use client";

import { useCallback, useState, type ReactNode } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import type { SiteContentDraft } from "@/lib/api/recommendation-issues.types";
import { Dialog } from "@/components/ui/dialog";
import { PreviewViewport } from "./curation/fixed-page-editor";
import { siteBase, type useSiteContent } from "./use-site-content";
import styles from "./site-content.module.css";

type Check = {code:string;severity:string;title:string;detail:string;section:string;slot_id:string};
type Review = {edit_version:string;fingerprint:string;checked_at:string;snapshot:SiteContentDraft;can_publish:boolean;
  checks:Check[];changes:Array<{field:string;label:string;before_display:string;after_display:string;change:string}>};

export function SitePublicationReview({owner,editor,preview,onBack,onHistory,initialPage="home"}:{initialPage?:string;owner:string;editor:ReturnType<typeof useSiteContent>;
  preview:(snapshot:SiteContentDraft,page:string)=>ReactNode;onBack:(section?:string,slot?:string)=>void;onHistory:()=>void}) {
  const [tab,setTab]=useState("preview"),[confirm,setConfirm]=useState<Review|null>(null),[page,setPage]=useState(initialPage);
  const version=editor.draft?.edit_version;
  const load=useCallback((path:string,signal:AbortSignal)=>apiRequest<Review>(path,{signal,cache:"no-store",headers:{"X-Editor-Owner":owner}},getServerSessionCredential(),false),[owner]);
  const resource=usePersistentWorkspace<Review>(version?`${siteBase}review/?edit_version=${encodeURIComponent(version)}`:"",owner,undefined,load);
  const review=resource.error?null:resource.data;
  const locked=editor.busy||Boolean(editor.operation)||editor.blocked||editor.conflict||editor.dirty;
  const publishable=Boolean(!locked&&!resource.loading&&review?.can_publish&&review.edit_version===version);
  const changes=<section className={styles.reviewPanel}><h2>本次发布将改变什么</h2><p>当前公开内容与已保存草稿比较，包含欢迎页、首页编排及所有公共说明与公告。</p><div className={styles.reviewTable}><table><thead><tr><th>内容</th><th>当前公开</th><th>已保存草稿</th></tr></thead><tbody>{review?.changes.map(row=><tr key={row.field}><th>{row.label}</th><td><pre>{row.before_display}</pre></td><td><pre>{row.after_display}</pre></td></tr>)}</tbody></table></div>{review&&!review.changes.length?<p>当前没有内容差异。</p>:null}</section>;
  const checks=<section className={styles.reviewPanel}><h2>发布检查</h2><p>检查时间 {review?new Date(review.checked_at).toLocaleString("zh-CN"):"尚未读取"}。原文授权、图片权利仍需人工核对，不以自动检查代替许可。</p>{review?.checks.map((row,index)=><div key={`${row.code}:${row.slot_id}:${index}`} className={styles.reviewCheck} data-severity={row.severity}><div><strong>{row.severity==="blocking"?"必须处理":"请核对"} · {row.title}</strong><p>{row.detail}</p></div><button disabled={editor.busy} onClick={()=>onBack(row.section,row.slot_id)}>定位修改</button></div>)}{review&&!review.checks.length?<p>当前规则未发现阻断或提醒。发布时将重新核对保存版本与来源。</p>:null}</section>;
  const settings=<section className={styles.reviewPanel}><h2>发布范围</h2><p>一次发布同步更新欢迎页、首页、关于、公共说明与公告。来源对象的公开状态与读者私人记录保持各自原有规则。</p><p>{review?.snapshot.has_unpublished_changes?"已有已保存草稿，确认后替换网站公开文字与编排。":"当前没有待发布的网站草稿。"}</p><p>若只想修正当前输入，请返回编辑器；保存后再核对这份完整预览。</p><button onClick={()=>onBack()}>返回网站内容</button><button onClick={onHistory}>查看版本历史</button><a href="/home" target="_blank" rel="noopener noreferrer">查看当前公开首页 ↗</a></section>;
  return <main className={styles.page}><header className={styles.heading}><h1>预览与发布</h1><p>欢迎页、首页、关于、公共说明与公告 · 已保存版本</p><div className={styles.reviewActions}><button disabled={editor.busy} onClick={()=>onBack()}>返回编辑器</button><button disabled={editor.busy||Boolean(editor.operation)} onClick={resource.reload}>重新核对</button><button className={styles.primary} disabled={!publishable} onClick={()=>setConfirm(review)}>发布已检查版本</button></div></header>
    {editor.message?<p role="status" className={styles.notice}>{editor.message}</p>:null}
    {editor.operation?<aside className={styles.warning}><p>原操作结果尚未确认，先查询或停止原请求。</p><button disabled={editor.busy} onClick={()=>void editor.recover()}>查询原结果</button>{editor.operation.body?<button disabled={editor.busy} onClick={()=>void editor.persist()}>重试原请求</button>:null}<button disabled={editor.busy} onClick={()=>void editor.recover(true)}>停止尚未执行的请求</button></aside>:null}
    {editor.dirty?<aside className={styles.warning}><p>当前仍有未保存输入，下方显示已保存版本。</p><button disabled={editor.busy||Boolean(editor.operation)||editor.conflict} onClick={()=>void editor.persist()}>保存输入后重新检查</button></aside>:null}
    {editor.conflict?<p className={styles.warning}>服务器版本已变化，请返回编辑器比较并处理冲突。</p>:null}
    <nav className={styles.tabs} aria-label="固定页面发布检查">{[["preview","页面预览"],["changes","版本差异"],["checks","发布检查"],["settings","发布设置"]].map(([id,label])=><button key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</nav>
    {resource.loading?<p role="status">正在读取已保存页面与来源状态…</p>:null}{resource.error?<p role="alert" className={styles.warning}>{resource.error}<button onClick={resource.reload}>重新读取</button></p>:null}
    {review&&!resource.loading?<div className={styles.reviewColumns} data-tab={tab}>{tab==="preview"?<><section className={styles.reviewPanel}><h2>完整已保存页面</h2><nav className={styles.tabs} aria-label="网站预览页面">{[["welcome","欢迎页"],["home","首页"],["about","关于书库"],["content","公共说明"],["updates","公告"]].map(([key,label])=><button key={key} aria-pressed={page===key} onClick={()=>setPage(key)}>{label}</button>)}</nav><PreviewViewport locateFields={false}>{preview(review.snapshot,page)}</PreviewViewport></section><aside>{changes}{checks}{settings}</aside></>:tab==="changes"?changes:tab==="checks"?checks:settings}</div>:null}
    <Dialog open={Boolean(confirm)} onRequestClose={()=>{if(!editor.busy)setConfirm(null);}} className={styles.reviewDialog} aria-label="确认发布网站已检查版本"><h2>确认发布已检查的网站版本</h2><p>欢迎页、首页、关于、公共说明与公告会一起更新。请确认已核对提醒及公开范围。</p>{confirm&&confirm!==review?<p role="alert">检查内容已变化，请关闭窗口并重新核对本次发布范围。</p>:null}{editor.message?<p role="status">{editor.message}</p>:null}<div className={styles.reviewActions}><button disabled={editor.busy} onClick={()=>setConfirm(null)}>返回核对</button><button disabled={!publishable||!confirm||confirm!==review} onClick={()=>{if(confirm&&confirm===review)void editor.persist(true,confirm.fingerprint).then(applied=>{if(applied)setConfirm(null);resource.reload();});}}>确认发布</button></div></Dialog>
  </main>;
}
