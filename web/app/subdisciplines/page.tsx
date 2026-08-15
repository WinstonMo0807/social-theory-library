import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Layers3 } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ArchitecturalImage, SearchField, SectionHeading } from "@/components/ui";
import { loadDisciplines, loadSubdisciplines } from "@/lib/server-api";

export const metadata: Metadata = { title: "子学科" };

export default async function SubdisciplinesPage({ searchParams }: { searchParams: Promise<{ discipline?: string; q?: string }> }) {
  const params = await searchParams;
  const [disciplines, items] = await Promise.all([
    loadDisciplines(),
    loadSubdisciplines(params.discipline ?? ""),
  ]);
  const query = (params.q ?? "").trim().toLocaleLowerCase();
  const filtered = query
    ? items.filter((item) => [item.name, item.foreign_name, item.description, item.research_object].join(" ").toLocaleLowerCase().includes(query))
    : items;
  return (
    <>
      <main className="page-shell subdiscipline-directory">
        <section className="directory-hero">
          <div><p className="eyebrow">知识领域</p><h1>子学科</h1><p>子学科与理论传统分别管理，并通过经确认的关系相互连接。</p></div>
          <ArchitecturalImage compact />
        </section>
        <div className="subdiscipline-controls panel">
          <form action="/subdisciplines"><SearchField defaultValue={params.q ?? ""} placeholder="搜索子学科、研究对象或问题……" /></form>
          <nav><Link className={!params.discipline ? "active" : ""} href="/subdisciplines">全部</Link>{disciplines.map((item) => <Link className={params.discipline === item.slug ? "active" : ""} href={`/subdisciplines?discipline=${item.slug}`} key={item.id}>{item.name}</Link>)}</nav>
        </div>
        <section className="panel">
          <SectionHeading title="浏览子学科" action={`${filtered.length} 个结果`} />
          <div className="subdiscipline-grid">
            {filtered.map((item) => (
              <Link href={`/subdisciplines/${item.slug}`} key={item.id}>
                <span className="subdiscipline-icon"><Layers3 size={24} /></span>
                <div><p className="eyebrow">{item.discipline.name}</p><h2>{item.name}</h2><p>{item.description || item.research_object}</p></div>
                <dl><div><dt>理论传统</dt><dd>{item.theories.length}</dd></div><div><dt>主题</dt><dd>{item.topics.length}</dd></div><div><dt>馆藏</dt><dd>{item.works.length}</dd></div></dl>
                <ArrowRight />
              </Link>
            ))}
            {!filtered.length ? <p className="empty-state">管理员建立并发布子学科后会在这里显示。</p> : null}
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
