import Link from "next/link";
import { ArrowLeft, ArrowRight, BookOpen } from "lucide-react";
import { BookCard, ScholarCard } from "@/components/ui";
import type { LibraryTopic } from "@/lib/api/topics.types";
import { CuratedClaimSections } from "@/components/curated-claim-sections";
import { CollectionLink } from "@/components/collection-link";
import { EvidenceCurationView } from "@/components/public/evidence-curation-view";

export const topicSectionTitles: Record<string, string> = {
  works: "奠基文献",
  recent: "最近入库",
  scholars: "相关学者",
  "theory-schools": "关联理论流派",
  timeline: "概念时间线",
  "reading-paths": "策展阅读路径",
  concepts: "关键概念",
  questions: "研究对象与核心问题",
  history: "形成与发展",
  dimensions: "主要研究维度",
  methods: "研究方法 / 工具",
  subdisciplines: "相关子学科",
  passages: "主题相关原文",
};

export function TopicSectionPublicView({ topic, section }: { topic: LibraryTopic; section: string }) {
  const works = section === "recent"
    ? topic.curated.recentWorks.length ? topic.curated.recentWorks : topic.works
    : topic.curated.foundationalWorks.length ? topic.curated.foundationalWorks : topic.works;
  const normalizedTheories = topic.knowledgeNodes.filter((node) => node.node_type === "theory_tradition");
  const normalizedConcepts = topic.knowledgeNodes.filter((node) => node.node_type === "concept");

  return (
    <main className="page-shell secondary-detail-page v307-knowledge knowledge-section-page" data-public-page={section}>
      <Link className="back-link" href={`/topics/${topic.slug}`}><ArrowLeft size={15} />返回{topic.name}</Link>
      <header><p className="eyebrow">研究主题</p><h1>{topicSectionTitles[section]}</h1><p>{topic.description}</p></header>
      {["questions", "dimensions", "methods"].includes(section) ? <section className="knowledge-detail-cards" data-edit-section={section}>
        {section === "questions" && topic.problemStatement ? <p>{topic.problemStatement}</p> : null}
        {(section === "questions" ? topic.coreQuestions : section === "dimensions" ? topic.researchDimensions : topic.methods).map((item, index) => <article className="panel" id={`item-${index + 1}`} key={`${index}-${item}`}><span className="eyebrow">{String(index + 1).padStart(2, "0")}</span><h2>{item}</h2><Link href={`/explore?q=${encodeURIComponent(item)}&topic=${encodeURIComponent(topic.slug)}`}>查找相关馆藏 <ArrowRight size={15}/></Link></article>)}
      </section> : null}
      {section === "history" ? <section data-edit-section="history"><p className="knowledge-long-copy">{topic.formationContext}</p><div className="panel timeline-detail-list">{topic.timeline.map(([year, label, text]) => <article key={`${year}-${label}`}><time>{year}</time><p><strong>{label}</strong><span>{text}</span></p></article>)}</div></section> : null}
      {section === "subdisciplines" ? <section className="knowledge-detail-cards">{topic.subdisciplines.map(row => <Link className="panel" href={`/subdisciplines/${row.slug}`} key={row.id}><h2>{row.name}</h2><p>{row.relation_label}</p><ArrowRight size={18}/></Link>)}</section> : null}
      {section === "passages" ? <section className="knowledge-evidence-layout" data-module-id="topic-evidence" data-edit-section="passages">{topic.evidenceCuration?.configured ? <EvidenceCurationView items={topic.evidenceCuration.items} /> : <div className="knowledge-evidence-grid">{topic.passages.map(passage => <article className="panel" id={`passage-${passage.id}`} key={passage.id}><h2>{passage.title}</h2><small>{passage.printedLabel || `PDF 第 ${passage.pageIndex} 页`}</small><blockquote>{passage.snippet}</blockquote>{passage.id === topic.curated.featuredPassageId && topic.curated.featuredPassageReason ? <p>策展说明：{topic.curated.featuredPassageReason}</p> : null}<CollectionLink href={`/reader/${passage.assetId}?page=${passage.pageIndex}&passage=${encodeURIComponent(passage.id)}`}>阅读原文 <ArrowRight size={15}/></CollectionLink></article>)}{!topic.passages.length ? <p className="empty-state">尚未策展可公开的原文。</p> : null}</div>}<aside className="panel"><h2>阅读出处</h2><p>每则原文保留馆藏、版本与页面位置。策展说明与原文分开显示。</p><Link href={`/topics/${topic.slug}/works`}>查看相关文献 <ArrowRight size={15}/></Link></aside></section> : null}
      {section === "passages" && !topic.evidenceCuration?.configured ? <CuratedClaimSections groups={topic.curatedClaims}/> : null}
      {["works", "recent"].includes(section) ? <section className="four-book-grid" data-module-id="topic-works">{works.map((work) => <BookCard work={work} key={work.id} />)}{!works.length ? <p className="empty-state">尚无已发布的关联文献。</p> : null}</section> : null}
      {section === "scholars" ? <section className="scholar-grid" data-module-id="topic-scholars">{topic.scholars.map((scholar) => <ScholarCard scholar={scholar} key={scholar.slug} />)}{!topic.scholars.length ? <p className="empty-state">尚无已确认的相关学者。</p> : null}</section> : null}
      {section === "theory-schools" ? (
        <section className="panel secondary-link-list" data-module-id="topic-theories">
          {normalizedTheories.length
            ? normalizedTheories.map((node) => <Link href={`/theories/nodes/${node.slug}`} key={node.id}><span className="theory-symbol">{node.name.slice(0, 2)}</span><p><strong>{node.name}</strong><small>{node.relation_label || node.summary}</small></p><ArrowRight size={15} /></Link>)
            : topic.theories.map((school) => <Link href={`/theory-schools/${school.slug}`} key={school.slug}><span className="theory-symbol">{school.symbol}</span><p><strong>{school.name}</strong><small>{school.description}</small></p><ArrowRight size={15} /></Link>)}
          {!normalizedTheories.length && !topic.theories.length ? <p className="empty-state">尚无已确认的关联理论流派。</p> : null}
        </section>
      ) : null}
      {section === "timeline" ? <section className="panel timeline-detail-list" data-module-id="topic-timeline">{topic.timeline.map(([year, label, text]) => <article key={`${year}-${label}`}><time>{year}</time><p><strong>{label}</strong><span>{text}</span></p></article>)}{!topic.timeline.length ? <p className="empty-state">概念时间线尚待管理员编辑。</p> : null}</section> : null}
      {section === "concepts" ? <section className="panel definition-list" data-module-id="topic-concepts">
        {normalizedConcepts.length
          ? normalizedConcepts.map((node, index) => <article className="definition-row" key={node.id}><b>{String(index + 1).padStart(2, "0")}</b><Link href={`/theories/nodes/${node.slug}`}><strong>{node.name}</strong></Link><p>{node.relation_label || node.summary || "概念说明待编辑。"}</p></article>)
          : topic.concepts.map((concept, index) => <article className="definition-row" key={concept}><b>{String(index + 1).padStart(2, "0")}</b><strong>{concept}</strong><p>主题概念说明由管理员维护。</p></article>)}
        {!normalizedConcepts.length && !topic.concepts.length ? <p className="empty-state">关键概念尚待管理员编辑。</p> : null}
      </section> : null}
      {section === "reading-paths" ? (
        <section className="panel reading-path-detail-list" data-module-id="topic-reading-paths">
          {topic.curated.readingPaths.map((path, index) => <article id={`path-${index + 1}`} key={path.title}><BookOpen size={20} /><div><h2>{path.title}</h2><p>{path.description}</p><small>{path.level || "未分级"} · {path.works.length} 部文献</small><div className="four-book-grid">{path.works.map((work) => <BookCard work={work} key={work.id} />)}</div></div></article>)}
          {!topic.curated.readingPaths.length ? <p className="empty-state">尚无公开阅读路径。</p> : null}
        </section>
      ) : null}
    </main>
  );
}
