import Link from "next/link";
import { ArrowRight, BookOpen, ChevronDown, ExternalLink, UserRound } from "lucide-react";
import { CollectionLink } from "@/components/collection-link";
import type { ApiTheorySchool } from "@/lib/api/theories.types";
import type { ApiWork } from "@/lib/api/public-catalog";
import { adaptApiWork } from "@/lib/public-data-adapters";
import styles from "./theory-detail.module.css";
import legacyStyles from "./legacy-theory-public-view.module.css";

const relationLabels: Record<string, string> = {
  influence: "影响", continuation: "继承", split: "分化",
  critique: "批评", synthesis: "综合", adjacent: "相邻",
};

function WorkRow({ value, compact = false }: { value: ApiWork; compact?: boolean }) {
  const work = adaptApiWork(value);
  return <article className={`${styles.workRow} ${compact ? styles.compactWork : ""}`}>
    {work.coverImage
      ? <img src={work.coverImage} alt={work.coverAlt || `《${work.title}》封面`} loading="lazy" />
      : <div className={styles.workPlaceholder} aria-label="尚无封面"><BookOpen size={22} /></div>}
    <div>
      <h3><CollectionLink href={`/works/${work.slug}`}>《{work.title}》</CollectionLink></h3>
      <p>{work.author}</p><small>{work.year} · {work.kind}</small>
      {work.readerHref
        ? <Link className={styles.readLink} href={work.readerHref} target="_blank" rel="noopener noreferrer">阅读原文<ExternalLink size={12} /></Link>
        : <CollectionLink className={styles.readLink} href={`/works/${work.slug}`}>查看书目<ArrowRight size={12} /></CollectionLink>}
    </div>
  </article>;
}

function RelationRows({ entity, rows }: {
  entity: ApiTheorySchool; rows: ApiTheorySchool["relations"];
}) {
  return <div className={legacyStyles.relations}>{rows.map(relation => <article key={relation.id}>
    <Link href={`/theory-schools/${encodeURIComponent(relation.theory.slug)}`}>
      <strong>{relation.theory.name}</strong>
      <span>{relationLabels[relation.relation_type] || "已确认关系"}</span><ArrowRight size={14} />
    </Link>
    <p>{relation.direction === "incoming"
      ? `${relation.theory.name} → ${entity.name}`
      : `${entity.name} → ${relation.theory.name}`}</p>
  </article>)}</div>;
}

// This remains a TheorySchool presentation. Only an explicit backend mapping may
// redirect it to a KnowledgeNode; its legacy ID must never enter node mutations.
export function LegacyTheoryPublicView({ entity }: { entity: ApiTheorySchool }) {
  const base = `/theory-schools/${encodeURIComponent(entity.slug)}`;
  const works = entity.works || [];
  const scholars = entity.scholars || [];
  const curated = entity.curated;
  const readingWorks = curated?.curated_reading_works.length
    ? curated.curated_reading_works : curated?.foundational_works || [];
  const supplementalScholars = (curated?.key_scholars || []).filter(
    person => !scholars.some(scholar => scholar.slug === person.slug),
  );
  const critiques = entity.relations.filter(relation => relation.relation_type === "critique");
  const related = entity.relations.filter(relation => relation.relation_type !== "critique");
  const relatedIds = new Set(entity.relations.map(relation => relation.theory.id));
  const curatedNeighbors = (curated?.neighbors || []).filter(neighbor => !relatedIds.has(neighbor.id));
  const nav = [
    ["overview", "概览"], ["scholars", "代表人物与作品"], ["debates", "主要分歧与争论"],
    ["paths", "入门书目"], ["relations", "相关与区别的学派"], ["works", "馆藏与知识对象"],
  ];

  return <article className={`${styles.page} ${styles.tradition} ${legacyStyles.page}`}>
    <nav className={styles.breadcrumb} aria-label="面包屑">
      <Link href="/home">首页</Link><span>›</span><Link href="/theories">理论流派</Link><span>›</span><span>{entity.name}</span>
    </nav>
    <p className={legacyStyles.editorialNotice}>条目正在整理，已公开资料仍可阅读</p>
    <header className={`${styles.hero} ${legacyStyles.hero}`}>
      <div className={`${styles.heroCopy} ${legacyStyles.heroCopy}`} id="overview">
        <span className={styles.kind}>{entity.entity_level === "branch" ? "理论分支" : entity.entity_level === "school" ? "理论流派" : "理论传统"}</span>
        <h1>{entity.name}</h1>
        {entity.foreign_name ? <p className={styles.foreignName}>{entity.foreign_name}</p> : null}
        <p className={styles.heroDescription}>{entity.description || "本条目的概述尚待编辑。"}</p>
        <div className={styles.tags}>
          {entity.key_themes.map((theme, index) => <Link key={`${theme}-${index}`} href={`/explore?q=${encodeURIComponent(theme)}`}>{theme}</Link>)}
        </div>
      </div>
      <aside className={`${styles.heroGuide} ${legacyStyles.heroGuide}`}>
        <h2>流派导读</h2>
        <p>{curated?.hero_caption || entity.description || "可从已公开的人物与馆藏开始阅读。"}</p>
        {entity.formation_period ? <small>形成时期 · {entity.formation_period}</small> : null}
        {entity.disciplines.length ? <small>相关学科 · {entity.disciplines.map(item => item.name).join("、")}</small> : null}
      </aside>
    </header>
    <nav className={`${styles.navigation} ${legacyStyles.navigation}`} aria-label="条目内容">
      {nav.map(([id, title]) => <a href={`#${id}`} key={id}>{title}</a>)}
    </nav>

    <div className={`${styles.traditionGrid} ${legacyStyles.body}`}>
      <section className={`${styles.section} ${styles.peopleArea}`} id="scholars">
        <header className={styles.sectionHeading}><h2>代表人物与作品</h2><Link href={`${base}/scholars`}>查看全部<ArrowRight size={14} /></Link></header>
        <div className={styles.people}>
          {scholars.map(scholar => {
            const person = scholar.person;
            const work = works.find(value => value.edition?.contributors.some(
              contributor => contributor.role === "author" && contributor.person.id === person.id,
            ));
            return <article key={scholar.slug}>
              {person.portrait
                ? <img src={person.portrait} alt={person.preferred_name} loading="lazy" />
                : <div className={styles.personPlaceholder} aria-label="尚无肖像"><UserRound size={32} /></div>}
              <div>
                <h3><Link href={`/scholars/${scholar.slug}`}>{person.preferred_name}</Link></h3>
                {person.original_name ? <small>{person.original_name}</small> : null}
                <small>{[person.birth_year, person.death_year].filter(value => value != null).join(" — ")}</small>
                {scholar.short_description ? <p>{scholar.short_description}</p> : null}
                {work ? <WorkRow value={work} compact /> : <Link className={styles.readLink} href={`/scholars/${scholar.slug}`}>查看人物与著作<ArrowRight size={12} /></Link>}
              </div>
            </article>;
          })}
          {supplementalScholars.map(person => <article key={person.id}>
            <div className={styles.personPlaceholder} aria-label="尚无肖像"><UserRound size={32} /></div>
            <div><h3><Link href={`/scholars/${person.slug}`}>{person.name}</Link></h3><Link className={styles.readLink} href={`/scholars/${person.slug}`}>查看人物与著作<ArrowRight size={12} /></Link></div>
          </article>)}
        </div>
        {!scholars.length && !supplementalScholars.length ? <p className={styles.empty}>尚无已确认并公开的代表人物。</p> : null}
      </section>
      <section className={`${styles.section} ${styles.questionsArea}`} id="questions">
        <header className={styles.sectionHeading}><h2>核心观点与问题</h2></header>
        <div className={styles.propositions}>{entity.core_questions.map((question, index) => <p key={`${question}-${index}`}><span className={styles.questionMark}>?</span><span>{question}</span></p>)}</div>
        {!entity.core_questions.length ? <p className={styles.empty}>核心问题尚待编辑。</p> : null}
        <Link className={styles.readLink} href={`${base}/concepts`}>浏览核心概念<ArrowRight size={14} /></Link>
      </section>
      <section className={`${styles.section} ${styles.debatesArea}`} id="debates">
        <header className={styles.sectionHeading}><h2>主要分歧与争论</h2></header>
        <div className={styles.debates}>{critiques.map(relation => <section data-content-section key={relation.id}>
          <header data-section-heading><span className={styles.debateSymbol}><BookOpen size={18} /></span><strong>{relation.theory.name}<small>已确认的批评关系</small></strong><ChevronDown size={15} /></header>
          <div className={styles.debateBody}>
            <p>{relation.direction === "incoming" ? relation.theory.name : entity.name} → {relation.direction === "incoming" ? entity.name : relation.theory.name}</p>
            <p className={styles.notice}>本页暂未提供可核对版本与页码的争论原文。</p>
            <Link href={`/theory-schools/${encodeURIComponent(relation.theory.slug)}`}>查看{relation.theory.name}<ArrowRight size={14} /></Link>
          </div>
        </section>)}</div>
        {!critiques.length ? <p className={styles.empty}>尚无已确认并公开的争论关系。</p> : null}
      </section>
      <section className={`${styles.section} ${styles.pathsArea}`} id="paths">
        <header className={styles.sectionHeading}><h2>入门书目</h2><Link href={`${base}/reading-list`}>查看全部<ArrowRight size={14} /></Link></header>
        {readingWorks.length ? <article className={styles.readingPath}><ol>{readingWorks.map((value, index) => <li key={value.id}><span>{index + 1}</span><div><WorkRow value={value} compact /></div></li>)}</ol></article> : <p className={styles.empty}>入门书目尚待整理。可从下方关联馆藏继续阅读。</p>}
      </section>
      <section className={`${styles.section} ${styles.relationsArea}`} id="relations">
        <header className={styles.sectionHeading}><h2>相关与区别的学派</h2><Link href="/theory-schools/graph">查看图谱<ArrowRight size={14} /></Link></header>
        <section data-content-section className={legacyStyles.relationGroup}>
          <header data-section-heading>相关学派（{related.length + curatedNeighbors.length}）<ChevronDown size={14} /></header>
          <RelationRows entity={entity} rows={related} />
          <div className={legacyStyles.relations}>{curatedNeighbors.map(neighbor => <article key={neighbor.id}>
            <Link href={`/theory-schools/${encodeURIComponent(neighbor.slug)}`}><strong>{neighbor.name}</strong><span>策展关联</span><ArrowRight size={14} /></Link>
            {neighbor.description ? <p>{neighbor.description}</p> : null}
          </article>)}</div>
          {!related.length && !curatedNeighbors.length ? <p className={styles.empty}>尚无已确认并公开的相关学派。</p> : null}
        </section>
        <section data-content-section className={legacyStyles.relationGroup}>
          <header data-section-heading>区别与批评（{critiques.length}）<ChevronDown size={14} /></header>
          <RelationRows entity={entity} rows={critiques} />
          {!critiques.length ? <p className={styles.empty}>尚无已确认并公开的批评关系。</p> : null}
        </section>
      </section>
    </div>

    {entity.timeline.length ? <section className={`${styles.section} ${legacyStyles.secondarySection}`} id="history">
      <header className={styles.sectionHeading}><h2>历史发展</h2><Link href="/theory-schools/timeline">浏览历史时间轴<ArrowRight size={14} /></Link></header>
      <div className={styles.timeline}>{entity.timeline.map(event => <article key={event.id}>
        <time>{event.date_label || [event.start_year, event.end_year].filter(value => value !== null).join(" — ") || "时期待考"}</time><h3>{event.title}</h3><p>{event.description}</p>
      </article>)}</div>
    </section> : null}
    <section className={`${styles.section} ${legacyStyles.secondarySection}`} id="works">
      <header className={styles.sectionHeading}><h2>馆藏与知识对象</h2><Link href={`${base}/works`}>查看全部文献<ArrowRight size={14} /></Link></header>
      <div className={styles.workGrid}>{works.map(value => <WorkRow value={value} key={value.id} />)}</div>
      {!works.length ? <p className={styles.empty}>尚无已公开的关联馆藏。</p> : null}
      {!!curated?.foundational_works.length ? <div className={styles.workGroup}><h3>奠基文献</h3><div className={styles.workGrid}>{curated.foundational_works.map(value => <WorkRow value={value} key={value.id} />)}</div></div> : null}
    </section>
    {(entity.hierarchy.parents.length || entity.hierarchy.branches.length || entity.subdisciplines.length) ? <section className={`${styles.section} ${legacyStyles.secondarySection}`}>
      <header className={styles.sectionHeading}><h2>谱系与相关领域</h2></header>
      <div className={styles.contexts}>
        {entity.hierarchy.parents.map(item => <Link href={`/theory-schools/${encodeURIComponent(item.slug)}`} key={`parent-${item.id}`}><strong>{item.name}</strong><span>上位传统</span><ArrowRight size={15} /></Link>)}
        {entity.hierarchy.branches.map(item => <Link href={`/theory-schools/${encodeURIComponent(item.slug)}`} key={`branch-${item.id}`}><strong>{item.name}</strong><span>理论分支</span><ArrowRight size={15} /></Link>)}
        {entity.subdisciplines.map(item => <Link href={`/subdisciplines/${encodeURIComponent(item.slug)}`} key={`discipline-${item.id}`}><strong>{item.name}</strong><span>相关子学科</span><ArrowRight size={15} /></Link>)}
      </div>
    </section> : null}
    <nav className={styles.mobileNavigation} aria-label="详情快捷导航">
      <a href="#overview">流派概览</a><a href="#scholars">人物与作品</a><a href="#relations">相关学派</a><a href="#works">馆藏</a>
    </nav>
  </article>;
}
