import Link from "next/link";
import { ArrowRight, BookOpen, CalendarDays, CheckCircle2, ExternalLink, Network, UsersRound } from "lucide-react";
import type { ReactNode } from "react";
import { AskLibraryLink } from "@/components/ask-library-link";
import { CuratedClaimSections } from "@/components/curated-claim-sections";
import { EvidenceCurationView } from "@/components/public/evidence-curation-view";
import {
  TheoryBanner,
  TheorySectionHeading,
  WorkCompactCard,
  nodeTypeLabels,
  workRoleLabels,
} from "@/components/theory-system-ui";
import type { loadKnowledgeNode, loadNormalizedReadingPaths, loadNormalizedTheoryTimeline } from "@/lib/api/knowledge.server";

type KnowledgeNodePayload = NonNullable<Awaited<ReturnType<typeof loadKnowledgeNode>>>;
type ReadingPathPayload = Awaited<ReturnType<typeof loadNormalizedReadingPaths>>;
type TimelinePayload = Awaited<ReturnType<typeof loadNormalizedTheoryTimeline>>;

export function KnowledgeNodePublicView({
  node,
  timeline,
  allPaths,
  slug,
  footer,
  publicationStatusLabel = "已审核并公开",
  section = "overview",
  pagination,
}: {
  node: KnowledgeNodePayload;
  timeline: TimelinePayload;
  allPaths: ReadingPathPayload;
  slug: string;
  footer: ReactNode;
  publicationStatusLabel?: string;
  section?: string;
  pagination?: ReactNode;
}) {
  const readingPaths = allPaths.filter((path) => path.items.some((item) => item.node_data?.id === node.id));
  const groupedWorks = Object.entries(node.work_groups).filter(([, rows]) => rows.length);
  const disciplineLinks = [node.primary_discipline, ...node.related_disciplines].filter(Boolean);
  const subdisciplines = (node.subdiscipline_links ?? []).map((row) => row.subdiscipline);
  const topics = (node.topic_links ?? []).map((row) => row.topic);

  return (
    <>
      <main className={`page-shell theory-system-page theory-node-page v307-knowledge theory-v307 ${section !== "overview" ? "knowledge-section-page" : ""}`}>
        <div className="theory-breadcrumb">
          <Link href="/theories">理论流派</Link><span>/</span>
          {node.primary_discipline ? <><Link href={`/theories/disciplines/${node.primary_discipline.slug}`}>{node.primary_discipline.name}</Link><span>/</span></> : null}
          <strong>{node.canonical_name_zh}</strong>
        </div>

        <section className="theory-node-hero" data-module-id="theory-identity" data-edit-section="identity">
          <div className="theory-node-intro">
            <p className="eyebrow">{nodeTypeLabels[node.node_type]}</p>
            <h1>{node.canonical_name_zh}</h1>
            {section !== "overview" ? <h2>{({timeline: "流派脉络", concepts: "概念与人物", works: "代表作品与阅读路径", evidence: "相关原文", relations: "学术关系", propositions: "基本命题与理论边界"} as Record<string, string>)[section]}</h2> : null}
            {node.canonical_name_en ? <h2>{node.canonical_name_en}</h2> : null}
            {disciplineLinks.length ? <div className="theory-discipline-pills" data-module-id="theory-disciplines">{disciplineLinks.map((discipline, index) => discipline ? <Link className={index === 0 ? "primary" : ""} href={`/theories/disciplines/${discipline.slug}`} key={discipline.id}>{discipline.name}</Link> : null)}</div> : null}
            {subdisciplines.length ? <div className="theory-discipline-pills" data-module-id="theory-disciplines" aria-label="规范子学科">
              {subdisciplines.map((item) => <Link href={`/subdisciplines/${item.slug}`} key={`subdiscipline-${item.id}`}>{item.name}</Link>)}
            </div> : null}
            {topics.length ? <div className="theory-discipline-pills" data-module-id="theory-topics" aria-label="规范研究主题">
              {topics.map((item) => <Link href={`/topics/${item.slug}`} key={`topic-${item.id}`}>{item.name}</Link>)}
            </div> : null}
            {node.definition || node.summary ? <p className="definition" data-module-id="theory-definition">{node.definition || node.summary}</p> : null}
            {node.core_questions.length ? <div className="theory-core-question" data-module-id="theory-core-questions"><strong>{node.node_type === "debate" ? "争论问题" : "核心问题"}</strong><p>{node.core_questions[0]}</p></div> : null}
            <AskLibraryLink context="theories" ids={[node.id]} label={`询问关于${node.canonical_name_zh}的馆藏`} />
          </div>
          <div className="theory-node-hero-side">
            <TheoryBanner image={node.cover_url} media={node.cover_media} />
            <dl>
              {node.representative_scholars.length ? <><dt data-module-id="theory-scholars"><UsersRound size={17} />代表学者</dt><dd>{node.representative_scholars.map((person) => person.scholar_slug ? <Link href={`/scholars/${person.scholar_slug}`} key={person.id}>{person.name}</Link> : <span key={person.id}>{person.name}</span>)}</dd></> : null}
              {node.period_label ? <><dt><CalendarDays size={17} />形成时期</dt><dd>{node.period_label}</dd></> : null}
              {node.work_count ? <><dt><BookOpen size={17} />馆藏数量</dt><dd>{node.work_count.toLocaleString("zh-CN")} 部文献</dd></> : null}
              <dt><CheckCircle2 size={17} />审核状态</dt><dd>{publicationStatusLabel}</dd>
              {node.updated_at ? <><dt><CalendarDays size={17} />最近编辑</dt><dd>{new Date(node.updated_at).toLocaleDateString("zh-CN")}</dd></> : null}
            </dl>
          </div>
        </section>

        {section === "overview" && node.node_type === "theory_tradition" ? <section className="knowledge-section"><TheorySectionHeading title={`深入了解${node.canonical_name_zh}`} /><div className="knowledge-three-grid">{[{id: "timeline", title: "流派脉络", text: "沿真实事件与来源，了解形成与发展。"}, {id: "concepts", title: "概念与人物", text: "从核心概念、相关人物与学术关系继续。"}, {id: "works", title: "代表作品与阅读路径", text: "回到馆藏文献，沿策展路径深入阅读。"}].map(item => <Link className="knowledge-entry-card" href={`/theories/nodes/${slug}/${item.id}`} key={item.id}><TheoryBanner image={node.cover_url} media={node.cover_media}/><h2>{item.title}</h2><p>{item.text}</p><span>进入页面 <ArrowRight size={16}/></span></Link>)}</div></section> : null}
        {(section === "propositions" || (section === "overview" && node.node_type !== "theory_tradition")) && (node.basic_propositions.length || node.theoretical_boundary) ? <section className="theory-node-foundations" data-module-id="theory-propositions" data-edit-section="content">
          {node.basic_propositions.length ? <article><TheorySectionHeading title="基本命题" /> <ol>{node.basic_propositions.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ol></article> : null}
          {node.theoretical_boundary ? <article><TheorySectionHeading title="理论边界" /><p>{node.theoretical_boundary}</p></article> : null}
        </section> : null}

        {section === "evidence" ? <div data-module-id="theory-curated-claims">{node.evidenceCuration?.configured ? <EvidenceCurationView items={node.evidenceCuration.items} /> : <CuratedClaimSections groups={node.curated_claims} debate={node.node_type === "debate"} />}</div> : null}

        {section === "timeline" && timeline.length ? <section className="theory-node-development" data-module-id="theory-development" data-edit-section="timeline">
          <TheorySectionHeading title="形成与发展" href={`/theories/timeline?node=${encodeURIComponent(slug)}`} action="查看完整时间轴" />
          <div>{timeline.map((event) => <Link href={`/theories/events/${event.id}`} key={event.id}><i /><time>{event.date_label || event.start_year}</time><strong>{event.title}</strong><small>{event.description}</small></Link>)}</div>
        </section> : null}

        {["concepts", "relations"].includes(section) && node.direct_relations.length ? <section className="theory-node-relations" data-module-id="theory-relations" data-edit-section="relations">
          <TheorySectionHeading title="与其他理论的关系" href={`/theories/graph?center=${encodeURIComponent(slug)}`} action="打开局部图谱" />
          <div>{node.direct_relations.map((relation) => {
            const outgoing = relation.source_node === node.id;
            const target = outgoing ? { name: relation.target_name, slug: relation.target_slug } : { name: relation.source_name, slug: relation.source_slug };
            return <Link href={`/theories/nodes/${target.slug}`} key={relation.id}><span className="relation-mark"><Network size={20} /></span><span><small>{relation.relation_label}</small><strong>{target.name}</strong><p>{relation.description}</p></span><ArrowRight size={18} /></Link>;
          })}</div>
        </section> : null}

        {["overview", "concepts"].includes(section) && node.representative_scholars.length ? <section id="scholars" className="knowledge-section" data-edit-section="relations"><TheorySectionHeading title="代表学者"/><div className="knowledge-person-grid">{node.representative_scholars.map(person => <article key={person.id}>{person.portrait_url ? <img src={person.portrait_url} alt={person.name} loading="lazy"/> : null}<span>{person.scholar_slug ? <Link href={`/scholars/${person.scholar_slug}`}>{person.name}</Link> : <strong>{person.name}</strong>}<small>{[person.birth_year, person.death_year].filter(Boolean).join(" — ")}</small><p>{person.relation_label}</p></span></article>)}</div></section> : null}
        {["overview", "works"].includes(section) && groupedWorks.length ? <section className="theory-node-works" data-module-id="theory-works" data-edit-section="works">
          <TheorySectionHeading title="馆藏文献" href={`/explore?theory=${encodeURIComponent(node.slug)}`} action={`查看全部 ${node.work_count} 部`} />
          {(section === "overview" ? groupedWorks.slice(0, 1) : groupedWorks).map(([role, relations]) => <article key={role}>{section !== "overview" ? <h3>{workRoleLabels[role] || role}</h3> : null}<div>{(section === "overview" ? relations.slice(0, 4) : relations).map((relation) => relation.work_data ? <WorkCompactCard key={relation.id} work={relation.work_data} /> : null)}</div></article>)}
        </section> : null}

        {section === "evidence" && !node.evidenceCuration?.configured && node.evidence.length ? <section className="theory-node-evidence" data-module-id="theory-evidence">
          <TheorySectionHeading title="馆藏证据" />
          <div className="theory-evidence-table" role="table" aria-label="馆藏文献与理论关系证据">
            <header role="row"><span role="columnheader">书名</span><span role="columnheader">关系类型</span><span role="columnheader">页码范围</span><span role="columnheader">原文证据</span><span role="columnheader">操作</span></header>
            {node.evidence.map((evidence) => <div role="row" key={evidence.id}>
              <strong role="cell" data-label="书名">{evidence.work_title}</strong>
              <span role="cell" data-label="关系类型">{workRoleLabels[evidence.relation_role] || evidence.relation_role}</span>
              <span role="cell" data-label="页码范围">{evidence.printed_page_label || `PDF ${evidence.page_number}${evidence.page_end && evidence.page_end !== evidence.page_number ? `–${evidence.page_end}` : ""} 页`}</span>
              <p role="cell" data-label="原文证据">{evidence.quote}</p>
              <div role="cell"><Link href={evidence.reader_href}>阅读原文<ExternalLink size={14} /></Link></div>
            </div>)}
          </div>
        </section> : null}

        {section === "works" && readingPaths.length ? <section className="theory-node-reading-order" data-module-id="theory-reading-paths" data-edit-section="paths">
          <TheorySectionHeading title="推荐阅读顺序" />
          {readingPaths.map((path) => <article key={path.id}><header><Link href={`/theories/reading-paths/${path.slug}`}>{path.title}<ArrowRight size={17} /></Link><p>{path.introduction}</p></header><ol>{path.items.map((item) => <li key={item.id}><b>{item.reading_order}</b><span><strong>{item.stage_name}</strong><small>{item.work_data?.title || item.node_data?.canonical_name_zh || item.stage_description}</small></span></li>)}</ol></article>)}
        </section> : null}
        {pagination}
        {section === "timeline" && !timeline.length ? <p className="empty-state">尚无已确认并公开的相关事件。</p> : null}
        {section === "works" && !groupedWorks.length && !readingPaths.length ? <p className="empty-state">尚无已确认并公开的相关馆藏与阅读路径。</p> : null}
        {section === "propositions" && !node.basic_propositions.length && !node.theoretical_boundary ? <p className="empty-state">基本命题与理论边界尚待编辑。</p> : null}
        {section === "relations" && !node.direct_relations.length ? <p className="empty-state">尚无已确认并公开的学术关系。</p> : null}
        <nav className="knowledge-section-nav"><Link href={`/theories/nodes/${slug}`}>返回条目总览</Link><Link href={`/theories/nodes/${slug}/timeline`}>流派脉络</Link><Link href={`/theories/nodes/${slug}/concepts`}>概念与人物</Link><Link href={`/theories/nodes/${slug}/works`}>作品与阅读路径</Link><Link href={`/theories/nodes/${slug}/propositions`}>基本命题与边界</Link><Link href={`/theories/nodes/${slug}/evidence`}>相关原文</Link><Link href={`/theories/graph?center=${encodeURIComponent(slug)}`}>打开完整图谱</Link></nav>
      </main>
      {footer}
    </>
  );
}
