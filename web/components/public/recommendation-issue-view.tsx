import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { RecommendationIssue, IssueItem } from "@/lib/api/recommendation-issues.types";
import { CollectionLink } from "@/components/collection-link";
import { SaveIssueList } from "@/components/save-issue-list";

export function IssueItemCard({ item, editIndex }: { item: IssueItem; editIndex?:number }) {
  const cover = item.cover_url ? <img className="issue-book-cover" src={item.cover_url} alt={`${item.title}封面`} loading="lazy" /> : <div className="issue-book-cover issue-book-empty" />;
  return <article className="issue-book-card" data-edit-item={editIndex}>
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
    <header data-edit-section="identity"><div className="issue-reference-meta"><Link className="issue-section-label" href="/recommendations">每日荐读</Link>{date ? <time dateTime={date}>{new Date(date).toLocaleDateString("zh-CN",{timeZone:"Asia/Hong_Kong"})}</time> : null}</div>{issue.issue_label ? <p className="issue-reference-category">{issue.issue_label}</p> : null}<h1 data-edit-field="title">{issue.title}</h1>{issue.introduction ? <p className="issue-introduction" data-edit-field="introduction">{issue.introduction}</p> : null}<div className="issue-byline"><span data-edit-field="public_byline">{issue.public_byline}</span></div></header>
    <div className={`issue-reference-media${headings.length ? " has-toc" : ""}`}><div className="issue-reference-image" data-edit-section="cover">{issue.cover_url ? <img src={issue.cover_url} alt=""/> : null}</div>{headings.length ? <nav className="issue-reference-toc" aria-label="文章目录"><h2>本篇目录</h2>{headings.map(heading=><a href={`#issue-section-${heading.index}`} key={heading.index}>{heading.text}</a>)}</nav> : null}</div>
    <section className="issue-reference-prose" data-edit-section="body">{issue.body_blocks.map((block,index)=>block.type==="heading" ? <h2 data-edit-row={index} id={`issue-section-${index}`} key={index}>{block.text}</h2> : block.type==="quote" ? <blockquote data-edit-row={index} key={index}><p>{block.text}</p>{block.source ? <cite>{block.source}</cite> : null}</blockquote> : block.type==="link" ? <p data-edit-row={index} key={index}><a href={block.url} rel="noopener noreferrer">{block.text}</a></p> : <p data-edit-row={index} key={index}>{block.text}</p>)}</section>
    <section className="issue-reference-books" data-edit-section="items"><header><h2>继续阅读</h2></header><div>{issue.items.map((item,index)=><IssueItemCard item={item} editIndex={preview ? index : undefined} key={item.id || index}/>)}</div></section>
    {!preview ? <SaveIssueList slug={issue.slug}/> : null}
  </article>;
}

export function DailyReadingContent({lead,cards,preview=false}: {lead:RecommendationIssue|null;cards:RecommendationIssue[];preview?:boolean}) {
  const issueLink = (issue:RecommendationIssue) => `/recommendations/${issue.slug}`;
  return <div className="daily-reading-content daily-reading-home"><header><div><h2>每日荐读</h2><p>从社会视角，阅读问题与世界。</p></div><Link href="/recommendations">查看全部文章 <ArrowRight size={16}/></Link></header>
    {lead ? <section className="daily-reading-lead" data-edit-section="schedule"><Link className="daily-reading-lead-image" href={issueLink(lead)}>{lead.cover_url ? <img src={lead.cover_url} alt=""/> : null}</Link><div className="daily-reading-lead-copy">{lead.display_from || lead.published_at ? <time>{new Date((lead.display_from || lead.published_at)!).toLocaleDateString("zh-CN",{timeZone:"Asia/Hong_Kong"})}</time> : null}<h2><Link href={issueLink(lead)}>{lead.title}</Link></h2><div className="daily-reading-byline"><span>{lead.public_byline}</span></div><p>{lead.introduction}</p><Link className="text-link" href={issueLink(lead)}>阅读文章 <ArrowRight size={16}/></Link></div></section> : <p className="empty-state">当前没有匹配文章。</p>}
    {cards.length ? <section className="daily-reading-section"><header><h2>本周推荐</h2><Link href="/recommendations">查看全部 <ArrowRight size={16}/></Link></header><div className="daily-reading-grid">{cards.map(issue => <article key={issue.id}><Link href={issueLink(issue)}>{issue.cover_url ? <img src={issue.cover_url} alt="" loading="lazy"/> : <div className="daily-reading-empty-image"/>}{issue.display_from || issue.published_at ? <time>{new Date((issue.display_from || issue.published_at)!).toLocaleDateString("zh-CN",{timeZone:"Asia/Hong_Kong"})}</time> : null}<h3>{issue.title}</h3><span>{issue.public_byline}</span></Link></article>)}</div></section> : null}
    {lead?.items.length ? <section className="daily-reading-books" data-edit-section="items"><header><h2>从馆藏继续阅读</h2>{!preview ? <Link href="/explore">探索更多相关书籍 →</Link> : null}</header><div>{lead.items.map((item,index) => <IssueItemCard item={item} editIndex={preview ? index : undefined} key={item.id || index}/>)}</div></section> : null}
  </div>;
}

/** The saved calendar preview and the public index share the same article view. */
export function DailyReadingIndexView({lead,cards}: {lead:RecommendationIssue|null;cards:RecommendationIssue[]}) {
  const date = (issue:RecommendationIssue) => { const value=issue.display_from || issue.published_at; return value ? new Date(value).toLocaleDateString("zh-CN",{timeZone:"Asia/Hong_Kong"}) : ""; };
  const link = (issue:RecommendationIssue) => `/recommendations/${issue.slug}`;
  return <main className="daily-reading-index"><header><h1>每日荐读</h1><p>从社会理论看见更大的世界</p><small>每天一篇，与你分享值得阅读的思想与故事。</small></header><div className="daily-reading-index-columns">
    {lead ? <article className="daily-reading-index-lead"><Link className="daily-reading-index-image" href={link(lead)}>{lead.cover_url ? <img src={lead.cover_url} alt=""/> : null}</Link><time>{date(lead)}</time><h2><Link href={link(lead)}>{lead.title}</Link></h2><p>{lead.introduction}</p><footer><span>{lead.public_byline}</span><Link href={link(lead)}>阅读全文 <ArrowRight size={16}/></Link></footer></article> : <p className="empty-state">当前没有匹配文章。</p>}
    <aside className="daily-reading-index-recent"><h2>近期荐读</h2>{cards.slice(0,2).map(issue=><article key={issue.id}><Link className="daily-reading-index-image" href={link(issue)}>{issue.cover_url ? <img src={issue.cover_url} alt=""/> : null}</Link><div><time>{date(issue)}</time><h3><Link href={link(issue)}>{issue.title}</Link></h3><p>{issue.public_byline}</p><Link href={link(issue)}>阅读全文 <ArrowRight size={16}/></Link></div></article>)}</aside>
  </div>{cards.length>2 ? <section className="daily-reading-index-more"><header><h2>更多精彩</h2><Link href="/recommendations">查看全部文章 <ArrowRight size={16}/></Link></header><div>{cards.slice(2).map(issue=><article key={issue.id}><Link className="daily-reading-index-image" href={link(issue)}>{issue.cover_url ? <img src={issue.cover_url} alt="" loading="lazy"/> : null}</Link><time>{date(issue)}</time><h3><Link href={link(issue)}>{issue.title}</Link></h3><p>{issue.public_byline}</p></article>)}</div></section> : null}</main>;
}
