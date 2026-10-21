import Link from "next/link";
import { ArrowRight, UserRound } from "lucide-react";
import { ResponsiveMediaImage } from "@/components/responsive-media-image";
import { scholarHref, scholarYears } from "@/lib/api/scholars.params";
import type { PublicScholarCard, ScholarPage, ScholarSearchParams } from "@/lib/api/scholars.types";
import styles from "./scholar.module.css";

export function ScholarImage({ scholar, eager = false }: { scholar: PublicScholarCard; eager?: boolean }) {
  const person = scholar.person, media = person.portrait_media;
  return <div className={styles.portrait}>{person.portrait ? media?.renditions?.length ? <ResponsiveMediaImage src={person.portrait} sources={media.renditions} alt={media.alt_text || `${person.preferred_name}肖像`} sizes="(max-width: 700px) 110px, 25vw" loading={eager ? "eager" : "lazy"} /> : <img src={person.portrait} alt={`${person.preferred_name}肖像`} loading={eager ? "eager" : "lazy"} /> : <span className={styles.noPortrait} aria-label={`${person.preferred_name}暂无肖像`}><UserRound size={52} strokeWidth={1} /></span>}</div>;
}
export function ScholarResultCard({ scholar, compact = false }: { scholar: PublicScholarCard; compact?: boolean }) {
  return <article className={`${styles.scholarCard} ${compact ? styles.compactCard : ""}`} data-scholar-id={scholar.id}>
    <Link prefetch={false} href={scholar.href} className={styles.cardPortrait} aria-label={`查看${scholar.person.preferred_name}档案`}><ScholarImage scholar={scholar} /></Link>
    <div className={styles.cardCopy}><h3><Link prefetch={false} href={scholar.href}>{scholar.person.preferred_name}</Link></h3>{scholar.person.original_name ? <p className={styles.originalName}>{scholar.person.original_name}</p> : null}<p>{scholarYears(scholar.person)}</p><p className={styles.concerns}>{scholar.key_concerns.join(" · ") || scholar.short_description || "资料仍待补充"}</p>
      {scholar.matched_alias ? <p className={styles.aliasMatch}>别名命中：<strong>{scholar.matched_alias}</strong></p> : null}
      <Link prefetch={false} className={styles.cardFooter} href={`${scholar.href}/works`}>查看作品（{scholar.work_count}）<ArrowRight size={15} /></Link>
    </div>
  </article>;
}
export function ScholarPagination({ page, path, params, label = "学者分页" }: { page: Pick<ScholarPage<unknown>, "page" | "total_pages" | "previous" | "next">; path: string; params: ScholarSearchParams; label?: string }) {
  if (!page.previous && !page.next) return null;
  return <nav className={styles.pagination} aria-label={label}>{page.previous ? <Link prefetch={false} href={scholarHref(path, params, { page: String(page.page - 1) })}>上一页</Link> : <span>上一页</span>}<span>第 {page.page} / {page.total_pages} 页</span>{page.next ? <Link prefetch={false} href={scholarHref(path, params, { page: String(page.page + 1) })}>下一页</Link> : <span>下一页</span>}</nav>;
}
