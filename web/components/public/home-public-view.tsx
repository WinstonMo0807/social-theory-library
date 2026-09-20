import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import { BookCard, SearchField } from "@/components/ui";
import { HomeRandom, HomeScholars } from "@/components/home-random";
import { IssueItemCard } from "@/components/public/recommendation-issue-view";
import type { SiteConfig } from "@/lib/site-config";
import type { Scholar, Work } from "@/lib/data";
import type { LibraryTopic } from "@/lib/api/topics.types";
import type { RecommendationIssue } from "@/lib/api/recommendation-issues.types";

export type HomeViewData = { config: SiteConfig; works: Work[]; scholars: Scholar[]; topics: LibraryTopic[]; randomWorks: Work[]; issue: RecommendationIssue | null; hotSearches: string[] };
export function HomePublicView({ config, works, scholars, topics, randomWorks, issue, hotSearches }: HomeViewData) {
  return <div className="v307-home">
    <section className="v307-home-hero" data-edit-section="home"><div className="v307-home-hero-copy"><p className="eyebrow">Social Theory Library · 社会理论书库</p><h1>{config.home_title_left_lines.join("")}<br />{config.home_title_right_lines.join("")}</h1><div className="hero-intro">{config.intro_lines.map((line, index) => <p key={index}>{line}</p>)}</div><form action="/explore"><input type="hidden" name="context" value="global"/><SearchField placeholder="搜索理论、学者、主题或关键词…" /><button type="submit"><Search size={16} /><span>搜索</span></button></form>{hotSearches.length ? <div className="v307-hot-searches"><span>热门检索</span>{hotSearches.slice(0, 5).map(tag => <Link key={tag} href={`/explore?q=${encodeURIComponent(tag)}`}>{tag}</Link>)}</div> : null}</div><img className="v307-home-hero-image" src={config.home_hero_image || "/editorial/library-architecture-hero.webp"} alt={config.home_hero_alt || "书库建筑与阅读空间"} /></section>
    <section className="v307-home-panel home-current-issue" data-edit-section="recommendations"><div className="home-issue-intro"><h2>本期书库推荐</h2><p className="eyebrow">Featured issue</p>{issue ? <><h3>{issue.title}</h3><p>{issue.introduction}</p>{issue.public_byline ? <p className="home-issue-byline">本期策划　{issue.public_byline}</p> : null}<Link className="button secondary" href={`/recommendations/${issue.slug}`}>阅读本期导语 <ArrowRight size={14} /></Link></> : <><p>新的推荐正在整理。已发布的往期推荐会保留在归档中。</p><Link className="text-link" href="/recommendations">推荐归档 <ArrowRight size={14} /></Link></>}</div><div className="home-issue-books">{issue?.items.slice(0, 4).map((item, index) => <IssueItemCard item={item} key={item.id || index} />)}</div><aside className="home-issue-topics"><h3>主题阅读</h3>{topics.slice(0, 5).map(topic => <Link href={`/topics/${topic.slug}`} key={topic.slug}>{topic.name}<ArrowRight size={13} /></Link>)}<Link href="/recommendations">往期推荐 <ArrowRight size={13} /></Link></aside></section>
    <HomeScholars scholars={scholars} />
    <section className="v307-home-panel home-topics" data-edit-section="topics"><header className="v307-section-heading"><h2>精选主题 <small>Themes</small></h2><Link className="text-link" href="/topics">查看全部主题 <ArrowRight size={14} /></Link></header><div className="v307-topic-grid">{topics.slice(0, 5).map(topic => <Link className="v307-topic-card" href={`/topics/${topic.slug}`} key={topic.slug}><img src={topic.heroImage || "/editorial/topics-archive-hero.webp"} alt="" loading="lazy" /><div><h3>{topic.name}</h3><p>{topic.description}</p><ArrowRight size={15} /></div></Link>)}</div>{!topics.length ? <p className="empty-state">发布后的主题会显示在这里。</p> : null}</section>
    <section className="v307-home-panel home-recent" data-edit-section="recent"><header className="v307-section-heading"><h2>最近入库 <small>Recently added</small></h2><Link className="text-link" href="/explore?sort=newest">查看全部 <ArrowRight size={14} /></Link></header><div className="v307-recent-grid">{works.slice(0, 4).map(work => <BookCard work={work} dense key={work.id} />)}</div>{!works.length ? <p className="empty-state">尚无公开馆藏。</p> : null}</section>
    <HomeRandom works={randomWorks} />
  </div>;
}
