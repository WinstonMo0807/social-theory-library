import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, CircleDot, Layers3, Network, Search } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ArchitecturalImage, BookCover, SearchField, SectionHeading } from "@/components/ui";
import {
  loadKnowledgeMatrix,
  loadRecommendations,
  loadTheorySchools,
  recommendationWorks,
} from "@/lib/server-api";

export const metadata: Metadata = {
  title: "探索理论流派",
  description: "从学科、理论传统、历史时间轴、理论图谱和子学科进入馆藏。",
};

type TheorySearchParams = {
  q?: string;
  discipline?: string;
  has_works?: string;
  sort?: string;
};

export default async function TheorySchoolsPage({
  searchParams,
}: {
  searchParams: Promise<TheorySearchParams>;
}) {
  const params = await searchParams;
  const query = params.q?.trim() ?? "";
  const discipline = params.discipline?.trim() ?? "";
  const [matrix, schools, recommendations] = await Promise.all([
    loadKnowledgeMatrix(),
    loadTheorySchools(query, {
      discipline,
      hasWorks: params.has_works === "true",
      sort: params.sort === "works" ? "works" : "name",
    }),
    loadRecommendations(),
  ]);
  const weeklyWorks = recommendationWorks(recommendations, "theory_weekly");

  return (
    <>
      <main className="page-shell theory-world-page">
        <section className="theory-world-hero">
          <div>
            <p className="eyebrow">探索理论流派</p>
            <h1>从三大学科进入理论世界</h1>
            <p>以学科为起点，贯通理论传统与子学科，系统探索社会理论的多元脉络。</p>
            <form className="theory-world-hero-search" action="/theory-schools">
              <SearchField defaultValue={query} placeholder="搜索理论、学者、概念或馆藏文献……" />
              {discipline ? <input type="hidden" name="discipline" value={discipline} /> : null}
              <button type="submit"><Search size={18} />搜索</button>
            </form>
          </div>
          <ArchitecturalImage compact />
        </section>

        <section className="discipline-matrix" aria-label="学科矩阵">
          {matrix.disciplines.map((item) => (
            <Link
              className={discipline === item.slug ? "discipline-card active" : "discipline-card"}
              href={theoryHref(params, { discipline: discipline === item.slug ? null : item.slug })}
              key={item.id}
            >
              <div
                className={`discipline-card-image ${item.hero_image ? "has-image" : ""}`}
                style={item.hero_image ? { backgroundImage: `url("${item.hero_image}")` } : undefined}
              >
                {!item.hero_image ? <ArchitecturalImage compact /> : null}
                <h2>{item.name}</h2>
              </div>
              <footer>
                <p>{disciplineIntroduction(item.slug, item.name)}</p>
                <div>
                  <span><Network size={17} /><b>{item.theory_count}</b><small>理论传统</small></span>
                  <span><Layers3 size={17} /><b>{item.subdiscipline_count}</b><small>子学科</small></span>
                  <span><BookOpen size={17} /><b>{item.work_count}</b><small>馆藏文献</small></span>
                </div>
                <ArrowRight size={20} />
              </footer>
            </Link>
          ))}
          {!matrix.disciplines.length ? (
            <p className="empty-state">学科基础数据正在建立。管理员可在知识组织后台新增学科。</p>
          ) : null}
        </section>

        <nav className="theory-view-switch" aria-label="理论浏览方式">
          <strong>浏览方式</strong>
          <Link className="active" href="/theory-schools">学科脉络</Link>
          <Link href="/theory-schools/timeline">历史时间轴</Link>
          <Link href="/theory-schools/graph">理论图谱</Link>
        </nav>

        <section className="theory-entry-section">
          <h2>推荐进入方式</h2>
          <div className="theory-entry-grid">
            {(matrix.entry_modes.length ? matrix.entry_modes : defaultEntryModes).map((entry) => (
              <Link href={entry.href} key={entry.key}>
                <span className="entry-icon">
                  {entry.key === "theory" ? <Network /> : entry.key === "subdiscipline" ? <Layers3 /> : <CircleDot />}
                </span>
                <span><strong>{entry.title}</strong><small>{entry.description}</small></span>
                <ArrowRight />
              </Link>
            ))}
          </div>
        </section>

        <section className="theory-weekly panel">
          <SectionHeading title="本期馆藏推荐" href="/explore" action="查看全部馆藏" />
          <div className="theory-weekly-grid">
            {weeklyWorks.map((work) => (
              <Link href={`/works/${work.slug}`} key={work.id}>
                <BookCover work={work} size="small" />
                <span><strong>{work.title}</strong><small>{work.author}</small><time>{work.year}</time></span>
                <ArrowRight size={18} />
              </Link>
            ))}
            {!weeklyWorks.length ? <p className="empty-state">馆藏发布后，系统每三天生成一组全站一致的推荐。</p> : null}
          </div>
        </section>

        <section className="theory-directory panel">
          <SectionHeading title="浏览理论传统" action={`${schools.length} 个结果`} />
          <form className="theory-directory-search" action="/theory-schools">
            {discipline ? <input type="hidden" name="discipline" value={discipline} /> : null}
            <SearchField defaultValue={query} placeholder="搜索理论传统、别名或相关内容……" />
            <label><input type="checkbox" name="has_works" value="true" defaultChecked={params.has_works === "true"} />仅显示有馆藏的理论</label>
            <select name="sort" defaultValue={params.sort === "works" ? "works" : "name"}>
              <option value="name">按名称</option>
              <option value="works">按馆藏数量</option>
            </select>
            <button className="button" type="submit">应用</button>
          </form>
          <div className="theory-card-grid">
            {schools.map((school) => (
              <Link href={`/theory-schools/${school.slug}`} key={school.slug}>
                <span className="theory-symbol large">{school.symbol}</span>
                <div><h2>{school.name}</h2><p>{school.description}</p></div>
                <footer><span>{school.books} 部文献</span><span>{school.scholars} 位学者</span><ArrowRight size={17} /></footer>
              </Link>
            ))}
            {!schools.length ? <p className="empty-state">没有找到符合条件的公开理论传统。</p> : null}
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}

const defaultEntryModes = [
  { key: "theory", title: "按理论传统进入", description: "沿经典理论和当代流派进入。", href: "/theory-schools" },
  { key: "subdiscipline", title: "按子学科进入", description: "聚焦具体研究领域。", href: "/subdisciplines" },
  { key: "topic", title: "按研究主题进入", description: "从研究领域与核心概念连接理论资源。", href: "/topics" },
];

function theoryHref(
  params: TheorySearchParams,
  changes: Partial<Record<keyof TheorySearchParams, string | null>>,
) {
  const output = new URLSearchParams();
  Object.entries(params).forEach(([name, value]) => value && output.set(name, value));
  Object.entries(changes).forEach(([name, value]) => value ? output.set(name, value) : output.delete(name));
  return output.size ? `/theory-schools?${output.toString()}` : "/theory-schools";
}

function disciplineIntroduction(slug: string, name: string) {
  if (slug.includes("sociology") || name.includes("社会学")) {
    return "从社会关系、制度与结构出发，理解工业化、都市生活与现代社会。";
  }
  if (slug.includes("anthropology") || name.includes("人类学")) {
    return "从田野、文化实践与比较视野出发，理解人类生活的多样经验。";
  }
  if (slug.includes("ethnology") || name.includes("民族学")) {
    return "研究族群、边疆社会与民族交往，追踪中国民族学的田野传统。";
  }
  return "从学科传统进入理论、学者、主题与可在线阅读的馆藏文本。";
}
