import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { CollectionLink } from "@/components/collection-link";
import { serverRequest, ServerApiError } from "@/lib/api/server-request";
import type { NormalizedTimelineEvent } from "@/lib/api/knowledge.types";

export default async function TheoryEventPage({ params }: {params: Promise<{eventId: string}>}) {
  const {eventId} = await params;
  let event: NormalizedTimelineEvent;
  try { event = await serverRequest<NormalizedTimelineEvent>(`/catalog/theory-system/timeline/${encodeURIComponent(eventId)}/`); } catch(error) { if(error instanceof ServerApiError && error.status===404) notFound(); throw error; }
  return <><main className="page-shell v307-knowledge knowledge-section-page"><p className="breadcrumbs"><Link href="/theories/timeline">历史时间线</Link><span>›</span>{event.title}</p><header><p className="eyebrow">{event.date_label || [event.start_year, event.end_year].filter(value => value !== null).join(" — ") || "日期未详"}</p><h1>{event.title}</h1></header><article className="panel knowledge-long-copy"><p>{event.description}</p></article>{event.relations.length ? <section className="knowledge-section"><h2>事件涉及的对象</h2><div className="knowledge-chip-grid">{event.relations.map((row, index) => {const href = row.slug ? row.type === "node" ? `/theories/nodes/${row.slug}` : row.type === "scholar" ? `/scholars/${row.slug}` : row.type === "work" ? `/works/${row.slug}` : "" : ""; return href ? <Link href={href} key={`${row.id}-${index}`}>{row.name}</Link> : <span key={`${row.id}-${index}`}>{row.name}</span>;})}</div></section> : null}{event.source || event.evidence_text ? <section className="knowledge-section"><h2>事实来源</h2><p>{event.source}</p>{event.evidence_text ? <blockquote>{event.evidence_text}</blockquote> : null}{event.reader_href ? <CollectionLink href={event.reader_href}>阅读出处 · {event.evidence_printed_label || `PDF 第 ${event.evidence_page} 页`}</CollectionLink> : null}</section> : null}</main><SiteFooter/></>;
}
