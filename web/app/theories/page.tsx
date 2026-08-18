import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, CircleDot, Layers3, Network } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ScopedSearchPagination } from "@/components/scoped-search";
import {
  DisciplineCard,
  ReadingPathCard,
  TheoryBanner,
  TheoryEmpty,
  TheorySearchForm,
  TheorySectionHeading,
  WorkCompactCard,
  nodeTypeLabels,
} from "@/components/theory-system-ui";
import { loadScopedSearch, loadTheorySystemOverview } from "@/lib/server-api";
import { searchPage } from "@/lib/search-context";

export const metadata: Metadata = {
  title: "探索理论流派",
  description: "从学科、理论传统、子学科、争论和馆藏证据进入社会理论世界。",
};

export default async function TheoriesPage({ searchParams }: { searchParams: Promise<{ q?: string; page?: string; context?: string }> }) {
  const { q = "", page: rawPage } = await searchParams;
  const page = searchPage(rawPage);
  const [overview, searchEnvelope] = await Promise.all([
    loadTheorySystemOverview(),
    q.trim() ? loadScopedSearch("theories", q, { page }) : Promise.resolve(null),
  ]);
  const theoryGroup = searchEnvelope?.groups[0];
  const searchResults = theoryGroup?.results ?? [];
  const browseCounts = overview ? Object.values(overview.browse) : [];
  const hasBrowseEntries = browseCounts.some((count) => (count ?? 0) > 0);

  return (
    <>
      <main className="page-shell theory-system-page theory-system-home">
        <section className="theory-system-home-hero">
          <div>
            <p className="eyebrow">探索理论流派</p>
            <h1>从三大学科进入理论世界</h1>
            <p>使用本馆已审核的学术条目与馆藏证据，探索社会理论的思想脉络和学科传播。</p>
            <TheorySearchForm defaultValue={q} />
          </div>
          <TheoryBanner />
        </section>

        {q.trim() ? (
          <section className="theory-search-results panel">
            <TheorySectionHeading title={`“${q.trim()}”的搜索结果`} href="/theories" action="清除搜索" />
            {searchResults.length ? (
              <div>
                {searchResults.map((result) => (
                  <Link href={result.url || "/theories"} key={`${result.entity_type}-${result.id}`}>
                    <span>{result.entity_type === "knowledge_node" ? nodeTypeLabels[String(result.metadata.node_type || "")] || "知识节点" : "理论传统"}</span>
                    <strong>{result.title}</strong>
                    {result.subtitle ? <small>{result.subtitle}</small> : null}
                    {result.description ? <p>{result.description}</p> : null}
                    <ArrowRight size={18} />
                  </Link>
                ))}
              </div>
            ) : <TheoryEmpty title="没有找到公开理论" detail="可改用理论规范名、别名、外文名或核心概念再次搜索。" />}
            <ScopedSearchPagination path="/theories" context="theories" page={page} totalPages={searchEnvelope?.pagination.total_pages ?? 0} params={{ q }} />
          </section>
        ) : null}

        {overview?.disciplines.length ? (
          <section className="theory-discipline-grid" aria-label="学科入口">
            {overview.disciplines.map((discipline) => <DisciplineCard key={discipline.id} discipline={discipline} counts={discipline.counts} />)}
          </section>
        ) : <TheoryEmpty title="学科资料尚未发布" detail="管理员完成学科和理论条目审核后，这里会自动形成学科入口。" />}

        {overview ? (
          <section className="theory-browse-section">
            <TheorySectionHeading title="浏览馆藏理论" />
            {hasBrowseEntries ? (
              <div className="theory-browse-grid">
                {overview.browse.theory_traditions ? <Link href="/theories/directory?type=theory_tradition"><Network /><span><strong>理论传统</strong><small>按思想脉络浏览经审核的理论传统</small></span><b>{overview.browse.theory_traditions}</b><ArrowRight /></Link> : null}
                {overview.browse.subdisciplines ? <Link href="/theories/directory?type=subdiscipline"><Layers3 /><span><strong>子学科</strong><small>按研究领域与方法脉络浏览</small></span><b>{overview.browse.subdisciplines}</b><ArrowRight /></Link> : null}
                {overview.browse.debates ? <Link href="/theories/directory?type=debate"><CircleDot /><span><strong>关键争论</strong><small>追踪社会理论中的持续讨论</small></span><b>{overview.browse.debates}</b><ArrowRight /></Link> : null}
              </div>
            ) : (
              <TheoryEmpty title="馆藏理论目录正在整理" detail="学科入口已经开放。理论传统、子学科和关键争论会在条目审核发布后出现在这里。" />
            )}
          </section>
        ) : null}

        {overview?.reading_paths.length ? (
          <section className="theory-path-section">
            <TheorySectionHeading title="精选阅读路径" />
            <div className="theory-reading-path-grid">{overview.reading_paths.map((path) => <ReadingPathCard key={path.id} path={path} />)}</div>
          </section>
        ) : null}

        {overview && (overview.recent.nodes.length || overview.recent.timeline_events.length || overview.recent.work_relations.length) ? (
          <section className="theory-recent-section">
            <TheorySectionHeading title="最近整理" />
            <div className="theory-recent-grid">
              {overview.recent.nodes.length ? <article><h3>最新编辑的理论条目</h3>{overview.recent.nodes.slice(0, 4).map((node) => <Link href={`/theories/nodes/${node.slug}`} key={node.id}><span>{nodeTypeLabels[node.node_type]}</span><strong>{node.canonical_name_zh}</strong><time>{new Date(node.updated_at).toLocaleDateString("zh-CN")}</time></Link>)}</article> : null}
              {overview.recent.timeline_events.length ? <article><h3>最新时间轴事件</h3>{overview.recent.timeline_events.slice(0, 4).map((event) => <Link href={`/theories/timeline?q=${encodeURIComponent(event.title)}`} key={event.id}><span>{event.start_year || event.date_label}</span><strong>{event.title}</strong><ArrowRight size={15} /></Link>)}</article> : null}
              {overview.recent.work_relations.length ? <article><h3>最新确认的馆藏关系</h3>{overview.recent.work_relations.slice(0, 3).map((relation) => relation.work_data ? <WorkCompactCard key={relation.id} work={relation.work_data} role={relation.role_label} /> : null)}</article> : null}
            </div>
          </section>
        ) : null}
      </main>
      <SiteFooter />
    </>
  );
}
