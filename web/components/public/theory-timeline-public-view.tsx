import Link from "next/link";
import { BookOpen, CalendarDays, ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { TheoryEmpty } from "@/components/theory-system-ui";
import type { NormalizedTimelineEvent } from "@/lib/server-api";

export const theoryTimelineEventTypeLabels: Record<string, string> = {
  publication: "重要著作出版",
  concept_proposed: "理论概念提出",
  school_formation: "学派形成",
  institution: "学术机构建立",
  debate: "重要争论",
  theoretical_turn: "理论转向",
  translation: "重要译介",
  china_reception: "进入中国学界",
  scholar: "学者生平事件",
  institutionalization: "学科制度化事件",
  formation: "形成",
  development: "发展",
};

export function TheoryTimelinePublicList({
  events,
  pagination = null,
}: {
  events: NormalizedTimelineEvent[];
  pagination?: ReactNode;
}) {
  return (
    <section className="theory-timeline-list" data-module-id="theory-development">
      {events.length ? events.map((event) => {
        const nodeNames = event.relations.filter((item) => item.type === "node").map((item) => item.name);
        const hasWork = event.relations.some((item) => item.type === "work");
        return <article key={event.id}>
          <time>{event.start_year ? `${Math.floor(event.start_year / 10) * 10}s` : event.date_label}</time>
          <span className="event-icon">{hasWork ? <BookOpen size={21} /> : <CalendarDays size={21} />}</span>
          <div className="event-main"><small>{event.date_label || event.start_year}</small><h2>{event.title}</h2><p>{event.description}</p></div>
          <dl>{event.event_type ? <><dt>事件类型</dt><dd>{theoryTimelineEventTypeLabels[event.event_type] || event.event_type}</dd></> : null}{nodeNames.length ? <><dt>相关理论</dt><dd>{nodeNames.join("、")}</dd></> : null}{event.source ? <><dt>信息来源</dt><dd>{event.source}</dd></> : null}</dl>
          {event.reader_href ? <Link href={event.reader_href}>查看馆藏证据<ExternalLink size={15} /></Link> : null}
        </article>;
      }) : <TheoryEmpty title="没有符合条件的公开事件" detail="调整筛选条件，或等待管理员审核并发布新的时间轴事件。" />}
      {pagination}
    </section>
  );
}
