import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Search } from "lucide-react";
import { TheoryTimelinePublicList, theoryTimelineEventTypeLabels } from "@/components/public/theory-timeline-public-view";
import { SiteFooter } from "@/components/site-footer";
import { TheoryBanner } from "@/components/theory-system-ui";
import { loadDisciplines } from "@/lib/api/taxonomy.server";
import { loadNormalizedTheoryTimelinePage, loadTheorySystemNodes } from "@/lib/api/knowledge.server";
import { searchPage } from "@/lib/search-context";

export const metadata: Metadata = { title: "社会理论历史时间轴", description: "按学科、理论传统、事件类型和馆藏证据浏览社会理论历史。" };

type TimelineParams = { discipline?: string; node?: string; event_type?: string; has_collection?: string; q?: string; page?: string; year_from?: string; year_to?: string };

export default async function TheoryTimelinePage({ searchParams }: { searchParams: Promise<TimelineParams> }) {
  const filters = await searchParams;
  const currentPage = searchPage(filters.page);
  const yearError = [filters.year_from,filters.year_to].some(value => value && !/^-?\d+$/.test(value)) ? "年份请填写整数。" : filters.year_from && filters.year_to && Number(filters.year_from) > Number(filters.year_to) ? "起始年不能晚于结束年。" : "";
  const [eventPage, disciplines, theories] = await Promise.all([
    yearError ? Promise.resolve({count:0,results:[],next:null,previous:null}) : loadNormalizedTheoryTimelinePage({...filters,page:String(currentPage)}),
    loadDisciplines(),
    loadTheorySystemNodes({ type: "theory_tradition" }),
  ]);
  const events = eventPage.results;
  const pageCount = Math.max(1, Math.ceil(eventPage.count / 24));
  function pageHref(page: number) {
    const parameters = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (key !== "page" && value) parameters.set(key, value);
    });
    parameters.set("page", String(page));
    return `/theories/timeline?${parameters.toString()}`;
  }
  const periods = new Map<string, {count: number; firstEventId: string}>();
  events.forEach((event) => {
    const decade = event.start_year !== null ? `${Math.floor(event.start_year / 10) * 10} 年代` : "时期未定";
    const previous = periods.get(decade);
    periods.set(decade, {count:(previous?.count || 0)+1,firstEventId:previous?.firstEventId || event.id});
  });

  return (
    <>
      <main className="page-shell theory-system-page theory-timeline-page v307-knowledge">
        <div className="theory-breadcrumb"><Link href="/theories">探索理论流派</Link><span>/</span><strong>社会理论历史时间轴</strong></div>
        <section className="theory-timeline-hero"><div><p className="eyebrow">历史时间轴</p><h1>社会理论历史时间轴</h1><p>追踪经过人工审核的关键事件，并从文献证据回到馆藏原页。</p></div><TheoryBanner /></section>
        <nav className="theory-view-mode"><Link href="/theories">学科脉络</Link><Link className="active" href="/theories/timeline">历史时间轴</Link><Link href="/theories/graph">理论图谱</Link></nav>
        {yearError ? <p role="alert">{yearError}请调整年份后重新筛选。</p> : null}

        <form className="theory-timeline-filters" action="/theories/timeline">
          {filters.year_from ? <input type="hidden" name="year_from" value={filters.year_from}/> : null}
          {filters.year_to ? <input type="hidden" name="year_to" value={filters.year_to}/> : null}
          <label><span>学科</span><select name="discipline" defaultValue={filters.discipline || ""}><option value="">全部学科</option>{disciplines.map((item) => <option value={item.slug} key={item.id}>{item.name}</option>)}</select></label>
          <label><span>理论传统</span><select name="node" defaultValue={filters.node || ""}><option value="">全部理论</option>{theories.map((item) => <option value={item.slug} key={item.id}>{item.canonical_name_zh}</option>)}</select></label>
          <label><span>事件类型</span><select name="event_type" defaultValue={filters.event_type || ""}><option value="">全部类型</option>{Object.entries(theoryTimelineEventTypeLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
          <label><span>馆藏状态</span><select name="has_collection" defaultValue={filters.has_collection || ""}><option value="">全部</option><option value="true">仅看有馆藏</option></select></label>
          <label className="timeline-search"><Search size={18} /><input name="q" defaultValue={filters.q || ""} placeholder="搜索事件、学者、著作或概念" /><button type="submit">筛选</button></label>
        </form>

        {periods.size ? <section className="theory-history-stages" aria-label="当前页事件年代">
          {Array.from(periods.entries()).slice(0,6).map(([period, data]) => <Link href={`#timeline-event-${data.firstEventId}`} key={period}><span><i /><b>{period}</b><small>本页 {data.count} 个事件</small></span></Link>)}
        </section> : null}

        <div className="theory-timeline-layout">
          <TheoryTimelinePublicList events={events} pagination={eventPage.count > 24 ? <nav className="theory-timeline-pagination" aria-label="时间轴分页"><Link aria-disabled={currentPage <= 1} href={pageHref(Math.max(1, currentPage - 1))}>上一页</Link><span>第 {currentPage} / {pageCount} 页 · 共 {eventPage.count} 条</span><Link aria-disabled={currentPage >= pageCount} href={pageHref(Math.min(pageCount, currentPage + 1))}>下一页</Link></nav> : null} />
          <aside className="theory-timeline-aside"><h2>筛选年份</h2><form action="/theories/timeline">{Object.entries(filters).filter(([key,value]) => value && !["page","year_from","year_to"].includes(key)).map(([key,value])=><input key={key} type="hidden" name={key} value={value}/>)}<label>起始年<input type="number" name="year_from" defaultValue={filters.year_from || ""} placeholder="不限"/></label><label>结束年<input type="number" name="year_to" defaultValue={filters.year_to || ""} placeholder="不限"/></label><button type="submit" className="button secondary">应用年份</button></form>{periods.size ? <><h2>本页年代</h2>{Array.from(periods.entries()).map(([period, data]) => <Link href={`#timeline-event-${data.firstEventId}`} key={period}><span>{period}</span><b>{data.count}</b></Link>)}</> : null}<Link className="aside-more" href="/theories/timeline">查看全部事件<ArrowRight size={16} /></Link></aside>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
