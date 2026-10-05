"use client";

import { BarChart3, BookOpen, Users, Search } from "lucide-react";
import { useState } from "react";
import { AdminPublicPreviewFrame } from "@/components/admin/admin-public-preview-frame";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";

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
  const user = useAdminSession();
  const allowed = hasAdminCapability(user, "can_view_audit_log");
  const [days,setDays]=useState(30);
  const [selected,setSelected]=useState("");
  const { data, error, retry } = useApiResource<Analytics>(allowed ? `/catalog/admin/usage-analytics/?days=${days}` : "", user ? getServerSessionCredential() : null, String(user?.id ?? ""));
  if (!allowed) return <div className="admin-page"><h1>当前账户没有统计查看权限</h1><p>请返回今日工作继续编目。</p></div>;
  const cards = [["页面浏览量", "—", BarChart3],["匿名阅读会话",data?.anonymous_sessions ?? "—",Users],["站内搜索次数",data?.events.search_submit ?? "—",Search],["馆藏阅读次数",data?.events.reader_open ?? "—",BookOpen]] as const;
  const zeroQueries=(data?.top_queries || []).filter(row=>row.zero_result_count>0).sort((a,b)=>b.zero_result_count-a.zero_result_count).slice(0,5);
  const selectedUrl=selected || (zeroQueries[0] ? `/explore?q=${encodeURIComponent(zeroQueries[0].normalized_query)}` : "");
  return <div className="admin-page analytics-page analytics-reference"><header className="admin-page-title"><div><h1>使用统计</h1><span>查看读者如何使用书库，了解哪些内容受欢迎，并发现可以改进的地方。</span></div></header><div className="analytics-reference-period"><select aria-label="统计范围" value={days} onChange={event=>{setDays(Number(event.target.value));setSelected("");}}>{[7,30,90,365].map(value=><option key={value} value={value}>最近 {value} 天</option>)}</select><p>数据为匿名聚合统计，不包含个人信息、私人笔记或 IP 地址。</p></div>
    {error ? <p role="alert">{error}<button type="button" onClick={retry}>重试统计</button></p> : null}
    <section className="metric-grid">{cards.map(([label,value,Icon])=><article key={label}><Icon size={25}/><div><span>{label}</span><strong>{value}</strong><small>较上期　—</small></div></article>)}</section>
    <div className="analytics-reference-columns"><div><section className="admin-panel"><h2>阅读与搜索趋势</h2><div className="analytics-reference-chart" aria-label="当前接口未提供按日趋势">—</div></section><section className="admin-panel"><h2>热门馆藏 <small>按阅读次数</small></h2><table><thead><tr><th>#</th><th>书名</th><th>阅读次数</th><th>匿名会话</th><th>操作</th></tr></thead><tbody>{(data?.top_works || []).map((row,index)=><tr key={row.work_id}><td>{index+1}</td><td>{row.work__title}</td><td>{row.opens}</td><td>{row.unique_sessions}</td><td><button type="button" onClick={()=>setSelected(`/works/${row.work_id}`)}>查看</button></td></tr>)}</tbody></table>{data && !data.top_works.length ? <p>尚无匿名阅读记录。</p> : null}</section><section className="admin-panel"><h2>热门无结果查询 <small>当前热门查询中的前 5 项</small></h2><table><thead><tr><th>#</th><th>查询关键词</th><th>无结果次数</th><th>操作</th></tr></thead><tbody>{zeroQueries.map((row,index)=><tr key={row.normalized_query}><td>{index+1}</td><td>{row.normalized_query}</td><td>{row.zero_result_count}</td><td><button type="button" onClick={()=>setSelected(`/explore?q=${encodeURIComponent(row.normalized_query)}`)}>在馆藏中检索</button></td></tr>)}</tbody></table>{data && !zeroQueries.length ? <p>当前没有达到聚合条件的无结果查询。</p> : null}</section></div><AdminPublicPreviewFrame title="读者会看到什么" description="选择查询或热门馆藏，查看它在前台的实际呈现。" src={selectedUrl || null}><select aria-label="预览查询与馆藏" value={selectedUrl} onChange={event=>setSelected(event.target.value)}><option value="">选择内容</option>{zeroQueries.map(row=><option key={row.normalized_query} value={`/explore?q=${encodeURIComponent(row.normalized_query)}`}>无结果查询：{row.normalized_query}</option>)}{(data?.top_works || []).map(row=><option key={row.work_id} value={`/works/${row.work_id}`}>{row.work__title}</option>)}</select></AdminPublicPreviewFrame></div>
  </div>;
}
