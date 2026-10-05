import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { RecommendationIssue, IssueItem } from "@/lib/api/recommendation-issues.types";
import { CollectionLink } from "@/components/collection-link";
import { SaveIssueList } from "@/components/save-issue-list";
import { IssueRelatedWorks } from "@/components/issue-related-works";

export function IssueItemCard({ item }: { item: IssueItem }) {
  const cover = item.cover_url ? <img className="issue-book-cover" src={item.cover_url} alt={`${item.title}封面`} loading="lazy" /> : <div className="issue-book-cover issue-book-empty" />;
  return <article className="issue-book-card">
    {item.work_url ? <CollectionLink href={item.work_url} aria-label={`查看${item.title}`}>{cover}</CollectionLink> : cover}
    <h3>{item.work_url ? <CollectionLink href={item.work_url}>{item.title}</CollectionLink> : item.title}</h3>
    {item.authors ? <p className="issue-book-author">{item.authors}</p> : null}
    {item.version_note ? <p className="issue-book-version">{item.version_note}</p> : null}
    {item.note ? <p className="issue-book-note">{item.note}</p> : null}
    <p className={`issue-item-status ${item.reader_url ? "available" : "planned"}`}>{item.reader_url ? "可阅读全文" : item.work_url ? "已入藏 · 书目信息" : item.kind === "planned" ? "计划上架" : "馆藏暂不可用"}</p>
    {item.work_url ? <CollectionLink className="text-link" href={item.work_url}>查看详情 <ArrowRight size={14} /></CollectionLink> : <span className="issue-awaiting">{item.kind === "planned" ? "上架后可从本期进入馆藏" : "本期推介保留，馆藏入口暂未开放"}</span>}
  </article>;
}

export function RecommendationIssueView({ issue, preview = false }: { issue: RecommendationIssue; preview?: boolean }) {
  const headings = issue.body_blocks.flatMap((block,index)=>block.type==="heading" ? [{index,text:block.text}] : []);
  const date = issue.display_from || issue.published_at;
  return <article className="issue-article issue-reference-article">
    <div className="issue-reference-main">
      <header data-edit-section="identity"><Link className="issue-section-label" href="/recommendations">每日荐读</Link>{issue.issue_label ? <p className="issue-reference-category">{issue.issue_label}</p> : null}<h1>{issue.title}</h1><p className="issue-introduction">{issue.introduction}</p><div className="issue-byline"><span>{issue.public_byline}</span>{date ? <time dateTime={date}>{new Date(date).toLocaleDateString("zh-CN",{timeZone:"Asia/Hong_Kong"})}</time> : null}</div></header>
      <div className="issue-reference-image" data-edit-section="cover">{issue.cover_url ? <img src={issue.cover_url} alt=""/> : null}</div>
      <section className="issue-reference-prose" data-edit-section="body">{issue.body_blocks.map((block,index)=>block.type==="heading" ? <h2 id={`issue-section-${index}`} key={index}>{block.text}</h2> : block.type==="quote" ? <blockquote key={index}><p>{block.text}</p>{block.source ? <cite>{block.source}</cite> : null}</blockquote> : block.type==="link" ? <p key={index}><a href={block.url} rel="noopener noreferrer">{block.text}</a></p> : <p key={index}>{block.text}</p>)}</section>
      {!preview ? <SaveIssueList slug={issue.slug}/> : null}
    </div>
    <aside className="issue-reference-aside">
      <section className="issue-reference-books" data-edit-section="items"><header><h2>本文提及的书目</h2></header>{issue.items.map((item,index)=><IssueItemCard item={item} key={item.id || index}/>)}</section>
      {headings.length ? <nav className="issue-reference-toc" aria-label="文章目录"><h2>文章目录</h2>{headings.map(heading=><a href={`#issue-section-${heading.index}`} key={heading.index}>{heading.text}</a>)}</nav> : null}
      <IssueRelatedWorks excludedHrefs={issue.items.map(item=>item.work_url || "")}/>
    </aside>
  </article>;
}

export function DailyReadingContent({lead,cards,preview=false}: {lead:RecommendationIssue|null;cards:RecommendationIssue[];preview?:boolean}) {
  const issueLink = (issue:RecommendationIssue) => `/recommendations/${issue.slug}`;
  return <div className="daily-reading-content">
    {lead ? <section className="daily-reading-lead"><Link className="daily-reading-lead-image" href={issueLink(lead)}>{lead.cover_url ? <img src={lead.cover_url} alt=""/> : null}</Link><div className="daily-reading-lead-copy"><p className="eyebrow">{lead.issue_label || "每日荐读"}</p><h2><Link href={issueLink(lead)}>{lead.title}</Link></h2><p>{lead.introduction}</p><div className="daily-reading-byline"><span>{lead.public_byline}</span>{lead.published_at ? <time dateTime={lead.published_at}>{new Date(lead.published_at).toLocaleDateString("zh-CN",{timeZone:"Asia/Hong_Kong"})}</time> : null}</div><Link className="button" href={issueLink(lead)}>阅读文章 →</Link></div></section> : <p className="empty-state">当前没有匹配文章。</p>}
    {cards.length ? <section className="daily-reading-section"><header><h2>最新文章</h2></header><div className="daily-reading-grid">{cards.map(issue => <article key={issue.id}><Link href={issueLink(issue)}>{issue.cover_url ? <img src={issue.cover_url} alt="" loading="lazy"/> : <div className="daily-reading-empty-image"/>}<p className="eyebrow">{issue.issue_label || "每日荐读"}</p><h3>{issue.title}</h3><p>{issue.introduction}</p><span>{issue.public_byline}</span></Link></article>)}</div></section> : null}
    {lead?.items.length ? <section className="daily-reading-books"><header><h2>从馆藏继续阅读</h2>{!preview ? <Link href="/explore">探索更多相关书籍 →</Link> : null}</header><div>{lead.items.map(item => <article key={item.id}><span className="daily-reading-book-cover">{item.cover_url ? <img src={item.cover_url} alt="" loading="lazy"/> : null}</span><div><h3>{item.work_url ? <Link href={item.work_url}>{item.title}</Link> : item.title}</h3><p>{item.authors}</p><small>{item.version_note}</small></div></article>)}</div></section> : null}
  </div>;
}
