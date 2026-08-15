import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, CircleDot, Layers3, Network, UsersRound } from "lucide-react";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import {
  KnowledgeNodeCard,
  ReadingPathCard,
  TheoryBanner,
  TheoryEmpty,
  TheorySectionHeading,
  TheoryStat,
} from "@/components/theory-system-ui";
import { loadTheoryDisciplinePage } from "@/lib/server-api";

const allowedTypes = new Set(["theory_tradition", "subdiscipline", "debate"]);

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const payload = await loadTheoryDisciplinePage(slug);
  return { title: payload?.discipline.name || "学科详情", description: payload?.discipline.description || "从学科浏览理论条目和馆藏。" };
}

export default async function TheoryDisciplinePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ type?: string }>;
}) {
  const { slug } = await params;
  const query = await searchParams;
  const activeType = allowedTypes.has(query.type || "") ? query.type! : "theory_tradition";
  const payload = await loadTheoryDisciplinePage(slug, activeType);
  if (!payload) notFound();
  const { discipline, counts } = payload;

  return (
    <>
      <main className="page-shell theory-system-page theory-discipline-page">
        <div className="theory-breadcrumb"><Link href="/theories">理论流派</Link><span>/</span><strong>{discipline.name}</strong></div>
        <section className="theory-discipline-hero">
          <div>
            <p className="eyebrow">学科详情</p>
            <h1>{discipline.name}</h1>
            {discipline.foreign_name ? <h2>{discipline.foreign_name}</h2> : null}
            {discipline.description ? <p>{discipline.description}</p> : null}
          </div>
          <TheoryBanner image={discipline.hero_image} />
        </section>

        {Object.keys(counts).length ? <section className="theory-discipline-stats">
          <TheoryStat value={counts.theory_traditions} label="理论传统" kind="network" />
          <TheoryStat value={counts.subdisciplines} label="子学科" kind="layers" />
          <TheoryStat value={counts.scholars} label="学者" kind="people" />
          <TheoryStat value={counts.works} label="馆藏文献" kind="works" />
        </section> : null}

        <section className="theory-discipline-directory panel">
          <nav className="theory-tab-list" aria-label="学科内容分类">
            <Link className={activeType === "theory_tradition" ? "active" : ""} href={`/theories/disciplines/${slug}?type=theory_tradition`}><Network size={17} />理论传统{counts.theory_traditions ? <b>{counts.theory_traditions}</b> : null}</Link>
            <Link className={activeType === "subdiscipline" ? "active" : ""} href={`/theories/disciplines/${slug}?type=subdiscipline`}><Layers3 size={17} />子学科{counts.subdisciplines ? <b>{counts.subdisciplines}</b> : null}</Link>
            <Link className={activeType === "debate" ? "active" : ""} href={`/theories/disciplines/${slug}?type=debate`}><CircleDot size={17} />关键争论{counts.debates ? <b>{counts.debates}</b> : null}</Link>
            <Link href={`/explore?discipline=${encodeURIComponent(slug)}`}><BookOpen size={17} />全部馆藏{counts.works ? <b>{counts.works}</b> : null}</Link>
          </nav>
          {payload.nodes.length ? <div className="theory-node-grid">{payload.nodes.map((node) => <KnowledgeNodeCard key={node.id} node={node} />)}</div> : <TheoryEmpty title="该分类尚无公开条目" detail="仅发布并通过审核的条目会出现在这里。" />}
        </section>

        {payload.lineage.length ? <section className="theory-lineage-section">
          <TheorySectionHeading title="本学科脉络" href={`/theories/timeline?discipline=${encodeURIComponent(slug)}`} action="查看完整时间轴" />
          <div className="theory-lineage-track">
            {payload.lineage.slice(0, 8).map((event) => <Link href={`/theories/timeline?q=${encodeURIComponent(event.title)}`} key={event.id}><i /><time>{event.date_label || event.start_year}</time><strong>{event.title}</strong><small>{event.description}</small></Link>)}
          </div>
        </section> : null}

        {payload.reading_paths.length ? <section className="theory-path-section">
          <TheorySectionHeading title="推荐阅读路径" />
          <div className="theory-reading-path-grid">{payload.reading_paths.map((path) => <ReadingPathCard key={path.id} path={path} />)}</div>
        </section> : null}

        <nav className="theory-discipline-shortcuts" aria-label="理论系统快捷入口">
          <Link href={`/theories/timeline?discipline=${encodeURIComponent(slug)}`}><CircleDot />历史时间轴<ArrowRight /></Link>
          <Link href={`/theories/graph?discipline=${encodeURIComponent(slug)}`}><Network />局部理论图谱<ArrowRight /></Link>
          {counts.scholars ? <Link href={`/scholars?discipline=${encodeURIComponent(slug)}`}><UsersRound />相关学者<ArrowRight /></Link> : null}
        </nav>
      </main>
      <SiteFooter />
    </>
  );
}
