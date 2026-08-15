import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, BookOpen } from "lucide-react";
import { BookCard, ScholarCard } from "@/components/ui";
import { loadTopic } from "@/lib/server-api";

const titles: Record<string, string> = {
  works: "奠基文献",
  recent: "最近入库",
  scholars: "相关学者",
  "theory-schools": "关联理论流派",
  timeline: "概念时间线",
  "reading-paths": "策展阅读路径",
  concepts: "关键概念",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; section: string }>;
}): Promise<Metadata> {
  const { slug, section } = await params;
  const topic = await loadTopic(slug);
  return { title: topic ? `${titles[section] ?? "主题资料"} · ${topic.name}` : "主题资料" };
}

export default async function TopicSectionPage({
  params,
}: {
  params: Promise<{ slug: string; section: string }>;
}) {
  const { slug, section } = await params;
  if (!titles[section]) notFound();
  const topic = await loadTopic(slug);
  if (!topic) notFound();
  const works = section === "recent"
    ? topic.curated.recentWorks.length ? topic.curated.recentWorks : topic.works
    : topic.curated.foundationalWorks.length ? topic.curated.foundationalWorks : topic.works;

  return (
    <main className="page-shell secondary-detail-page">
      <Link className="back-link" href={`/topics/${slug}`}><ArrowLeft size={15} />返回{topic.name}</Link>
      <header><p className="eyebrow">研究主题</p><h1>{titles[section]}</h1><p>{topic.description}</p></header>
      {["works", "recent"].includes(section) ? <section className="four-book-grid">{works.map((work) => <BookCard work={work} key={work.id} />)}{!works.length ? <p className="empty-state">尚无已发布的关联文献。</p> : null}</section> : null}
      {section === "scholars" ? <section className="scholar-grid">{topic.scholars.map((scholar) => <ScholarCard scholar={scholar} key={scholar.slug} />)}{!topic.scholars.length ? <p className="empty-state">尚无已确认的相关学者。</p> : null}</section> : null}
      {section === "theory-schools" ? (
        <section className="panel secondary-link-list">{topic.theories.map((school) => <Link href={`/theory-schools/${school.slug}`} key={school.slug}><span className="theory-symbol">{school.symbol}</span><p><strong>{school.name}</strong><small>{school.description}</small></p><ArrowRight size={15} /></Link>)}{!topic.theories.length ? <p className="empty-state">尚无已确认的关联理论流派。</p> : null}</section>
      ) : null}
      {section === "timeline" ? <section className="panel timeline-detail-list">{topic.timeline.map(([year, label, text]) => <article key={`${year}-${label}`}><time>{year}</time><p><strong>{label}</strong><span>{text}</span></p></article>)}{!topic.timeline.length ? <p className="empty-state">概念时间线尚待管理员编辑。</p> : null}</section> : null}
      {section === "concepts" ? <section className="panel definition-list">{topic.concepts.map((concept, index) => <article className="definition-row" key={concept}><b>{String(index + 1).padStart(2, "0")}</b><strong>{concept}</strong><p>主题概念说明由管理员维护。</p></article>)}{!topic.concepts.length ? <p className="empty-state">关键概念尚待管理员编辑。</p> : null}</section> : null}
      {section === "reading-paths" ? (
        <section className="panel reading-path-detail-list">
          {topic.curated.readingPaths.map((path) => <article key={path.title}><BookOpen size={20} /><div><h2>{path.title}</h2><p>{path.description}</p><small>{path.level || "未分级"} · {path.works.length} 部文献</small><div className="four-book-grid">{path.works.map((work) => <BookCard work={work} key={work.id} />)}</div></div></article>)}
          {!topic.curated.readingPaths.length ? <p className="empty-state">尚无公开阅读路径。</p> : null}
        </section>
      ) : null}
    </main>
  );
}
