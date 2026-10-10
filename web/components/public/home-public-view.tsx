import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { BookCard } from "@/components/ui";
import { HomeRandom, HomeScholars } from "@/components/home-random";
import { DailyReadingContent } from "@/components/public/recommendation-issue-view";
import type { SiteConfig } from "@/lib/site-config";
import type { Scholar, Work } from "@/lib/data";
import type { LibraryTopic } from "@/lib/api/topics.types";
import type { RecommendationIssue } from "@/lib/api/recommendation-issues.types";

export type HomeViewData = { config: SiteConfig; works: Work[]; scholars: Scholar[]; topics: LibraryTopic[]; randomWorks: Work[]; issue: RecommendationIssue | null };
export function HomePublicView({ config, works, scholars, topics, randomWorks, issue }: HomeViewData) {
  return <div className="v307-home">
    <section className="v307-home-hero" data-edit-section="home"><div className="v307-home-hero-copy"><h1 data-edit-field="home_title_left_lines">{config.home_title_left_lines.map((line, index) => <span key={index}>{line}</span>)}</h1><div className="hero-intro">{config.intro_lines.map((line, index) => <p key={index} data-edit-field={`intro-${index}`}>{line}</p>)}</div></div>{config.home_hero_image ? <img className="v307-home-hero-image" data-edit-field="home_hero_image" src={config.home_hero_image} alt={config.home_hero_alt || ""}/> : <div className="v307-home-hero-image" data-edit-field="home_hero_image" aria-hidden="true"/>}</section>
    <section className="v307-home-panel home-current-issue" data-edit-section="recommendations"><DailyReadingContent lead={issue} cards={[]} showBooks={false}/></section>
    <HomeScholars scholars={scholars} />
    <section className="v307-home-panel home-topics" data-edit-section="topics"><header className="v307-section-heading"><h2>精选主题 <small>Themes</small></h2><Link className="text-link" href="/topics">查看全部主题 <ArrowRight size={14} /></Link></header><div className="v307-topic-grid">{topics.slice(0, 5).map(topic => <Link className="v307-topic-card" href={`/topics/${topic.slug}`} key={topic.slug}>{topic.heroImage ? <img src={topic.heroImage} alt="" loading="lazy"/> : <span className="reference-topic-image-blank" aria-hidden="true"/>}<div><h3>{topic.name}</h3><p>{topic.description}</p><ArrowRight size={15} /></div></Link>)}</div>{!topics.length ? <p className="empty-state">发布后的主题会显示在这里。</p> : null}</section>
    <section className="v307-home-panel home-recent" data-edit-section="recent"><header className="v307-section-heading"><h2>最近入库 <small>Recently added</small></h2><Link className="text-link" href="/explore?sort=newest">查看全部 <ArrowRight size={14} /></Link></header><div className="v307-recent-grid">{works.slice(0, 4).map(work => <BookCard work={work} dense key={work.id} />)}</div>{!works.length ? <p className="empty-state">尚无公开馆藏。</p> : null}</section>
    <HomeRandom works={randomWorks} />
  </div>;
}
