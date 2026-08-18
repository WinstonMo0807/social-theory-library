"use client";

import Link from "next/link";
import {
  ArrowRight,
  FileText,
  Plus,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
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
  published: "已发布",
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
  const [live, setLive] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [hotSearches, setHotSearches] = useState<HotSearchPayload["results"]>([]);

  useEffect(() => {
    const token = getServerSessionCredential();
    if (!token) return;
    apiRequest<DashboardData>("/ingestion/dashboard/", {}, token)
      .then(setLive)
      .catch((reason) => setError(reason instanceof Error ? reason.message : "仪表盘读取失败。"));
    apiRequest<UsageSummary>("/catalog/admin/usage-analytics/?days=30", {}, token).then(setUsage).catch(() => undefined);
    apiRequest<HotSearchPayload>("/catalog/hot-searches/?days=30&limit=8", {}, token).then((payload) => setHotSearches(payload.results)).catch(() => undefined);
  }, []);

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
        ["馆藏总量", String(live.documents.total), `${live.documents.published} 已发布`],
        ["PDF 文档", String(live.pdf_assets), "规范阅读副本"],
        ["理论流派", String(live.theory_schools), "公开与草稿合计"],
        ["学者", String(live.scholars), "人物档案"],
        ["账户", String(live.users), "不作为读者数量"],
        ["待复核", String(live.needs_review), `${live.processing} 处理中`],
      ]
    : [
        ["馆藏总量", "—", "正在读取"],
        ["PDF 文档", "—", "正在读取"],
        ["理论流派", "—", "正在读取"],
        ["学者", "—", "正在读取"],
        ["账户", "—", "正在读取"],
        ["待复核", "—", "正在读取"],
      ];

  return (
    <div className="admin-dashboard">
      <PageHeader
        eyebrow="概览"
        title="管理概览"
        description="查看馆藏处理、人工复核、读者使用和系统状态。"
        actions={(
          <Link className="admin-outline-button" href="/admin/uploads">
            <Plus size={14} />
            快速上传
          </Link>
        )}
      />
      {error ? <p className="admin-error" role="alert">{error}</p> : null}
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

        <AdminPanel title="OCR 与元数据识别" href="/admin/uploads" className="recognition-panel">
          <div className="donut-wrap">
            <svg viewBox="0 0 120 120" aria-label={`处理进度 ${recognitionPercent}%`}>
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
                ["已发布", live?.status_counts.published ?? 0],
                ["需要复核", live?.status_counts.needs_review ?? 0],
                ["处理中", live?.processing ?? 0],
                ["失败", live?.status_counts.failed ?? 0],
              ].map(([label, count]) => (
                <p key={String(label)}><i /><span>{label}</span><strong>{count}</strong></p>
              ))}
            </div>
          </div>
          <footer><span>上传项目总数</span><strong>{totalItems}</strong></footer>
        </AdminPanel>

        <AdminPanel title="修正队列" href="/admin/review" badge={String(live?.needs_review ?? 0)} className="correction-queue">
          <div className="admin-table">
            <header><span>项目</span><span>问题</span><span>进度</span><span>操作</span></header>
            {reviewItems.slice(0, 6).map((item) => (
              <p key={item.id}>
                <span>{item.source_filename}</span>
                <span>{item.error_message || "元数据需要确认"}</span>
                <span>{item.stage_progress}%</span>
                <Link href={`/admin/review/${item.id}`}>复核 <ArrowRight size={13} /></Link>
              </p>
            ))}
            {live && !reviewItems.length ? <p className="empty-state">当前没有需要人工处理的项目。</p> : null}
          </div>
        </AdminPanel>
      </div>

      <div className="admin-grid middle">
        <AdminPanel title="元数据候选" href="/admin/review" badge={String(candidates.length)}>
          {candidates.map(({ item, candidate }) => (
            <div className="candidate-row" key={candidate.id}>
              <span>{candidate.field_name}</span>
              <p><strong>{displayCandidate(candidate.value)}</strong><small>{item.source_filename} · {candidate.source}</small></p>
              <b>{Math.round(candidate.confidence * 100)}%</b>
              <Link href={`/admin/review/${item.id}`}>复核 <ArrowRight size={13} /></Link>
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

        <AdminPanel title="匿名使用统计" href="/admin/analytics" className="user-chart-panel">
          <div className="chart-stats">
            <p><strong>{usage?.anonymous_sessions ?? "—"}</strong><span>最近 30 天匿名会话</span></p>
            <p><strong>{usage?.events.reader_open ?? "—"}</strong><span>图书打开次数</span></p>
          </div>
          <p className="empty-state">不保存 IP 身份，也不把匿名会话永久绑定到注册账号。</p>
        </AdminPanel>

        <AdminPanel title="热门搜索" href="/admin/analytics">
          {hotSearches.map((item) => <p className="status-count-row" key={item.query}><span>{item.query}</span><strong>{item.search_count}</strong></p>)}
          {!hotSearches.length ? <p className="empty-state">尚无达到匿名阈值的热门搜索。低频与敏感查询不会公开聚合。</p> : null}
        </AdminPanel>
      </div>

      <div className="admin-grid bottom">
        <AdminPanel title="系统健康" href="/admin/system-health">
          {[["Web 应用", "已连接"], ["数据库", live ? "可查询" : "等待"], ["搜索索引", "需独立探测"]].map(([service, state]) => (
            <p className="health-row" key={service}><i /><strong>{service}</strong><span>{state}</span></p>
          ))}
        </AdminPanel>
        <AdminPanel title="元数据编辑器" href={selectedReview ? `/admin/review/${selectedReview.id}` : "/admin/review"} className="metadata-editor-preview">
          {selectedReview ? Object.entries(selectedReview.recognized_metadata).slice(0, 6).map(([label, value]) => (
            <label key={label}><span>{label}</span><input value={displayCandidate(value)} readOnly /></label>
          )) : <p className="empty-state">待复核项目会在这里显示识别结果。</p>}
        </AdminPanel>
        <AdminPanel title="PDF 预览" href={selectedReview ? `/admin/review/${selectedReview.id}` : "/admin/review"} className="pdf-admin-preview">
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
