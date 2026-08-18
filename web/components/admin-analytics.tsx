"use client";

import { useEffect, useState } from "react";
import { BarChart3, BookOpen, Download, Search } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";

type Analytics = {
  period_days: number;
  anonymous_sessions: number;
  events: Record<string, number>;
  zero_result_searches: number;
  top_works: { work_id: string; work__title: string; opens: number; unique_sessions: number }[];
  top_queries: { normalized_query: string; search_count: number; unique_sessions: number; click_count: number; zero_result_count: number; click_through_rate: number }[];
  privacy: { stores_ip_identity: boolean; links_registered_user: boolean; retention_days: number };
};

export function AdminAnalytics() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const token = getServerSessionCredential();
    if (!token) return;
    void apiRequest<Analytics>("/catalog/admin/usage-analytics/?days=30", {}, token)
      .then(setData)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "统计读取失败。"));
  }, []);
  const cards = [
    ["匿名阅读会话", data?.anonymous_sessions ?? "—", BarChart3],
    ["图书打开", data?.events.reader_open ?? "—", BookOpen],
    ["搜索提交", data?.events.search_submit ?? "—", Search],
    ["下载", data?.events.download ?? "—", Download],
  ] as const;
  return (
    <div className="admin-page analytics-page">
      <header className="admin-page-title"><div><p>数据分析</p><h1>阅读与搜索统计</h1><span>只使用第一方匿名会话做聚合，不以 IP 标识读者，也不与注册账号永久关联。</span></div></header>
      {error ? <p className="review-error">{error}</p> : null}
      <section className="metric-grid">{cards.map(([label, value, Icon]) => <article key={label}><header><span>{label}</span><Icon size={15} /></header><div><strong>{value}</strong></div><p>最近 30 天</p></article>)}</section>
      <div className="admin-grid top">
        <section className="admin-panel"><h2>热门馆藏</h2>{(data?.top_works ?? []).map((item) => <p className="status-count-row" key={item.work_id}><span>{item.work__title}</span><strong>{item.opens} 次 · {item.unique_sessions} 会话</strong></p>)}{data && !data.top_works.length ? <p className="empty-state">尚无匿名阅读事件。</p> : null}</section>
        <section className="admin-panel"><h2>搜索质量</h2><p className="status-count-row"><span>无结果搜索</span><strong>{data?.zero_result_searches ?? "—"}</strong></p><p className="status-count-row"><span>结果点击</span><strong>{data?.events.search_result_click ?? "—"}</strong></p><p className="empty-state">原始事件保留 {data?.privacy.retention_days ?? 90} 天，长期仅保留聚合。</p></section>
      </div>
      <section className="admin-panel"><h2>热门搜索</h2><div className="admin-table-scroll"><table><thead><tr><th>规范化查询</th><th>搜索</th><th>匿名会话</th><th>点击</th><th>点击率</th><th>无结果</th></tr></thead><tbody>{(data?.top_queries ?? []).map((item) => <tr key={item.normalized_query}><td>{item.normalized_query}</td><td>{item.search_count}</td><td>{item.unique_sessions}</td><td>{item.click_count}</td><td>{Math.round(item.click_through_rate * 100)}%</td><td>{item.zero_result_count}</td></tr>)}{data && !data.top_queries.length ? <tr><td colSpan={6}>尚无达到聚合条件的搜索。</td></tr> : null}</tbody></table></div></section>
    </div>
  );
}
