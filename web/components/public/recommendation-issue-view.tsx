import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { RecommendationIssue, IssueItem } from "@/lib/api/recommendation-issues.types";
import { CollectionLink } from "@/components/collection-link";
import { SaveIssueList } from "@/components/save-issue-list";
import { IssueRelatedWorks } from "@/components/issue-related-works";

export function IssueItemCard({ item }: { item: IssueItem }) {
  const cover = item.cover_url ? <img className="issue-book-cover" src={item.cover_url} alt={`${item.title}封面`} loading="lazy" /> : <div className="issue-book-cover issue-book-typographic"><span>{item.title}</span><small>{item.authors}</small></div>;
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
  const asideQuote = issue.body_blocks.find(block => block.type === "quote");
  return <article className="issue-article">
    <nav className="breadcrumbs" aria-label="位置"><Link href="/">首页</Link><span>›</span><Link href="/recommendations">本期书库推荐</Link><span>›</span><span>{issue.title}</span></nav>
    <section className="issue-hero" data-edit-section="identity">
      <div className="issue-hero-copy"><p className="eyebrow">本期书库推荐 {issue.issue_label}</p><h1>{issue.title || "填写本期标题"}</h1><p className="issue-introduction">{issue.introduction}</p>
        <div className="issue-byline"><span>{issue.public_byline ? `本期策划 ${issue.public_byline}` : ""}</span>{issue.published_at ? <time dateTime={issue.published_at}>{new Date(issue.published_at).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" })} 发布</time> : null}</div>
      </div>
      <div className="issue-hero-image" data-edit-section="cover"><img src={issue.cover_url || "/editorial/library-architecture-hero.webp"} alt="" /></div>
    </section>
    {issue.body_blocks.length ? <section className={`issue-prose${asideQuote ? " has-quote" : ""}`} data-edit-section="body"><header><h2>导语</h2><span className="eyebrow">Introduction</span></header><div>{issue.body_blocks.map((block, index) => block === asideQuote ? null : block.type === "heading" ? <h3 key={index}>{block.text}</h3> : block.type === "quote" ? <blockquote key={index}><p>{block.text}</p><cite>{block.source}</cite></blockquote> : block.type === "link" ? <p key={index}><a href={block.url} rel="noopener noreferrer">{block.text}</a></p> : <p key={index}>{block.text}</p>)}</div>{asideQuote ? <aside><blockquote><p>{asideQuote.text}</p>{asideQuote.source ? <cite>{asideQuote.source}</cite> : null}</blockquote></aside> : null}</section> : null}
    <section className="issue-works" data-edit-section="items"><header className="v307-section-heading"><h2>推荐书目 <small>Featured works</small></h2><p>{issue.items.length} 项 · 按策展阅读顺序推荐</p></header><div className="issue-books-grid">{issue.items.map((item, index) => <IssueItemCard item={item} key={item.id || index} />)}</div></section>
    {!preview ? <SaveIssueList slug={issue.slug} /> : <p className="issue-save-banner">保存本期书单 · 读者登录后可保存到自己的书架</p>}
    <IssueRelatedWorks excludedHrefs={issue.items.map(item => item.work_url || "")} />
  </article>;
}
