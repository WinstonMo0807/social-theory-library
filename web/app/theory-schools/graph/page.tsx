import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { TheoryGraphClient } from "@/components/theory-graph-client";
import { loadDisciplines, loadTheoryGraph } from "@/lib/server-api";

export const metadata: Metadata = { title: "社会理论图谱" };

export default async function TheoryGraphPage({ searchParams }: { searchParams: Promise<{ discipline?: string }> }) {
  const discipline = (await searchParams).discipline ?? "";
  const [disciplines, graph] = await Promise.all([loadDisciplines(), loadTheoryGraph(discipline)]);
  return (
    <>
      <main className="page-shell theory-graph-page">
        <header><p className="eyebrow">探索理论流派</p><h1>社会理论图谱</h1><p>浏览经过人工确认的理论谱系、影响、批评与相邻关系。</p></header>
        <div className="graph-page-controls panel">
          <nav><Link className={!discipline ? "active" : ""} href="/theory-schools/graph">全部学科</Link>{disciplines.map((item) => <Link className={discipline === item.slug ? "active" : ""} href={`/theory-schools/graph?discipline=${item.slug}`} key={item.id}>{item.name}</Link>)}</nav>
          <div><Link href="/theory-schools">学科脉络</Link><Link href="/theory-schools/timeline">历史时间轴</Link><Link className="active" href="/theory-schools/graph">理论图谱</Link></div>
        </div>
        <TheoryGraphClient graph={graph} />
      </main>
      <SiteFooter />
    </>
  );
}
