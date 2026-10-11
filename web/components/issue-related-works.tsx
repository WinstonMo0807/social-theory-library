"use client";
import Link from "next/link";
import { BookCard } from "@/components/ui";
import { useApiResource } from "@/lib/api/use-api-resource";
import { getServerSessionCredential } from "@/lib/api";
import { adaptApiWork } from "@/lib/public-data-adapters";
import type { ApiWork } from "@/lib/api/public-catalog";

export function IssueRelatedWorks({ excludedWorkIds }: { excludedWorkIds: string[] }) {
  const resource = useApiResource<{ results: ApiWork[] }>("/catalog/works/?ordering=-editions__first_published_at", getServerSessionCredential());
  const works = (resource.data?.results || []).filter(work => !excludedWorkIds.includes(work.id)).map(adaptApiWork).slice(0, 4);
  return <section className="issue-related-space"><header><h2>从馆藏继续阅读</h2><Link href="/explore">更多 ›</Link></header>
    {resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.retry}>重新读取馆藏</button></p> : resource.loading ? <p role="status">正在读取公开馆藏…</p> : works.length ? <div className="issue-reading-list">{works.map(work => <BookCard work={work} dense key={work.id} />)}</div> : <p className="empty-state">更多馆藏发布后会显示在这里。</p>}
  </section>;
}
