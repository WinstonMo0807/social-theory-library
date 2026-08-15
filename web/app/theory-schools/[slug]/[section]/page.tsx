import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { KnowledgeMap } from "@/components/knowledge-map";
import { BookCard, ScholarCard } from "@/components/ui";
import { loadTheorySchool } from "@/lib/server-api";

const titles: Record<string, string> = {
  works: "奠基文献与策展书目",
  concepts: "核心概念",
  scholars: "代表学者",
  neighbors: "相邻理论流派",
  "concept-map": "概念关系图",
  "reading-list": "策展阅读书目",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; section: string }>;
}): Promise<Metadata> {
  const { slug, section } = await params;
  const data = await loadTheorySchool(slug);
  return { title: data ? `${titles[section] ?? "流派资料"} · ${data.school.name}` : "流派资料" };
}

export default async function TheorySectionPage({
  params,
}: {
  params: Promise<{ slug: string; section: string }>;
}) {
  const { slug, section } = await params;
  if (!titles[section]) notFound();
  const data = await loadTheorySchool(slug);
  if (!data) notFound();
  const works = section === "reading-list" && data.curated.curatedReadingWorks.length
    ? data.curated.curatedReadingWorks
    : data.curated.foundationalWorks.length
      ? data.curated.foundationalWorks
      : data.works;
  const scholars = data.curated.keyScholars.length
    ? data.scholars.filter((scholar) => data.curated.keyScholars.some((item) => item.slug === scholar.slug))
    : data.scholars;

  return (
    <main className="page-shell secondary-detail-page">
      <Link className="back-link" href={`/theory-schools/${slug}`}><ArrowLeft size={15} />返回{data.school.name}</Link>
      <header><p className="eyebrow">理论流派</p><h1>{titles[section]}</h1><p>{data.school.description}</p></header>
      {["works", "reading-list"].includes(section) ? <section className="four-book-grid">{works.map((work) => <BookCard work={work} key={work.id} />)}{!works.length ? <p className="empty-state">尚无已发布的策展文献。</p> : null}</section> : null}
      {section === "scholars" ? <section className="scholar-grid">{scholars.map((scholar) => <ScholarCard scholar={scholar} key={scholar.slug} />)}{!scholars.length ? <p className="empty-state">尚无已确认的代表学者。</p> : null}</section> : null}
      {section === "concepts" ? (
        <section className="panel definition-list">
          {(data.curated.coreConcepts.length
            ? data.curated.coreConcepts
            : data.keyThemes.map((name) => ({ name, description: "", source: "" }))
          ).map((concept, index) => {
            const name = typeof concept === "string" ? concept : concept.name || `概念 ${index + 1}`;
            const description = typeof concept === "string" ? "" : concept.description || "";
            const source = typeof concept === "string" ? "" : concept.source || "";
            return (
              <article className="definition-row" key={`${name}-${index}`}>
                <b>{String(index + 1).padStart(2, "0")}</b>
                <strong>{name}</strong>
                <p>{description || "该概念在本流派中的说明由管理员维护。"}</p>
                {source ? <small>依据：{source}</small> : null}
              </article>
            );
          })}
          {!data.curated.coreConcepts.length && !data.keyThemes.length ? <p className="empty-state">核心概念尚待管理员编辑。</p> : null}
        </section>
      ) : null}
      {section === "neighbors" ? (
        <section className="panel secondary-link-list">
          {data.curated.neighbors.map((school) => (
            <Link href={`/theory-schools/${school.slug}`} key={school.id}>
              <span className="theory-symbol">{school.name.slice(0, 2)}</span>
              <p>
                <strong>{school.name}</strong>
                <small>{school.relation || school.description || "查看相邻流派"}</small>
                {school.source ? <small>依据：{school.source}</small> : null}
              </p>
              <ArrowRight size={15} />
            </Link>
          ))}
          {!data.curated.neighbors.length ? <p className="empty-state">相邻流派尚待管理员确认。</p> : null}
        </section>
      ) : null}
      {section === "concept-map" ? <section className="panel"><KnowledgeMap entries={data.curated.conceptualMap} /></section> : null}
    </main>
  );
}
