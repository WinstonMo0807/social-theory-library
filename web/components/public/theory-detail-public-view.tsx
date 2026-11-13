"use client";

import { DefaultCover } from "@/components/default-cover";
import Link from "next/link";
import { ScholarPortraitFallback } from "@/components/default-scholar-portrait";
import { MediaPlacement } from "@/components/media-placement";
import { ArrowRight, BookOpen, ChevronDown, ExternalLink, FileText } from "lucide-react";
import { useState, type ReactNode } from "react";
import { AskLibraryLink } from "@/components/ask-library-link";
import { CollectionLink } from "@/components/collection-link";
import { EvidenceCurationView } from "@/components/public/evidence-curation-view";
import { CuratedClaimSections } from "@/components/curated-claim-sections";
import { ResponsiveMediaImage } from "@/components/responsive-media-image";
import { nodeTypeLabels, workRoleLabels } from "@/components/theory-system-ui";
import type { KnowledgeNodeDetail, NormalizedReadingPath, NormalizedTimelineEvent, TheoryWorkCompact } from "@/lib/api/knowledge.types";
import { TheoryRelations, TheoryUsageExplorer } from "./theory-detail-interactions";
import { IssueProse } from "./issue-prose";
import { scholarProseBlock } from "@/lib/api/scholar-prose";
import type { NodeProseField } from "@/lib/api/node-editorial";
import styles from "./theory-detail.module.css";

function NodeProse({ node, field, fallback, empty = "", className }: { node: KnowledgeNodeDetail; field: NodeProseField; fallback?: NodeProseField; empty?: string; className?: string }) {
  const selected = node[field] ? field : fallback || field;
  return <IssueProse className={className} block={scholarProseBlock(node[selected] || empty, node.prose?.[selected])}/>;
}

type Props = {
  node: KnowledgeNodeDetail; timeline: NormalizedTimelineEvent[]; paths: NormalizedReadingPath[];
  section?: string; initialCompare?: string; pagination?: ReactNode; actions?: ReactNode;
};
const sectionAlias: Record<string, string> = { concepts: "usages", timeline: "history", propositions: "guide", evidence: "sources", debates: "debates", works: "works", relations: "relations", paths: "paths" };

function WorkRow({ work, compact = false }: { work: TheoryWorkCompact; compact?: boolean }) {
  return <article className={`${styles.workRow} ${compact ? styles.compactWork : ""}`}>
    {work.cover_url ? <MediaPlacement uses={work.cover_media?.display_uses} fallback={<DefaultCover className={styles.workPlaceholder} title={work.title} />}><img src={work.cover_url} alt={`《${work.title}》封面`} loading="lazy" /></MediaPlacement> : <DefaultCover className={styles.workPlaceholder} title={work.title} />}
    <div><h3>{work.detail_href ? <CollectionLink href={work.detail_href}>{work.title}</CollectionLink> : work.title}</h3>{work.subtitle ? <p>{work.subtitle}</p> : null}<small>{[work.author, work.year, work.publisher].filter(value => value !== "" && value !== null).join(" · ")}</small>
      {work.reader_href ? <CollectionLink className={styles.readLink} href={work.reader_href}>阅读原文<ExternalLink size={13} /></CollectionLink> : <><p className={styles.unavailable}>这一版本暂无可读取的原文。</p>{work.detail_href ? <CollectionLink className={styles.readLink} href={work.detail_href}>查看书目与其他版本<ArrowRight size={13} /></CollectionLink> : null}</>}
    </div>
  </article>;
}

function DebateSection({ node }: { node: KnowledgeNodeDetail }) {
  const [filter, setFilter] = useState("all");
  const groups = [
    ["major_criticism", "主要批评"], ["major_response", "主要回应"], ["debate_position", "争论立场"],
  ] as const;
  const claims = groups.flatMap(([key, name]) => (node.curated_claims[key] || []).map(claim => ({ ...claim, group: key, groupLabel: name })));
  const visible = filter === "all" ? claims : claims.filter(claim => claim.group === filter);
  return <section className={styles.section} id="debates" data-module-id="theory-curated-claims"><header className={styles.sectionHeading}><h2>{node.node_type === "theory_tradition" ? "主要分歧与争论" : "争论与回应"}</h2></header>
    {claims.length ? <div className={styles.segmentButtons}><button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>全部（{claims.length}）</button>{groups.filter(([key]) => claims.some(claim => claim.group === key)).map(([key, name]) => <button type="button" key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{name}（{claims.filter(claim => claim.group === key).length}）</button>)}</div> : null}
    <div className={styles.debates}>{visible.map(claim => <section data-content-section key={claim.id}><header data-section-heading><span className={styles.debateSymbol}><BookOpen size={18} /></span><span><strong>{claim.title || claim.groupLabel}</strong><small>{claim.proposition}</small></span><ChevronDown size={16} /></header><div className={styles.debateBody}>
      {claim.editorial_note ? <p>{claim.editorial_note}</p> : null}
      {claim.evidence.length ? claim.evidence.map(evidence => <blockquote key={evidence.id}><p>{evidence.text}</p><cite>《{evidence.source.work_title}》{evidence.locator.printed_page_label ? ` · 印刷页 ${evidence.locator.printed_page_label}` : ` · PDF 第 ${evidence.locator.page} 页`}</cite>{evidence.reader_url ? <Link href={evidence.reader_url} target="_blank" rel="noopener noreferrer">查看依据<ExternalLink size={13} /></Link> : null}</blockquote>) : <p className={styles.notice}>此项尚无可公开读取的原文依据。</p>}
    </div></section>)}</div>{!claims.length ? <p className={styles.empty}>尚无已确认并公开的争论条目。可从相关作品继续核对不同论述。</p> : null}
  </section>;
}

export function TheoryDetailPublicView({ node, timeline, paths, section = "overview", initialCompare = "", pagination, actions }: Props) {
  const tradition = node.node_type === "theory_tradition";
  const current = sectionAlias[section] || section;
  const shown = (...ids: string[]) => section === "overview" || ids.includes(current);
  const allWorks = Object.values(node.work_groups).flatMap(rows => rows.flatMap(row => row.work_data || []));
  const works = [...new Map(allWorks.map(work => [work.id, work])).values()];
  const disciplines = [...new Map([node.primary_discipline, ...node.related_disciplines].flatMap(item => item ? [[item.id, item] as const] : [])).values()];
  const usages = node.public_detail?.usages || [];
  const readingPaths = paths.filter(path => path.items.some(item => item.node_id === node.id));
  const nav = tradition
    ? [["guide", "核心观点与问题"], ["scholars", "代表人物与作品"], ["debates", "主要分歧与争论"], ["paths", "入门路径"], ["relations", "相关与区别的学派"], ["history", "形成与变化"], ["works", "馆藏与知识对象"], ["sources", "原文依据"], ["research", "继续研究"]]
    : [["guide", "概念总览"], ["usages", "不同作者的用法"], ["history", "形成与变化"], ["debates", "争论"], ["relations", "关系与图谱"], ["works", "相关作品"], ["contexts", "语境探索"], ["sources", "原文依据"], ["research", "继续研究"]];
  const base = `/theories/nodes/${encodeURIComponent(node.slug)}`;
  const collectionHref = `/explore/original?${new URLSearchParams(node.node_type === "concept" ? { concept: node.slug } : tradition ? { theory: node.slug } : { q: node.canonical_name_zh })}`;
  const firstReader = usages[0]?.source.reader_url || node.evidence.find(evidence => evidence.reader_href)?.reader_href;
  // Decorative photograph extracted from the final PDF 49, not an example source document.
  const heroImage = node.cover_url || "/images/stl4/theory-detail-final-r2.webp";
  const heroMedia = node.cover_url && node.cover_media?.renditions.length
    ? <MediaPlacement uses={node.cover_media.display_uses} placement="detail"><ResponsiveMediaImage src={heroImage} sources={node.cover_media.renditions} alt={node.cover_media.alt_text || ""} sizes="(max-width: 700px) 100vw, 32vw" loading="eager" /></MediaPlacement>
    : <img src={heroImage} alt="" />;
  const historySection = <section id="history" className={styles.section} data-module-id="theory-development"><header className={styles.sectionHeading}><h2>形成与变化</h2><Link href={`${base}/timeline`}>查看完整脉络<ArrowRight size={15} /></Link></header><div className={styles.timeline}>{timeline.map(event => <article key={event.id}><time>{event.date_label || event.start_year || "时间待确认"}</time><h3><Link href={`/theories/events/${event.id}`}>{event.title}</Link></h3><p>{event.description}</p>{event.reader_href ? <Link href={event.reader_href} target="_blank" rel="noopener noreferrer">核对原文<ExternalLink size={13} /></Link> : null}</article>)}</div>{!timeline.length ? <p className={styles.empty}>尚无已确认并公开的相关事件。</p> : null}</section>;
  const scholarSection = <section className={styles.section} id="scholars" data-module-id="theory-scholars"><header className={styles.sectionHeading}><h2>代表人物{tradition ? "与作品" : ""}</h2></header>
    <div className={styles.people}>{node.representative_scholars.map(person => {
      // Author and work must share a confirmed usage; list order is not an attribution.
      const source = usages.find(usage => usage.author?.id === person.id)?.source;
      const work = source ? works.find(item => item.id === source.work_id) : null;
      return <article key={person.id}>{person.portrait_url ? <MediaPlacement uses={person.portrait_media?.display_uses} fallback={<ScholarPortraitFallback name={person.name} identity={person.scholar_slug || person.id} className={styles.personPlaceholder}/>}><img src={person.portrait_url} alt={person.name} loading="lazy" /></MediaPlacement> : <ScholarPortraitFallback name={person.name} identity={person.scholar_slug || person.id} className={styles.personPlaceholder}/>}
        <div><h3>{person.scholar_slug ? <Link href={`/scholars/${person.scholar_slug}`}>{person.name}</Link> : person.name}</h3>{person.original_name ? <small>{person.original_name}</small> : null}<small>{[person.birth_year, person.death_year].filter(value => value !== null).join(" — ")}</small>{person.relation_label ? <p>{person.relation_label}</p> : null}{work ? <WorkRow work={work} compact /> : person.scholar_slug ? <Link className={styles.readLink} href={`/scholars/${person.scholar_slug}`}>查看人物与著作<ArrowRight size={14} /></Link> : null}</div>
      </article>;
    })}</div>{!node.representative_scholars.length ? <p className={styles.empty}>暂无已确认的代表人物。</p> : null}
  </section>;
  const pathSection = <section className={styles.section} id="paths" data-module-id="theory-reading-paths"><header className={styles.sectionHeading}><h2>{tradition ? "入门路径" : "继续阅读的路径"}</h2><Link href={`${base}/paths`}>查看全部<ArrowRight size={15} /></Link></header>
    {readingPaths.map(path => <article className={styles.readingPath} key={path.id}><header><h3><Link href={`/theories/reading-paths/${path.slug}`}>{path.title}<ArrowRight size={14} /></Link></h3>{path.introduction ? <p>{path.introduction}</p> : null}</header><ol>{path.items.map(item => <li key={item.id}><span>{item.reading_order}</span><div><strong>{path.stages.find(stage => stage.id === item.stage_id)?.name || "阅读步骤"}</strong><p>{item.title}</p>{item.reason ? <p>{item.reason}</p> : null}{item.href ? <Link href={item.href}>查看材料<ArrowRight size={13} /></Link> : <small>来源当前不可用，保留路径位置。</small>}</div></li>)}</ol></article>)}
    {!readingPaths.length ? <p className={styles.empty}>尚无包含本条目的已公开阅读路径。可先从下方相关作品开始。</p> : null}
  </section>;

  return <article data-theory-kind={tradition ? "tradition" : "concept"} className={`${styles.page} ${tradition ? styles.tradition : styles.concept} ${section !== "overview" ? styles.sectionPage : ""}`}>
    <div className={styles.utility}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><Link href="/theories">理论流派</Link><span>›</span><span>{node.canonical_name_zh}</span></nav>
      <div className={styles.heroActions}>{!tradition ? <a className={styles.primary} href={section === "overview" ? "#usages" : `${base}#usages`}>比较两个用法<ArrowRight size={15} /></a> : null}{firstReader ? <Link className={styles.secondary} href={firstReader} target="_blank" rel="noopener noreferrer">查看原文<ExternalLink size={15} /></Link> : null}{actions}</div>
    </div>
    <header className={styles.hero} data-module-id="theory-identity" data-edit-section="identity">
      {!tradition ? <div className={styles.heroMedia}>{heroMedia}</div> : null}
      <div className={styles.heroCopy}><h1>{node.canonical_name_zh}</h1>{node.canonical_name_en ? <p className={styles.foreignName}>{node.canonical_name_en}</p> : null}
        {node.aliases.length ? <section data-content-section className={styles.aliases}><header data-section-heading><span>常见译名</span><strong>{node.aliases.slice(0, 3).map(alias => alias.alias).join(" · ")}</strong><span>更多译名<ChevronDown size={13} /></span></header><div><div className={styles.aliasTable}><table><caption>已收录的译名与别名</caption><thead><tr><th>译名</th><th>使用者与语境</th><th>原文示例</th><th>本页已确认用法</th></tr></thead><tbody>{node.aliases.map(alias => {
          const matches = usages.filter(usage => usage.term.normalize("NFKC").trim().toLocaleLowerCase() === alias.alias.normalize("NFKC").trim().toLocaleLowerCase());
          return <tr key={alias.id}><th scope="row">{alias.alias}<small>{({ "zh-CN": "中文", "zh-TW": "繁体中文", zh: "中文", en: "英语", de: "德语", fr: "法语" } as Record<string, string>)[alias.language] || alias.language || "语言未注明"} · {({ alias: "别名", translation: "译名", abbreviation: "简称", historical: "历史名称", transliteration: "音译" } as Record<string, string>)[alias.alias_type] || "别名"}</small></th><td>{matches.length ? [...new Set(matches.map(usage => [usage.author?.name, usage.context].filter(Boolean).join(" · ")).filter(Boolean))].join("；") || "已关联用法尚未注明语境" : "未收录关联原文"}</td><td>{matches.map(usage => <Link key={usage.id} href={usage.source.reader_url} target="_blank" rel="noopener noreferrer">《{usage.source.work_title}》<ExternalLink size={11} /></Link>)}</td><td>{matches.length}</td></tr>;
        })}</tbody></table></div><p>这里的数量仅为本页已公开的确认用法，不代表全馆出现频次。别名登记不表示不同语境中的含义相同。</p></div></section> : null}
        <div data-module-id="theory-definition"><NodeProse node={node} field="definition" fallback="summary" empty="本条目的说明尚待编辑，已公开关系与馆藏可继续浏览。" className={styles.heroDescription}/></div>
        <div className={styles.tags} data-module-id="theory-disciplines">{!tradition ? <span className={styles.kind}>{nodeTypeLabels[node.node_type] || "理论条目"}</span> : null}{disciplines.map(item => <Link href={`/theories/disciplines/${item.slug}`} key={item.id}>{item.name}</Link>)}{node.topic_links.map(row => <Link href={`/topics/${row.topic.slug}`} key={row.id} data-module-id={row === node.topic_links[0] ? "theory-topics" : undefined}>{row.topic.name}</Link>)}</div>
      </div>
      {tradition ? <aside className={styles.heroGuide}><h2>流派导读</h2><NodeProse node={node} field="summary" fallback="definition" empty="流派导读尚待编辑。"/>{node.period_label ? <small>形成时期 · {node.period_label}</small> : null}</aside> : null}
    </header>
    <div className={styles.readingLayout}>
    <nav className={styles.navigation} aria-label="条目内容">{nav.map(([id, name], index) => <Link key={`${id}-${index}`} href={section === "overview" ? `#${id}` : `${base}#${id}`} aria-current={(current === "overview" && index === 0) || current === id ? "location" : undefined}>{name}</Link>)}</nav>
    <div className={styles.document}>

    {tradition ? <div className={styles.traditionGrid}>
      {shown("guide") ? <section className={styles.section} id="guide" data-module-id="theory-propositions"><header className={styles.sectionHeading}><h2>核心观点与问题</h2></header><div className={styles.propositions} data-module-id="theory-core-questions">{node.basic_propositions.map((proposition, index) => <p key={`${index}-${proposition}`}><BookOpen size={17} /><span>{proposition}</span></p>)}{node.core_questions.map((question, index) => <p key={`question-${index}`}><span className={styles.questionNumber} aria-hidden="true">{String(index + 1).padStart(2, "0")}</span><span>{question}</span></p>)}</div>{!node.basic_propositions.length && !node.core_questions.length ? <p className={styles.empty}>核心观点与问题尚待编辑。</p> : null}{node.theoretical_boundary ? <section data-content-section className={styles.boundary}><header data-section-heading>适用范围与理论边界<ChevronDown size={15} /></header><NodeProse node={node} field="theoretical_boundary"/></section> : null}</section> : null}
      {shown("scholars", "usages") ? <div >{scholarSection}</div> : null}
      {shown("debates") ? <div ><DebateSection node={node} /></div> : null}
      {shown("paths", "works") ? <div >{pathSection}</div> : null}
      {shown("relations", "usages") ? <div ><TheoryRelations node={node} /></div> : null}
    </div> : <div className={styles.conceptLayout}>
      <div className={styles.mainColumn}>
        {shown("usages") ? <TheoryUsageExplorer key={`${node.id}:${node.public_detail?.revision_id || ""}:${usages.map(usage => `${usage.id}:${usage.source.document_revision_id}`).join(",")}`} usages={usages} unavailableCount={node.public_detail?.unavailable_usage_count} initialCompare={initialCompare} /> : null}
        {shown("guide") ? <section id="guide" className={`${styles.section} ${styles.guide}`} data-module-id="theory-propositions"><header className={styles.sectionHeading}><h2>策划导读</h2></header><NodeProse node={node} field="summary" fallback="definition" empty="概念导读尚待编写。"/>
          <dl className={styles.facts}>{node.canonical_name_en ? <div><dt>原文词</dt><dd>{node.canonical_name_en}</dd></div> : null}{node.period_label ? <div><dt>历史时期</dt><dd>{node.period_label}</dd></div> : null}{disciplines.length ? <div><dt>相关学科</dt><dd>{disciplines.map(item => item.name).join("、")}</dd></div> : null}{node.core_questions.length ? <div><dt data-module-id="theory-core-questions">核心问题</dt><dd>{node.core_questions.map(question => <p key={question}>{question}</p>)}</dd></div> : null}</dl>
          {node.basic_propositions.length ? <section data-content-section className={styles.boundary}><header data-section-heading>基本命题<ChevronDown size={15} /></header><ul>{node.basic_propositions.map(proposition => <li key={proposition}>{proposition}</li>)}</ul></section> : null}
          {node.theoretical_boundary ? <section data-content-section className={styles.boundary}><header data-section-heading>适用范围与理论边界<ChevronDown size={15} /></header><NodeProse node={node} field="theoretical_boundary"/></section> : null}
        </section> : null}

        {shown("history") ? historySection : null}
        {shown("debates") ? <DebateSection node={node} /> : null}
        {shown("relations") ? <TheoryRelations node={node} /> : null}
        {shown("contexts") ? <section id="contexts" className={styles.section}><header className={styles.sectionHeading}><h2>语境探索</h2></header><div className={styles.contexts}>{node.topic_links.map(row => <Link href={`/topics/${row.topic.slug}`} key={row.id}><strong>{row.topic.name}</strong>{row.relation_label ? <span>{row.relation_label}</span> : null}<ArrowRight size={17} /></Link>)}{node.subdiscipline_links.map(row => <Link href={`/subdisciplines/${row.subdiscipline.slug}`} key={row.id}><strong>{row.subdiscipline.name}</strong><ArrowRight size={17} /></Link>)}</div>{!node.topic_links.length && !node.subdiscipline_links.length ? <p className={styles.empty}>尚无已确认的主题与学科语境关联。</p> : null}</section> : null}
        {shown("paths") ? pathSection : null}
      </div>
      <aside className={styles.aside}><section><header className={styles.sectionHeading}><h2>相关原文</h2><Link href={`${base}/evidence`}>查看全部<ArrowRight size={14} /></Link></header>{works.slice(0, 3).map(work => <WorkRow key={work.id} work={work} compact />)}{!works.length ? <p className={styles.empty}>尚无已公开的关联馆藏。</p> : null}</section><section className={styles.libraryFacts}><h2>在本书库中</h2><dl><div><dt>相关作品</dt><dd>{node.work_count}</dd></div><div><dt>公开关联</dt><dd>{node.relation_count}</dd></div><div><dt>本页作者用法</dt><dd>{usages.length}</dd></div></dl></section></aside>
    </div>}
    {tradition && shown("history") ? historySection : null}
    {shown("guide", "sources") && node.curated_claims.core_viewpoint.length ? <div className={styles.coreClaims}><CuratedClaimSections groups={{ core_viewpoint: node.curated_claims.core_viewpoint }} /></div> : null}

    {shown("works") ? <section id="works" className={styles.section} data-module-id="theory-works"><header className={styles.sectionHeading}><h2>{tradition ? "馆藏与知识对象" : "相关作品"}</h2><Link href={collectionHref}>在馆藏中查找<ArrowRight size={15} /></Link></header>{Object.entries(node.work_groups).filter(([, rows]) => rows.some(row => row.work_data)).map(([role, rows]) => <div key={role} className={styles.workGroup}><h3>{workRoleLabels[role] || "相关馆藏"}</h3><div className={styles.workGrid}>{rows.map(row => row.work_data ? <WorkRow work={row.work_data} key={row.id} /> : null)}</div></div>)}{!works.length ? <p className={styles.empty}>尚无已确认并公开的关联作品。</p> : null}</section> : null}
    {shown("sources") ? <section id="sources" className={styles.section} data-module-id="theory-evidence"><header className={styles.sectionHeading}><h2>原文依据</h2></header>{node.evidenceCuration?.configured ? <EvidenceCurationView items={node.evidenceCuration.items} /> : node.evidence.length ? <div className={styles.sourceList}>{node.evidence.map(evidence => <article key={evidence.id}><h3>{evidence.work_title}</h3><blockquote>{evidence.quote}</blockquote><p>{evidence.printed_page_label || `PDF 第 ${evidence.page_number}${evidence.page_end && evidence.page_end !== evidence.page_number ? `–${evidence.page_end}` : ""} 页`}</p>{evidence.reader_href ? <Link href={evidence.reader_href} target="_blank" rel="noopener noreferrer">阅读原文<ExternalLink size={14} /></Link> : null}</article>)}</div> : <p className={styles.empty}>暂未提供可公开定位的原文。书目仍可在相关作品中核对。<Link href={`/feedback?category=content&path=${encodeURIComponent(base)}`}>反馈原文线索</Link></p>}</section> : null}
    {pagination ? <div className={styles.pagination}>{pagination}</div> : null}
    {shown("research") ? <section id="research" className={`${styles.section} ${styles.research}`}><div><h2>继续研究</h2><p>从相关馆藏继续查找，保留版本、页码与原文依据。</p></div><AskLibraryLink context="theories" ids={[node.id]} label={`围绕${node.canonical_name_zh}询问书库`} className={styles.secondary} /><Link className={styles.secondary} href={collectionHref}>检索相关馆藏<ArrowRight size={15} /></Link></section> : null}
    </div>
    </div>
  </article>;
}
