import { PublishedPlacements } from "@/components/public/published-placements";
import type { Metadata } from "next";
import { publicMediaMetadata } from "@/lib/public-image-metadata";
import { notFound } from "next/navigation";
import { SubdisciplinePublicView } from "@/components/public/subdiscipline-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadSubdiscipline, SubdisciplineWorksPageError } from "@/lib/api/taxonomy.server";
import Link from "next/link";
import styles from "@/components/public/subdiscipline.module.css";

export async function generateMetadata({params}: {params: Promise<{slug: string}>}): Promise<Metadata> {
  try { const item = await loadSubdiscipline((await params).slug); return {title: item?.name || "子学科详情", ...await publicMediaMetadata(item?.cover_media, item?.name || "子学科")}; }
  catch { return {title: "子学科详情"}; }
}

export default async function SubdisciplinePage({ params, searchParams }: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ works_page?: string | string[] }>;
}) {
  const { slug } = await params;
  const query = await searchParams;
  const worksPage = (Array.isArray(query.works_page) ? query.works_page[0] : query.works_page) || "1";
  const detailHref = `/subdisciplines/${encodeURIComponent(slug)}`;
  let item;
  try {
    item = await loadSubdiscipline(slug, worksPage);
  } catch (error) {
    if (error instanceof SubdisciplineWorksPageError) {
      return <><div className={styles.page}><section className={styles.errorPage} aria-labelledby="subdiscipline-page-error">
        <h1 id="subdiscipline-page-error">核心文献页码不可用</h1>
        <p role="alert">{error.reason === "invalid" ? "文献页码必须是正整数，请从第一页重新浏览。" : "所选文献页码超出当前公开结果范围，条目内容可能已经更新。"}</p>
        <Link href={`${detailHref}#works`}>返回核心文献第一页</Link>
        <Link href="/subdisciplines">返回子学科目录</Link>
      </section></div><SiteFooter /></>;
    }
    return <><div className={styles.page}><section className={styles.errorPage} aria-labelledby="subdiscipline-load-error">
      <h1 id="subdiscipline-load-error">子学科资料暂时无法读取</h1>
      <p role="alert">当前请求未能完成，尚不能判断这条子学科是否已经发布。请稍后重试。</p>
      <a href={`${detailHref}${worksPage === "1" ? "" : `?${new URLSearchParams({ works_page: worksPage })}`}`}>重新载入资料</a>
      <Link href="/subdisciplines">返回子学科目录</Link>
    </section></div><SiteFooter /></>;
  }
  if (!item) notFound();

  return <SubdisciplinePublicView item={item} footer={<><PublishedPlacements type="subdiscipline" id={item.id}/><SiteFooter /></>} />;
}
