import Link from "next/link";
import { ArrowRight, BookOpen, CircleDot, Compass, Grid2X2, MessagesSquare, Users, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { AskLibraryLink } from "@/components/ask-library-link";
import { SaveTopicButton } from "@/components/save-topic-button";
import { ArchitecturalImage, BookCard, ScholarPortrait, SectionHeading } from "@/components/ui";
import type { LibraryTopic } from "@/lib/api/topics.types";

export function TopicPublicView({ topic, footer }: { topic: LibraryTopic; footer?: ReactNode }) {
  const works = topic.curated.foundationalWorks.length ? topic.curated.foundationalWorks : topic.works;
  const scholars = topic.curated.relatedScholars.length ? topic.scholars.filter(row => topic.curated.relatedScholars.some(item => item.slug === row.slug)) : topic.scholars;
  const href = (section: string) => `/topics/${topic.slug}/${section}`;
  const knowledge = topic.knowledgeNodes.filter(row => ["concept", "debate", "theory_tradition", "research_problem"].includes(row.node_type));
  const curatedEvidence = topic.evidenceCuration?.configured ? topic.evidenceCuration.items : null;
  const hasEvidence = curatedEvidence ? curatedEvidence.length > 0 : topic.passages.length > 0;
  return <><main className="page-shell v307-knowledge topic-v307">
    <p className="breadcrumbs"><Link href="/topics">主题</Link><span>›</span>{topic.name}</p>
    <section className="knowledge-hero" data-module-id="topic-identity" data-edit-section="identity"><div><p className="eyebrow">主题</p><h1>{topic.name}</h1><p>{topic.problemStatement || topic.description}</p><AskLibraryLink context="topics" ids={[topic.id]} label="向图书馆提问" /></div><div className="knowledge-hero-image" style={topic.heroImage ? { backgroundImage: `url("${topic.heroImage}")` } : undefined}>{!topic.heroImage ? <ArchitecturalImage compact /> : null}</div></section>
    <div className="knowledge-facts"><span>相关学科 <strong>{topic.disciplines.map(row => row.name).join("、") || "跨学科"}</strong></span><span>关联馆藏 <strong>{topic.workCount} 部</strong></span><span>关联学者 <strong>{scholars.length} 位</strong></span><SaveTopicButton topicId={topic.id} /></div>
    <section className="topic-module-grid">
      {topic.coreQuestions.length || topic.problemStatement ? <article data-module-id="topic-framework" data-edit-section="questions"><MessagesSquare size={21}/><SectionHeading title="研究对象与核心问题"/><p>{topic.problemStatement}</p><ul>{topic.coreQuestions.slice(0, 4).map(item => <li key={item}>{item}</li>)}</ul><Link href={href("questions")}>深入了解 <ArrowRight size={15}/></Link></article> : null}
      {topic.formationContext || topic.timeline.length ? <article data-module-id="topic-history" data-edit-section="history"><CircleDot size={21}/><SectionHeading title="形成与发展"/><p>{topic.formationContext}</p>{topic.timeline.slice(0, 2).map(([year, title]) => <p key={`${year}-${title}`}><time>{year}</time> {title}</p>)}<Link href={href("history")}>查看时间线 <ArrowRight size={15}/></Link></article> : null}
      {works.length ? <article className="topic-intro-works" data-module-id="topic-works" data-edit-section="works"><BookOpen size={21}/><SectionHeading title="入门阅读"/>{works.slice(0, 3).map(work => <BookCard work={work} dense key={work.id}/>)}<Link href={href("works")}>查看全部 <ArrowRight size={15}/></Link></article> : null}
      {topic.researchDimensions.length ? <article data-edit-section="dimensions"><Grid2X2 size={21}/><SectionHeading title="主要研究维度"/>{topic.researchDimensions.slice(0, 6).map((item, index) => <Link className="knowledge-list-link" href={`${href("dimensions")}#item-${index + 1}`} key={item}>{item}<ArrowRight size={14}/></Link>)}</article> : null}
      {topic.methods.length ? <article data-edit-section="methods"><Wrench size={21}/><SectionHeading title="研究方法 / 工具"/>{topic.methods.slice(0, 6).map((item, index) => <Link className="knowledge-list-link" href={`${href("methods")}#item-${index + 1}`} key={item}>{item}<ArrowRight size={14}/></Link>)}</article> : null}
      {knowledge.length || topic.concepts.length || topic.theories.length ? <article data-module-id="topic-theories" data-edit-section="concepts"><SectionHeading title="理论、概念与争论"/><div className="knowledge-chip-grid">{knowledge.map(row => <Link href={`/theories/nodes/${row.slug}`} key={row.id}>{row.name}</Link>)}{!knowledge.length ? topic.concepts.map(item => <Link href={href("concepts")} key={item}>{item}</Link>) : null}{!knowledge.length ? topic.theories.slice(0, 3).map(row => <Link href={`/theory-schools/${row.slug}`} key={row.slug}>{row.name}</Link>) : null}</div><Link href={href("concepts")}>查看全部 <ArrowRight size={15}/></Link></article> : null}
      {topic.subdisciplines.length ? <article data-module-id="topic-subdisciplines" data-edit-section="relations"><Compass size={21}/><SectionHeading title="相关子学科"/>{topic.subdisciplines.slice(0, 6).map(row => <Link className="knowledge-list-link" href={`/subdisciplines/${row.slug}`} key={row.id}>{row.name}<ArrowRight size={14}/></Link>)}</article> : null}
      {scholars.length ? <article data-module-id="topic-scholars" data-edit-section="relations"><Users size={21}/><SectionHeading title="代表学者"/>{scholars.slice(0, 3).map(row => <Link className="knowledge-person-row" href={`/scholars/${row.slug}`} key={row.slug}><ScholarPortrait scholar={row}/><span><strong>{row.name}</strong><small>{row.years}</small></span><ArrowRight size={14}/></Link>)}<Link href={href("scholars")}>查看全部学者 <ArrowRight size={15}/></Link></article> : null}
    </section>
    {topic.curated.readingPaths.length || hasEvidence ? <section className="topic-bottom-grid">
      {topic.curated.readingPaths.length ? <article data-module-id="topic-reading-paths" data-edit-section="paths"><SectionHeading title="策展阅读路径" href={href("reading-paths")}/><div className="knowledge-path-steps">{topic.curated.readingPaths.slice(0, 4).map((path, index) => <Link href={`${href("reading-paths")}#path-${index + 1}`} key={`${path.title}-${index}`}><b>{String(index + 1).padStart(2, "0")}</b><span><strong>{path.title}</strong><small>{path.description}</small></span></Link>)}</div></article> : null}
      {hasEvidence ? <article data-module-id="topic-evidence" data-edit-section="passages"><SectionHeading title="主题相关原文" href={href("passages")}/>{curatedEvidence ? curatedEvidence.slice(0, 4).map(row => <Link className="knowledge-list-link" href={`${href("passages")}#curated-${row.id || row.source_id}`} key={row.id || row.source_id}>{row.group_title || row.source.work_title}<ArrowRight size={14}/></Link>) : topic.passages.slice(0, 4).map(row => <Link className="knowledge-list-link" href={`${href("passages")}#passage-${row.id}`} key={row.id}>{row.title}<ArrowRight size={14}/></Link>)}</article> : null}
    </section> : null}
  </main>{footer}</>;
}
