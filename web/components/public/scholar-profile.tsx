"use client";

import Link from "next/link";
import { IssueProse } from "./issue-prose";
import { scholarProseBlock } from "@/lib/api/scholar-prose";
import { useEffect, useState } from "react";
import { ArrowRight, ExternalLink, Network, Search } from "lucide-react";
import { subscribeToSessionChanges } from "@/lib/api";
import { CollectionLink } from "@/components/collection-link";
import { ScholarFollowButton } from "./source-follow-control";
import { ScholarContent, ScholarRelations } from "./scholar-content";
import { ScholarImage, ScholarPagination, ScholarResultCard } from "./scholar-shared";
import { scholarQuery, scholarSection, scholarSectionHref, scholarSections, scholarYears } from "@/lib/api/scholars.params";
import type { PublicScholarDetail, ScholarSearchParams, ScholarSection } from "@/lib/api/scholars.types";
import styles from "./scholar.module.css";

export function ScholarProfile({ data, preview = false, initialSection = "overview", params = {} }: { data: PublicScholarDetail; preview?: boolean; initialSection?: string; params?: ScholarSearchParams }) {
  const section = scholarSection(initialSection) || "overview", quote = data.featured_quote?.source;
  return <main className={`${styles.page} ${styles.profilePage}`} onClickCapture={preview ? event => { if ((event.target as HTMLElement).closest("a")) event.preventDefault(); } : undefined} onAuxClickCapture={preview ? event => event.preventDefault() : undefined}>
    <nav className={styles.breadcrumbs} aria-label="面包屑"><Link prefetch={false} href="/home">首页</Link><span>›</span><Link prefetch={false} href="/scholars">学者</Link><span>›</span><span>{data.person.preferred_name}</span></nav>
    <header className={styles.profileHero} data-module-id="scholar-identity" data-edit-section="identity"><div className={styles.profilePortrait}><ScholarImage scholar={data} eager placement="detail" /></div><div className={styles.profileCopy}>
      <h1>{data.person.preferred_name}</h1><p className={styles.identityLine}>{data.person.original_name ? <span>{data.person.original_name}</span> : null}<span>{scholarYears(data.person)}</span></p>{data.nationalities.length || data.occupations.length ? <p className={styles.identityDescription}>{[...data.nationalities, ...data.occupations].join(" · ")}</p> : null}
      {data.short_description ? <div className={styles.profileDescription}><IssueProse block={scholarProseBlock(data.short_description,data.profile_prose?.short_description)}/></div> : <p className={styles.profileDescription}>此学者的简介仍待补充，可从已收录的作品、问题与来源展开研究。</p>}
      {data.profile_state === "sparse" ? <span className={styles.sparseBadge}>资料仍待补充</span> : null}
      {data.sources.results.length ? <p className={styles.profileSources} data-edit-section="sources">资料来源：{data.sources.results.slice(0, 3).map((source, index) => <span key={source.id}>{index ? "、" : ""}{source.url ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.title}</a> : source.title}</span>)}<Link prefetch={false} href={scholarSectionHref(data.slug, "sources")}>查看全部（{data.sources.count}）</Link></p> : null}
      {data.person.aliases.length ? <details className={styles.aliases}><summary>已确认的异名与译名（{data.person.aliases.length}）</summary><p>{data.person.aliases.join("、")}</p></details> : null}
    </div>{quote ? <blockquote className={styles.featuredQuote} data-module-id="scholar-quote" data-edit-section="sources"><span aria-hidden="true">“</span><p>{quote.text}</p><cite>《{quote.work_title}》{quote.edition_label ? ` · ${quote.edition_label}` : ""}{quote.page_start ? ` · PDF 第 ${quote.page_start} 页` : ""}</cite>{quote.reader_url ? <CollectionLink prefetch={false} href={quote.reader_url}>核对原文<ExternalLink size={13} /></CollectionLink> : null}</blockquote> : <div className={styles.quoteEmpty}><BookProfileLinks data={data} /></div>}
      <div className={styles.profileActions}>{preview ? <button type="button" disabled className={styles.primaryButton}><Search size={17} />围绕此学者开展研究</button> : <Link prefetch={false} className={styles.primaryButton} href={data.research_href}><Search size={17} />围绕此学者开展研究</Link>}{preview || !data.graph_href ? <button type="button" disabled className={styles.outlineButton}><Network size={17} />查看学术关系图</button> : <Link prefetch={false} className={styles.outlineButton} href={data.graph_href}><Network size={17} />查看学术关系图</Link>}<ScholarFollowButton profileId={data.id} href={data.href} className={styles.outlineButton} preview={preview} /></div>
    </header>
    <nav className={styles.profileNav} aria-label="学者内容">{scholarSections.map(tab => preview ? <button type="button" key={tab.id} aria-current={section === tab.id ? "page" : undefined} data-edit-section={tab.editor}>{tab.label}</button> : <Link prefetch={false} key={tab.id} href={scholarSectionHref(data.slug, tab.id)} aria-current={section === tab.id ? "page" : undefined}>{tab.label}</Link>)}</nav>
    {data.disambiguation.length ? <details className={styles.disambiguation}><summary>区分同名学者（另有 {data.disambiguation.length} 位公开档案）</summary><p>当前档案为 {data.person.preferred_name}{data.person.original_name ? ` · ${data.person.original_name}` : ""}，{scholarYears(data.person)}。请结合生卒年与研究领域确认身份。</p><div>{data.disambiguation.map(person => <ScholarResultCard scholar={person} key={person.id} compact />)}</div></details> : null}
    {(section === "works" || section === "relations") && !preview ? <ScholarSectionFilters data={data} section={section} params={params} /> : null}
    {section === "sources" ? <p className={styles.publicRevision}>当前公开档案{data.public_revision.number ? ` · 第 ${data.public_revision.number} 版` : ""}{data.public_revision.published_at ? ` · ${new Date(data.public_revision.published_at).toLocaleDateString("zh-CN")} 发布` : ""}{data.public_revision.change_note ? ` · ${data.public_revision.change_note}` : ""}</p> : null}
    <ScholarContent data={data} section={section} params={params} preview={preview} />
    {section === "relations" && !preview ? <ScholarCandidates key={`${data.id}:${data.candidate_access.requested}`} data={data} params={params} /> : null}
    {section !== "overview" ? <Link prefetch={false} className={styles.backLink} href={data.href}>返回学者概览<ArrowRight size={15} /></Link> : null}
  </main>;
}
function BookProfileLinks({ data }: { data: PublicScholarDetail }) {
  return <><h2>从作品与来源了解学者</h2><p>{data.key_concerns.join(" · ") || "已确认的馆藏与关联内容"}</p><Link prefetch={false} href={scholarSectionHref(data.slug, "works")}>馆藏作品 · {data.work_count}<ArrowRight size={14} /></Link><Link prefetch={false} href={scholarSectionHref(data.slug, "sources")}>人物资料来源 · {data.sources.count}<ArrowRight size={14} /></Link></>;
}
function ScholarSectionFilters({ data, section, params }: { data: PublicScholarDetail; section: ScholarSection; params: ScholarSearchParams }) {
  const work = section === "works", facets = work ? data.facets.roles : data.facets.relation_types, selected = work ? data.filters.role : data.filters.relation_type;
  return <form key={`${selected.join(",")}:${data.filters.relation_direction}`} action={scholarSectionHref(data.slug, section)} className={styles.sectionFilters} aria-label={work ? "筛选学者作品角色" : "筛选学术关系"}>
    <fieldset><legend>{work ? "本人的贡献角色" : "关系类型"}</legend>{facets.map(facet => <label key={facet.value}><input type="checkbox" name={work ? "role" : "relation_type"} value={facet.value} defaultChecked={selected.includes(facet.value)} />{facet.label}<small>（{facet.count}）</small></label>)}</fieldset>
    {!work ? <label>关系方向<select name="relation_direction" defaultValue={data.filters.relation_direction}><option value="all">全部方向</option><option value="incoming">指向此学者</option><option value="outgoing">由此学者指向他人</option></select></label> : <p>同一作品的不同出版版本分别保留；作者、编者、译者与章节贡献不会合并。</p>}
    {params.page_size ? <input type="hidden" name="page_size" value={String(params.page_size)} /> : null}<button type="submit" className={styles.outlineButton}>应用筛选</button><Link prefetch={false} href={scholarSectionHref(data.slug, section)}>清空</Link>
  </form>;
}
function ScholarCandidates({ data, params }: { data: PublicScholarDetail; params: ScholarSearchParams }) {
  const [sessionChanged, setSessionChanged] = useState(false);
  useEffect(() => subscribeToSessionChanges(() => setSessionChanged(true)), []);
  if (sessionChanged || !data.candidate_access.allowed) return null;
  return <section className={styles.candidatePanel}><form action={scholarSectionHref(data.slug, "relations")}>
    {[...scholarQuery(params)].filter(([key]) => !["include_candidates", "page", "section"].includes(key)).map(([key, value], index) => <input type="hidden" name={key} value={value} key={`${key}:${index}`} />)}
    <label><input type="checkbox" name="include_candidates" value="true" defaultChecked={data.candidate_access.requested} />查看未确认关系</label><button className={styles.outlineButton} type="submit">更新显示</button>
  </form><p>{data.candidate_access.notice}</p>{data.candidate_access.review_href ? <Link prefetch={false} href={data.candidate_access.review_href}>进入后台核对<ArrowRight size={14} /></Link> : null}
    {data.candidate_relations ? <><h2>待核对关系 · {data.candidate_relations.count}</h2>{data.candidate_relations.results.length ? <ScholarRelations rows={data.candidate_relations.results} candidate /> : <p className={styles.empty}>此范围暂无可显示的待核对关系。</p>}<ScholarPagination page={data.candidate_relations} path={scholarSectionHref(data.slug, "relations")} params={{ ...params, include_candidates: "true" }} label="待核对关系分页" /></> : null}
  </section>;
}
