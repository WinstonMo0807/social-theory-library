"use client";

import { BookOpen, CalendarDays, FileText, Users, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { AdminPublicPreviewFrame } from "@/components/admin/admin-public-preview-frame";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import type { components } from "@/lib/api/generated/schema";

type Comparison = components["schemas"]["UsageComparison"];
type TrendDay = components["schemas"]["UsageTrendDay"];
type Analytics = components["schemas"]["AdminUsageAnalytics"];

function comparisonText(comparison?: Comparison) {
  if (!comparison) return "较上期　—";
  if (comparison.change_percent !== null) return `较上期　${comparison.change_percent > 0 ? "+" : ""}${comparison.change_percent}%`;
  if (comparison.status === "outside_retention") return "上期超出保留范围";
  if (comparison.status === "page_view_history_incomplete") return "页面浏览历史不足";
  return "上期无记录";
}

function TrendChart({ rows }: { rows: TrendDay[] }) {
  const chart = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(680);
  useEffect(() => {
    const element = chart.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setWidth(Math.max(160, element.clientWidth)));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const maximum = Math.max(4, ...rows.flatMap(row => [row.page_views ?? 0, row.searches ?? 0]));
  const top = Math.ceil(maximum / 4) * 4;
  const x = (index: number) => 48 + (rows.length > 1 ? index * (width - 68) / (rows.length - 1) : (width - 68) / 2);
  const y = (value: number) => 160 - value * 128 / top;
  const line = (key: "page_views" | "searches") => {
    let connected = false;
    return rows.map((row, index) => {
      const value = row[key];
      if (value === null) { connected = false; return ""; }
      const segment = `${connected ? "L" : "M"}${x(index).toFixed(2)},${y(value).toFixed(2)}`;
      connected = true;
      return segment;
    }).join(" ");
  };
  const tickCount = Math.min(width < 500 ? 3 : 7, rows.length);
  const ticks = [...new Set(Array.from({ length: tickCount }, (_, index) => Math.round(index * (rows.length - 1) / Math.max(1, tickCount - 1))))];
  return <div ref={chart} className="analytics-reference-chart">
    <svg viewBox={`0 0 ${width} 194`} role="img" aria-label="按书库时区显示已保留的页面浏览量与搜索次数；缺失历史留空">
      {[0, 1, 2, 3, 4].map(index => <g key={index}><line className="analytics-chart-grid" x1="48" x2={width - 20} y1={y(top * index / 4)} y2={y(top * index / 4)} /><text x="38" y={y(top * index / 4) + 4} textAnchor="end">{(top * index / 4).toLocaleString("zh-CN")}</text></g>)}
      {ticks.map((index, position) => <g key={index}><line className="analytics-chart-grid" x1={x(index)} x2={x(index)} y1="32" y2="160" /><text data-middle={position > 0 && position < ticks.length - 1 && position !== Math.floor(ticks.length / 2)} x={x(index)} y="184" textAnchor={position === 0 ? "start" : position === ticks.length - 1 ? "end" : "middle"}>{Number(rows[index].date.slice(5, 7))}月{Number(rows[index].date.slice(8))}日</text></g>)}
      <path className="analytics-chart-views" d={line("page_views")} />
      <path className="analytics-chart-searches" d={line("searches")} />
      {rows.flatMap((row, index) => (["page_views", "searches"] as const).map(key => row[key] === null ? null : <circle key={`${row.date}-${key}`} className={key === "page_views" ? "analytics-chart-views" : "analytics-chart-searches"} cx={x(index)} cy={y(row[key])} r="1.5"><title>{row.date}　{key === "page_views" ? "页面浏览量" : "搜索次数"}：{row[key]}</title></circle>))}
    </svg>
    <table className="sr-only"><caption>每日匿名使用记录</caption><thead><tr><th>日期</th><th>页面浏览量</th><th>搜索次数</th><th>阅读次数</th></tr></thead><tbody>{rows.map(row => <tr key={row.date}><th>{row.date}</th><td>{row.page_views ?? "无可用历史"}</td><td>{row.searches ?? "超出保留范围"}</td><td>{row.reader_opens ?? "超出保留范围"}</td></tr>)}</tbody></table>
  </div>;
}

export function AdminAnalytics() {
  const user = useAdminSession();
  const allowed = hasAdminCapability(user, "can_view_audit_log");
  const [days, setDays] = useState(30);
  const [customRange, setCustomRange] = useState<{ start: string; end: string } | null>(null);
  const [draftStart, setDraftStart] = useState<string | null>(null);
  const [draftEnd, setDraftEnd] = useState<string | null>(null);
  const [selected, setSelected] = useState("");
  const query = customRange ? `start_date=${customRange.start}&end_date=${customRange.end}` : `days=${days}`;
  const { data, error, retry } = useApiResource<Analytics>(allowed ? `/catalog/admin/usage-analytics/?${query}` : "", user ? getServerSessionCredential() : null, String(user?.id ?? ""));
  if (!allowed) return <div className="admin-page"><h1>当前账户没有统计查看权限</h1><p>请返回今日工作继续编目。</p></div>;
  const cards = [
    ["page_views", "页面浏览量", data?.coverage?.page_views_first_recorded_at ? data.events.page_view : "—", BookOpen],
    ["anonymous_sessions", "匿名阅读会话", data?.anonymous_sessions ?? "—", Users],
    ["search_submit", "站内搜索次数", data?.events.search_submit ?? "—", Search],
    ["reader_open", "馆藏阅读次数", data?.events.reader_open ?? "—", FileText],
  ] as const;
  const zeroQueries = (data?.top_queries || []).filter(row => row.zero_result_count > 0).sort((a, b) => b.zero_result_count - a.zero_result_count).slice(0, 5);
  const selectedUrl = selected || (zeroQueries[0] ? `/explore?q=${encodeURIComponent(zeroQueries[0].normalized_query)}` : "");
  return <div className="admin-page analytics-page analytics-reference">
    <header className="admin-page-title"><div><h1>使用统计</h1><span>查看读者如何使用书库，了解哪些内容受欢迎，并发现可以改进的地方。</span></div></header>
    <div className="analytics-reference-period">
      <div className="analytics-range-controls">
        <select aria-label="统计范围" value={customRange ? "custom" : days} onChange={event => { if (event.target.value !== "custom") { setDays(Number(event.target.value)); setCustomRange(null); setDraftStart(null); setDraftEnd(null); setSelected(""); } }}>
          {[7, 30, 90, 365].map(value => <option key={value} value={value}>最近 {value} 天</option>)}{customRange ? <option value="custom">自选日期</option> : null}
        </select>
        <details className="analytics-date-range"><summary><CalendarDays size={16} />{data?.range ? `${data.range.start_date} — ${data.range.end_date}` : "自选日期"}</summary>
          <form onSubmit={event => { event.preventDefault(); const values = new FormData(event.currentTarget); setCustomRange({ start: String(values.get("start")), end: String(values.get("end")) }); setSelected(""); event.currentTarget.closest("details")?.removeAttribute("open"); }}>
            <label>开始日期<input name="start" type="date" required value={draftStart ?? data?.range?.start_date ?? ""} onChange={event => setDraftStart(event.target.value)} /></label>
            <label>结束日期<input name="end" type="date" required min={draftStart ?? data?.range?.start_date} value={draftEnd ?? data?.range?.end_date ?? ""} onChange={event => setDraftEnd(event.target.value)} /></label>
            <button type="submit" className="button secondary">应用日期</button>
          </form>
        </details>
      </div>
      <p>数据为匿名聚合统计，不包含个人信息、私人笔记或 IP 地址。</p>
    </div>
    {error ? <p role="alert">{error}<button type="button" onClick={retry}>重试统计</button></p> : null}
    <section className="metric-grid">{cards.map(([key, label, value, Icon]) => <article key={key} data-metric={key}><Icon size={25} aria-hidden="true" /><div><span>{label}</span><strong>{typeof value === "number" ? value.toLocaleString("zh-CN") : value}</strong><small title={data?.range ? `上期 ${data.range.previous_start} 至 ${data.range.previous_end}；按保留的匿名记录比较` : undefined}>{comparisonText(data?.comparisons?.[key])}</small></div></article>)}</section>
    <div className="analytics-reference-columns"><div>
      <section className="admin-panel analytics-trend-panel"><header><h2>阅读与搜索趋势</h2><p className="analytics-chart-legend"><span className="analytics-chart-view-key" />页面浏览量<span className="analytics-chart-search-key" />搜索次数</p></header>
        {data?.trend?.length ? <TrendChart rows={data.trend} /> : <div className="analytics-reference-chart">{data ? "当前范围暂无可用趋势。" : "正在读取趋势…"}</div>}
        {data ? <p className="analytics-coverage-note">按 {data.range.timezone} 显示保留记录，保留期 {data.coverage.retention_days} 天。{!data.coverage.range_within_retention ? " 超出保留期的日期留空。" : ""}{!data.coverage.page_views_first_recorded_at ? " 页面浏览尚无记录，不以阅读次数代替。" : " 页面浏览从首条记录开始，历史未回填。"}</p> : null}
      </section>
      <section className="admin-panel"><h2>热门馆藏 <small>按阅读次数</small></h2><table><thead><tr><th>#</th><th>书名</th><th>阅读次数</th><th>匿名会话</th><th>操作</th></tr></thead><tbody>{(data?.top_works || []).map((row, index) => <tr key={row.work_id}><td>{index + 1}</td><td>{row.work__title}</td><td>{row.opens}</td><td>{row.unique_sessions}</td><td><button type="button" disabled={!row.public_url} onClick={() => { if (row.public_url) setSelected(row.public_url); }}>{row.public_url ? "查看" : "暂未公开"}</button></td></tr>)}</tbody></table>{data && !data.top_works.length ? <p>尚无匿名阅读记录。</p> : null}</section>
      <section className="admin-panel"><h2>热门无结果查询 <small>当前热门查询中的前 5 项</small></h2><table><thead><tr><th>#</th><th>查询关键词</th><th>无结果次数</th><th>操作</th></tr></thead><tbody>{zeroQueries.map((row, index) => <tr key={row.normalized_query}><td>{index + 1}</td><td>{row.normalized_query}</td><td>{row.zero_result_count}</td><td><button type="button" onClick={() => setSelected(`/explore?q=${encodeURIComponent(row.normalized_query)}`)}>在馆藏中检索</button></td></tr>)}</tbody></table>{data && !zeroQueries.length ? <p>当前没有达到聚合条件的无结果查询。</p> : null}</section>
    </div><AdminPublicPreviewFrame title="读者会看到什么" description="选择查询或热门馆藏，查看它在前台的实际呈现。" src={selectedUrl || null}><select aria-label="预览查询与馆藏" value={selectedUrl} onChange={event => setSelected(event.target.value)}><option value="">选择内容</option>{zeroQueries.map(row => <option key={row.normalized_query} value={`/explore?q=${encodeURIComponent(row.normalized_query)}`}>无结果查询：{row.normalized_query}</option>)}{(data?.top_works || []).map(row => row.public_url ? <option key={row.work_id} value={row.public_url}>{row.work__title}</option> : null)}</select></AdminPublicPreviewFrame></div>
  </div>;
}
