import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, CircleHelp, Search, Shapes } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ArchitecturalImage, SearchField, SectionHeading, TagList } from "@/components/ui";
import { loadDisciplines, loadRecommendations, loadTopics } from "@/lib/server-api";

export const metadata: Metadata = { title: "从研究主题进入社会理论" };

export default async function TopicsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; discipline?: string; sort?: "name" | "works" }>;
}) {
  const parameters = await searchParams;
  const query = parameters.q?.trim() ?? "";
  const discipline = parameters.discipline?.trim() ?? "";
  const sort = parameters.sort === "name" ? "name" : "works";
  const [topics, disciplines, recommendations] = await Promise.all([
    loadTopics(query, { discipline, sort }),
    loadDisciplines(),
    loadRecommendations(),
  ]);
  const recommendedIds = new Set(
    (recommendations.placements.home_topics?.current?.items ?? [])
      .filter((item) => item.target_type === "topic")
      .map((item) => item.target.id),
  );
  const recommended = topics.filter((topic) => recommendedIds.has(topic.id));
  const visibleTopics = query || discipline ? topics : (recommended.length ? recommended : topics.slice(0, 6));
  const popularConcepts = Array.from(new Set(topics.flatMap((item) => item.concepts))).slice(0, 9);

  return (
    <>
      <main className="page-shell topic-hub-page">
        <section className="topic-hub-hero">
          <div>
            <p className="eyebrow">研究主题与理论资源</p>
            <h1>从研究主题进入社会理论</h1>
            <p>主题连接原始文献、理论传统、子学科、学者与核心概念。主题内部的研究问题和知识关系经管理员确认后进入公开结构。</p>
          </div>
          <ArchitecturalImage compact />
        </section>

        <form className="topic-hub-search" action="/topics">
          <SearchField defaultValue={query} placeholder="搜索研究主题、研究领域或核心概念……" />
          {discipline ? <input type="hidden" name="discipline" value={discipline} /> : null}
          <button type="submit"><Search size={18} />搜索主题</button>
        </form>

        <nav className="topic-discipline-filter" aria-label="按学科筛选主题">
          <strong>按学科</strong>
          <Link className={!discipline ? "active" : ""} href="/topics">全部</Link>
          {disciplines.map((item) => (
            <Link className={discipline === item.slug ? "active" : ""} href={`/topics?discipline=${encodeURIComponent(item.slug)}`} key={item.id}>{item.name}</Link>
          ))}
        </nav>

        {!query && !discipline ? (
          <section className="topic-entry-guide">
            <article><CircleHelp size={28} /><h2>从研究主题进入</h2><p>从国家、现代性、阶层、权力等研究主题出发，寻找相关理论资源。</p></article>
            <article><Shapes size={28} /><h2>沿知识关系展开</h2><p>查看主题与理论、子学科、学者和文献的已确认关系。</p></article>
            <article><BookOpen size={28} /><h2>回到原始文本</h2><p>从相关段落进入 PDF 具体页面，继续阅读和引用。</p></article>
          </section>
        ) : null}

        <section className="panel topic-hub-directory">
          <SectionHeading
            title={query ? `“${query}”的主题结果` : discipline ? "该学科的研究主题" : "本期推荐主题"}
            action={query || discipline ? `${topics.length} 个结果` : "全站读者每三天同步更新"}
          />
          <div className="topic-directory-grid topic-hub-grid">
            {visibleTopics.map((item, index) => (
              <Link href={`/topics/${item.slug}`} key={item.slug}>
                <div className="topic-number">{String(index + 1).padStart(2, "0")}</div>
                <div
                  className={`topic-card-image${item.heroImage ? " has-image" : ""}`}
                  style={item.heroImage ? { backgroundImage: `url("${item.heroImage}")` } : undefined}
                >
                  {!item.heroImage ? <ArchitecturalImage compact /> : null}
                </div>
                <h2>{item.name}</h2>
                <p>{item.problemStatement || item.description || "主题说明尚待管理员编辑。"}</p>
                <div className="topic-card-tags">
                  {item.disciplines.slice(0, 2).map((row) => <span key={row.id}>{row.name}</span>)}
                  {item.concepts.slice(0, 2).map((concept) => <span key={concept}>{concept}</span>)}
                </div>
                <footer><span>{item.workCount} 部关联文献</span><ArrowRight size={17} /></footer>
              </Link>
            ))}
            {!visibleTopics.length ? <p className="empty-state">没有找到匹配的公开主题。主题也可以不归入任何学科。</p> : null}
          </div>
          {!query && !discipline && topics.length > visibleTopics.length ? (
            <Link className="topic-view-all" href="/topics?sort=name">查看全部主题 <ArrowRight size={16} /></Link>
          ) : null}
        </section>

        {popularConcepts.length ? (
          <section className="panel topic-concept-entry">
            <SectionHeading title="从核心概念继续" />
            <TagList items={popularConcepts} hrefFor={(item) => `/topics?q=${encodeURIComponent(item)}`} />
          </section>
        ) : null}
      </main>
      <SiteFooter />
    </>
  );
}
