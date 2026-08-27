import Link from "next/link";
import { ArrowLeft, ArrowRight, BookOpen } from "lucide-react";
import { KnowledgeMap } from "@/components/knowledge-map";
import { BookCard, SectionHeading } from "@/components/ui";
import type { TheorySchool } from "@/lib/data";
import type { ScholarDetailData } from "@/lib/public-data-adapters";

export const scholarSectionTitles: Record<string, string> = {
  biography: "完整传记",
  timeline: "生平与主要发表",
  works: "重要文献与馆藏作品",
  concepts: "关键概念",
  "concept-map": "概念地图",
  network: "学术关系网络",
  theories: "相关理论流派",
  "frequently-read": "经常连着阅读",
};

export function ScholarSectionPublicView({
  data,
  schools,
  section,
  slug,
}: {
  data: ScholarDetailData;
  schools: TheorySchool[];
  section: string;
  slug: string;
}) {
  const { scholar, works, timeline, knowledgeNodes, curated } = data;
  const essentialWorks = curated.essentialWorks.length ? curated.essentialWorks : works;
  const normalizedTheories = knowledgeNodes.filter((node) => node.node_type === "theory_tradition");
  const normalizedConcepts = knowledgeNodes.filter((node) => node.node_type === "concept");
  const relatedSchools = normalizedTheories.length
    ? normalizedTheories.map((node) => ({
        ...node,
        href: `/theories/nodes/${node.slug}`,
        symbol: node.name.slice(0, 2),
        description: node.summary || node.relation_label || "已确认的知识关系",
      }))
    : curated.relatedTheories.length
      ? curated.relatedTheories.map((school) => ({
          ...school,
          href: `/theory-schools/${school.slug}`,
          symbol: school.symbol || school.name.slice(0, 2),
          books: 0,
          scholars: 0,
          description: school.description || "管理员确认的相关理论流派",
        }))
      : schools
          .filter((school) => works.some((work) => work.theories?.some((item) => item.slug === school.slug)))
          .map((school) => ({ ...school, href: `/theory-schools/${school.slug}` }));

  return (
    <main className="page-shell secondary-detail-page" data-public-page={section}>
      <Link className="back-link" href={`/scholars/${slug}`}><ArrowLeft size={15} />返回{scholar.name}主页</Link>
      <header><p className="eyebrow">学者档案</p><h1>{scholarSectionTitles[section]}</h1><p>{scholar.name} · {scholar.years}</p></header>
      {section === "biography" ? <section className="panel longform-panel" data-module-id="scholar-biography"><p>{scholar.biography}</p></section> : null}
      {section === "timeline" ? (
        <section className="panel timeline-detail-list" data-module-id="scholar-timeline">
          {timeline.map(([year, event]) => <article key={`${year}-${event}`}><time>{year}</time><p>{event}</p></article>)}
          {!timeline.length ? <p className="empty-state">时间线尚待管理员编辑。</p> : null}
        </section>
      ) : null}
      {section === "works" ? (
        <section className="detail-section" data-module-id="scholar-works"><div className="four-book-grid">{essentialWorks.map((work) => <BookCard work={work} key={work.id} />)}{!essentialWorks.length ? <p className="empty-state">尚无已发布的馆藏作品。</p> : null}</div></section>
      ) : null}
      {section === "concepts" ? (
        <section className="panel definition-list" data-module-id="scholar-concepts">
          {(curated.keyConcepts.length ? curated.keyConcepts : normalizedConcepts).map((item, index) => {
            if (typeof item !== "string" && "node_type" in item) {
              return <article className="definition-row" key={item.id}><b>{String(index + 1).padStart(2, "0")}</b><Link href={`/theories/nodes/${item.slug}`}><strong>{item.name}</strong></Link><p>{item.summary || "说明待管理员补充。"}</p>{item.relation_label ? <small>关系：{item.relation_label}</small> : null}</article>;
            }
            const label = typeof item === "string" ? item : item.name || `概念 ${index + 1}`;
            const description = typeof item === "string" ? "" : item.description || "";
            const source = typeof item === "string" ? "" : item.source || "";
            return <article className="definition-row" key={`${label}-${index}`}><b>{String(index + 1).padStart(2, "0")}</b><strong>{label}</strong><p>{description || "说明待管理员补充。"}</p>{source ? <small>依据：{source}</small> : null}</article>;
          })}
          {!curated.keyConcepts.length && !normalizedConcepts.length ? <p className="empty-state">关键概念尚待管理员编辑。</p> : null}
        </section>
      ) : null}
      {section === "concept-map" ? <section className="panel" data-module-id="scholar-concept-map"><KnowledgeMap entries={curated.conceptMap} emptyText="概念地图尚待管理员编辑。" /></section> : null}
      {section === "network" ? (
        <section className="panel secondary-link-list" data-module-id="scholar-network">
          {curated.network.map((item) => <Link href={`/scholars/${item.scholar.slug}`} key={item.scholar.id}><span className="tiny-portrait" /><p><strong>{item.scholar.name}</strong><small>{item.relation} · {item.source}</small></p><ArrowRight size={15} /></Link>)}
          {!curated.network.length ? <p className="empty-state">尚无经过来源确认的公开关系。</p> : null}
        </section>
      ) : null}
      {section === "theories" ? (
        <section className="panel secondary-link-list" data-module-id="scholar-theories">
          {relatedSchools.map((school) => <Link href={school.href} key={school.slug}><span className="theory-symbol">{school.symbol}</span><p><strong>{school.name}</strong><small>{school.description}</small></p><ArrowRight size={15} /></Link>)}
          {!relatedSchools.length ? <p className="empty-state">相关理论流派尚待管理员确认。</p> : null}
        </section>
      ) : null}
      {section === "frequently-read" ? (
        <section className="panel secondary-link-list" data-module-id="scholar-frequently-read">
          {curated.frequentlyReadScholars.map((item) => <Link href={`/scholars/${item.slug}`} key={item.id}><BookOpen size={17} /><p><strong>{item.name}</strong><small>查看学者主页和馆藏作品</small></p><ArrowRight size={15} /></Link>)}
          {!curated.frequentlyReadScholars.length ? <p className="empty-state">尚无管理员确认的关联阅读条目。</p> : null}
        </section>
      ) : null}
      <SectionHeading title="继续探索" href={`/explore?q=${encodeURIComponent(scholar.name)}`} action="检索全部相关馆藏" />
    </main>
  );
}
