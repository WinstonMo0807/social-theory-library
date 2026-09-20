import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { ArchitecturalImage, ScholarCard, SearchField, SectionHeading } from "@/components/ui";
import { ScholarDirectoryRecommendations } from "@/components/public/scholar-directory-recommendations";
import { loadRecommendations, loadRecommendedScholars } from "@/lib/api/recommendations.server";
import { loadScholarPage } from "@/lib/api/people.server";
import { searchPage } from "@/lib/search-context";

export const metadata: Metadata = {title: "学者"};
export default async function ScholarsPage({ searchParams }: {searchParams: Promise<{q?: string; page?: string; view?: string}>}) {
  const params = await searchParams;
  const query = params.q?.trim() || "";
  const page = searchPage(params.page);
  const [result, recommended] = await Promise.all([loadScholarPage(query, page), loadRecommendations().then(bundle => loadRecommendedScholars(bundle, 4))]);
  const directory = params.view === "directory" || Boolean(query) || page > 1;
  return <><main className={`page-shell v307-knowledge scholars-hub-v307 ${directory ? "directory-only" : ""}`}>
    <section className="knowledge-hero"><div><p className="eyebrow">SCHOLARS</p><h1>{directory ? "全部学者" : "学者"}</h1><h2>思想改变世界，也由具体的人产生。</h2><p>从学者的作品、概念与学术关系，进入社会理论的不同视野。</p><form action="/scholars" className="knowledge-search"><input type="hidden" name="context" value="scholars"/><input type="hidden" name="view" value="directory"/><SearchField defaultValue={query} placeholder="搜索学者姓名、译名或关键词…"/><button type="submit">搜索</button></form></div>{!directory ? <div className="knowledge-hero-image"><ArchitecturalImage compact/></div> : null}</section>
    {!directory ? <ScholarDirectoryRecommendations recommended={recommended} pool={result.results}/> : null}
    <section className="knowledge-section"><SectionHeading title={query ? "搜索结果" : "全部学者"} href={!directory ? "/scholars?view=directory" : undefined} action={`查看全部 ${result.count} 位`}/><div className={`knowledge-scholar-directory ${directory ? "full" : ""}`}>{result.results.map(row => <ScholarCard scholar={row} key={row.slug}/>)}</div>{!result.results.length ? <p className="empty-state">没有找到匹配的公开学者档案。</p> : null}<ScopedSearchPagination path="/scholars" context="scholars" page={page} totalPages={result.totalPages} params={{q: query, view: "directory"}}/></section>
  </main><SiteFooter/></>;
}
