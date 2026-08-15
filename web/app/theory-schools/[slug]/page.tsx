import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ArrowRight,
  BookOpen,
  Bookmark,
  CalendarDays,
  CircleDot,
  Layers3,
  Users,
} from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import {
  ArchitecturalImage,
  BookCard,
  ScholarPortrait,
  SectionHeading,
  TagList,
} from "@/components/ui";
import { loadTheoryEntity, loadTheorySchool } from "@/lib/server-api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const data = await loadTheoryEntity(slug);
  return { title: data?.name ?? "理论流派" };
}

const relationLabels: Record<string, string> = {
  influence: "影响关系",
  critique: "批评与争论",
  dialogue: "理论对话",
  adjacent: "相邻理论",
  development: "发展关系",
  opposition: "对立关系",
  hierarchy: "谱系关系",
};

export default async function TheorySchoolDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [entity, legacy] = await Promise.all([
    loadTheoryEntity(slug),
    loadTheorySchool(slug),
  ]);
  if (!entity || !legacy) notFound();

  const { works, scholars, curated } = legacy;
  const introductoryWorks = curated.curatedReadingWorks.length
    ? curated.curatedReadingWorks
    : curated.foundationalWorks.length
      ? curated.foundationalWorks
      : works;
  const disciplines = entity.disciplines.map((item) => item.name);
  const branches = entity.hierarchy.branches;
  const neighbors = entity.relations.filter((item) => item.relation_type !== "hierarchy");
  const heroStyle = entity.hero_image
    ? { backgroundImage: `url("${entity.hero_image}")` }
    : undefined;

  return (
    <>
      <main className="page-shell theory-profile-page">
        <p className="breadcrumbs">
          <Link href="/theory-schools">理论流派</Link>
          {disciplines[0] ? <> / {disciplines[0]}</> : null}
          {entity.entity_level ? <> / {entity.entity_level === "branch" ? "理论分支" : "理论传统"}</> : null}
          <> / {entity.name}</>
        </p>

        <section className="theory-profile-hero">
          <div className="theory-profile-copy">
            <h1>{entity.name}</h1>
            {entity.foreign_name ? <p className="theory-foreign-name">{entity.foreign_name}</p> : null}
            <p>{entity.description || "该理论传统的概述尚待管理员编辑。"}</p>
            <TagList
              items={entity.key_themes}
              hrefFor={(item) => `/explore?q=${encodeURIComponent(item)}`}
            />
          </div>
          <div className={`theory-profile-image${entity.hero_image ? " has-image" : ""}`} style={heroStyle}>
            {!entity.hero_image ? <ArchitecturalImage compact /> : null}
          </div>
        </section>

        <section className="theory-fact-strip">
          <div><Layers3 size={24} /><span>主要学科</span><strong>{disciplines.join("、") || "暂未归类"}</strong></div>
          <div><CalendarDays size={24} /><span>形成时期</span><strong>{entity.formation_period || "待确认"}</strong></div>
          <div><Users size={24} /><span>代表学者</span><strong>{scholars.slice(0, 3).map((item) => item.name).join("、") || "待确认"}</strong></div>
          <div><BookOpen size={24} /><span>收录文献</span><strong>{entity.work_count.toLocaleString("zh-CN")} 部</strong></div>
          <Link aria-label={`收藏${entity.name}`} href="/login?next=/account"><Bookmark size={23} /></Link>
        </section>

        <div className="theory-profile-layout">
          <div className="theory-profile-main">
            <section className="panel theory-overview-block">
              <SectionHeading title="理论概览" />
              <p>{entity.description || "理论概览尚待管理员编辑。"}</p>
            </section>

            <section className="panel theory-question-block">
              <SectionHeading title="核心问题" />
              {entity.core_questions.length ? (
                <ul>{entity.core_questions.map((question) => <li key={question}>{question}</li>)}</ul>
              ) : <p className="empty-state">核心问题尚待管理员确认。</p>}
            </section>

            <section className="panel theory-history-block">
              <SectionHeading title="历史发展" href={`/theory-schools/timeline?theory=${encodeURIComponent(entity.slug)}`} />
              {entity.timeline.length ? (
                <div className="theory-history-track">
                  {entity.timeline.slice(0, 5).map((event) => (
                    <article key={event.id}>
                      <span />
                      <strong>{event.date_label || event.start_year || "时期待定"}</strong>
                      <h3>{event.title}</h3>
                      <p>{event.description}</p>
                    </article>
                  ))}
                </div>
              ) : <p className="empty-state">仅在管理员确认事件依据后显示历史发展。</p>}
            </section>

            <div className="theory-profile-pairs">
              <section className="panel">
                <SectionHeading title="理论分支" />
                <div className="theory-chip-links">
                  {branches.map((branch) => <Link href={`/theory-schools/${branch.slug}`} key={branch.id}>{branch.name}</Link>)}
                </div>
                {!branches.length ? <p className="empty-state">尚无已确认分支。</p> : null}
              </section>
              <section className="panel">
                <SectionHeading title="相关子学科" />
                <div className="theory-chip-links">
                  {entity.subdisciplines.map((item) => <Link href={`/subdisciplines/${item.slug}`} key={item.id}>{item.name}</Link>)}
                </div>
                {!entity.subdisciplines.length ? <p className="empty-state">尚无已确认子学科。</p> : null}
              </section>
            </div>

            <section className="panel">
              <SectionHeading title="相邻理论与学术关系" href="/theory-schools/graph" action="查看理论图谱" />
              <div className="theory-neighbor-grid">
                {neighbors.slice(0, 6).map((relation) => (
                  <Link href={`/theory-schools/${relation.theory.slug}`} key={relation.id}>
                    <CircleDot size={18} />
                    <span><strong>{relation.theory.name}</strong><small>{relationLabels[relation.relation_type] || relation.relation_type}</small></span>
                    <ArrowRight size={16} />
                  </Link>
                ))}
              </div>
              {!neighbors.length ? <p className="empty-state">理论关系须经人工确认，当前尚无公开关系。</p> : null}
            </section>
          </div>

          <aside className="theory-profile-aside">
            <section className="panel">
              <SectionHeading title="代表学者" href={`/theory-schools/${slug}/scholars`} />
              {scholars.slice(0, 4).map((scholar) => (
                <Link className="theory-scholar-row" href={`/scholars/${scholar.slug}`} key={scholar.slug}>
                  <ScholarPortrait scholar={scholar} />
                  <span><strong>{scholar.name}</strong><small>{scholar.years}</small></span>
                  <ArrowRight size={16} />
                </Link>
              ))}
              {!scholars.length ? <p className="empty-state">代表学者尚待确认。</p> : null}
            </section>
            <section className="panel">
              <SectionHeading title="入门阅读" href={`/theory-schools/${slug}/works`} action="查看全部文献" />
              <ol className="theory-reading-list">
                {introductoryWorks.slice(0, 6).map((work) => (
                  <li key={work.workId}>
                    <Link href={`/works/${work.slug}`}><strong>{work.title}</strong><small>{work.author} · {work.year}</small></Link>
                  </li>
                ))}
              </ol>
              {!introductoryWorks.length ? <p className="empty-state">入门阅读尚待策展。</p> : null}
            </section>
          </aside>
        </div>

        {works.length ? (
          <section className="detail-section">
            <SectionHeading title="关联馆藏" href={`/theory-schools/${slug}/works`} />
            <div className="four-book-grid">{works.slice(0, 4).map((work) => <BookCard work={work} key={work.id} />)}</div>
          </section>
        ) : null}
      </main>
      <SiteFooter />
    </>
  );
}
