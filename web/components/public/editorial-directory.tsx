"use client";

import Link from "next/link";
import { ScholarPortraitFallback } from "@/components/default-scholar-portrait";
import { useRouter } from "next/navigation";
import { useState, type ChangeEvent } from "react";
import { ArrowRight, FileText, ImageOff, LayoutGrid, List, Search, UserRound, X } from "lucide-react";
import type { EditorialCard, EditorialCurator, EditorialDirectory, EditorialSearchParams } from "@/lib/api/recommendation-issues.types";
import styles from "./editorial.module.css";
import { MediaPlacement } from "@/components/media-placement";
import type { MediaDisplayUse } from "@/lib/media-usage";
import { editorialImageSources } from "@/lib/performance-assets";

export const editorialValue = (params: EditorialSearchParams, key: string) => { const value = params[key]; return Array.isArray(value) ? value[0] || "" : value || ""; };
export function editorialHref(params: EditorialSearchParams, patch: Record<string, string | undefined> = {}) {
  const query = new URLSearchParams();
  for (const key of ["q", "topic", "theory", "kind", "curator", "year_from", "year_to", "sort", "page", "page_size", "layout"]) {
    const value = key in patch ? patch[key] : editorialValue(params, key);
    if (value) query.set(key, value);
  }
  return `/recommendations${query.size ? `?${query}` : ""}`;
}

export function EditorialImage({ src, className = "", portrait = false, retry = false, displayUses, scholar, loading = "lazy" }: { src: string; className?: string; portrait?: boolean; retry?: boolean; displayUses?:readonly MediaDisplayUse[]; scholar?: {name:string; identity:string}; loading?: "lazy" | "eager" }) {
  const [failedSource, setFailedSource] = useState("");
  const failed=!!src&&failedSource===src;
  const fallback=scholar ? <ScholarPortraitFallback name={scholar.name} identity={scholar.identity} className={className}/> : <span className={`${className} ${styles.imageMissing}`}><span role="img" aria-label={failed?"图片暂不可用":src?"本位置不展示配图":portrait?"未提供公开头像":"暂未提供配图"}>{portrait ? <UserRound size={20} strokeWidth={1} /> : <ImageOff size={28} strokeWidth={1} />}</span>{retry && failed ? <button type="button" onClick={() => setFailedSource("")}>重新加载</button> : null}</span>;
  return <MediaPlacement uses={displayUses} fallback={fallback}>{src && !failed ? <img className={className} src={src} {...editorialImageSources(src, portrait ? "96px" : "(max-width: 760px) 100vw, 50vw")} alt="" loading={loading} decoding={loading === "eager" ? "auto" : "async"} onError={() => setFailedSource(src)} /> : fallback}</MediaPlacement>;
}
export function EditorialByline({ curator, date }: { curator: EditorialCurator; date: string | null }) {
  return <div className={styles.byline}>{curator.name ? <EditorialImage key={curator.portrait_url} src={curator.portrait_url} portrait className={styles.avatar} /> : null}
    <div>{curator.name ? <><strong>{curator.name}</strong>{curator.affiliation || curator.role ? <span>{[curator.affiliation,curator.role].filter(Boolean).join(" · ")}</span> : null}</> : null}
    {date ? <time dateTime={date}>{new Date(date).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "long", day: "numeric" })}</time> : null}</div></div>;
}
function Card({ card, lead = false }: { card: EditorialCard; lead?: boolean }) {
  return <article className={styles.card} data-lead={lead || undefined}><Link prefetch={false} href={card.href} className={styles.cardImageLink} aria-label={`阅读${card.title}`}>
    <EditorialImage key={card.cover_url} src={card.cover_url} className={styles.cardImage} />{card.issue_label ? <span className={styles.badge}>{card.issue_label}</span> : null}</Link>
    <div className={styles.cardCopy}><h2><Link prefetch={false} href={card.href}>{card.title}</Link></h2>{card.introduction ? <p>{card.introduction}</p> : null}
      <EditorialByline curator={card.curator} date={card.published_at} /><Link className={styles.cardArrow} prefetch={false} href={card.href} aria-label={`阅读${card.title}`}><ArrowRight size={17} /></Link></div></article>;
}

export function EditorialRelated({ related }: { related: EditorialDirectory["related"] }) {
  const [tab, setTab] = useState("scholars");
  if (!related.scholars.length && !related.materials.length && !related.paths.length) return null;
  return <section className={styles.related} aria-label="继续探索"><nav aria-label="关联内容">
    {[["scholars","相关学者"],["materials","相关材料"],["paths","相关阅读路径"]].map(([key,label]) => <button key={key} type="button" aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}
  </nav><p>{related.notice}</p><div className={styles.relatedRows}>
    {tab === "scholars" ? related.scholars.length ? related.scholars.map(row => <Link key={row.id} href={row.href}><EditorialImage scholar={{name:row.person.preferred_name,identity:row.href}} src={row.person.portrait} displayUses={row.person.portrait_media?.display_uses} className={styles.relatedPortrait} portrait /><span><strong>{row.person.preferred_name}</strong><small>{row.person.original_name}</small><small>{row.short_description}</small></span><ArrowRight size={16} /></Link>) : <p>这些文章尚未编入公开学者档案。</p> : null}
    {tab === "materials" ? related.materials.length ? related.materials.map(row => <Link key={row.id} href={row.href}><EditorialImage src={row.cover_url} displayUses={row.cover_display_uses} className={styles.relatedCover} /><span><strong>{row.title}</strong><small>{row.authors}</small><small>{row.source_status === "available" ? "馆藏原文" : "公开书目"}</small></span><ArrowRight size={16} /></Link>) : <p>这些文章暂无可公开的关联材料。</p> : null}
    {tab === "paths" ? related.paths.length ? related.paths.map(row => <Link key={row.id} href={row.href}><span><strong>{row.title}</strong><small>打开完整阅读路径</small></span><ArrowRight size={16} /></Link>) : <p>这些文章尚未编入公开阅读路径。</p> : null}
  </div></section>;
}

function DirectoryRelated({related}:{related:EditorialDirectory["related"]}){
  return <div className={styles.directoryRelated}>
    <section aria-labelledby="directory-related-scholars"><header><h2 id="directory-related-scholars">相关学者 </h2><Link href="/scholars">学者目录 <ArrowRight size={13}/></Link></header>
      {related.scholars.length?<div className={styles.directoryScholars}>{related.scholars.map(row=><Link key={row.id} href={row.href}>
        <EditorialImage scholar={{name:row.person.preferred_name,identity:row.href}} src={row.person.portrait} displayUses={row.person.portrait_media?.display_uses} className={styles.directoryPortrait} portrait/>
        <div><h3>{row.person.preferred_name}</h3>{row.person.birth_year!=null||row.person.death_year!=null?<small>{row.person.birth_year==null?"出生年未详":row.person.birth_year}{row.person.death_year!=null?`—${row.person.death_year}`:""}</small>:null}<p>{row.short_description||row.fields.map(field=>field.name).join("、")||"公开资料待补充"}</p><ArrowRight size={13}/></div>
      </Link>)}</div>:<p className={styles.directoryRelatedEmpty}>当前文章尚未编入公开学者档案。</p>}
    </section>
    <section aria-labelledby="directory-related-materials"><header><h2 id="directory-related-materials">相关材料与阅读路线 </h2><Link href="/explore">检索馆藏 <ArrowRight size={13}/></Link></header>
      {related.materials.length?<ol className={styles.directoryMaterials}>{related.materials.map(row=><li key={row.id}><Link href={row.href}>
        <EditorialImage src={row.cover_url} displayUses={row.cover_display_uses} className={styles.relatedCover}/><span><strong>{row.title}</strong>{row.authors?<small>{row.authors}</small>:null}<small>{row.source_status==="available"?"馆藏原文":"公开书目"}</small></span><ArrowRight size={13}/>
      </Link></li>)}</ol>:<p className={styles.directoryRelatedEmpty}>当前文章暂无可公开的关联材料。</p>}
      {related.paths.length?<nav className={styles.directoryPaths} aria-label="相关阅读路线">{related.paths.map(row=><Link key={row.id} href={row.href}><span>{row.title}</span><ArrowRight size={13}/></Link>)}</nav>:null}
    </section>
    {related.notice?<p className={styles.directoryRelatedNotice}>{related.notice}</p>:null}
  </div>;
}

export function EditorialDirectoryView({ data, params, error }: { data: EditorialDirectory | null; params: EditorialSearchParams; error: string }) {
  const router = useRouter(), q = editorialValue(params,"q"), list = editorialValue(params,"layout") === "list";
  const [filtersOpen, setFiltersOpen] = useState(false);
  const value = (key: string) => editorialValue(params,key);
  const chips = ["topic","theory","kind","curator","year_from","year_to"].filter(key => value(key));
  const label = (key: string) => key === "topic" ? data?.facets.topics.find(row => [row.id,row.slug].includes(value(key)))?.name || "原主题条件" : key === "theory" ? data?.facets.theories?.find(row => [row.id,row.slug].includes(value(key)))?.name || "原理论条件" : key === "kind" ? data?.facets.kinds.find(row => row.id === value(key))?.label || value(key) : key.startsWith("year") ? `${key === "year_from" ? "起始" : "结束"} ${value(key)} 年` : value(key);
  const submit = (event: ChangeEvent<HTMLSelectElement>) => event.currentTarget.form?.requestSubmit();
  return <main className={styles.directory}>
    <header className={styles.hero}><nav className={styles.breadcrumbs} aria-label="面包屑"><Link href="/home">首页</Link><span>›</span><span>特别策划</span><span>›</span><span>专题文章索引</span></nav>
      <div className={styles.heroCopy}><h1>专题文章索引</h1><p className={styles.subtitle}>发现策划文章、阅读专题和原文展览。</p></div>
      <img className={styles.heroImage} src="/editorial/generated-20261030/editorial.webp" alt="" />
      <form id="editorial-filter" action="/recommendations" className={styles.search}><Search size={19} /><input name="q" aria-label="搜索专题文章" placeholder="搜索文章、作者、概念、主题…" defaultValue={q} /><button type="submit">搜索</button>{list ? <input type="hidden" name="layout" value="list" /> : null}</form>
    </header>
    <div className={styles.directoryToolbar}>
    <button type="button" className={styles.filterToggle} aria-expanded={filtersOpen} aria-controls="editorial-filters" onClick={() => setFiltersOpen(!filtersOpen)}>筛选 <span aria-hidden>⌄</span></button>
    <div id="editorial-filters" className={styles.filters} data-open={filtersOpen || undefined} aria-label="专题文章筛选">
      <button type="button" className={styles.filterLabel} aria-expanded={filtersOpen} title="展开策划者筛选" onClick={() => setFiltersOpen(!filtersOpen)}>筛选：</button>
      <label><span className="sr-only">主题领域</span><select data-stl-select form="editorial-filter" name="topic" defaultValue={value("topic")} onChange={submit}><option value="">主题领域</option>{value("topic") && !data?.facets.topics.some(row => [row.id,row.slug].includes(value("topic"))) ? <option value={value("topic")}>原主题条件</option> : null}{data?.facets.topics.map(row => <option key={row.id} value={value("topic") === row.slug ? row.slug : row.id}>{row.name}</option>)}</select></label>
      <label><span className="sr-only">理论流派</span><select data-stl-select form="editorial-filter" name="theory" defaultValue={value("theory")} onChange={submit}><option value="">理论流派</option>{value("theory") && !data?.facets.theories?.some(row => [row.id,row.slug].includes(value("theory"))) ? <option value={value("theory")}>原理论条件</option> : null}{data?.facets.theories?.map(row => <option key={row.id} value={value("theory") === row.slug ? row.slug : row.id}>{row.name}</option>)}</select></label>
      <details data-disclosure="collection" className={styles.years}><summary>{value("year_from") || value("year_to") ? `${value("year_from") || "最早"}–${value("year_to") || "至今"}` : "时期"}</summary><div><label>起始年份<input form="editorial-filter" type="number" name="year_from" min="1" max="9998" defaultValue={value("year_from")} placeholder="不限" /></label><label>结束年份<input form="editorial-filter" type="number" name="year_to" min="1" max="9998" defaultValue={value("year_to")} placeholder="不限" /></label><button form="editorial-filter" type="submit">应用时间</button></div></details>
      <label><span className="sr-only">文章类型</span><select data-stl-select form="editorial-filter" name="kind" defaultValue={value("kind")} onChange={submit}><option value="">文章类型</option>{(data?.facets.kinds || [{id:"article",label:"策划文章"},{id:"research",label:"研究论文"},{id:"exhibition",label:"原文展览"}]).map(row => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
      <label className={styles.curatorFilter}>策划者<select data-stl-select form="editorial-filter" name="curator" defaultValue={value("curator")} onChange={submit}><option value="">全部策划者</option>{value("curator") && !data?.facets.curators.includes(value("curator")) ? <option value={value("curator")}>{value("curator")}</option> : null}{data?.facets.curators.map(name => <option key={name} value={name}>{name}</option>)}</select></label>
      <Link className={styles.reset} href={editorialHref({q})}>重置筛选</Link>
    </div>
    {chips.length ? <div className={styles.chips}>{chips.map(key => <Link key={key} href={editorialHref(params,{[key]:undefined,page:undefined})}>{label(key)}<X size={12} aria-hidden /></Link>)}</div> : null}
    <div className={styles.resultsHeading}><p aria-live="polite">{data ? `共 ${data.count} 个专题文章` : "专题文章"}</p><div><label className="sr-only" htmlFor="editorial-sort">文章排序</label><select data-stl-select id="editorial-sort" form="editorial-filter" name="sort" defaultValue={value("sort") || "newest"} onChange={submit}><option value="newest">最新发布</option><option value="oldest">最早发布</option><option value="title">按标题排序</option></select>
      <nav className={styles.layoutSwitch} aria-label="文章布局"><Link href={editorialHref(params,{layout:undefined})} aria-label="网格布局" aria-current={!list ? "true" : undefined}><LayoutGrid size={17} /></Link><Link href={editorialHref(params,{layout:"list"})} aria-label="列表布局" aria-current={list ? "true" : undefined}><List size={18} /></Link></nav></div></div>
    </div>
    {error ? <section className={styles.empty} role="alert"><h2>专题文章未能读取</h2><p>{error}</p><button onClick={() => router.refresh()}>重新读取</button><Link href="/recommendations">重置筛选</Link></section> : data?.results.length ? <div className={`${styles.cards} ${list ? styles.list : ""}`} data-featured={!list && !q && !chips.length && data.page === 1 || undefined}>{data.results.map((card, index) => <Card key={card.id} card={card} lead={!list && !q && !chips.length && data.page === 1 && index === 0} />)}</div> : <section className={styles.empty}><FileText size={34} strokeWidth={1} /><h2>{q || chips.length ? "未找到符合条件的专题文章" : "当前暂无公开的专题文章"}</h2><p>{q || chips.length ? "可以减少筛选条件，或尝试其他关键词。" : "新的策划内容发布后会在这里显示。"}</p><Link href="/recommendations">查看已发布专题</Link></section>}
    {data && data.total_pages > 1 ? <nav className={styles.pagination} aria-label="专题文章分页">{data.previous ? <Link href={editorialHref(params,{page:String(data.page-1)})}>上一页</Link> : <span>上一页</span>}<span>第 {data.page} / {data.total_pages} 页</span>{data.next ? <Link href={editorialHref(params,{page:String(data.page+1)})}>下一页<ArrowRight size={14} /></Link> : <span>下一页</span>}</nav> : null}
    {data ? <DirectoryRelated related={data.related} /> : null}
  </main>;
}
