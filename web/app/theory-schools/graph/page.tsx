import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { KnowledgeMapHero } from "@/components/public/knowledge-map-hero";
import styles from "@/components/public/secondary-public-view.module.css";
import { TheoryGraphClient } from "@/components/theory-graph-client";
import { loadDisciplines } from "@/lib/api/taxonomy.server";
import { loadTheoryGraph } from "@/lib/api/theories.server";

export const metadata: Metadata = { title: "社会理论图谱" };

export default async function TheoryGraphPage({ searchParams }: { searchParams: Promise<{ discipline?: string }> }) {
  const discipline = (await searchParams).discipline ?? "";
  const [disciplines, graph] = await Promise.all([loadDisciplines(), loadTheoryGraph(discipline)]);
  return (
    <>
      <main className={styles.page}>
        <KnowledgeMapHero title="社会理论图谱" description="浏览经过人工确认的理论谱系、影响、批评与相邻关系。" />
        <div className={styles.content}><div className={styles.controls}>
          <nav><Link aria-current={!discipline ? "page" : undefined} href="/theory-schools/graph">全部学科</Link>{disciplines.map((item) => <Link aria-current={discipline === item.slug ? "page" : undefined} href={`/theory-schools/graph?discipline=${item.slug}`} key={item.id}>{item.name}</Link>)}</nav>
          <div><Link href="/theory-schools">学科脉络</Link><Link href="/theory-schools/timeline">历史时间轴</Link><Link aria-current="page" href="/theory-schools/graph">理论图谱</Link></div>
        </div>
        <>{graph.nodes.length ? <TheoryGraphClient graph={graph} /> : <p className="empty-state">理论关系需要证据并经管理员确认后才会出现在图谱中。</p>}</></div>
      </main>
      <SiteFooter />
    </>
  );
}
