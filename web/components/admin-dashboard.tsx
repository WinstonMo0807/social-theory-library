"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, FileText, Plus, Tags, UserRound, CircleDot, Sparkles, AlertTriangle, Upload } from "lucide-react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { useAdminSession } from "@/lib/admin-session";
import { documentLabels, queueWorkbenchHref, type WorkflowQueueItem, type WorkflowQueuePage } from "@/lib/api/admin-collections";
import { withAdminReturn } from "@/lib/admin-route-context";
import { PageHeader, StatusBadge } from "./admin-ui";

type DashboardData = {
  documents: { total: number; published: number; withdrawn: number };
  needs_review: number; processing: number;
  recent_items: { id: string; title: string; source_filename: string; status: string; created_at: string; updated_at: string }[];
};

function deduplicate(items: WorkflowQueueItem[]) {
  const seen = new Set<string>();
  return items.filter(item => {
    const key = item.edition_id || item.work_id || item.item_id || item.id;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function AdminDashboard() {
  const user = useAdminSession();
  const credential = user ? getServerSessionCredential() : null;
  const context = String(user?.id ?? "");
  const dashboard = useApiResource<DashboardData>("/ingestion/dashboard/", credential, context);
  const queue = useApiResource<WorkflowQueuePage>("/catalog/admin/workflows/queue/?category=all&page_size=8", credential, context);
  const items = deduplicate(queue.data?.results ?? []).slice(0, 8);
  const cards = [
    { title: "未完成馆藏", value: queue.data?.counts.all, detail: "当前需要处理的出版版本", href: "/admin/review", Icon: BookOpen },
    { title: "需要处理的异常", value: queue.data?.counts.exception, detail: "查看原因与下一步", href: "/admin/review?category=exception", Icon: AlertTriangle },
    { title: "等待发布检查", value: queue.data?.counts.publication_ready, detail: "请核对后明确发布", href: "/admin/review?category=publication_ready", Icon: FileText },
    { title: "已公开馆藏", value: dashboard.data?.documents.published, detail: "来自当前馆藏汇总", href: "/admin/library?view=published", Icon: Upload },
  ];
  const shortcuts = [
    {href:"/admin/topics", title:"主题", Icon:Tags}, {href:"/admin/scholars", title:"学者", Icon:UserRound},
    {href:"/admin/theories", title:"理论流派", Icon:CircleDot}, {href:"/admin/recommendations", title:"本期书库推荐", Icon:Sparkles},
  ];
  return <div className="admin-dashboard admin-v307-dashboard">
    <PageHeader eyebrow="管理后台" title="今日工作" description="继续整理未完成的馆藏，处理异常，或开始一次策展。" actions={<Link className="button" href="/admin/uploads"><Plus size={16} />上传 PDF</Link>} />
    {dashboard.error ? <p className="admin-error" role="alert">{dashboard.error}<button type="button" onClick={dashboard.retry}>重新读取概况</button></p> : null}
    <section className="admin-v307-metrics" aria-label="工作概况">{cards.map(({ title, value, detail, href, Icon }) => <Link href={href} key={title}><Icon size={25} /><div><span>{title}</span><strong>{value ?? "—"}<small>项</small></strong><p>{detail}</p></div></Link>)}</section>
    <div className="admin-v307-day-grid">
      <section className="admin-panel admin-v307-unfinished"><header><div><h2>未完成的馆藏</h2><p>每个出版版本只列一次，直接进入当前需要处理的位置。</p></div><Link href="/admin/review">查看全部 <ArrowRight size={14} /></Link></header>
        {queue.error ? <p className="admin-error" role="alert">{queue.error}<button type="button" onClick={queue.retry}>重试工作队列</button></p> : null}
        {queue.loading ? <p role="status">正在读取待办…</p> : null}
        <div className="admin-v307-table-scroll"><table><thead><tr><th>馆藏信息</th><th>类型</th><th>当前工作</th><th>最近更新</th><th>操作</th></tr></thead><tbody>{items.map(item => {
          const destination = queueWorkbenchHref(item);
          return <tr key={item.id}><td><strong>{item.title || item.source_filename || "未命名馆藏"}</strong>{item.source_filename ? <small>{item.source_filename}</small> : null}</td><td>{documentLabels[item.document_type || ""] || "待确认"}</td><td><StatusBadge label={item.current_step_label || "继续编辑"} tone={item.blockers_count ? "warning" : "neutral"} /><small>{item.blockers_count ? `${item.blockers_count} 项需要处理` : item.unresolved_count ? `${item.unresolved_count} 项待确认` : "核对预览与发布"}</small></td><td><time>{new Date(item.updated_at).toLocaleDateString("zh-CN")}</time></td><td>{destination ? <Link className="button secondary" href={withAdminReturn(destination, "/admin", item.current_step)}>继续处理 <ArrowRight size={13} /></Link> : <span>工作位置待核实</span>}</td></tr>;
        })}</tbody></table></div>
        {queue.data && !items.length ? <p className="admin-list-state">当前没有未完成的馆藏。</p> : null}
      </section>
      <aside className="admin-v307-day-aside"><section className="admin-panel"><header><h2>最近上传</h2><Link href="/admin/uploads">查看全部 <ArrowRight size={14} /></Link></header>{dashboard.data?.recent_items.slice(0, 5).map(item => <Link className="admin-v307-recent" key={item.id} href={withAdminReturn(`/admin/intake/${item.id}`, "/admin")}><FileText size={28} /><div><strong>{item.title || item.source_filename}</strong><time>{new Date(item.created_at).toLocaleDateString("zh-CN")}</time></div><ArrowRight size={14} /></Link>)}{dashboard.data && !dashboard.data.recent_items.length ? <p className="admin-list-state">尚无上传记录。</p> : null}</section>
        <section className="admin-panel"><header><h2>策展快捷入口</h2><Link href="/admin/review?workspace=curation">继续草稿 <ArrowRight size={14} /></Link></header>{shortcuts.map(({href,title,Icon}) => <Link className="admin-v307-quick" key={href} href={href}><Icon size={21} /><strong>{title}</strong><ArrowRight size={14} /></Link>)}</section>
      </aside>
    </div>
  </div>;
}
