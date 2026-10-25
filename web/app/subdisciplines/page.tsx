import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { loadSubdisciplinePage } from "@/lib/api/taxonomy.server";
import type { SubdisciplineListItem } from "@/lib/api/taxonomy.types";
import { searchPage } from "@/lib/search-context";
import styles from "@/components/public/subdiscipline.module.css";

export const metadata: Metadata = { title: "子学科" };
type SearchParams = { q?: string | string[]; discipline?: string | string[]; page?: string | string[]; featured_page?: string | string[] };
const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value)?.trim() || "";
const photos = "/visual/stl4/subdisciplines";
const featuredPhotos = ["featured-stairs", "featured-shelves", "featured-branches"];
const directoryPhotos = ["card-room", "card-street", "card-columns", "card-globe", "card-books", "card-interior"];

function DirectoryCard({ item, index, featured = false }: { item: SubdisciplineListItem; index: number; featured?: boolean }) {
  const choices = featured ? featuredPhotos : directoryPhotos;
  const photo = item.hero_image || `${photos}/${choices[index % choices.length]}.webp`;
  return <Link href={item.href || `/subdisciplines/${encodeURIComponent(item.slug)}`} className={styles.directoryCard}>
    <span className={styles.cardPhoto} style={{ backgroundImage: `url("${photo}")` }} aria-hidden="true" />
    <span className={styles.cardCopy}><strong>{item.name}</strong><span>{item.description || item.research_object || "简介尚未发布"}</span></span>
    <ArrowRight className={styles.cardArrow} size={17} strokeWidth={1.6} aria-hidden="true" />
  </Link>;
}

export default async function SubdisciplineDirectory({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const query = first(params.q), discipline = first(params.discipline);
  const page = searchPage(params.page), featuredPage = searchPage(params.featured_page);
  const [featuredResult, allResult] = await Promise.allSettled([
    loadSubdisciplinePage(discipline, query, featuredPage, { featured: true }),
    loadSubdisciplinePage(discipline, query, page),
  ]);
  const featured = featuredResult.status === "fulfilled" ? featuredResult.value : null;
  const all = allResult.status === "fulfilled" ? allResult.value : null;
  const href = (changes: Record<string, string | number> = {}) => {
    const values = new URLSearchParams({
      ...(query ? { q: query } : {}), ...(discipline ? { discipline } : {}),
      ...(page > 1 ? { page: String(page) } : {}), ...(featuredPage > 1 ? { featured_page: String(featuredPage) } : {}),
      ...Object.fromEntries(Object.entries(changes).map(([key, value]) => [key, String(value)])),
    });
    return `/subdisciplines${values.size ? `?${values}` : ""}`;
  };
  const disciplineName = [...(all?.results || []), ...(featured?.results || [])].find(item => item.discipline?.slug === discipline)?.discipline?.name;
  return <>
    <div className={styles.page}>
      <section className={styles.directoryHero} aria-labelledby="subdiscipline-directory-title">
        <picture className={styles.directoryHeroPhoto}>
          <source media="(max-width: 700px)" srcSet={`${photos}/hero-mobile.webp`} />
          <Image src={`${photos}/hero.webp`} alt="" width={684} height={339} priority unoptimized />
        </picture>
        <div className={styles.directoryHeroCopy}>
          <h1 id="subdiscipline-directory-title">子学科</h1>
          <p>沿着学科边界进入具体问题与研究传统。</p>
          <form action="/subdisciplines" role="search" aria-label="搜索子学科" className={styles.search}>
            <Search size={21} strokeWidth={1.6} aria-hidden="true" />
            <input type="search" name="q" aria-label="子学科名称、概念或主题" placeholder="搜索子学科名称、概念、主题…" defaultValue={query} />
            {discipline ? <input type="hidden" name="discipline" value={discipline} /> : null}
            <button type="submit">搜索</button>
          </form>
        </div>
      </section>
      <div className={styles.directoryContent}>
        {query || discipline ? <div className={styles.filterSummary}><p>{[query ? `搜索：${query}` : "", discipline ? `学科：${disciplineName || discipline}` : ""].filter(Boolean).join(" · ")}{all ? ` · 共 ${all.count} 个公开子学科` : ""}</p><Link href="/subdisciplines">清除筛选<ArrowRight size={14} aria-hidden="true" /></Link></div> : null}
        <section className={styles.section} aria-labelledby="featured-subdisciplines-title">
          <h2 id="featured-subdisciplines-title">精选子学科</h2>
          {featured ? featured.results.length ? <div className={styles.featuredGrid}>{featured.results.map((item, index) => <DirectoryCard key={item.id} item={item} index={index} featured />)}</div>
            : <p className={styles.empty} role="status">{query || discipline ? "当前筛选下没有已发布的精选子学科。" : "尚无已发布的精选子学科。下方可浏览全部公开条目。"}</p>
            : <div className={styles.empty} role="alert"><p>精选子学科暂时无法读取，当前状态不能判断是否已有精选内容。</p><a href={href()}>重新载入精选子学科</a></div>}
          {featured && featured.totalPages > 1 ? <nav className={styles.pagination} aria-label="精选子学科分页">
            {featuredPage > 1 ? <Link href={href({ featured_page: featuredPage - 1 })}>上一页精选</Link> : null}
            <span>第 {featuredPage} / {featured.totalPages} 页</span>
            {featuredPage < featured.totalPages ? <Link href={href({ featured_page: featuredPage + 1 })}>下一页精选</Link> : null}
          </nav> : null}
        </section>
        <section className={styles.section} aria-labelledby="all-subdisciplines-title">
          <h2 id="all-subdisciplines-title">{query ? "子学科搜索结果" : "全部子学科"}</h2>
          {all ? all.results.length ? <div className={styles.directoryGrid}>{all.results.map((item, index) => <DirectoryCard key={item.id} item={item} index={index} />)}</div>
            : <p className={styles.empty} role="status">{query || discipline ? "没有找到符合条件的公开子学科。请调整名称、概念或主题后再次搜索。" : "子学科资料尚未发布。已确认并公开的条目会显示在这里。"}</p>
            : <div className={styles.empty} role="alert"><p>子学科目录暂时无法读取，请稍后重试。</p><a href={href()}>重新载入子学科目录</a></div>}
          {all ? <div className={styles.pagination}><ScopedSearchPagination path="/subdisciplines" context="subdisciplines" page={page} totalPages={all.totalPages} params={{ q: query, discipline, featured_page: featuredPage > 1 ? featuredPage : undefined }} /></div> : null}
        </section>
      </div>
    </div>
  </>;
}
