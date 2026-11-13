import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { BookCard } from "@/components/ui";
import { HomeContinueReading, HomeSearch, HomeDiscoveryCards, HomeRandomBook } from "./home-interactions";
import type { SiteConfig } from "@/lib/site-config";
import type { Scholar, Work } from "@/lib/data";
import type { LibraryTopic } from "@/lib/api/topics.types";
import type { RecommendationIssue } from "@/lib/api/recommendation-issues.types";
import type { HomeSections } from "@/lib/api/home.types";
import type { HomeLayoutPreview } from "@/lib/api/home.types";
import { EditorialByline } from "./editorial-directory";
import { HomeCuratedSection } from "./home-curated-section";

export type HomeViewData = {
  config: SiteConfig; works: Work[]; scholars: Scholar[]; topics: LibraryTopic[];
  randomWorks: Work[]; issue: RecommendationIssue | null; hotSearches: string[];
  issues?: RecommendationIssue[]; issueCount?: number | null; sections?: HomeSections;
  homeLayout?: HomeLayoutPreview | null;
  preview?: boolean;
  reserveReadingSpace?: boolean;
};

function HomeSectionState({ section, empty }: { section?: HomeSections[keyof HomeSections]; empty: string }) {
  const failed = section?.status === "unavailable";
  return <div className="stl4-home-state" role={failed ? "alert" : "status"}>
    <BookOpen size={24} strokeWidth={1} aria-hidden="true" /><p>{failed ? section.message : empty}</p>
    {failed ? <Link href="/home">重新加载首页 <ArrowRight size={14} aria-hidden="true" /></Link> : null}
  </div>;
}

export function HomePublicView({ config, works, scholars, topics, randomWorks, issue, issues, issueCount, hotSearches, sections, homeLayout, preview = false, reserveReadingSpace = false }: HomeViewData) {
  const editions = issues ?? (issue ? [issue] : []);
  return <div className="stl4-home">
    <section className="stl4-home-hero" data-edit-section="home" aria-labelledby="home-title">
      <div className="stl4-hero-picture">
        <picture><img src={config.home_hero_image || "/editorial/generated-20261030/home.webp"} alt={config.home_hero_alt || "公共阅览室中的书籍、书架与读者"} width={643} height={278} fetchPriority="high" /></picture>
      </div>
      <div className="stl4-hero-copy">
        <h1 id="home-title">{config.home_title_left_lines.join("")}<br />{config.home_title_right_lines.join("")}</h1>
        <div className="stl4-hero-intro">{config.intro_lines.map((line, index) => <p key={index}>{line}</p>)}</div>
        <HomeSearch />
        {hotSearches.length ? <div className="stl4-hot-searches"><span>热门搜索</span>{hotSearches.slice(0, 5).map(tag => <Link key={tag} href={`/explore?q=${encodeURIComponent(tag)}`}>{tag}</Link>)}</div> : null}
        {sections?.hot_searches.status === "unavailable" ? <p className="stl4-small-status" role="status">热门搜索暂时无法加载，仍可直接检索。</p> : null}
      </div>
    </section>
    {sections?.config.status === "unavailable" ? <p className="stl4-small-status" role="status">网站文案暂时无法加载，当前显示系统默认介绍。</p> : null}
    {preview ? null : <HomeContinueReading reserveSpace={reserveReadingSpace} />}
    {sections?.home_layout?.status === "unavailable" ? <p role="alert" className="stl4-small-status">首页编排暂时无法读取，当前显示公开内容目录。</p> : null}
    {homeLayout?.featured != null ? <HomeCuratedSection area="featured" cards={homeLayout.featured}/> : <section className="stl4-home-section" data-edit-section="recommendations" aria-labelledby="home-issues">
      <header className="stl4-home-heading"><h2 id="home-issues">特别策划</h2><div>{issueCount != null ? <span className="stl4-issue-count">{issueCount} 期</span> : null}<Link href="/recommendations">查看全部 <ArrowRight size={15} /></Link></div></header>
      {editions.length ? <div className="stl4-issue-grid">{editions.slice(0, 4).map((entry, index) => <Link className={`stl4-issue-card${index === 0 ? " stl4-issue-lead" : ""}`} href={`/recommendations/${entry.slug}`} key={entry.id} data-no-image={!entry.cover_url || undefined}>
        {entry.cover_url ? <img src={entry.cover_url} alt="" loading="lazy" /> : null}
        <div className="stl4-issue-copy">{entry.issue_label ? <span className="stl4-issue-label">{entry.issue_label}</span> : null}<h3>{entry.title}</h3><p>{entry.introduction}</p>{index === 0 && (entry.curator?.name || entry.public_byline) ? <div className="stl4-issue-byline"><EditorialByline curator={entry.curator || {name:entry.public_byline,portrait_url:"",role:"",affiliation:""}} date={null}/></div> : null}<ArrowRight size={17} aria-hidden="true" /></div>
      </Link>)}</div> : <HomeSectionState section={sections?.issues} empty="暂无特别策划。" />}
      {editions.length > 1 ? <Link href="/recommendations" className="stl4-mobile-more">继续浏览特别策划 <ArrowRight size={15} /></Link> : null}
    </section>}
    <HomeDiscoveryCards scholars={scholars} topics={topics} sections={sections} homeLayout={homeLayout}/>
    <section className="stl4-home-section" data-edit-section="recent" aria-labelledby="home-recent">
      <header className="stl4-home-heading"><h2 id="home-recent">最近入库</h2><Link href="/explore?sort=newest">查看全部 <ArrowRight size={15} /></Link></header>
      {works.length ? <div className="stl4-recent-grid">{works.slice(0, 4).map(work => <BookCard work={work} dense key={work.id} />)}</div> : <HomeSectionState section={sections?.works} empty="暂无公开馆藏。" />}
    </section>
    <HomeRandomBook works={randomWorks} section={sections?.random_works} />
  </div>;
}
