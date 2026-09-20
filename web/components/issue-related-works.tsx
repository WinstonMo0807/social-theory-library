"use client";
import Link from "next/link";
import { BookCard } from "@/components/ui";
import { useApiResource } from "@/lib/api/use-api-resource";
import { getServerSessionCredential } from "@/lib/api";
import { adaptApiWork } from "@/lib/public-data-adapters";
import type { ApiWork } from "@/lib/api/public-catalog";

export function IssueRelatedWorks({ excludedHrefs }: { excludedHrefs: string[] }) {
  const resource = useApiResource<{ results: ApiWork[] }>("/catalog/works/?ordering=-editions__first_published_at", getServerSessionCredential());
  const works = (resource.data?.results || []).map(adaptApiWork).filter(work => !excludedHrefs.includes(`/works/${work.slug}`)).slice(0, 4);
  return <section className="issue-related-works"><header className="v307-section-heading"><h2>继续阅读 <small>Explore the library</small></h2><Link href="/explore">查看全部馆藏 →</Link></header>
    {resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.retry}>重新读取馆藏</button></p> : resource.loading ? <p role="status">正在读取公开馆藏…</p> : works.length ? <div className="v307-recent-grid">{works.map(work => <BookCard work={work} dense key={work.id} />)}</div> : <p className="empty-state">更多馆藏发布后会显示在这里。</p>}
  </section>;
}
