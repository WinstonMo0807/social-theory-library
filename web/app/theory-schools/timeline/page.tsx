import type { Metadata } from "next";
import Link from "next/link";
import { CalendarDays, Network } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ArchitecturalImage } from "@/components/ui";
import { loadDisciplines, loadTheoryTimeline } from "@/lib/server-api";

export const metadata: Metadata = { title: "理论历史时间轴" };

export default async function TheoryTimelinePage({
  searchParams,
}: {
  searchParams: Promise<{ discipline?: string }>;
}) {
  const discipline = (await searchParams).discipline ?? "";
  const [disciplines, events] = await Promise.all([
    loadDisciplines(),
    loadTheoryTimeline(discipline),
  ]);
  return (
    <>
      <main className="page-shell theory-timeline-page">
        <section className="timeline-title-row">
          <div><p className="eyebrow">探索理论流派</p><h1>社会理论历史时间轴</h1><p>仅展示经过人工确认、有证据来源的重要形成、发展、争论与发表事件。</p></div>
          <ArchitecturalImage compact />
        </section>
        <div className="timeline-controls panel">
          <span><CalendarDays size={18} />学科</span>
          <nav>
            <Link className={!discipline ? "active" : ""} href="/theory-schools/timeline">全部</Link>
            {disciplines.map((item) => (
              <Link className={discipline === item.slug ? "active" : ""} href={`/theory-schools/timeline?discipline=${item.slug}`} key={item.id}>{item.name}</Link>
            ))}
          </nav>
          <div className="theory-view-links">
            <Link href="/theory-schools"><Network size={16} />学科脉络</Link>
            <Link className="active" href="/theory-schools/timeline">历史时间轴</Link>
            <Link href="/theory-schools/graph">理论图谱</Link>
          </div>
        </div>
        <section className="horizontal-timeline" aria-label="理论历史事件">
          <div className="timeline-line" />
          {events.map((event, index) => {
            const target = event.theory
              ? `/theory-schools/${event.theory.slug}`
              : event.subdiscipline
                ? `/subdisciplines/${event.subdiscipline.slug}`
                : event.scholar
                  ? `/scholars/${event.scholar.slug}`
                  : "";
            const content = (
              <>
                <time>{event.date_label || [event.start_year, event.end_year].filter(Boolean).join("—") || "时期待考"}</time>
                <strong>{event.title}</strong>
                <p>{event.description}</p>
                {event.evidence_text ? <small>证据：{event.evidence_text.slice(0, 90)}</small> : null}
              </>
            );
            return (
              <article className={index % 2 ? "below" : "above"} key={event.id}>
                <span className="timeline-dot" />
                {target ? <Link href={target}>{content}</Link> : <div>{content}</div>}
              </article>
            );
          })}
          {!events.length ? <p className="empty-state">时间轴暂时保持空白。管理员确认事件和证据后才会公开。</p> : null}
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
