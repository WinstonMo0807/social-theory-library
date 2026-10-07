import Link from "next/link";
import { ArrowRight, BookOpen, CircleDot, Layers3, Network, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import {
  KnowledgeNodeCard,
  DisciplineCard,
  ReadingPathCard,
  TheoryEmpty,
  TheorySectionHeading,
} from "@/components/theory-system-ui";
import type { loadTheoryDisciplinePage } from "@/lib/api/knowledge.server";
import type { TheorySystemOverview } from "@/lib/api/knowledge.types";

type DisciplinePagePayload = NonNullable<Awaited<ReturnType<typeof loadTheoryDisciplinePage>>>;

export function DisciplinePublicView({
  payload,
  activeType,
  slug,
  footer,
  directory,
  subdisciplines = [],
  collectionsAvailable = true,
}: {
  payload: DisciplinePagePayload;
  activeType: string;
  slug: string;
  footer: ReactNode;
  directory?: TheorySystemOverview["disciplines"];
  subdisciplines?: {id:string;name:string;slug:string}[];
  collectionsAvailable?: boolean;
}) {
  const { discipline, counts } = payload;
  const contextCards = directory ? [{...discipline,counts},...directory.filter(row=>row.id!==discipline.id)].slice(0,3) : [];

  return (
    <>
      <main className="page-shell theory-system-page theory-discipline-page v307-knowledge discipline-v307 discipline-reference-page">
        {directory ? <section className="discipline-reference-directory"><header><h1>理论流派</h1><p>从不同学科视角，探索社会世界的多重面向。</p></header><div className="discipline-reference-cards" data-edit-section="media">{contextCards.map(row=><div key={row.id} className={row.id===discipline.id ? "selected" : ""}><DisciplineCard discipline={row} counts={row.counts}/></div>)}</div></section> : <nav className="taxonomy-public-breadcrumb"><Link href="/theories">理论流派</Link><span>›</span><strong>{discipline.name}</strong></nav>}
        <section className="discipline-reference-overview" id="overview"><header><h1 data-edit-section="identity">{discipline.name}</h1><nav aria-label="学科详情栏目"><a href="#overview" aria-current="page">概述</a><button type="button" disabled>主要议题</button><button type="button" disabled>代表学者</button><Link href={`/explore?discipline=${encodeURIComponent(slug)}`}>相关书籍</Link></nav></header><p data-edit-section="content">{discipline.description}</p>{subdisciplines.length ? <div data-edit-section="relations"><span>主要子学科</span><div>{subdisciplines.slice(0,5).map(row=><Link key={row.id} href={`/subdisciplines/${row.slug}`}>{row.name}</Link>)}</div></div> : null}</section>

        {collectionsAvailable ? <><section className="theory-discipline-directory panel" data-edit-section="content">
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
            {payload.lineage.slice(0, 8).map((event) => <Link href={`/theories/events/${event.id}`} key={event.id}><i /><time>{event.date_label || event.start_year}</time><strong>{event.title}</strong><small>{event.description}</small></Link>)}
          </div>
        </section> : null}

        {payload.reading_paths.length ? <section className="theory-path-section">
          <TheorySectionHeading title="推荐阅读路径" />
          <div className="theory-reading-path-grid">{payload.reading_paths.map((path) => <ReadingPathCard key={path.id} path={path} />)}</div>
        </section> : null}

        <nav className="theory-discipline-shortcuts" aria-label="理论系统快捷入口">
          <Link href={`/theories/timeline?discipline=${encodeURIComponent(slug)}`}><CircleDot />历史时间轴<ArrowRight /></Link>
          <Link href={`/theories/graph?discipline=${encodeURIComponent(slug)}`}><Network />局部理论图谱<ArrowRight /></Link>
          {counts.scholars ? <Link href="/scholars?view=directory"><UsersRound />浏览学者<ArrowRight /></Link> : null}
        </nav></> : null}
      </main>
      {footer}
    </>
  );
}
