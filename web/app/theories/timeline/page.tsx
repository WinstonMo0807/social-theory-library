import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, BookOpen, CalendarDays, ExternalLink, Search } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { TheoryBanner, TheoryEmpty } from "@/components/theory-system-ui";
import { loadDisciplines, loadNormalizedTheoryTimelinePage, loadTheorySystemNodes } from "@/lib/server-api";

export const metadata: Metadata = { title: "社会理论历史时间轴", description: "按学科、理论传统、事件类型和馆藏证据浏览社会理论历史。" };

type TimelineParams = { discipline?: string; node?: string; event_type?: string; has_collection?: string; q?: string; page?: string };

const eventTypeLabels: Record<string, string> = {
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

export default async function TheoryTimelinePage({ searchParams }: { searchParams: Promise<TimelineParams> }) {
  const filters = await searchParams;
  const [eventPage, disciplines, theories] = await Promise.all([
    loadNormalizedTheoryTimelinePage(filters),
    loadDisciplines(),
    loadTheorySystemNodes({ type: "theory_tradition" }),
  ]);
  const events = eventPage.results;
  const currentPage = Math.max(1, Number(filters.page || 1) || 1);
  const pageCount = Math.max(1, Math.ceil(eventPage.count / 24));
  function pageHref(page: number) {
    const parameters = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (key !== "page" && value) parameters.set(key, value);
    });
    parameters.set("page", String(page));
    return `/theories/timeline?${parameters.toString()}`;
  }
  const periodCounts = new Map<string, number>();
  events.forEach((event) => {
    const decade = event.start_year ? `${Math.floor(event.start_year / 10) * 10}s` : "时期未定";
    periodCounts.set(decade, (periodCounts.get(decade) || 0) + 1);
  });

  return (
    <>
      <main className="page-shell theory-system-page theory-timeline-page">
        <div className="theory-breadcrumb"><Link href="/theories">探索理论流派</Link><span>/</span><strong>社会理论历史时间轴</strong></div>
        <section className="theory-timeline-hero"><div><p className="eyebrow">历史时间轴</p><h1>社会理论历史时间轴</h1><p>追踪经过人工审核的关键事件，并从文献证据回到馆藏原页。</p></div><TheoryBanner /></section>
        <nav className="theory-view-mode"><Link href="/theories">学科脉络</Link><Link className="active" href="/theories/timeline">历史时间轴</Link><Link href="/theories/graph">理论图谱</Link></nav>

        <form className="theory-timeline-filters" action="/theories/timeline">
          <label><span>学科</span><select name="discipline" defaultValue={filters.discipline || ""}><option value="">全部学科</option>{disciplines.map((item) => <option value={item.slug} key={item.id}>{item.name}</option>)}</select></label>
          <label><span>理论传统</span><select name="node" defaultValue={filters.node || ""}><option value="">全部理论</option>{theories.map((item) => <option value={item.slug} key={item.id}>{item.canonical_name_zh}</option>)}</select></label>
          <label><span>事件类型</span><select name="event_type" defaultValue={filters.event_type || ""}><option value="">全部类型</option>{Object.entries(eventTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label><span>馆藏状态</span><select name="has_collection" defaultValue={filters.has_collection || ""}><option value="">全部</option><option value="true">仅看有馆藏</option></select></label>
          <label className="timeline-search"><Search size={18} /><input name="q" defaultValue={filters.q || ""} placeholder="搜索事件、学者、著作或概念" /><button type="submit">筛选</button></label>
        </form>

        <section className="theory-history-stages" aria-label="历史阶段">
          {[['1850','古典形成'],['1900','学科建制'],['1950','范式分化'],['2000','当代转向'],['2025','持续演进']].map(([year, label]) => <span key={year}><i /><b>{year}</b><small>{label}</small></span>)}
        </section>

        <div className="theory-timeline-layout">
          <section className="theory-timeline-list">
            {events.length ? events.map((event) => {
              const nodeNames = event.relations.filter((item) => item.type === "node").map((item) => item.name);
              const hasWork = event.relations.some((item) => item.type === "work");
              return <article key={event.id}>
                <time>{event.start_year ? `${Math.floor(event.start_year / 10) * 10}s` : event.date_label}</time>
                <span className="event-icon">{hasWork ? <BookOpen size={21} /> : <CalendarDays size={21} />}</span>
                <div className="event-main"><small>{event.date_label || event.start_year}</small><h2>{event.title}</h2><p>{event.description}</p></div>
                <dl>{event.event_type ? <><dt>事件类型</dt><dd>{eventTypeLabels[event.event_type] || event.event_type}</dd></> : null}{nodeNames.length ? <><dt>相关理论</dt><dd>{nodeNames.join("、")}</dd></> : null}{event.source ? <><dt>信息来源</dt><dd>{event.source}</dd></> : null}</dl>
                {event.reader_href ? <Link href={event.reader_href}>查看馆藏证据<ExternalLink size={15} /></Link> : null}
              </article>;
            }) : <TheoryEmpty title="没有符合条件的公开事件" detail="调整筛选条件，或等待管理员审核并发布新的时间轴事件。" />}
            {eventPage.count > 24 ? <nav className="theory-timeline-pagination" aria-label="时间轴分页"><Link aria-disabled={currentPage <= 1} href={pageHref(Math.max(1, currentPage - 1))}>上一页</Link><span>第 {currentPage} / {pageCount} 页 · 共 {eventPage.count} 条</span><Link aria-disabled={currentPage >= pageCount} href={pageHref(Math.min(pageCount, currentPage + 1))}>下一页</Link></nav> : null}
          </section>
          {periodCounts.size ? <aside className="theory-timeline-aside"><h2>按时期浏览</h2>{Array.from(periodCounts.entries()).map(([period, count]) => <Link href={`/theories/timeline?q=${encodeURIComponent(period.replace('s',''))}`} key={period}><span>{period}</span><b>{count}</b></Link>)}<Link className="aside-more" href="/theories/timeline">查看全部<ArrowRight size={16} /></Link></aside> : null}
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
