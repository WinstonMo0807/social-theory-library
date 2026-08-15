import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, CalendarDays, CheckCircle2, ExternalLink, Network, UsersRound } from "lucide-react";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import {
  TheoryBanner,
  TheorySectionHeading,
  WorkCompactCard,
  nodeTypeLabels,
  workRoleLabels,
} from "@/components/theory-system-ui";
import { loadKnowledgeNode, loadNormalizedReadingPaths, loadNormalizedTheoryTimeline } from "@/lib/server-api";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const node = await loadKnowledgeNode(slug);
  return { title: node?.canonical_name_zh || "理论条目", description: node?.summary || node?.definition || "理论条目详情" };
}

export default async function KnowledgeNodePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const [node, timeline, allPaths] = await Promise.all([
    loadKnowledgeNode(slug),
    loadNormalizedTheoryTimeline({ node: slug }),
    loadNormalizedReadingPaths(),
  ]);
  if (!node) notFound();
  const readingPaths = allPaths.filter((path) => path.items.some((item) => item.node_data?.id === node.id));
  const groupedWorks = Object.entries(node.work_groups).filter(([, rows]) => rows.length);
  const disciplineLinks = [node.primary_discipline, ...node.related_disciplines].filter(Boolean);

  return (
    <>
      <main className="page-shell theory-system-page theory-node-page">
        <div className="theory-breadcrumb">
          <Link href="/theories">理论流派</Link><span>/</span>
          {node.primary_discipline ? <><Link href={`/theories/disciplines/${node.primary_discipline.slug}`}>{node.primary_discipline.name}</Link><span>/</span></> : null}
          <strong>{node.canonical_name_zh}</strong>
        </div>

        <section className="theory-node-hero">
          <div className="theory-node-intro">
            <p className="eyebrow">{nodeTypeLabels[node.node_type]}</p>
            <h1>{node.canonical_name_zh}</h1>
            {node.canonical_name_en ? <h2>{node.canonical_name_en}</h2> : null}
            {disciplineLinks.length ? <div className="theory-discipline-pills">{disciplineLinks.map((discipline, index) => discipline ? <Link className={index === 0 ? "primary" : ""} href={`/theories/disciplines/${discipline.slug}`} key={discipline.id}>{discipline.name}</Link> : null)}</div> : null}
            {node.definition || node.summary ? <p className="definition">{node.definition || node.summary}</p> : null}
            {node.core_questions.length ? <div className="theory-core-question"><strong>核心问题</strong><p>{node.core_questions[0]}</p></div> : null}
          </div>
          <div className="theory-node-hero-side">
            <TheoryBanner image={node.cover_url} />
            <dl>
              {node.representative_scholars.length ? <><dt><UsersRound size={17} />代表学者</dt><dd>{node.representative_scholars.map((person) => person.scholar_slug ? <Link href={`/scholars/${person.scholar_slug}`} key={person.id}>{person.name}</Link> : <span key={person.id}>{person.name}</span>)}</dd></> : null}
              {node.period_label ? <><dt><CalendarDays size={17} />形成时期</dt><dd>{node.period_label}</dd></> : null}
              {node.work_count ? <><dt><BookOpen size={17} />馆藏数量</dt><dd>{node.work_count.toLocaleString("zh-CN")} 部文献</dd></> : null}
              <dt><CheckCircle2 size={17} />审核状态</dt><dd>已审核并公开</dd>
              <dt><CalendarDays size={17} />最近编辑</dt><dd>{new Date(node.updated_at).toLocaleDateString("zh-CN")}</dd>
            </dl>
          </div>
        </section>

        {(node.basic_propositions.length || node.theoretical_boundary) ? <section className="theory-node-foundations">
          {node.basic_propositions.length ? <article><TheorySectionHeading title="基本命题" /> <ol>{node.basic_propositions.slice(0, 5).map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ol></article> : null}
          {node.theoretical_boundary ? <article><TheorySectionHeading title="理论边界" /><p>{node.theoretical_boundary}</p></article> : null}
        </section> : null}

        {timeline.length ? <section className="theory-node-development">
          <TheorySectionHeading title="形成与发展" href={`/theories/timeline?node=${encodeURIComponent(slug)}`} action="查看完整时间轴" />
          <div>{timeline.slice(0, 6).map((event) => <Link href={`/theories/timeline?q=${encodeURIComponent(event.title)}`} key={event.id}><i /><time>{event.date_label || event.start_year}</time><strong>{event.title}</strong><small>{event.description}</small></Link>)}</div>
        </section> : null}

        {node.direct_relations.length ? <section className="theory-node-relations">
          <TheorySectionHeading title="与其他理论的关系" href={`/theories/graph?center=${encodeURIComponent(slug)}`} action="打开局部图谱" />
          <div>{node.direct_relations.map((relation) => {
            const outgoing = relation.source_node === node.id;
            const target = outgoing ? { name: relation.target_name, slug: relation.target_slug } : { name: relation.source_name, slug: relation.source_slug };
            return <Link href={`/theories/nodes/${target.slug}`} key={relation.id}><span className="relation-mark"><Network size={20} /></span><span><small>{relation.relation_label}</small><strong>{target.name}</strong><p>{relation.description}</p></span><ArrowRight size={18} /></Link>;
          })}</div>
        </section> : null}

        {groupedWorks.length ? <section className="theory-node-works">
          <TheorySectionHeading title="馆藏文献" href={`/explore?theory=${encodeURIComponent(node.slug)}`} action={`查看全部 ${node.work_count} 部`} />
          {groupedWorks.map(([role, relations]) => <article key={role}><h3>{workRoleLabels[role] || role}</h3><div>{relations.map((relation) => relation.work_data ? <WorkCompactCard key={relation.id} work={relation.work_data} /> : null)}</div></article>)}
        </section> : null}

        {node.evidence.length ? <section className="theory-node-evidence">
          <TheorySectionHeading title="馆藏证据" />
          <div className="theory-evidence-table" role="table" aria-label="馆藏文献与理论关系证据">
            <header role="row"><span>书名</span><span>关系类型</span><span>页码范围</span><span>原文证据</span><span>操作</span></header>
            {node.evidence.map((evidence) => <div role="row" key={evidence.id}><strong>{evidence.work_title}</strong><span>{workRoleLabels[evidence.relation_role] || evidence.relation_role}</span><span>{evidence.printed_page_label || `PDF ${evidence.page_number}${evidence.page_end && evidence.page_end !== evidence.page_number ? `–${evidence.page_end}` : ""} 页`}</span><p>{evidence.quote}</p><Link href={evidence.reader_href}>进入阅读器<ExternalLink size={14} /></Link></div>)}
          </div>
        </section> : null}

        {readingPaths.length ? <section className="theory-node-reading-order">
          <TheorySectionHeading title="推荐阅读顺序" />
          {readingPaths.map((path) => <article key={path.id}><header><Link href={`/theories/reading-paths/${path.slug}`}>{path.title}<ArrowRight size={17} /></Link><p>{path.introduction}</p></header><ol>{path.items.map((item) => <li key={item.id}><b>{item.reading_order}</b><span><strong>{item.stage_name}</strong><small>{item.work_data?.title || item.node_data?.canonical_name_zh || item.stage_description}</small></span></li>)}</ol></article>)}
        </section> : null}
      </main>
      <SiteFooter />
    </>
  );
}
