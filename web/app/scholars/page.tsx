import type { Metadata } from "next";
import { Search } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { ScholarCard, SearchField, SectionHeading, TagList } from "@/components/ui";
import { loadRecommendations, loadRecommendedScholars, loadScholarPage } from "@/lib/server-api";
import { searchPage, scopedSearchHref } from "@/lib/search-context";

export const metadata: Metadata = {
  title: "学者",
};

export default async function ScholarsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; page?: string; context?: string }>;
}) {
  const parameters = await searchParams;
  const query = parameters.q?.trim() ?? "";
  const page = searchPage(parameters.page);
  const recommendationsPromise = loadRecommendations();
  const recommendedScholarsPromise = recommendationsPromise.then((bundle) => loadRecommendedScholars(bundle, 3));
  const [scholarPage, recommendedScholars] = await Promise.all([
    loadScholarPage(query, page),
    recommendedScholarsPromise,
  ]);
  const scholars = scholarPage.results;
  const primaryRecommendation = recommendedScholars[0];
  const supportingRecommendations = recommendedScholars.slice(1, 3);
  return (
    <>
      <div className="page-shell directory-page">
        <section className="directory-hero">
          <div>
            <p className="eyebrow">思想、方法与文献</p>
            <h1>学者</h1>
            <p>沿着人物进入社会理论。查找作品、概念、思想关系和可以在线阅读的馆藏版本。</p>
          </div>
          <form action="/scholars" role="search">
            <input type="hidden" name="context" value="scholars" />
            <SearchField defaultValue={query} placeholder="搜索中文名、外文名或译名……" />
            <button className="directory-search-submit" type="submit">
              <Search aria-hidden="true" size={18} />
              搜索学者
            </button>
            <TagList
              items={["权力", "阶级", "性别", "殖民", "现代性", "文化"]}
              hrefFor={(item) => scopedSearchHref("/scholars", "scholars", { q: item })}
            />
          </form>
        </section>
        <section className="scholar-recommendations panel" aria-labelledby="scholar-recommendations-title">
          <header className="scholar-recommendations-heading">
            <div>
              <p className="eyebrow">重点人物</p>
              <h2 id="scholar-recommendations-title">学者推荐</h2>
            </div>
            <p>每三天更新一轮，也可由馆员策展。</p>
          </header>
          {primaryRecommendation ? (
            <div className="scholar-recommendations-layout">
              <div className="scholar-recommendation-primary">
                <ScholarCard scholar={primaryRecommendation} />
              </div>
              {supportingRecommendations.length ? (
                <div className="scholar-recommendation-supporting">
                  {supportingRecommendations.map((scholar) => (
                    <ScholarCard scholar={scholar} key={scholar.slug} />
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="empty-state">本轮暂无重点推荐，仍可在下方浏览全部公开学者。</p>
          )}
        </section>
        <section className="directory-results panel">
          <SectionHeading title={query ? "搜索结果" : "全部学者"} action={`${scholarPage.count} 位学者`} />
          <div className="scholar-directory-grid">
            {scholars.map((scholar) => (
              <ScholarCard scholar={scholar} key={scholar.slug} />
            ))}
            {!scholars.length ? <p className="empty-state">没有找到匹配的公开学者档案。</p> : null}
          </div>
        </section>
        <ScopedSearchPagination path="/scholars" context="scholars" page={page} totalPages={scholarPage.totalPages} params={{ q: query }} />
      </div>
      <SiteFooter />
    </>
  );
}
