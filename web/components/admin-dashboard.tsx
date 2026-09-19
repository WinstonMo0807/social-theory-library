"use client";

import Link from "next/link";
import {
  ArrowRight,
  FileText,
  Plus,
} from "lucide-react";
import { useMemo } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import { queueWorkbenchHref, sourceLabels, type WorkflowQueueItem, type WorkflowQueuePage } from "@/lib/api/admin-collections";
import { withAdminReturn } from "@/lib/admin-route-context";
import { EmptyState, PageHeader, StatusBadge, type StatusTone } from "./admin-ui";

type MetadataCandidate = {
  id: string;
  field_name: string;
  value: unknown;
  source: string;
  confidence: number;
};

type UploadItem = {
  id: string;
  source_filename: string;
  uploaded_by: string;
  title: string;
  status: string;
  stage_progress: number;
  error_message: string;
  recognized_metadata: Record<string, unknown>;
  metadata_candidates: MetadataCandidate[];
  created_at: string;
  updated_at: string;
};

type DashboardData = {
  documents: { total: number; published: number; withdrawn: number };
  pdf_assets: number;
  theory_schools: number;
  scholars: number;
  users: number;
  needs_review: number;
  processing: number;
  recent_items: UploadItem[];
  status_counts: Record<string, number>;
};

type UsageSummary = {
  anonymous_sessions: number;
  events: Record<string, number>;
  zero_result_searches: number;
};

type HotSearchPayload = {
  results: { query: string; search_count: number; unique_sessions: number; click_count: number; zero_result_count: number }[];
};

const statusLabels: Record<string, string> = {
  received: "已接收",
  validating: "校验中",
  deduplicating: "查重中",
  extracting: "提取中",
  ocr: "OCR 中",
  metadata: "识别元数据",
  linking: "建立关联",
  indexing: "建立索引",
  preparing_public_asset: "准备公开文件",
  syncing_cloud: "同步云端",
  ready: "可发布",
  published: "发布决定已保存",
  needs_review: "需要复核",
  failed: "失败",
  withdrawn: "已下架",
  deleted: "已删除",
};

const statusTones: Record<string, StatusTone> = {
  received: "neutral",
  validating: "info",
  deduplicating: "info",
  extracting: "info",
  ocr: "info",
  metadata: "info",
  linking: "info",
  indexing: "info",
  preparing_public_asset: "info",
  syncing_cloud: "info",
  ready: "success",
  published: "success",
  needs_review: "warning",
  failed: "danger",
  withdrawn: "warning",
  deleted: "danger",
};

export function AdminDashboard() {
  const user = useAdminSession();
  const credential = user ? getServerSessionCredential() : null;
  const contextKey = String(user?.id ?? "");
  const canViewAnalytics = hasAdminCapability(user, "can_view_audit_log");
  const canViewSystemStatus = hasAdminCapability(user, "can_view_system_status");
  const dashboard = useApiResource<DashboardData>("/ingestion/dashboard/", credential, contextKey);
  const queue = useApiResource<WorkflowQueuePage>("/catalog/admin/workflows/queue/", credential, contextKey);
  const analytics = useApiResource<UsageSummary>(canViewAnalytics ? "/catalog/admin/usage-analytics/?days=30" : "", credential, contextKey);
  const hot = useApiResource<HotSearchPayload>("/catalog/hot-searches/?days=30&limit=8", credential, contextKey);
  const live = dashboard.data;
  const error = dashboard.error;
  const workflowQueue = queue.data;
  const usage = analytics.data;
  const hotSearches = hot.data?.results ?? [];

  const totalItems = useMemo(
    () => Object.values(live?.status_counts ?? {}).reduce((sum, value) => sum + value, 0),
    [live?.status_counts],
  );
  const completedItems = live
    ? ["published", "needs_review", "ready", "failed", "withdrawn"]
        .reduce((sum, key) => sum + (live.status_counts[key] ?? 0), 0)
    : 0;
  const recognitionPercent = totalItems ? Math.round((completedItems / totalItems) * 100) : 0;
  const reviewItems = live?.recent_items.filter((item) =>
    ["needs_review", "failed"].includes(item.status),
  ) ?? [];
  const candidates = live?.recent_items.flatMap((item) =>
    item.metadata_candidates.map((candidate) => ({ item, candidate })),
  ).slice(0, 6) ?? [];
  const selectedReview = reviewItems[0];

  const displayCards = live
    ? [
        ["馆藏总量", String(live.documents.total), `${live.documents.published} 已公开`],
        ["PDF 文档", String(live.pdf_assets), "规范阅读副本"],
        ["理论流派", String(live.theory_schools), "公开与草稿合计"],
        ["学者", String(live.scholars), "人物档案"],
        ["账户", String(live.users), "不作为读者数量"],
        ["待复核", String(live.needs_review), `${live.processing} 处理中`],
      ]
    : ["馆藏总量", "PDF 文档", "理论流派", "学者", "账户", "待复核"]
        .map((label) => [label, "—", error ? "读取失败" : "正在读取"]);

  return (
    <div className="admin-dashboard">
      <PageHeader
        eyebrow="待办与上架"
        title="今日工作"
        description="继续当前馆藏，优先解决异常和人工确认，再处理发布准备。"
        actions={(
          <Link className="admin-outline-button" href="/admin/uploads">
            <Plus size={14} />
            快速上传
          </Link>
        )}
      />
      {error ? <p className="admin-error" role="alert">{error}<button type="button" onClick={dashboard.retry}>重新读取概况</button></p> : null}
      <section className="admin-work-entry-grid" aria-label="今日工作入口">
        {queue.error ? <p className="admin-error" role="alert">工作队列读取失败。{queue.error}<button type="button" onClick={queue.retry}>重试工作队列</button></p> : queue.loading ? <p role="status">正在读取工作队列…</p> : <>
        <WorkflowQueuePanel title="继续处理" total={workflowQueue?.counts?.continue} href="/admin/review?category=continue" items={workflowQueue?.continue_items ?? []} empty="当前没有中断的馆藏工作。" />
        <WorkflowQueuePanel title="待人工确认" total={workflowQueue?.counts?.attention} href="/admin/review?category=attention" items={workflowQueue?.attention_items ?? []} empty="当前没有待确认项目。" />
        <WorkflowQueuePanel title="异常" total={workflowQueue?.counts?.exception} href="/admin/review?category=exception" items={workflowQueue?.exception_items ?? []} empty="当前没有处理异常。" tone="danger" />
        <WorkflowQueuePanel title="待发布" total={workflowQueue?.counts?.publication_ready} href="/admin/review?category=publication_ready" items={workflowQueue?.publication_ready ?? []} empty="当前没有完成发布准备的项目。" step="publication" />
        <WorkflowQueuePanel title="较早待办" total={workflowQueue?.counts?.all} href="/admin/review?category=all" items={workflowQueue?.recent_items ?? []} empty="尚无待处理记录。" />
        </>}
        <section className="admin-panel admin-work-queue-panel">
          <header><h2>知识策展</h2><Link href="/admin/knowledge">打开字段工作台 <ArrowRight size={13} /></Link></header>
          <p>选择作品、学者、主题或理论，在需要补充的字段中查看依据并确认修改。</p>
        </section>
      </section>

      <header className="admin-dashboard-section-heading"><p>概况</p><h2>馆藏与运行摘要</h2></header>
      <section className="metric-grid">
        {displayCards.map(([label, value, detail]) => (
          <article key={label}>
            <header><span>{label}</span><small>⌃</small></header>
            <div><strong>{value}</strong><MetricMark /></div>
            <p><Plus size={11} />{detail}</p>
          </article>
        ))}
      </section>

      <div className="admin-grid top">
        <AdminPanel title="最近上传" href="/admin/uploads" className="recent-uploads-admin">
          <div className="admin-table">
            <header><span>文件名</span><span>上传者</span><span>日期</span><span>状态</span></header>
            {(live?.recent_items ?? []).slice(0, 6).map((item) => (
              <p key={item.id}>
                <span><FileText size={14} />{item.source_filename}</span>
                <span>{item.uploaded_by}</span>
                <span>{new Date(item.created_at).toLocaleDateString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</span>
                <span>
                  <StatusBadge
                    label={statusLabels[item.status] ?? item.status}
                    tone={statusTones[item.status] ?? "neutral"}
                  />
                </span>
              </p>
            ))}
            {live && !live.recent_items.length ? (
              <EmptyState compact title="尚无上传记录" description="上传 PDF 后，处理状态会显示在这里。" />
            ) : null}
          </div>
          <Link className="admin-panel-action" href="/admin/uploads"><Plus size={14} /> 上传新文档</Link>
        </AdminPanel>

        <AdminPanel title="上传阶段记录" href="/admin/uploads" className="recognition-panel">
          <div className="donut-wrap">
            <svg viewBox="0 0 120 120" aria-label={`初始上传处理已结束的记录占比 ${recognitionPercent}%，包含待复核和失败`}>
              <circle cx="60" cy="60" r="45" />
              <circle
                className="progress"
                cx="60"
                cy="60"
                r="45"
                pathLength="100"
                style={{ strokeDasharray: `${recognitionPercent} 100` }}
              />
              <text x="60" y="65">{recognitionPercent}%</text>
            </svg>
            <div>
              {[
                ["已保存发布决定", live?.status_counts.published ?? 0],
                ["需要复核", live?.status_counts.needs_review ?? 0],
                ["处理中", live?.processing ?? 0],
                ["失败", live?.status_counts.failed ?? 0],
              ].map(([label, count]) => (
                <p key={String(label)}><i /><span>{label}</span><strong>{count}</strong></p>
              ))}
            </div>
          </div>
          <p className="empty-state">分母为全部上传记录，分子为已结束初始处理阶段的记录，包含待复核和失败。不表示OCR质量、PDF可读或公开就绪。</p>
          <footer><span>上传项目总数</span><strong>{totalItems}</strong></footer>
        </AdminPanel>

        <AdminPanel title="最近上传异常" href="/admin/review?source=upload&category=attention" badge={String(reviewItems.length)} className="correction-queue">
          <div className="admin-table">
            <header><span>项目</span><span>问题</span><span>进度</span><span>操作</span></header>
            {reviewItems.slice(0, 6).map((item) => (
              <p key={item.id}>
                <span>{item.source_filename}</span>
                <span>{item.error_message || "元数据需要确认"}</span>
                <span>{item.stage_progress}%</span>
                <Link href={`/admin/intake/${item.id}#bibliography`}>继续 <ArrowRight size={13} /></Link>
              </p>
            ))}
            {live && !reviewItems.length ? <p className="empty-state">最近上传中没有待展示的异常；完整待办请查看全部。</p> : null}
          </div>
        </AdminPanel>
      </div>

      <div className="admin-grid middle">
        <AdminPanel title="最近上传的元数据候选" href="/admin/review?source=upload" badge={`本页 ${candidates.length}`}>
          {candidates.map(({ item, candidate }) => (
            <div className="candidate-row" key={candidate.id}>
              <span>{candidate.field_name}</span>
              <p><strong>{displayCandidate(candidate.value)}</strong><small>{item.source_filename} · {candidate.source}</small></p>
              <b>{Math.round(candidate.confidence * 100)}%</b>
              <Link href={`/admin/intake/${item.id}#bibliography`}>审核 <ArrowRight size={13} /></Link>
            </div>
          ))}
          {live && !candidates.length ? <p className="empty-state">最近项目没有待展示的识别候选。</p> : null}
        </AdminPanel>

        <AdminPanel title="处理状态" href="/admin/uploads">
          {Object.entries(live?.status_counts ?? {}).map(([key, count]) => (
            <p className="status-count-row" key={key}>
              <span>{statusLabels[key] ?? key}</span><strong>{count}</strong>
            </p>
          ))}
        </AdminPanel>

        {canViewAnalytics ? <AdminPanel title="匿名使用统计" href="/admin/analytics" className="user-chart-panel">
          {analytics.error ? <p role="alert">统计读取失败。{analytics.error}<button type="button" onClick={analytics.retry}>重试统计</button></p> : analytics.loading ? <p role="status">正在读取统计…</p> : null}
          <div className="chart-stats">
            <p><strong>{usage?.anonymous_sessions ?? "—"}</strong><span>最近 30 天匿名会话</span></p>
            <p><strong>{usage?.events.reader_open ?? "—"}</strong><span>图书打开次数</span></p>
          </div>
          <p className="empty-state">不保存 IP 身份，也不把匿名会话永久绑定到注册账号。</p>
        </AdminPanel> : null}

        <AdminPanel title="热门搜索" href={canViewAnalytics ? "/admin/analytics" : undefined}>
          {hot.error ? <p role="alert">热门搜索读取失败。{hot.error}<button type="button" onClick={hot.retry}>重试热门搜索</button></p> : hot.loading ? <p role="status">正在读取热门搜索…</p> : null}
          {hotSearches.map((item) => <p className="status-count-row" key={item.query}><span>{item.query}</span><strong>{item.search_count}</strong></p>)}
          {hot.data && !hotSearches.length ? <p className="empty-state">尚无达到匿名阈值的热门搜索。低频与敏感查询不会公开聚合。</p> : null}
        </AdminPanel>
      </div>

      <div className="admin-grid bottom">
        <AdminPanel title="系统健康" href={canViewSystemStatus ? "/admin/system-health" : undefined}>
          {[["Web 应用", "当前页面已加载"], ["数据库", live ? "摘要请求已返回，不代表全部功能" : "未取得摘要结果"], ["搜索索引", "需独立探测"]].map(([service, state]) => (
            <p className="health-row" key={service}><i /><strong>{service}</strong><span>{state}</span></p>
          ))}
        </AdminPanel>
        <AdminPanel title="馆藏编辑器" href={selectedReview ? `/admin/intake/${selectedReview.id}#bibliography` : "/admin/review"} className="metadata-editor-preview">
          {selectedReview ? Object.entries(selectedReview.recognized_metadata).slice(0, 6).map(([label, value]) => (
            <label key={label}><span>{label}</span><input value={displayCandidate(value)} readOnly /></label>
          )) : <p className="empty-state">待复核项目会在这里显示识别结果。</p>}
        </AdminPanel>
        <AdminPanel title="PDF 预览" href={selectedReview ? `/admin/intake/${selectedReview.id}#reader` : "/admin/review"} className="pdf-admin-preview">
          <div>
            <small>{selectedReview ? `${selectedReview.stage_progress}%` : "暂无文档"}</small>
            <h2>{selectedReview?.title || selectedReview?.source_filename || "等待上传"}</h2>
            <p>{selectedReview ? statusLabels[selectedReview.status] : "上传 PDF 后开始识别"}</p>
          </div>
        </AdminPanel>
        <AdminPanel title="入库动态" href="/admin/uploads">
          {(live?.recent_items ?? []).slice(0, 6).map((item) => (
            <div className="activity-row" key={item.id}>
              <FileText size={17} />
              <p><strong>{item.source_filename}</strong><span>{statusLabels[item.status] ?? item.status}</span></p>
              <small>{new Date(item.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Hong_Kong" })}</small>
            </div>
          ))}
        </AdminPanel>
      </div>
    </div>
  );
}

function WorkflowQueuePanel({
  title,
  total,
  href,
  items,
  empty,
  tone = "neutral",
  step,
}: {
  title: string;
  total?: number;
  href: string;
  items: WorkflowQueueItem[];
  empty: string;
  tone?: "neutral" | "danger";
  step?: string;
}) {
  return (
    <section className={`admin-panel admin-work-queue-panel tone-${tone}`}>
      <header><h2>{title}</h2><span>{total ?? "—"}</span><Link href={href}>查看全部 <ArrowRight size={13} /></Link></header>
      {items.slice(0, 4).map((item) => {
        const targetStep = step ?? item.current_step ?? "file";
        const issueCount = item.blockers_count + item.unresolved_count;
        const destination = queueWorkbenchHref(item);
        if (!destination) return <p key={item.id} role="status">{item.title}：工作位置待核实，请刷新。</p>;
        return (
          <Link className="admin-work-queue-item" href={withAdminReturn(destination, href, targetStep)} key={item.id}>
            <span><strong>{item.title || item.source_filename || "未命名馆藏"}</strong><small>{sourceLabels[item.source_type] || "来源待核实"} · {item.current_step_label || targetStep}</small></span>
            <b>{issueCount ? `${issueCount} 项` : "继续"}<ArrowRight size={13} /></b>
          </Link>
        );
      })}
      {!items.length ? <p className="empty-state">{empty}</p> : null}
      {items.length ? <p className="empty-state">仅展示前{Math.min(items.length, 4)}项。优先级优先，同级较早更新在前；完整数量来自全量查询。</p> : null}
    </section>
  );
}

function displayCandidate(value: unknown) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.join("、");
  if (value && typeof value === "object") return JSON.stringify(value);
  return "未识别";
}

function MetricMark() {
  return <svg className="sparkline" viewBox="0 0 75 36" aria-hidden><path d="M0 18H75" /></svg>;
}

function AdminPanel({
  title,
  href,
  badge,
  className = "",
  children,
}: {
  title: string;
  href?: string;
  badge?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`admin-panel ${className}`}>
      <header><h2>{title}</h2>{href ? <Link href={href}>查看全部 <ArrowRight size={13} /></Link> : null}{badge ? <b>{badge}</b> : null}</header>
      {children}
    </section>
  );
}
