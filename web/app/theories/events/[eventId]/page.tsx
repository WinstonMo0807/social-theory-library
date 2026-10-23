import { PublishedPlacements } from "@/components/public/published-placements";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { TimelineEventDetails } from "@/components/public/timeline-event-details";
import { loadTimelineEvent } from "@/lib/api/timeline.server";
import type { TimelineEventDetail } from "@/lib/api/timeline.types";
import styles from "@/components/public/theory-timeline.module.css";

export default async function TheoryEventPage({ params }: { params: Promise<{ eventId: string }> }) {
  const { eventId } = await params;
  let event: TimelineEventDetail | null;
  try { event = await loadTimelineEvent(eventId); }
  catch {
    return <><div className={styles.page}><section className={styles.error} role="alert"><h1>事件详情暂时无法读取</h1><p>未能取得实际事件与来源数据，请稍后重试。</p><Link href={`/theories/events/${encodeURIComponent(eventId)}`}>重试事件详情</Link><Link href="/theories/timeline">返回时间线</Link></section></div><SiteFooter /></>;
  }
  if (!event) notFound();
  return <><div className={styles.page}><nav className={`${styles.breadcrumb} ${styles.standaloneBreadcrumb}`} aria-label="面包屑"><Link href="/theories/timeline">学科与概念时间线</Link><span>/</span><span>{event.title}</span></nav><TimelineEventDetails event={event} standalone /></div><PublishedPlacements type="timeline_event" id={event.id}/><SiteFooter /></>;
}
