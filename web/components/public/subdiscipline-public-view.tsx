import Image from "next/image";
import Link from "next/link";
import { MediaPlacement } from "@/components/media-placement";
import { ArrowRight, BookOpen, ExternalLink, FileText } from "lucide-react";
import type { ReactNode } from "react";
import type { loadSubdiscipline } from "@/lib/api/taxonomy.server";
import type { SubdisciplineSource } from "@/lib/api/taxonomy.types";
import styles from "./subdiscipline.module.css";

type SubdisciplinePayload = NonNullable<Awaited<ReturnType<typeof loadSubdiscipline>>>;
const photos = "/visual/stl4/subdisciplines";
const relatedPhotos = ["related-columns-final-r2.png", "related-street-final-r2.png", "related-shelves-final-r2.png"];

function SourceExcerpt({ source }: { source: SubdisciplineSource }) {
  return <blockquote className={styles.sourceExcerpt}>
    {source.quote ? <p>{source.quote}</p> : null}
    <cite>《{source.title}》{source.edition_label ? ` · ${source.edition_label}` : ""} · {source.printed_page_label ? `印刷页 ${source.printed_page_label}` : `PDF 第 ${source.pdf_page} 页`}</cite>
    {source.reader_href ? <Link href={source.reader_href} target="_blank" rel="noopener noreferrer">核对原文<ExternalLink size={12} aria-hidden="true" /></Link> : null}
  </blockquote>;
}

function PreviewFields({ item }: { item: SubdisciplinePayload }) {
  const groups = [
    ["研究对象", item.research_object ? [item.research_object] : []],
    ["核心问题", item.core_questions || []],
    ["形成与发展", item.formation_period ? [item.formation_period] : []],
    ["主要研究方向", item.research_directions || []],
    ["常用方法", item.methods || []],
    ["代表性议题", item.representative_issues || []],
  ] as const;
  return <section className={styles.preview} data-edit-section="knowledge_fields" aria-label="后台草稿字段">
    <h2>草稿字段预览</h2><p>以下显示当前预览视角中的编辑字段，不表示内容已经公开发布。</p>
    <div>{groups.map(([title, values]) => <section key={title}><h3>{title}</h3>{values.length ? <ul>{values.map((value, index) => <li key={index}>{value}</li>)}</ul> : <p>尚未填写。</p>}</section>)}</div>
    <h3>关联馆藏预览</h3>{item.works.length ? <ul>{item.works.map(work => <li key={work.id}>{work.title} · {work.author}</li>)}</ul> : <p>当前预览未提供关联馆藏。</p>}
  </section>;
}

export function SubdisciplinePublicView({ item, footer, preview = false }: { item: SubdisciplinePayload; footer: ReactNode; preview?: boolean }) {
  const questions = item.key_questions || [];
  const theories = item.theories || [], scholars = item.scholars || [];
  const works = item.core_works || [], topics = item.topics || [];
  const paths = item.reading_paths || [], sources = item.sources || [];
  const worksPage = item.works_pagination;
  const worksHref = (page: number) => `/subdisciplines/${encodeURIComponent(item.slug)}?works_page=${page}#works`;
  return <>
    <article className={`${styles.page} ${styles.detailPage}`}>
      <header className={styles.detailHero} id="overview" data-edit-section="identity">
        <nav className={styles.breadcrumb} aria-label="面包屑">
          <Link href="/theories">理论流派</Link><span aria-hidden="true">›</span>
          <Link href="/subdisciplines">子学科</Link><span aria-hidden="true">›</span><span>{item.name}</span>
        </nav>
        <picture className={styles.detailHeroPhoto}>
          {!item.hero_image ? <source media="(max-width: 700px)" srcSet={`${photos}/detail-stairs-mobile.webp`} /> : null}
          {item.hero_image ? <MediaPlacement uses={item.cover_media?.display_uses} placement="detail"><img src={item.hero_image} alt="" /></MediaPlacement> : <Image src={`${photos}/detail-stairs.webp`} width={681} height={182} alt="" priority unoptimized />}
        </picture>
        <div className={styles.detailHeroCopy}><h1>{item.name}</h1><p>{item.description || item.research_object || "本条目的介绍尚未发布。"}</p></div>
      </header>
      <nav className={styles.navigation} aria-label="子学科内容">
        {[["overview", "概览"], ["questions", "关键问题"], ["theories", "理论"], ["scholars", "学者"], ["works", "文献"]].map(([id, name]) => <a key={id} href={`#${id}`}>{name}</a>)}
      </nav>
      <div className={styles.detailContent}>
        <section className={styles.section} id="questions" aria-labelledby="subdiscipline-questions-title" data-edit-section="core_questions">
          <h2 id="subdiscipline-questions-title">关键问题</h2>
          {questions.length ? <div className={styles.questions}>{questions.map((question, index) => {
            const copy = <><h3>{question.title}</h3>{question.description ? <p>{question.description}</p> : null}{question.href ? <ArrowRight size={17} strokeWidth={1.5} aria-hidden="true" /> : null}</>;
            return question.href ? <Link key={question.id || index} href={question.href}>{copy}</Link> : <article key={question.id || index}>{copy}</article>;
          })}</div> : <p className={styles.empty}>尚无已确认并公开的关键问题。</p>}
        </section>
        <section className={styles.section} id="theories" aria-labelledby="subdiscipline-theories-title" data-edit-section="theories">
          <h2 id="subdiscipline-theories-title">相关理论</h2>
          {theories.length ? <div className={styles.theories}>{theories.map((theory, index) => <article key={`${theory.kind}-${theory.id}`}>
            <div className={styles.relatedCard}>
              <MediaPlacement uses={theory.cover_media?.display_uses} fallback={<span className={styles.relatedPhoto}/>}><span className={styles.relatedPhoto} style={{ backgroundImage: `url("${theory.cover_url || `${photos}/${relatedPhotos[index % relatedPhotos.length]}`}")` }} aria-hidden="true" /></MediaPlacement>
              <div><h3>{theory.href ? <Link href={theory.href}>{theory.name}<ArrowRight size={16} aria-hidden="true" /></Link> : theory.name}</h3><p>{theory.summary || theory.role || "介绍尚未发布"}</p></div>
            </div>
            {theory.legacy_identities?.length ? <details className={styles.relationSource}><summary>查看关联记录</summary><ul>{theory.legacy_identities.map(legacy => <li key={legacy.id}>{legacy.name}{legacy.role ? ` · ${legacy.role}` : ""}{legacy.source ? <p>{legacy.source}</p> : null}</li>)}</ul></details> : null}
          </article>)}</div> : <p className={styles.empty}>尚无已确认并公开的相关理论。</p>}
        </section>
        <section className={styles.section} id="scholars" aria-labelledby="subdiscipline-scholars-title" data-edit-section="scholars">
          <h2 id="subdiscipline-scholars-title">代表性学者</h2>
          {scholars.length ? <div className={styles.scholars}>{scholars.map(person => <article key={person.id}>
            {person.portrait_url ? <MediaPlacement uses={person.portrait_media?.display_uses} fallback={<span className={styles.portraitPlaceholder}>{person.name.slice(0,1)}</span>}><img src={person.portrait_url} alt={person.name} loading="lazy" /></MediaPlacement> : <span className={styles.portraitPlaceholder} aria-label={`${person.name}暂无肖像`}>{person.name.slice(0, 1)}</span>}
            <div><h3>{person.href ? <Link href={person.href}>{person.name}</Link> : person.name}</h3>
              {person.reason || person.relation_label || person.summary ? <p>{person.reason || person.relation_label || person.summary}</p> : null}
              {person.source_href ? <Link className={styles.sourceLink} href={person.source_href} target="_blank" rel="noopener noreferrer">查看来源<ArrowRight size={14} aria-hidden="true" /></Link>
                : <span className={styles.unavailable}>原文来源未提供</span>}
              {person.source_label ? <details className={styles.relationSource}><summary>关联说明</summary><p>{person.source_label}</p></details> : null}
            </div>
          </article>)}</div> : <p className={styles.empty}>尚无已确认并公开的代表性学者。</p>}
        </section>
        <div className={styles.bottomGrid}>
          <section className={styles.section} id="works" aria-labelledby="subdiscipline-works-title" data-edit-section="works">
            <h2 id="subdiscipline-works-title">核心文献</h2>
            {worksPage ? <p className={styles.workRange}>{works.length
              ? `共 ${worksPage.count} 部文献 · 当前第 ${(worksPage.page - 1) * 48 + 1}—${Math.min(worksPage.count, (worksPage.page - 1) * 48 + works.length)} 部`
              : `共 ${worksPage.count} 部文献`}</p> : null}
            {works.length ? <div className={styles.works}>{works.map(work => <article key={work.edition_id || work.id}>
              {work.cover_url ? <MediaPlacement uses={work.cover_media?.display_uses} fallback={<span className={styles.bookPlaceholder}><FileText size={25}/></span>}><img src={work.cover_url} alt={`《${work.title}》封面`} loading="lazy" /></MediaPlacement> : <span className={styles.bookPlaceholder}><FileText size={25} aria-hidden="true" /><span>暂无封面</span></span>}
              <div><h3>{work.detail_href ? <Link href={work.detail_href}>{work.title}</Link> : work.title}</h3><small>{[work.author, work.year, work.publisher].filter(value => value !== "" && value !== null).join(" · ") || "出版信息未提供"}</small>
                {work.relation_label ? <p>{work.relation_label}</p> : null}
                <div className={styles.workActions}>{work.detail_href ? <Link className={styles.primary} href={work.detail_href}>查看版本</Link> : null}{work.reader_href ? <Link href={work.reader_href} target="_blank" rel="noopener noreferrer">阅读原文</Link> : <span className={styles.unavailable}>这一版本暂无可读原文</span>}</div>
                {work.evidence ? <details className={styles.relationSource}><summary>查看关联依据</summary><SourceExcerpt source={work.evidence} /></details> : work.source ? <details className={styles.relationSource}><summary>关联说明</summary><p>{work.source}</p></details> : null}
              </div>
            </article>)}</div> : worksPage?.count ? <div className={styles.empty}><p>当前页没有可展示的文献，公开状态可能已变化。</p><a href={worksHref(worksPage.page)}>重新载入本页文献</a></div> : <p className={styles.empty}>尚无与本子学科建立公开关联的核心文献。</p>}
            {worksPage && worksPage.total_pages > 1 ? <nav className={styles.pagination} aria-label="核心文献分页">
              {worksPage.page > 1 ? <Link href={worksHref(worksPage.page - 1)}>上一页文献</Link> : null}
              <span>第 {worksPage.page} / {worksPage.total_pages} 页</span>
              {worksPage.page < worksPage.total_pages ? <Link href={worksHref(worksPage.page + 1)}>下一页文献</Link> : null}
            </nav> : null}
          </section>
          <section className={styles.section} id="topics" aria-labelledby="subdiscipline-topics-title" data-edit-section="topics">
            <h2 id="subdiscipline-topics-title">相关主题</h2>
            {topics.length ? <div className={styles.topics}>{topics.map((topic, index) => <article key={topic.id} className={styles.relatedCard}>
              <MediaPlacement uses={topic.cover_media?.display_uses} fallback={<span className={styles.relatedPhoto}/>}><span className={styles.relatedPhoto} style={{ backgroundImage: `url("${topic.hero_image || `${photos}/${index % 2 ? "topic-street-final-r2.png" : "topic-room-final-r2.png"}`}")` }} aria-hidden="true" /></MediaPlacement>
              <div><h3>{topic.href ? <Link href={topic.href}>{topic.name}<ArrowRight size={16} aria-hidden="true" /></Link> : topic.name}</h3><p>{topic.description || topic.relation_label || "介绍尚未发布"}</p></div>
            </article>)}</div> : <p className={styles.empty}>尚无已确认并公开的相关主题。</p>}
          </section>
        </div>
        <section className={`${styles.section} ${styles.paths}`} id="paths" aria-labelledby="subdiscipline-paths-title">
          <h2 id="subdiscipline-paths-title">延伸阅读</h2>
          {paths.length ? paths.map(path => <Link href={path.href} className={styles.path} key={path.id}><BookOpen size={19} strokeWidth={1.5} aria-hidden="true" /><span><strong>查看阅读路径 · {path.title}</strong>{path.introduction ? <span>{path.introduction}</span> : null}</span><ArrowRight size={18} strokeWidth={1.5} aria-hidden="true" /></Link>)
            : <p className={styles.empty}>尚无包含本子学科已确认条目的公开阅读路径。</p>}
        </section>
        {sources.length ? <details className={styles.sources} id="sources"><summary>本页原文依据（{sources.length}）</summary>
          <p>包含当前页文献的关联依据与本子学科已公开编排的原文依据。每条来源保留自己的版本与页码。</p>
          {sources.map(source => <SourceExcerpt key={`${source.source_kind}-${source.id}`} source={source} />)}</details> : null}
        {item.children?.length || item.discipline || item.parent ? <nav className={styles.hierarchy} aria-label="继续浏览相关学科">
          {item.discipline ? <Link href={`/theories/disciplines/${encodeURIComponent(item.discipline.slug)}`}>所属学科 · {item.discipline.name}</Link> : null}
          {item.parent ? <Link href={`/subdisciplines/${encodeURIComponent(item.parent.slug)}`}>上级子学科 · {item.parent.name}</Link> : null}
          {(item.children || []).map(child => <Link key={child.id} href={child.href}>下级子学科 · {child.name}</Link>)}
        </nav> : null}
        {preview ? <PreviewFields item={item} /> : null}
      </div>
    </article>
    {footer}
  </>;
}
