import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  CircleDot,
  Compass,
  Grid2X2,
  MessagesSquare,
  Quote,
  Users,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";
import { AskLibraryLink } from "@/components/ask-library-link";
import { CuratedClaimSections } from "@/components/curated-claim-sections";
import { SaveTopicButton } from "@/components/save-topic-button";
import { ArchitecturalImage, BookCard, ScholarPortrait, SectionHeading, TagList } from "@/components/ui";
import type { LibraryTopic } from "@/lib/server-api";

function TextItems({ items, empty }: { items: string[]; empty: string }) {
  return items.length
    ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>
    : <p className="empty-state">{empty}</p>;
}

export function TopicPublicView({ topic, footer }: { topic: LibraryTopic; footer?: ReactNode }) {
  const works = topic.works;
  const scholars = topic.curated.relatedScholars.length
    ? topic.scholars.filter((scholar) => topic.curated.relatedScholars.some((item) => item.slug === scholar.slug))
    : topic.scholars;
  const normalizedTheories = topic.knowledgeNodes
    .filter((node) => node.node_type === "theory_tradition")
    .map((node) => ({ ...node, href: `/theories/nodes/${node.slug}`, symbol: node.name.slice(0, 2) }));
  const theorySchools = normalizedTheories.length
    ? normalizedTheories
    : (topic.linkedTheories.length ? topic.linkedTheories : topic.theories).map((theory) => ({
        ...theory,
        href: `/theory-schools/${theory.slug}`,
        symbol: "symbol" in theory ? theory.symbol : theory.name.slice(0, 2),
      }));
  const relatedKnowledge = topic.knowledgeNodes.filter((node) =>
    ["concept", "debate", "research_problem"].includes(node.node_type),
  );
  const excerpt = topic.passages.find((passage) => passage.id === topic.curated.featuredPassageId)
    ?? topic.passages[0];

  return (
    <>
      <main className="page-shell topic-problem-page">
        <p className="breadcrumbs"><Link href="/topics">研究主题</Link> / {topic.name}</p>
        <section className="topic-problem-hero" data-module-id="topic-identity">
          <div data-module-id="topic-problem">
            <p className="eyebrow">研究主题</p>
            <h1>{topic.name}</h1>
            <p>{topic.problemStatement || topic.description || "该研究主题的说明尚待管理员编辑。"}</p>
            <TagList items={topic.concepts} />
            <AskLibraryLink context="topics" ids={[topic.id]} label={`询问关于${topic.name}的馆藏`} />
          </div>
          <div
            className={`topic-problem-image${topic.heroImage ? " has-image" : ""}`}
            style={topic.heroImage ? { backgroundImage: `url("${topic.heroImage}")` } : undefined}
          >
            {!topic.heroImage ? <ArchitecturalImage compact /> : null}
          </div>
        </section>

        <section className="topic-fact-strip">
          <div><Compass size={23} /><span>相关学科</span><strong>{topic.disciplines.map((item) => item.name).join("、") || "跨学科或暂未归类"}</strong></div>
          <div><CalendarDays size={23} /><span>形成背景</span><strong>{topic.formationContext || "待编辑"}</strong></div>
          <div><BookOpen size={23} /><span>馆藏文献</span><strong>{topic.workCount.toLocaleString("zh-CN")} 部</strong></div>
          <div><Users size={23} /><span>关联学者</span><strong>{scholars.length} 位</strong></div>
          <SaveTopicButton topicId={topic.id} />
        </section>

        <div data-module-id="topic-curated-claims"><CuratedClaimSections groups={topic.curatedClaims} /></div>

        <div className="topic-problem-layout">
          <div className="topic-problem-main">
            <section className="topic-analysis-grid" data-module-id="topic-framework">
              <article className="panel"><MessagesSquare size={22} /><SectionHeading title="研究对象与核心问题" /><TextItems items={topic.coreQuestions} empty="核心问题尚待管理员确认。" /></article>
              <article className="panel"><CircleDot size={22} /><SectionHeading title="形成与发展" /><p>{topic.formationContext || "形成背景尚待管理员编辑。"}</p></article>
              <article className="panel"><Grid2X2 size={22} /><SectionHeading title="主要研究维度" /><TextItems items={topic.researchDimensions} empty="研究维度尚待管理员确认。" /></article>
              <article className="panel"><Wrench size={22} /><SectionHeading title="常用方法" /><TextItems items={topic.methods} empty="研究方法尚待管理员确认。" /></article>
            </section>

            <section className="topic-relations-row">
              <article className="panel" data-module-id="topic-theories">
                <SectionHeading title="理论、概念与争论" href={`/topics/${topic.slug}/theory-schools`} />
                {theorySchools.slice(0, 3).map((theory) => (
                  <Link className="topic-relation-link" href={theory.href} key={theory.slug}>
                    <span>{theory.symbol}</span><strong>{theory.name}</strong><ArrowRight size={15} />
                  </Link>
                ))}
                {relatedKnowledge.slice(0, 5 - Math.min(3, theorySchools.length)).map((node) => (
                  <Link className="topic-relation-link" href={`/theories/nodes/${node.slug}`} key={node.id}>
                    <span>{node.node_type === "debate" ? "争论" : node.node_type === "concept" ? "概念" : "问题"}</span>
                    <strong>{node.name}</strong><ArrowRight size={15} />
                  </Link>
                ))}
                {!theorySchools.length && !relatedKnowledge.length ? <p className="empty-state">尚无经过确认的知识关系。</p> : null}
              </article>
              <article className="panel" data-module-id="topic-subdisciplines">
                <SectionHeading title="相关子学科" href="/subdisciplines" />
                {topic.subdisciplines.slice(0, 5).map((item) => (
                  <Link className="topic-relation-link" href={`/subdisciplines/${item.slug}`} key={item.id}>
                    <span>{item.name.slice(0, 2)}</span><strong>{item.name}</strong><ArrowRight size={15} />
                  </Link>
                ))}
                {!topic.subdisciplines.length ? <p className="empty-state">尚无经过确认的子学科关系。</p> : null}
              </article>
              <article className="panel" data-module-id="topic-scholars">
                <SectionHeading title="代表学者" href={`/topics/${topic.slug}/scholars`} />
                {scholars.slice(0, 4).map((scholar) => (
                  <Link className="topic-scholar-link" href={`/scholars/${scholar.slug}`} key={scholar.slug}>
                    <ScholarPortrait scholar={scholar} /><span><strong>{scholar.name}</strong><small>{scholar.years}</small></span><ArrowRight size={15} />
                  </Link>
                ))}
                {!scholars.length ? <p className="empty-state">代表学者尚待管理员确认。</p> : null}
              </article>
            </section>

            {excerpt ? (
            <section className="panel topic-evidence-spotlight" data-module-id="topic-evidence">
                <SectionHeading title="主题相关原文" />
                <blockquote><Quote size={24} />{excerpt.snippet}</blockquote>
                {topic.curated.featuredPassageReason ? <p>入选说明：{topic.curated.featuredPassageReason}</p> : null}
                <cite>《{excerpt.title}》，PDF 第 {excerpt.pageIndex} 页</cite>
                <Link className="button secondary" href={`/reader/${excerpt.assetId}?page=${excerpt.pageIndex}&passage=${encodeURIComponent(excerpt.id)}`}>阅读原文 <ArrowRight size={16} /></Link>
              </section>
            ) : null}
          </div>

          <aside className="topic-problem-aside">
            <section className="panel" data-module-id="topic-works">
              <SectionHeading title="入门阅读" href={`/topics/${topic.slug}/works`} />
              {(topic.curated.foundationalWorks.length ? topic.curated.foundationalWorks : works).slice(0, 5).map((work) => (
                <BookCard work={work} dense key={work.id} />
              ))}
              {!works.length ? <p className="empty-state">尚无已确认馆藏。</p> : null}
            </section>
            <section className="panel" data-module-id="topic-reading-paths">
              <SectionHeading title="策展阅读路径" href={`/topics/${topic.slug}/reading-paths`} />
              {topic.curated.readingPaths.map((path) => (
                <Link className="reading-path-row" href={`/topics/${topic.slug}/reading-paths`} key={path.title}>
                  <BookOpen size={18} /><p><strong>{path.title}</strong><small>{path.description}</small></p><ArrowRight size={15} />
                </Link>
              ))}
              {!topic.curated.readingPaths.length ? <p className="empty-state">阅读路径尚待管理员策展。</p> : null}
            </section>
          </aside>
        </div>
      </main>
      {footer}
    </>
  );
}
