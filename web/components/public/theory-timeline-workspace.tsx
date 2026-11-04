"use client";

import { useState, useSyncExternalStore } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, ChevronDown, Search } from "lucide-react";
import { TimelinePicker } from "./timeline-picker";
import { TimelineEventDetails } from "./timeline-event-details";
import { timelineDate, timelineHref, timelineTypeLabels, type TimelineEvent, type TimelineEventDetail, type TimelineFilters, type TimelinePage } from "@/lib/api/timeline.types";
import styles from "./theory-timeline.module.css";

const scales = ["100", "50", "20", "10", "custom"];
function subscribeMobile(callback: () => void) { const media = window.matchMedia("(max-width:700px)"); media.addEventListener("change", callback); return () => media.removeEventListener("change", callback); }
const mobileSnapshot = () => window.matchMedia("(max-width:700px)").matches;
const serverSnapshot = () => false;
const primaryTypes = ["publication", "concept_proposed", "translation"];
const markerLabels = { publication: "作品出版", translation: "译本出版", concept_proposed: "概念使用", academic: "学术事件" };
function markerKind(type: string): keyof typeof markerLabels {
  return type === "publication" || type === "translation" || type === "concept_proposed" ? type : "academic";
}

export function TimelineHero({ scope }: { scope?: { name: string; href: string } }) {
  return <header className={styles.hero}>
    <div className={styles.heroCopy}>
      <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/">首页</Link><span>›</span><Link href="/explore">探索</Link><span>/</span>{scope ? <><Link href={scope.href}>{scope.name}</Link><span>/</span></> : null}<span>学科与概念时间线</span></nav>
      <h1>学科与概念时间线</h1>

    </div>
    <img className={styles.heroPhoto} src="/visual/stl4/timeline/hero-final-r2.png" alt="" width={800} height={180} />
  </header>;
}

function EventLink({ event, path, filters, selected }: { event: TimelineEvent; path: string; filters: TimelineFilters; selected?: boolean }) {
  return <Link className={styles.eventLink} href={timelineHref(path, filters, { focus: event.id, year: null, page: null, window_start: null })} aria-current={selected ? "true" : undefined}>
    <span className={styles.eventMarker} data-kind={markerKind(event.event_type)} aria-hidden="true" />
    <time>{timelineDate(event)}</time>
    <strong>{event.title}</strong>
    <small>{timelineTypeLabels[event.event_type] || event.event_type}{event.scholars.length ? ` · ${event.scholars.map(row => row.name).join("、")}` : ""}</small>
  </Link>;
}

export function TheoryTimelineWorkspace({ page, selected, selectionError, group, groupError, filters, actionPath, scope }: {
  page: TimelinePage; selected: TimelineEventDetail | null; selectionError?: string; group: TimelinePage | null; groupError?: string;
  filters: TimelineFilters; actionPath: string; scope?: { name: string; href: string };
}) {
  const router = useRouter();
  const mobile = useSyncExternalStore(subscribeMobile, mobileSnapshot, serverSnapshot);
  const [scale, setScale] = useState(scales.includes(filters.scale) ? filters.scale : "100");
  const [types, setTypes] = useState(filters.event_type?.split(",").filter(Boolean) || []);
  const [customFrom, setCustomFrom] = useState(filters.year_from || "");
  const [customTo, setCustomTo] = useState(filters.year_to || "");
  const appliedScale = scales.includes(filters.scale) ? filters.scale : "100";
  const selectedYear = selected ? selected.start_year ?? selected.end_year : null;
  const defaultAnchor = selectedYear ?? page.bounds.min_year ?? 0;
  const finiteYear = (value: string | undefined) => value && /^-?\d+$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : null;
  const customStart = finiteYear(filters.year_from) ?? page.bounds.min_year ?? 0;
  const customEnd = finiteYear(filters.year_to) ?? page.bounds.max_year ?? customStart + 100;
  const span = appliedScale === "custom" ? Math.max(1, customEnd - customStart) : Number(appliedScale);
  const windowStart = appliedScale === "custom" ? customStart : finiteYear(filters.window_start) ?? Math.floor(defaultAnchor / span) * span;
  const windowEnd = windowStart + span;
  const plottedGroups = page.year_groups.filter(row => row.year !== null && row.year >= windowStart && row.year <= windowEnd);
  const x = (year: number) => 40 + Math.max(0, Math.min(1, (year - windowStart) / span)) * 520;
  const rangeStart = selected?.start_year;
  const rangeEnd = selected?.end_year;
  const hasRange = selected?.date_precision === "range" && rangeStart !== null && rangeStart !== undefined && rangeEnd !== null && rangeEnd !== undefined && rangeEnd >= windowStart && rangeStart <= windowEnd;
  const resetFilters: TimelineFilters = scope ? { node: filters.node } : {};
  const currentGroup = selectedYear === null ? "时间未详" : `${selectedYear}年`;
  const otherTypes = Object.keys(timelineTypeLabels).filter(type => !primaryTypes.includes(type));
  const toggleType = (value: string, checked: boolean) => setTypes(previous => checked ? [...new Set([...previous, value])] : previous.filter(item => item !== value));
  return <div className={styles.page}>
    <TimelineHero scope={scope} />
    <form className={styles.filters} action={actionPath} aria-label="筛选时间线">
      {["node", "discipline", "related_to", "view", "sort"].filter(key => filters[key]).map(key => <input type="hidden" name={key} value={filters[key]} key={key} />)}
      <fieldset className={styles.scale}><legend>时间尺度</legend><div>{scales.map(value => <label key={value}><input type="radio" name="scale" value={value} checked={scale === value} onChange={() => setScale(value)} /><span>{value === "custom" ? "自定义" : `${value}年`}</span></label>)}</div></fieldset>
      <TimelinePicker kind="topic" values={filters.topic?.split(",").filter(Boolean) || []} selected={page.selected_topics} />
      <TimelinePicker kind="author" values={filters.author?.split(",").filter(Boolean) || []} selected={page.selected_authors} />
      <fieldset className={styles.typeFilter}><legend>事件类型</legend><details className={styles.typeDisclosure} open={!mobile}><summary>{types.length ? `${timelineTypeLabels[types[0]] || "已选类型"}${types.length > 1 ? ` 等 ${types.length} 项` : ""}` : "全部类型"}<ChevronDown size={12} /></summary><div className={styles.typeChoices}>{primaryTypes.map(type => <label key={type}><input name="event_type" type="checkbox" value={type} checked={types.includes(type)} onChange={e => toggleType(type, e.target.checked)} /><span>{timelineTypeLabels[type]}</span></label>)}<details><summary>其他类型<ChevronDown size={12} aria-hidden="true" />{types.filter(type => otherTypes.includes(type)).length ? ` (${types.filter(type => otherTypes.includes(type)).length})` : ""}</summary><div className={styles.typePanel}>{otherTypes.map(type => <label key={type}><input name="event_type" type="checkbox" value={type} checked={types.includes(type)} onChange={e => toggleType(type, e.target.checked)} /><span>{timelineTypeLabels[type]}</span></label>)}</div></details></div>
        {types.filter(type => !timelineTypeLabels[type]).map(type => <label key={type}><input name="event_type" type="checkbox" value={type} checked onChange={() => toggleType(type, false)} /><span>所选类型当前不可用</span></label>)}
      </details></fieldset>
      <div className={styles.filterActions}><Link href={timelineHref(actionPath, resetFilters)}>清空筛选</Link><button type="submit">应用筛选</button></div>
      <details className={styles.moreFilters} open={Boolean(scale === "custom" || filters.q || filters.year_from || filters.year_to || filters.has_collection || filters.related_to)}><summary>更多筛选<ChevronDown size={12} /></summary><div className={styles.searchRow}>
        <label className={styles.search}><Search size={16} aria-hidden="true" /><input name="q" aria-label="搜索时间线" defaultValue={filters.q || ""} placeholder="搜索事件、概念或来源说明" /></label>
        <div className={styles.yearInputs}><label>起始年份<input type="number" name="year_from" value={customFrom} onChange={e => setCustomFrom(e.target.value)} placeholder="不限" /></label><span>—</span><label>结束年份<input type="number" name="year_to" value={customTo} onChange={e => setCustomTo(e.target.value)} placeholder="不限" /></label></div>
        <label className={styles.collectionFilter}>馆藏<select name="has_collection" defaultValue={filters.has_collection || ""}><option value="">全部事件</option><option value="true">有馆藏依据</option><option value="false">无馆藏依据</option></select></label>
        {scope ? <Link className={styles.scopeNote} href={scope.href}>{scope.name}</Link> : filters.node || filters.discipline ? <span className={styles.scopeNote}>当前限定理论或学科范围</span> : null}
        {filters.related_to ? <span className={styles.scopeNote}>当前查看指定事件的相关事件</span> : null}
      </div></details>
    </form>
    <div className={styles.workspaceToolbar}>
      <p>共 <strong>{page.scope_count}</strong> 个事件{filters.year ? ` · ${filters.year === "undated" ? "时间未详" : `${filters.year}年`} ${page.count} 个` : ""}</p>
      <label>排序<select aria-label="事件排序" value={filters.sort || "asc"} onChange={e => router.push(timelineHref(actionPath, filters, { sort: e.target.value, page: null, focus: null }))}><option value="asc">由早到晚</option><option value="desc">由晚到早</option></select></label>
      <nav className={styles.viewToggle} aria-label="时间线显示方式"><Link href={timelineHref(actionPath, filters, { view: "timeline" })} aria-current={filters.view !== "list" ? "page" : undefined}>时间线视图</Link><Link href={timelineHref(actionPath, filters, { view: "list" })} aria-current={filters.view === "list" ? "page" : undefined}>列表视图</Link></nav>
    </div>
    <div className={`${styles.workspace} ${filters.view === "list" ? styles.listView : ""}`}>
      <section className={styles.eventList} aria-label="时间线事件">
        {page.results.length ? <ul>{page.results.map(event => <li key={event.id}><EventLink event={event} path={actionPath} filters={filters} selected={event.id === selected?.id} /></li>)}</ul> : <p role="status" className={styles.empty}>没有符合条件的公开事件。<span>没有匹配的已发布事件，请调整筛选。</span></p>}
        {page.count ? <nav className={styles.pagination} aria-label="时间线分页">{page.previous ? <Link href={timelineHref(actionPath, filters, { page: page.page - 1, focus: null })}>上一页</Link> : <span>上一页</span>}<span>第 {page.page} / {page.total_pages} 页</span>{page.next ? <Link href={timelineHref(actionPath, filters, { page: page.page + 1, focus: null })}>下一页</Link> : <span>下一页</span>}</nav> : null}
      </section>
      {filters.view !== "list" ? <div className={styles.axisColumn}>
        <details className={styles.axisDisclosure} open><summary>时间轴与同年事件<ChevronDown size={14} aria-hidden="true" /></summary><div className={styles.axisBody}>
          <section className={styles.axis} aria-label="时间轴">
            <div className={styles.axisHeading}>{appliedScale !== "custom" && page.bounds.min_year !== null && windowStart > page.bounds.min_year ? <Link aria-label="查看更早时间范围" href={timelineHref(actionPath, filters, { window_start: windowStart - span })}><ArrowLeft size={16} aria-hidden="true" /></Link> : <span />}<h2>{page.bounds.min_year === null ? "尚无已标注年份" : `${windowStart}—${windowEnd}`}</h2>{appliedScale !== "custom" && page.bounds.max_year !== null && windowEnd < page.bounds.max_year ? <Link aria-label="查看更晚时间范围" href={timelineHref(actionPath, filters, { window_start: windowStart + span })}><ArrowRight size={16} aria-hidden="true" /></Link> : <span />}</div>
            {page.bounds.min_year !== null ? <svg viewBox="0 0 600 152" className={styles.axisSvg} aria-label={`${windowStart}至${windowEnd}年的事件分布`}>
              <line x1="40" y1="75" x2="560" y2="75" className={styles.axisLine} />
              {Array.from({ length: 6 }, (_, index) => { const year = Math.round(windowStart + span * index / 5); return <g key={index}><line x1={40 + index * 104} y1="70" x2={40 + index * 104} y2="80" className={styles.tick} /><text x={40 + index * 104} y="117" textAnchor="middle">{year}</text></g>; })}
              {hasRange ? <rect x={x(rangeStart!)} y="56" width={Math.max(3, x(rangeEnd!) - x(rangeStart!))} height="38" className={styles.uncertainRange}><title>{timelineDate(selected!)}</title></rect> : null}
              {plottedGroups.map(row => {
                const counts = new Map<keyof typeof markerLabels, number>();
                row.event_types.forEach(type => { const kind = markerKind(type.event_type); counts.set(kind, (counts.get(kind) || 0) + type.count); });
                const markers = [...counts.entries()];
                const center = x(row.year!);
                return <a key={row.year} href={timelineHref(actionPath, filters, { year: row.year!, focus: null, page: null })} aria-label={`${row.year}年 · ${row.count}个事件`} className={row.year === selectedYear ? styles.activePoint : styles.point}>
                  <rect x={center - 12} y="44" width="24" height="62" rx="12" className={styles.pointTarget} />
                  {markers.map(([kind, count], index) => {
                    const cy = 75 + (index - (markers.length - 1) / 2) * 14;
                    return <g key={kind} className={styles.axisMarker} data-kind={kind}>
                      {kind === "academic" ? <path d={`M ${center} ${cy - 5} L ${center + 5} ${cy + 4} L ${center - 5} ${cy + 4} Z`} /> : <circle cx={center} cy={cy} r="4.5" />}
                      <title>{markerLabels[kind]} · {count} 个</title>
                    </g>;
                  })}
                  {row.count > 1 ? <text x={center} y="35" textAnchor="middle">{row.count}</text> : null}
                  <title>{row.year}年 · {row.count}个事件</title>
                </a>;
              })}
            </svg> : <p className={styles.muted}>有明确或暂定年份的事件将在这里按年聚合。</p>}
            <div className={styles.axisLegend}>{Object.entries(markerLabels).map(([kind, label]) => <span key={kind}><i className={styles.eventMarker} data-kind={kind} aria-hidden="true" />{label}</span>)}<p>同年按类型分列，数字为事件总数。{selected && selected.date_precision !== "year" ? `当前事件：${timelineDate(selected)} · ${selected.date_precision === "range" ? "虚线范围为实际记录区间" : "日期尚非确切年份"}` : ""}</p></div>
            {page.bounds.undated_count ? <Link className={styles.undated} href={timelineHref(actionPath, filters, { year: "undated", focus: null, page: null })}>时间未详 · {page.bounds.undated_count}个事件</Link> : null}
          </section>
          <section className={styles.yearGroup} aria-label="同年事件"><div className={styles.sectionHeading}><h2>{selected ? currentGroup : "同年事件"}</h2>{group ? <span>{group.count} 个事件</span> : null}</div>
            {groupError ? <p role="alert">{groupError}<Link href={timelineHref(actionPath, filters)}>重新读取</Link></p> : group?.results.length ? <><ul>{group.results.map(event => <li key={event.id}><EventLink event={event} path={actionPath} filters={filters} selected={event.id === selected?.id} /></li>)}</ul>{group.count > group.results.length ? <Link className={styles.textLink} href={timelineHref(actionPath, filters, { year: selectedYear === null ? "undated" : selectedYear, focus: null, page: null })}>查看全部 {group.count} 个同年事件<ArrowRight size={14} aria-hidden="true" /></Link> : null}</> : <p className={styles.muted}>选择事件后查看同年的其他记录。</p>}
          </section>
        </div></details>
      </div> : null}
      <div className={styles.detailColumn}>{selected ? <TimelineEventDetails key={selected.id} event={selected} filters={filters} actionPath={actionPath} /> : <section aria-label="所选事件详情" className={styles.empty}><p role={selectionError ? "alert" : "status"}>{selectionError || "选择一个事件，查看详情与原文来源。"}</p>{selectionError ? <Link href={timelineHref(actionPath, filters)}>重新读取事件详情</Link> : null}</section>}</div>
    </div>
  </div>;
}
