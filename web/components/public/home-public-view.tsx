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
};

function HomeSectionState({ section, empty }: { section?: HomeSections[keyof HomeSections]; empty: string }) {
  const failed = section?.status === "unavailable";
  return <div className="stl4-home-state" role={failed ? "alert" : "status"}>
    <BookOpen size={24} strokeWidth={1} aria-hidden="true" /><p>{failed ? section.message : empty}</p>
    {failed ? <Link href="/">重新加载首页 <ArrowRight size={14} aria-hidden="true" /></Link> : null}
  </div>;
}

export function HomePublicView({ config, works, scholars, topics, randomWorks, issue, issues, issueCount, hotSearches, sections, homeLayout, preview = false }: HomeViewData) {
  const editions = issues ?? (issue ? [issue] : []);
  return <div className="stl4-home">
    <section className="stl4-home-hero" data-edit-section="home" aria-labelledby="home-title">
      <div className="stl4-hero-picture">
        <picture><source media="(max-width: 700px)" srcSet={config.home_hero_image || "/editorial/stl4-home-mobile-final-r2.png"} /><img src={config.home_hero_image || "/editorial/stl4-home-desktop-final-r2.png"} alt={config.home_hero_alt || "阳光下的书桌、书籍与书架。更好地理解世界，为了更好地参与世界。"} width={643} height={278} fetchPriority="high" /></picture>
      </div>
      <div className="stl4-hero-copy">
        <p className="stl4-home-kicker">Social Theory Library</p>
        <h1 id="home-title">{config.home_title_left_lines.join("")}<br />{config.home_title_right_lines.join("")}</h1>
        <div className="stl4-hero-intro">{config.intro_lines.map((line, index) => <p key={index}>{line}</p>)}</div>
        <HomeSearch />
        {hotSearches.length ? <div className="stl4-hot-searches"><span>热门搜索</span>{hotSearches.slice(0, 5).map(tag => <Link key={tag} href={`/explore?q=${encodeURIComponent(tag)}`}>{tag}</Link>)}</div> : null}
        {sections?.hot_searches.status === "unavailable" ? <p className="stl4-small-status" role="status">热门搜索暂时无法加载，仍可直接检索。</p> : null}
      </div>
    </section>
    {sections?.config.status === "unavailable" ? <p className="stl4-small-status" role="status">网站文案暂时无法加载，当前显示系统默认介绍。</p> : null}
    {preview ? null : <HomeContinueReading />}
    {sections?.home_layout?.status === "unavailable" ? <p role="alert" className="stl4-small-status">首页编排暂时无法读取，当前显示公开内容目录。</p> : null}
    {homeLayout?.featured != null ? <HomeCuratedSection area="featured" cards={homeLayout.featured}/> : <section className="stl4-home-section" data-edit-section="recommendations" aria-labelledby="home-issues">
      <header className="stl4-home-heading"><h2 id="home-issues">特别策划 <small>Featured issues</small></h2><div>{issueCount != null ? <span className="stl4-issue-count">已策划 {issueCount} 期</span> : null}<Link href="/recommendations">查看全部 <ArrowRight size={15} /></Link></div></header>
      {editions.length ? <div className="stl4-issue-grid">{editions.slice(0, 4).map((entry, index) => <Link className={`stl4-issue-card${index === 0 ? " stl4-issue-lead" : ""}`} href={`/recommendations/${entry.slug}`} key={entry.id}>
        {entry.cover_url ? <img src={entry.cover_url} alt="" loading="lazy" /> : <div className="stl4-image-missing" aria-label="尚未提供策划配图"><BookOpen size={32} strokeWidth={1} /></div>}
        <div className="stl4-issue-copy">{entry.issue_label ? <span className="stl4-issue-label">{entry.issue_label}</span> : null}<h3>{entry.title}</h3><p>{entry.introduction}</p>{index === 0 && (entry.curator?.name || entry.public_byline) ? <div className="stl4-issue-byline"><EditorialByline curator={entry.curator || {name:entry.public_byline,portrait_url:"",role:"",affiliation:""}} date={null}/></div> : null}<ArrowRight size={17} aria-hidden="true" /></div>
      </Link>)}</div> : <HomeSectionState section={sections?.issues} empty="暂无已发布的特别策划。新内容发布后会显示在这里。" />}
      {editions.length > 1 ? <Link href="/recommendations" className="stl4-mobile-more">继续浏览特别策划 <ArrowRight size={15} /></Link> : null}
    </section>}
    <HomeDiscoveryCards scholars={scholars} topics={topics} sections={sections} homeLayout={homeLayout}/>
    <section className="stl4-home-section" data-edit-section="recent" aria-labelledby="home-recent">
      <header className="stl4-home-heading"><h2 id="home-recent">最近入库 <small>Recently added</small></h2><Link href="/explore?sort=newest">查看全部 <ArrowRight size={15} /></Link></header>
      {works.length ? <div className="stl4-recent-grid">{works.slice(0, 4).map(work => <BookCard work={work} dense key={work.id} />)}</div> : <HomeSectionState section={sections?.works} empty="书库当前暂无公开馆藏。发布后的作品会显示在这里。" />}
    </section>
    <HomeRandomBook works={randomWorks} section={sections?.random_works} />
  </div>;
}
