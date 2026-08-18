import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Layers3 } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { ArchitecturalImage, SearchField, SectionHeading } from "@/components/ui";
import { loadDisciplines, loadSubdisciplinePage } from "@/lib/server-api";
import { scopedSearchHref, searchPage } from "@/lib/search-context";

export const metadata: Metadata = { title: "子学科" };

export default async function SubdisciplinesPage({ searchParams }: { searchParams: Promise<{ discipline?: string; q?: string; page?: string; context?: string }> }) {
  const params = await searchParams;
  const query = (params.q ?? "").trim();
  const page = searchPage(params.page);
  const [disciplines, itemPage] = await Promise.all([
    loadDisciplines(),
    loadSubdisciplinePage(params.discipline ?? "", query, page),
  ]);
  const items = itemPage.results;
  return (
    <>
      <main className="page-shell subdiscipline-directory">
        <section className="directory-hero">
          <div><p className="eyebrow">知识领域</p><h1>子学科</h1><p>子学科与理论传统分别管理，并通过经确认的关系相互连接。</p></div>
          <ArchitecturalImage compact />
        </section>
        <div className="subdiscipline-controls panel">
          <form action="/subdisciplines"><input type="hidden" name="context" value="subdisciplines" />{params.discipline ? <input type="hidden" name="discipline" value={params.discipline} /> : null}<SearchField defaultValue={query} placeholder="搜索子学科、研究对象或问题……" /></form>
          <nav><Link className={!params.discipline ? "active" : ""} href={scopedSearchHref("/subdisciplines", "subdisciplines", { q: query })}>全部</Link>{disciplines.map((item) => <Link className={params.discipline === item.slug ? "active" : ""} href={scopedSearchHref("/subdisciplines", "subdisciplines", { q: query, discipline: item.slug })} key={item.id}>{item.name}</Link>)}</nav>
        </div>
        <section className="panel">
          <SectionHeading title="浏览子学科" action={`${itemPage.count} 个结果`} />
          <div className="subdiscipline-grid">
            {items.map((item) => (
              <Link href={`/subdisciplines/${item.slug}`} key={item.id}>
                <span className="subdiscipline-icon"><Layers3 size={24} /></span>
                <div><p className="eyebrow">{item.discipline.name}</p><h2>{item.name}</h2><p>{item.description || item.research_object}</p></div>
                <dl><div><dt>理论传统</dt><dd>{item.theories.length}</dd></div><div><dt>主题</dt><dd>{item.topics.length}</dd></div><div><dt>馆藏</dt><dd>{item.works.length}</dd></div></dl>
                <ArrowRight />
              </Link>
            ))}
            {!items.length ? <p className="empty-state">没有找到匹配的公开子学科。</p> : null}
          </div>
          <ScopedSearchPagination path="/subdisciplines" context="subdisciplines" page={page} totalPages={itemPage.totalPages} params={{ q: query, discipline: params.discipline }} />
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
