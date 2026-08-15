import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, Compass, Network, Search, Users } from "lucide-react";
import { RandomRecommendation } from "@/components/random-recommendation";
import { SiteFooter } from "@/components/site-footer";
import { BookCard, ScholarCard, SearchField, SectionHeading } from "@/components/ui";
import {
  loadCatalogOverview,
  loadRecommendedScholars,
  loadSiteConfig,
  loadRecommendations,
  loadHotSearches,
  loadTheorySchools,
  loadTopics,
  loadWorks,
  recommendationSlugs,
  recommendationWorks,
} from "@/lib/server-api";

export const metadata: Metadata = {
  title: "首页",
  description: "阅读社会理论原典，检索观点并精确回到 PDF 页码。",
};

export default async function Home() {
  const recommendationsPromise = loadRecommendations();
  const recommendedScholarsPromise = recommendationsPromise.then((bundle) => loadRecommendedScholars(bundle));
  const [works, theorySchools, topics, overview, config, recommendations, hotSearches, recommendedScholars] = await Promise.all([
    loadWorks(),
    loadTheorySchools(),
    loadTopics(),
    loadCatalogOverview(),
    loadSiteConfig(),
    recommendationsPromise,
    loadHotSearches(),
    recommendedScholarsPromise,
  ]);
  const stats = [
    [overview.works.toLocaleString("zh-CN"), "图书与论文"],
    [overview.scholars.toLocaleString("zh-CN"), "学者"],
    [overview.theories.toLocaleString("zh-CN"), "理论流派"],
  ];
  const featuredWorks = recommendationWorks(recommendations, "home_featured");
  const randomWorks = recommendationWorks(recommendations, "home_random");
  const recommendedTheorySlugs = recommendationSlugs(recommendations, "home_theories", "theory_school");
  const recommendedTopicSlugs = recommendationSlugs(recommendations, "home_topics", "topic");
  const shownTheories = orderedSelection(theorySchools, recommendedTheorySlugs, (item) => item.slug, 6);
  const shownScholars = recommendedScholars;
  const shownTopics = orderedSelection(topics, recommendedTopicSlugs, (item) => item.slug, 4);
  const topic = shownTopics[0] ?? topics[0];
  const popularTags = (hotSearches.length ? hotSearches : [
    ...topics.map((item) => item.name),
    ...theorySchools.map((item) => item.name),
  ]).filter((item, index, values) => values.indexOf(item) === index).slice(0, 10);

  return (
    <>
      <div className="page-shell home-page">
        <section className="home-editorial-hero">
          <div className="home-editorial-copy">
            <p className="eyebrow">Social Theory Library · 社会理论书库</p>
            <h1>
              {config.home_title_left_lines.map((line) => <span key={line}>{line}</span>)}
              <em>{config.home_title_right_lines.map((line) => <span key={line}>{line}</span>)}</em>
            </h1>
            <div className="hero-intro">
              {config.intro_lines.map((line) => <p key={line}>{line}</p>)}
            </div>
            <form className="home-hero-search" action="/explore">
              <SearchField placeholder="检索书名、学者、理论、主题与馆藏原文……" />
              <button type="submit"><Search size={18} />检索书库</button>
            </form>
            {popularTags.length ? (
              <div className="home-hero-terms" aria-label="热门检索">
                <span>近期检索</span>
                {popularTags.slice(0, 5).map((tag) => <Link href={`/explore?q=${encodeURIComponent(tag)}`} key={tag}>{tag}</Link>)}
              </div>
            ) : null}
          </div>
          <div className="home-editorial-visual" aria-hidden="true"><span /></div>
          <Link className="home-hero-about" href="/about">{config.about_label}<ArrowRight size={16} /></Link>
        </section>

        <section className="home-stat-ledger" aria-label="馆藏统计">
          <p><span>馆藏概览</span><small>持续整理、复核与开放</small></p>
          {stats.map(([value, label]) => (
            <div key={label}>
              <strong>{value}</strong>
              <span>{label}</span>
            </div>
          ))}
        </section>

        <div className="home-editorial-flow">
          <section className="home-featured-edition">
            <header className="home-section-intro">
              <div><p className="eyebrow">Curated collection</p><h2>{config.sections.featured}</h2></div>
              <p>从近期整理的馆藏中，进入原典、译本与研究文献。</p>
              <Link className="text-link" href="/explore">查看全部馆藏 <ArrowRight size={15} /></Link>
            </header>
            <div className="home-featured-layout">
              <div className="featured-books-grid">
                {(featuredWorks.length ? featuredWorks : works).slice(0, 4).map((work) => (
                  <BookCard work={work} showSummary={false} key={work.id} />
                ))}
              </div>
              <aside className="recent-additions">
                <SectionHeading title={config.sections.recent} href="/explore?sort=newest" />
                <div className="compact-book-list">
                  {works.slice(0, 3).map((work) => <BookCard dense work={work} key={work.id} />)}
                </div>
                <Link className="panel-bottom-link" href="/explore?sort=newest">浏览全部新书 <ArrowRight size={15} /></Link>
              </aside>
            </div>
          </section>

          <section className="home-pathways">
            <header className="home-section-intro">
              <div><p className="eyebrow">Ways of reading</p><h2>沿不同路径进入理论</h2></div>
              <p>理论传统、研究主题与人物档案，共同指向可核对的馆藏文本。</p>
            </header>
            <div className="home-pathways-grid">
              <section className="theory-strip">
                <div className="home-pathway-title"><Network size={21} /><span><small>01</small><strong>{config.sections.theory_schools}</strong></span><Link href="/theory-schools"><ArrowRight /></Link></div>
                <div className="theory-mini-grid">
                  {shownTheories.map((school) => (
                    <Link href={`/theory-schools/${school.slug}`} key={school.slug}>
                      <span className="theory-symbol">{school.symbol}</span>
                      <strong>{school.name}</strong>
                      <p>{school.description}</p>
                    </Link>
                  ))}
                </div>
              </section>
              <section className="featured-topic">
                <div className="topic-image" aria-hidden="true" />
                <div className="featured-topic-copy">
                  <div className="home-pathway-title"><Compass size={21} /><span><small>02</small><strong>{config.sections.featured_topic}</strong></span></div>
                  <h3>{topic?.name ?? "研究主题"}</h3>
                  {topic ? (
                    <>
                      <p>{topic.description.slice(0, 96)}{topic.description.length > 96 ? "……" : ""}</p>
                      <span>{topic.workCount} 部关联文献</span>
                      <Link className="text-link" href={`/topics/${topic.slug}`}>进入主题 <ArrowRight size={15} /></Link>
                    </>
                  ) : <p className="empty-state">管理员发布主题后会在这里显示。</p>}
                </div>
              </section>
            </div>
          </section>

          <section className="home-reading-room">
            <header className="home-section-intro">
              <div><p className="eyebrow">Reading room</p><h2>本期阅读桌</h2></div>
              <p>定期更新的作品与学者入口，保持全站读者在同一时间看到同一组选择。</p>
            </header>
            <div className="home-reading-room-grid">
              <RandomRecommendation works={randomWorks.length ? randomWorks : works.slice(0, 4)} title={config.sections.random} />
              <section className="scholar-spotlight">
                <div className="home-pathway-title"><Users size={21} /><span><small>人物档案</small><strong>{config.sections.scholars}</strong></span><Link href="/scholars"><ArrowRight /></Link></div>
                <div className="scholar-pair">
                  {shownScholars.slice(0, 2).map((scholar) => <ScholarCard scholar={scholar} key={scholar.slug} />)}
                  {!shownScholars.length ? <p className="empty-state">学者档案发布后会在这里显示。</p> : null}
                </div>
              </section>
            </div>
          </section>

          <section className="home-search-ledger">
            <div><BookOpen size={28} /><p className="eyebrow">Search the collection</p><h2>{config.sections.search}</h2><p>从书目检索进入，也可以沿逐页原文继续阅读与引用。</p></div>
            <div>
              <form action="/explore"><SearchField /><button className="button" type="submit">搜索 <ArrowRight size={16} /></button></form>
              <div className="tag-list">
                {popularTags.map((tag) => <Link href={`/explore?q=${encodeURIComponent(tag)}`} key={tag}>{tag}</Link>)}
                {!popularTags.length ? <span>暂无已发布标签</span> : null}
              </div>
            </div>
          </section>
        </div>
      </div>
      <SiteFooter />
    </>
  );
}

function orderedSelection<T>(
  items: T[],
  slugs: string[],
  getSlug: (item: T) => string,
  limit: number,
) {
  const bySlug = new Map(items.map((item) => [getSlug(item), item]));
  const ordered = slugs.flatMap((slug) => bySlug.has(slug) ? [bySlug.get(slug)!] : []);
  const chosen = new Set(ordered.map(getSlug));
  return [...ordered, ...items.filter((item) => !chosen.has(getSlug(item)))].slice(0, limit);
}
