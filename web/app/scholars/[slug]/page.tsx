import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowRight, Quote } from "lucide-react";
import { KnowledgeMap } from "@/components/knowledge-map";
import { SiteFooter } from "@/components/site-footer";
import { BookCover, ScholarPortrait, SectionHeading, TagList } from "@/components/ui";
import { loadScholar, loadTheorySchools } from "@/lib/server-api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const data = await loadScholar(slug);
  return { title: data?.scholar.name ?? "学者" };
}

export default async function ScholarDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [data, theorySchools] = await Promise.all([
    loadScholar(slug),
    loadTheorySchools(),
  ]);
  if (!data) notFound();
  const {
    scholar,
    shortDescription,
    works: scholarWorks,
    affiliations,
    timeline,
    featuredQuote,
    quoteSource,
    curated,
  } = data;
  const essentialWorks = curated.essentialWorks.length ? curated.essentialWorks : scholarWorks;
  const keyConcepts = curated.keyConcepts.length ? curated.keyConcepts : scholar.concerns;
  const relatedSchools = curated.relatedTheories.length
    ? curated.relatedTheories.map((school) => ({
        ...school,
        symbol: school.symbol || school.name.slice(0, 2),
        books: 0,
        scholars: 0,
        description: school.description || "管理员确认的相关理论流派",
      }))
    : theorySchools.filter((school) =>
        scholarWorks.some((work) => work.theories?.some((item) => item.slug === school.slug)),
      );

  return (
    <>
      <div className="page-shell scholar-detail">
        <section className="scholar-hero">
          <ScholarPortrait scholar={scholar} large />
          <div className="scholar-intro">
            <h1>{scholar.originalName}</h1>
            <p className="scholar-years">{scholar.years}</p>
            <p>{scholar.school}</p>
            <p className="biography">{shortDescription}</p>
            <div className="affiliation-concerns">
              <div>
                <h2>主要任职</h2>
                {affiliations.map((affiliation) => <p key={affiliation}>{affiliation}</p>)}
                {!affiliations.length ? <p className="muted-row">任职信息待编辑。</p> : null}
              </div>
              <div>
                <h2>核心关切</h2>
                <TagList items={scholar.concerns} />
              </div>
            </div>
          </div>
          <div className="scholar-timeline">
            <SectionHeading title="生平与主要著作" href={`/scholars/${slug}/timeline`} action="查看完整时间线" />
            {timeline.map(([year, event]) => (
              <p key={`${year}-${event}`}><time>{year}</time><span>{event}</span></p>
            ))}
            {!timeline.length ? <p className="muted-row">时间线尚未由编辑确认。</p> : null}
          </div>
          {featuredQuote ? (
            <blockquote className="scholar-quote">
              <Quote size={28} fill="currentColor" />
              {featuredQuote}
              <cite>— {quoteSource || scholar.originalName}</cite>
            </blockquote>
          ) : <div className="scholar-quote empty-state">尚无经过来源核对的公开引语。</div>}
        </section>

        <div className="scholar-body-grid">
          <section className="essential-texts panel">
            <SectionHeading title="重要文献" href={`/scholars/${slug}/works`} />
            {essentialWorks.map((work) => (
              <Link href={`/works/${work.slug}`} key={work.id}>
                <BookCover work={work} size="small" />
                <span><strong>{work.title}</strong><small>{work.year} · {work.kind}</small></span>
              </Link>
            ))}
          </section>

          <section className="about-scholar panel">
            <SectionHeading title={`关于${scholar.name}`} href={`/scholars/${slug}/biography`} action="查看完整传记" />
            <p>{scholar.biography}</p>
            <div className="scholar-key-grid">
              <div>
                <SectionHeading title="关键概念" href={`/scholars/${slug}/concepts`} action="查看全部" />
                {keyConcepts.map((concept, index) => {
                  const name = typeof concept === "string" ? concept : concept.name || `概念 ${index + 1}`;
                  const description = typeof concept === "string"
                    ? "组织其研究问题与经验分析的重要概念。"
                    : concept.description || "概念说明待编辑。";
                  const source = typeof concept === "string" ? "" : concept.source || "";
                  return <div className="concept-row" key={`${name}-${index}`}>
                    <span>{index + 1}</span>
                    <p>
                      <strong>{name}</strong>
                      <small>{description}</small>
                      {source ? <small>依据：{source}</small> : null}
                    </p>
                  </div>;
                })}
              </div>
              <div>
                <SectionHeading title="相关理论流派" href={`/scholars/${slug}/theories`} action="查看全部" />
                {relatedSchools.slice(0, 5).map((school) => (
                  <Link className="school-link-row" href={`/theory-schools/${school.slug}`} key={school.slug}>
                    <span className="theory-symbol">{school.symbol}</span>
                    <strong>{school.name}</strong>
                    <ArrowRight size={16} />
                  </Link>
                ))}
                {!relatedSchools.length ? <p className="empty-state">相关流派尚待编辑确认。</p> : null}
              </div>
            </div>
          </section>

          <section className="concept-map panel">
            <SectionHeading title="概念图" href={`/scholars/${slug}/concept-map`} action="查看交互图" />
            <div className="bourdieu-map">
              <span className="map-center">{scholar.name}<small>馆藏学者</small></span>
              {(curated.conceptMap.length ? curated.conceptMap : keyConcepts).slice(0, 4).map((concept, index) => {
                const fields = typeof concept === "string" ? null : concept as {
                  name?: string;
                  source?: string;
                  target?: string;
                  label?: string;
                  description?: string;
                };
                const label = typeof concept === "string"
                  ? concept
                  : fields?.name || fields?.source || fields?.target || fields?.label || fields?.description || `概念 ${index + 1}`;
                return <span className={["map-top", "map-left", "map-right", "map-bottom"][index]} key={`${label}-${index}`}>
                  {label}<small>核心关切</small>
                </span>
              })}
            </div>
            {curated.conceptMap.length ? <KnowledgeMap entries={curated.conceptMap.slice(0, 2)} /> : null}
          </section>

          <section className="network-connections panel">
            <SectionHeading title="学术关系" href={`/scholars/${slug}/network`} action="查看完整网络" />
            {curated.network.map((connection) => (
              <Link className="connection-row" href={`/scholars/${connection.scholar.slug}`} key={connection.scholar.id}>
                <span className="tiny-portrait" />
                <p><strong>{connection.scholar.name}</strong><small>{connection.relation || "相关学者"}</small></p>
                <span>{connection.source || "管理员确认"}</span>
              </Link>
            ))}
            {!curated.network.length ? <div className="connection-row empty-state">只有附有来源并经人工确认的学术关系才会公开。</div> : null}
          </section>

          <section className="curated-works panel">
            <SectionHeading title="馆藏作品" href={`/explore?q=${scholar.name}`} action={`查看全部 ${scholarWorks.length} 部`} />
            <div className="curated-cover-row">
              {scholarWorks.map((work) => (
                <Link href={`/works/${work.slug}`} key={work.id}>
                  <BookCover work={work} size="small" />
                  <span>{work.title}</span>
                </Link>
              ))}
            </div>
          </section>

          <section className="frequently-read panel">
            <SectionHeading title="经常连着阅读" href={`/scholars/${slug}/frequently-read`} action="查看全部" />
            <div className="frequent-scholar-row">
              {curated.frequentlyReadScholars.map((profile) => (
                <Link href={`/scholars/${profile.slug}`} key={profile.id}>
                  <span className="tiny-portrait" />
                  <strong>{profile.name}</strong>
                </Link>
              ))}
            </div>
            {!curated.frequentlyReadScholars.length ? <p className="empty-state">尚无人工确认的关联阅读学者。</p> : null}
          </section>
        </div>
      </div>
      <SiteFooter />
    </>
  );
}
