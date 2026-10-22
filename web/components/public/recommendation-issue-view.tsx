"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowLeft, ArrowRight, BookOpen, List, MessageSquare, Quote, Share2, X } from "lucide-react";
import type { RecommendationIssue, IssueItem, IssueBlock, IssueResolvedSource } from "@/lib/api/recommendation-issues.types";
import { SaveIssueList } from "@/components/save-issue-list";
import { Dialog } from "@/components/ui/dialog";
import { IssueBlockView } from "./issue-block-view";
import { IssueProse } from "./issue-prose";
import { EditorialByline, EditorialImage, EditorialRelated } from "./editorial-directory";
import { EditorialSource, EditorialSourceContent } from "./editorial-source";
import { ArticleComments } from "./article-comments";
import { EditorialReader } from "./editorial-reader";
import styles from "./editorial.module.css";

export function IssueItemCard({ item }: { item: IssueItem }) {
  return <article className={styles.material}><EditorialImage key={item.cover_url} src={item.cover_url || ""} className={styles.materialCover} /><div>
    <h3>{item.work_url ? <Link href={item.work_url}>{item.title}</Link> : item.title}</h3>{item.authors ? <p>{item.authors}</p> : null}{item.version_note ? <small>{item.version_note}</small> : null}
    <small>{item.reader_url ? "馆藏原文" : item.work_url ? "公开书目 · 暂无全文" : item.kind === "planned" ? "计划上架" : "馆藏暂不可用"}</small>
    {item.note ? <p>{item.note}</p> : null}{item.reader_url ? <Link className={styles.inlineAction} href={item.reader_url}>阅读全文 <ArrowRight size={13} /></Link> : null}
  </div></article>;
}
const heading = (block: IssueBlock) => block.type === "heading" || block.type === "analysis" && block.style === "heading";
const anchor = (block: IssueBlock, index: number) => `article-${block.id || index}`;
type Exhibit = { id: string; title: string; block?: IssueBlock; source?: IssueResolvedSource; item?: IssueItem };
function itemSource(item: IssueItem): IssueResolvedSource | undefined {
  if (!item.edition_id || !item.work_url) return undefined;
  const url = item.reader_url ? new URL(item.reader_url, "https://library.invalid") : null;
  return { type:"edition",id:item.edition_id,edition_id:item.edition_id,title:item.title,work_url:item.work_url,
    reader_url:item.reader_url,asset_id:url?.pathname.split("/").pop(),document_revision_id:url?.searchParams.get("revision") || undefined,edition_label:item.version_note };
}
function ExhibitionBody({issue,rows,base}:{issue:RecommendationIssue;rows:Exhibit[];base:string}){
  const groups:Array<{id:string;heading:IssueBlock|null;blocks:IssueBlock[]}>=[{id:"",heading:null,blocks:[]}];
  issue.body_blocks.forEach((block,index)=>{if(heading(block))groups.push({id:anchor(block,index),heading:block,blocks:[]});else groups[groups.length-1].blocks.push(block);});
  return <>{groups.map(group=>{
    const cards=rows.filter(row=>row.block?group.blocks.includes(row.block):(row.item?.section_id || "") === (group.heading?.id || ""));
    const prose=group.blocks.filter(block=>!cards.some(row=>row.block===block));
    if(!group.heading&&!cards.length&&!prose.length)return null;
    return <section key={group.id} id={group.id || "exhibit-introduction"} className={styles.exhibitGroup}>{group.heading?<IssueBlockView block={group.heading}/>:null}{prose.map((block,index)=><IssueBlockView key={block.id || index} block={block}/>)}<div className={styles.exhibitGrid}>{cards.map(row=><article key={row.id} className={styles.exhibitCard}>
      {row.item?<IssueItemCard item={row.item}/>:row.block?.type==="image"?<IssueBlockView block={row.block}/>:<><BookOpen size={25}/><h2>{row.title}</h2>{row.block?<IssueProse block={row.block}/>:null}</>}
      <Link href={`${base}?exhibit=${encodeURIComponent(row.id)}`}>{row.block?.type==="image"?"查看图像与资料":"进入展项"}<ArrowRight size={15}/></Link>
    </article>)}</div></section>;
  })}</>;
}
function exhibits(issue: RecommendationIssue): Exhibit[] {
  const rows: Exhibit[] = issue.body_blocks.flatMap((block, index) => block.type === "image" ? [{ id: block.id || String(index), title: block.text || "图像资料", block }] :
    ["work", "evidence"].includes(block.type) ? [{ id: block.id || String(index), title: block.resolved_sources?.[0]?.title || "来源暂不可用", block, source: block.resolved_sources?.[0] }] : []);
  for (const item of issue.items) {
    rows.push({ id: item.id, title: item.title, item, source: itemSource(item) });
  }
  return rows;
}
export function RecommendationIssueView({ issue, preview = false, selectedExhibit = "" }: { issue: RecommendationIssue; preview?: boolean; selectedExhibit?: string }) {
  const [commentCount, setCommentCount] = useState<number|null>(null);
  const [notice, setNotice] = useState(""), [citations, setCitations] = useState(false);
  const isExhibition = issue.article_metadata?.kind === "exhibition", headings = issue.body_blocks.flatMap((block,index) => heading(block) ? [{ id:anchor(block,index),text:block.text || "来源暂不可用的章节" }] : []);
  const materials = [...issue.body_blocks.flatMap(block => block.resolved_sources || []), ...issue.items.flatMap(item => { const source=itemSource(item); return source ? [source] : []; })].filter((source,index,rows) => rows.findIndex(row => row.type === source.type && row.id === source.id) === index);
  const exhibitRows = isExhibition ? exhibits(issue) : [], selected = exhibitRows.find(row => row.id === selectedExhibit);
  const base = `/recommendations/${encodeURIComponent(issue.slug)}`;
  const toc = <nav aria-label={isExhibition ? "展项章节" : "文章章节"}>{headings.length ? headings.map((row,index) => <a key={row.id} href={`#${row.id}`}><span>{String(index+1).padStart(2,"0")}</span>{row.text}</a>) : <a href="#article-body">{isExhibition ? "全部展项" : "正文与材料"}</a>}</nav>;
  async function share() {
    try { const url = new URL(base, window.location.origin).href; if (navigator.share) await navigator.share({title:issue.title,url}); else { await navigator.clipboard.writeText(url); setNotice("文章链接已复制。"); } }
    catch (reason) { if (!(reason instanceof DOMException && reason.name === "AbortError")) setNotice("未能分享链接，可以复制浏览器地址。"); }
  }
  const toolbar = <><button type="button" onClick={() => setCitations(true)}><Quote size={15} />引用 · 加入研究</button><button type="button" onClick={() => void share()}><Share2 size={15} />分享</button>{!preview ? <a href="#article-comments"><MessageSquare size={15}/>评论{commentCount!==null?`（${commentCount}）`:""}</a> : null}</>;
  return <article className={styles.article}>
    <nav className={styles.breadcrumbs} aria-label="面包屑"><Link href="/">首页</Link><span>›</span><Link href="/recommendations">特别策划</Link><span>›</span><span>{issue.title}</span></nav>
    {selected ? <section className={styles.exhibitReading}><Link href={base}><ArrowLeft size={15} /> 返回展项</Link><h1>{selected.title}</h1>
      {selected.item?.authors ? <p>{selected.item.authors}</p> : null}{selected.item?.note ? <p>{selected.item.note}</p> : null}
      <nav aria-label="切换展项">{exhibitRows.indexOf(selected) > 0 ? <Link href={`${base}?exhibit=${encodeURIComponent(exhibitRows[exhibitRows.indexOf(selected)-1].id)}`}>上一个展项</Link> : null}{exhibitRows.indexOf(selected) < exhibitRows.length-1 ? <Link href={`${base}?exhibit=${encodeURIComponent(exhibitRows[exhibitRows.indexOf(selected)+1].id)}`}>下一个展项 <ArrowRight size={14} /></Link> : null}</nav>
      {selected.block?.type === "image" ? <IssueBlockView block={selected.block} /> : selected.source?.asset_id && selected.source.document_revision_id ? <EditorialReader source={selected.source} returnTo={`${base}?exhibit=${encodeURIComponent(selected.id)}`} /> : selected.source ? <EditorialSourceContent key={selected.id} source={selected.source} /> : <section className={styles.empty}><h2>这份原文暂不可用</h2><p>可以返回展项阅读策划说明，或查看其他已公开的材料。</p><Link href={base}>阅读策划导读</Link></section>}
    </section> : <>
      {selectedExhibit ? <p role="status">原展项已不在当前公开版本中，以下为现有展项。</p> : null}
      <header className={styles.articleHero} data-edit-section="identity"><div className={styles.articleHeroMedia} data-edit-section="cover"><EditorialImage key={issue.cover_url} src={issue.cover_url} className={styles.articleHeroImage} /></div><div className={styles.articleHeroCopy}>
        <p className={styles.articleLabel}>{issue.issue_label || (isExhibition ? "原文微展览" : "专题文章")}</p><h1>{issue.title || (preview ? "填写文章标题" : "")}</h1><p className={styles.articleIntro}>{issue.introduction}</p>
        <EditorialByline curator={issue.curator || {name:issue.public_byline,role:"",affiliation:"",portrait_url:""}} date={issue.published_at} />{issue.reading_minutes ? <small title="按正文长度粗略估计，不含原文材料阅读">约 {issue.reading_minutes} 分钟阅读</small> : null}
      </div></header>
      <div className={styles.articleToolbar}>{toolbar}{notice ? <span role="status">{notice}</span> : null}</div>
      <div className={`${styles.articleLayout} ${isExhibition ? styles.exhibition : ""}`}>
        <aside className={styles.toc}><div className={styles.desktopToc}><h2>{isExhibition ? "展项目录" : "文章目录"}</h2>{toc}</div><details className={styles.mobileToc}><summary>{isExhibition ? "展项目录" : "文章目录"}</summary>{toc}</details></aside>
        <div className={styles.prose} id="article-body" data-edit-section="body">{isExhibition ? <ExhibitionBody issue={issue} rows={exhibitRows} base={base}/> : issue.body_blocks.map((block,index) => <section key={block.id || index} id={anchor(block,index)} className={heading(block) ? styles.proseHeading : ""}><IssueBlockView block={block} /></section>)}{!issue.body_blocks.length ? <p>本期以相关材料为阅读入口。</p> : null}
        </div>
        {!isExhibition ? <aside className={styles.materials} data-edit-section="items"><header><h2>相关材料</h2><a href="#article-materials">查看全部 <ArrowRight size={14} /></a></header>{issue.items.slice(0,3).map(item => <IssueItemCard key={item.id} item={item} />)}{!issue.items.length ? <p>尚未编入独立书目，可从正文的原文入口继续阅读。</p> : null}</aside> : null}
      </div>
      {!isExhibition && issue.items.length ? <section id="article-materials" className={styles.allMaterials}><h2>全部相关材料</h2><div>{issue.items.map(item => <IssueItemCard key={item.id} item={item} />)}</div></section> : null}
      {!preview && issue.items.length ? <SaveIssueList slug={issue.slug} revisionId={issue.public_revision_id} /> : null}{issue.related ? <EditorialRelated related={issue.related} /> : null}
      {!preview && issue.public_revision_id ? <ArticleComments issueId={issue.id} revisionId={issue.public_revision_id} slug={issue.slug} onCount={setCommentCount}/> : null}
      <nav className={styles.mobileArticleActions} aria-label="文章操作"><a href="#article-body"><List size={17} />正文</a>{toolbar}</nav>
    </>}
    <Dialog open={citations} onRequestClose={() => setCitations(false)} className={styles.materialDialog} aria-label="选择引用或研究材料"><header><h2>选择原文材料</h2><button aria-label="关闭材料选择" onClick={() => setCitations(false)}><X size={18} /></button></header><p>选择准确原文后，可引用、加入研究或在完整阅读器中记录笔记。</p>{materials.length ? materials.map((source,index) => <p key={`${source.type}:${source.id}:${index}`}><EditorialSource source={source} /></p>) : <p>本篇暂无已核验的正文来源。可以从相关书目进入原文。</p>}</Dialog>
  </article>;
}
