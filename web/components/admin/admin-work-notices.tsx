"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { Bell, RefreshCw } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { useAdminSession } from "@/lib/admin-session";
import { safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import type { components } from "@/lib/api/generated/schema";

export function AdminWorkNotices() {
  const user = useAdminSession();
  const pathname = usePathname(), search = useSearchParams();
  const resource = useApiResource<components["schemas"]["WorkNotices"]>("/catalog/admin/work-notices/", user ? getServerSessionCredential() : null, `${user?.id}:${pathname}`);
  const data = resource.data;
  const returnTo = `${pathname}${search.size ? `?${search}` : ""}`;
  return <details className="stl4-work-notices" data-action-menu data-menu-width="390" onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
    <summary aria-label={data ? `工作提醒，${data.count}项需要处理` : resource.error ? "工作提醒读取失败" : "工作提醒正在读取"}><Bell size={18} />{data && data.count > 0 ? <span className="stl4-notice-count">{data.count > 99 ? "99+" : data.count}</span> : resource.error ? <span className="stl4-notice-error">!</span> : null}</summary>
    <section aria-label="工作提醒" data-menu-panel>
      <header><strong>需要处理的提醒</strong><button type="button" data-menu-stay-open aria-label="刷新工作提醒" disabled={resource.loading} onClick={resource.retry}><RefreshCw size={14} /></button></header>
      {resource.loading ? <LoadingState variant="compact" role="status">正在读取工作记录…</LoadingState> : resource.error ? <div role="alert"><p>{resource.error}</p><button data-menu-stay-open type="button" onClick={resource.retry}>重试读取</button></div> : data ? <>
        <p>失败、暂停或部分完成的当前工作，共 {data.count} 项。</p>
        {data.results.length ? <ul>{data.results.map(row => { const href = safeAdminHref(row.url, ""); return <li key={row.id}>{href ? <Link href={withAdminReturn(href, returnTo)} prefetch={false} onClick={event => { const details = event.currentTarget.closest("details"); if (details) details.open = false; }}><strong>{row.title || "未命名条目"}</strong><span>{row.label} · {row.state_label}</span></Link> : <span>{row.title} · 工作位置待核对</span>}</li>; })}</ul> : <p>当前没有需要处理的提醒。</p>}
        <footer><time dateTime={data.checked_at}>更新于 {new Date(data.checked_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false })}</time><Link href="/admin?category=problems" onClick={event => { const details = event.currentTarget.closest("details"); if (details) details.open = false; }}>查看待处理问题</Link></footer>
      </> : null}
    </section>
  </details>;
}
