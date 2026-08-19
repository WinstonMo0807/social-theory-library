"use client";

import Link from "next/link";
import {
  AlertCircle,
  CheckCircle2,
  ClipboardCheck,
  ChevronRight,
  Clock3,
  Cpu,
  FileText,
  LoaderCircle,
  PauseCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { ConfirmDialog } from "./confirm-dialog";

type Attempt = {
  id: string;
  stage: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  error_message: string;
};

type ProcessingItem = {
  id: string;
  edition: string | null;
  source_filename: string;
  status: string;
  stage_progress: number;
  error_code: string;
  error_message: string;
  updated_at: string;
  review_data: { title: string } | null;
  attempts: Attempt[];
  is_stalled: boolean;
  stalled_seconds: number;
  suggested_action: "retry" | "resume" | "review" | "";
  queue_mode: "inline" | "worker";
  dispatch_status: "pending" | "queued" | "running" | "completed" | "failed";
  dispatch_attempts: number;
  dispatch_error: string;
};

type Paginated<T> = { count: number; results: T[] };
type QueueHealth = {
  mode: "inline" | "worker";
  worker_required: boolean;
  stalled_count: number;
  pending_dispatches: number;
  healthy: boolean;
  broker_reachable: boolean;
  worker_online: boolean;
  ocr: { configured: boolean; reachable: boolean; detail: string };
  search: { configured: boolean; reachable: boolean; detail: string };
  message: string;
};

type ProcessingJob = {
  id: string;
  source: "processing_job" | "semantic_index_job";
  job_type: string;
  item_id: string | null;
  asset_id: string | null;
  title: string;
  status: "pending" | "running" | "paused" | "succeeded" | "failed" | "canceled";
  progress: number;
  engine: string;
  attempt: number;
  max_attempts: number;
  settings_version: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  last_error: string;
  error_code: string;
  stats?: Record<string, unknown>;
};

type ProcessingJobsPayload = {
  results: ProcessingJob[];
  counts: Record<string, number>;
  workloads: Record<string, { paused: boolean }>;
};
type ReviewTask = {
  id: string;
  upload_item: string | null;
  task_type: string;
  target_type: string;
  title: string;
  details: Record<string, unknown>;
  status: "pending" | "in_progress" | "completed" | "cancelled";
  priority: number;
  assigned_to: string | null;
  assigned_to_name: string;
  due_at: string | null;
  created_at: string;
  item_title: string;
  source_filename: string;
};
type ReviewTasksPayload = {
  count: number;
  counts: Record<string, number>;
  can_manage: boolean;
  results: ReviewTask[];
};
type SemanticHealthPayload = {
  runtime: {
    enabled: boolean;
    model: string;
    model_repo_id: string;
    model_revision: string;
    semantic_ratio: number;
    offline_mode: boolean;
  };
  model_health: { available: boolean | null; reason: string };
  documents: { eligible: number; indexed: number; pending: number; failed: number };
};

const jobLabels: Record<string, string> = {
  ocr: "OCR",
  external_enrichment: "联网补充",
  text_extraction: "文本提取",
  page_labels: "页码识别",
  semantic_index: "语义索引",
  thumbnail: "缩略图",
  cache_refresh: "缓存刷新",
};

const statusLabels: Record<string, string> = {
  pending: "等待",
  running: "运行中",
  paused: "已暂停",
  succeeded: "成功",
  failed: "失败",
  canceled: "已取消",
};

const reviewStatusLabels: Record<string, string> = {
  pending: "待领取",
  in_progress: "处理中",
  completed: "已完成",
  cancelled: "已取消",
};

const reviewTypeLabels: Record<string, string> = {
  entity_resolution: "实体消歧",
  metadata_conflict: "元数据冲突",
  duplicate_person: "同名人物",
  page_labels: "页码校对",
  publication: "发布检查",
};

const stageLabels: Record<string, string> = {
  received: "等待处理",
  validating: "校验 PDF",
  extracting: "提取逐页文本",
  ocr: "PaddleOCR",
  metadata: "识别元数据",
  linking: "建立知识关联",
  indexing: "建立全文索引",
  syncing_cloud: "同步在线副本",
  ready: "等待发布",
  needs_review: "等待人工复核",
  failed: "处理失败",
};

function durationLabel(seconds: number | null) {
  if (seconds === null) return "尚未开始";
  if (seconds < 60) return `${Math.round(seconds)} 秒`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分 ${Math.round(seconds % 60)} 秒`;
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`;
}

function timeLabel(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

export function ProcessingCenter() {
  const [items, setItems] = useState<ProcessingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [queueHealth, setQueueHealth] = useState<QueueHealth | null>(null);
  const [semanticHealth, setSemanticHealth] = useState<SemanticHealthPayload | null>(null);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [workloads, setWorkloads] = useState<Record<string, { paused: boolean }>>({});
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [reviewCounts, setReviewCounts] = useState<Record<string, number>>({});
  const [canManageReviewTasks, setCanManageReviewTasks] = useState(false);
  const [reviewStatus, setReviewStatus] = useState("pending");
  const [jobType, setJobType] = useState("");
  const [jobStatus, setJobStatus] = useState("");
  const [filtersReady, setFiltersReady] = useState(false);
  const [revision, setRevision] = useState(0);
  const [removeTarget, setRemoveTarget] = useState<ProcessingItem | null>(null);
  const [actionPending, setActionPending] = useState(false);

  const load = useCallback(async () => {
    const token = getServerSessionCredential();
    if (!token) return;
    try {
      const [itemsResult, healthResult, jobsResult, semanticResult, reviewResult] = await Promise.allSettled([
        apiRequest<Paginated<ProcessingItem>>(
          "/ingestion/items/?scope=processing&ordering=-updated_at&page_size=100",
          {},
          token,
        ),
        apiRequest<QueueHealth>("/ingestion/queue-health/", {}, token),
        apiRequest<ProcessingJobsPayload>("/ingestion/processing-center/", {}, token),
        apiRequest<SemanticHealthPayload>("/catalog/admin/semantic-index/", {}, token),
        apiRequest<ReviewTasksPayload>(
          `/ingestion/review-tasks/?page_size=100${reviewStatus ? `&status=${encodeURIComponent(reviewStatus)}` : ""}`,
          {},
          token,
        ),
      ]);
      if (itemsResult.status === "fulfilled") {
        setItems(itemsResult.value.results);
        setError("");
      } else {
        throw itemsResult.reason;
      }
      setQueueHealth(healthResult.status === "fulfilled" ? healthResult.value : null);
      setSemanticHealth(semanticResult.status === "fulfilled" ? semanticResult.value : null);
      setJobs(jobsResult.status === "fulfilled" ? jobsResult.value.results : []);
      setWorkloads(jobsResult.status === "fulfilled" ? (jobsResult.value.workloads ?? {}) : {});
      if (reviewResult.status === "fulfilled") {
        setReviewTasks(reviewResult.value.results);
        setReviewCounts(reviewResult.value.counts);
        setCanManageReviewTasks(reviewResult.value.can_manage);
      } else {
        setReviewTasks([]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "处理中心加载失败。");
    } finally {
      setLoading(false);
    }
  }, [reviewStatus]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const parameters = new URLSearchParams(window.location.search);
      setJobType(parameters.get("type") ?? "");
      setJobStatus(parameters.get("status") ?? "");
      setReviewStatus(parameters.get("review_status") ?? "pending");
      setFiltersReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!filtersReady) return;
    const url = new URL(window.location.href);
    if (jobType) url.searchParams.set("type", jobType); else url.searchParams.delete("type");
    if (jobStatus) url.searchParams.set("status", jobStatus); else url.searchParams.delete("status");
    if (reviewStatus) url.searchParams.set("review_status", reviewStatus); else url.searchParams.delete("review_status");
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [filtersReady, jobStatus, jobType, reviewStatus]);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(load, 10000);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [load, revision]);

  async function retry(item: ProcessingItem) {
    const token = getServerSessionCredential();
    if (!token) return;
    setMessage("");
    try {
      const action = item.suggested_action === "resume" && item.edition ? "resume" : "retry";
      await apiRequest(`/ingestion/items/${item.id}/${action}/`, { method: "POST" }, token);
      setMessage(`${item.source_filename} 已重新进入处理队列。`);
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "重试失败。");
    }
  }

  async function removeConfirmed() {
    const token = getServerSessionCredential();
    if (!token || !removeTarget) return;
    const label = removeTarget.review_data?.title || removeTarget.source_filename;
    setActionPending(true);
    try {
      await apiRequest(`/ingestion/items/${removeTarget.id}/delete/`, {
        method: "POST",
        body: JSON.stringify({ confirmed: true }),
      }, token);
      setMessage(`${label} 已从处理队列移除。NAS 原文件和审计记录仍保留。`);
      setRemoveTarget(null);
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "移除失败。");
    } finally {
      setActionPending(false);
    }
  }

  async function jobAction(job: ProcessingJob, action: "retry" | "cancel" | "pause" | "resume") {
    const token = getServerSessionCredential();
    if (!token) return;
    setMessage("");
    try {
      await apiRequest("/ingestion/processing-center/", {
        method: "POST",
        body: JSON.stringify({ action, source: job.source, job_id: job.id }),
      }, token);
      setMessage(
        action === "retry" ? "处理任务已经重新排队。"
          : action === "pause" ? "暂停请求已记录，运行中的任务会在安全检查点暂停。"
            : action === "resume" ? "已暂停任务从保存进度恢复。"
              : "等待中的任务已经取消。",
      );
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "任务操作失败。");
    }
  }

  async function workloadAction(type: "ocr" | "external_enrichment", paused: boolean) {
    const token = getServerSessionCredential();
    if (!token) return;
    setMessage("");
    try {
      await apiRequest("/ingestion/processing-center/", {
        method: "POST",
        body: JSON.stringify({
          action: paused ? "pause_workload" : "resume_workload",
          job_type: type,
        }),
      }, token);
      setMessage(paused ? `${jobLabels[type]} 已请求暂停。当前批次保存后生效。` : `${jobLabels[type]} 已恢复，已保存任务会继续运行。`);
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "任务负载操作失败。");
    }
  }

  async function reviewTaskAction(task: ReviewTask, action: "assign_self" | "complete" | "reopen") {
    const token = getServerSessionCredential();
    if (!token) return;
    setMessage("");
    try {
      await apiRequest(`/ingestion/review-tasks/${task.id}/action/`, {
        method: "POST",
        body: JSON.stringify({ action }),
      }, token);
      setMessage(action === "assign_self" ? "审核任务已领取。" : action === "complete" ? "审核任务已完成。" : "审核任务已恢复。 ");
      setRevision((value) => value + 1);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "审核任务操作失败。");
    }
  }

  const statusCounts = useMemo(() => Object.fromEntries(
    ["pending", "running", "paused", "succeeded", "failed", "canceled"].map((status) => [
      status,
      jobs.filter((job) => job.status === status).length,
    ]),
  ), [jobs]);
  const typeCounts = useMemo(() => Object.fromEntries(
    Object.keys(jobLabels).map((type) => [type, jobs.filter((job) => job.job_type === type).length]),
  ), [jobs]);
  const filteredJobs = useMemo(() => jobs.filter((job) => (
    (!jobType || job.job_type === jobType) && (!jobStatus || job.status === jobStatus)
  )), [jobStatus, jobType, jobs]);
  const historicalNetworkFailures = useMemo(() => jobs.filter((job) => (
    job.job_type === "semantic_index"
    && job.status === "failed"
    && /huggingface|dns|name or service|network unreachable|resolve/i.test(`${job.error_code} ${job.last_error}`)
  )).length, [jobs]);
  const summary = useMemo(() => ({
    active: statusCounts.pending + statusCounts.running,
    review: items.filter((item) => item.status === "needs_review").length,
    failed: statusCounts.failed,
    succeeded: statusCounts.succeeded,
  }), [items, statusCounts]);

  return (
    <div className="admin-page processing-center-page">
      <header className="admin-page-title">
        <div><p>运行状态</p><h1>处理中心</h1><span>按任务类型和状态查看 OCR、页码与语义索引，并保留每次失败的完整记录。</span></div>
        <div className="admin-action-row"><Link className="button secondary" href="/admin/publication">前往发布台 <ChevronRight size={15} /></Link><button className="button secondary" type="button" onClick={() => setRevision((value) => value + 1)}><RefreshCw size={15} />刷新</button></div>
      </header>
      <section className="processing-summary">
        <article><Clock3 size={18} /><strong>{summary.active}</strong><span>等待或运行</span></article>
        <article><FileText size={18} /><strong>{summary.review}</strong><span>待复核</span></article>
        <article><AlertCircle size={18} /><strong>{summary.failed}</strong><span>失败</span></article>
        <article><CheckCircle2 size={18} /><strong>{summary.succeeded}</strong><span>成功</span></article>
      </section>
      <div className="processing-health-grid">
        {queueHealth ? (
          <section className={`processing-health ${!queueHealth.healthy || queueHealth.stalled_count ? "warning" : ""}`} role="status">
            <Cpu size={18} /><div><strong>{queueHealth.mode === "inline" ? "本地同步处理" : "后台工作者"}</strong><span>{queueHealth.message}</span></div>
            <dl><div><dt>worker</dt><dd>{queueHealth.worker_online ? "在线" : "未确认"}</dd></div><div><dt>OCR</dt><dd>{queueHealth.ocr.reachable ? "可用" : queueHealth.ocr.detail}</dd></div></dl>
          </section>
        ) : null}
        <section className={`processing-semantic-health ${semanticHealth?.model_health.available === false ? "warning" : ""}`}>
          <Search size={18} />
          <div><strong>{semanticHealth?.model_health.available === true ? "当前语义模型可用" : semanticHealth?.model_health.available === false ? "当前语义模型不可用" : "语义模型状态待确认"}</strong><span>{semanticHealth?.model_health.reason || "未能读取当前运行配置。"}</span></div>
          {semanticHealth ? <dl><div><dt>模型</dt><dd>{semanticHealth.runtime.model_repo_id || semanticHealth.runtime.model}</dd></div><div><dt>混合检索权重</dt><dd>{Math.round(semanticHealth.runtime.semantic_ratio * 100)}%</dd></div><div><dt>运行方式</dt><dd>{semanticHealth.runtime.offline_mode ? "NAS 离线模型" : "允许联网"}</dd></div></dl> : null}
          {semanticHealth ? <p>混合检索权重只表示关键词与语义结果的融合参数，不是检索质量分数。</p> : null}
          {semanticHealth?.model_health.available === true && historicalNetworkFailures ? <p>下方仍有 {historicalNetworkFailures} 条旧的 Hugging Face 网络错误。它们是历史任务记录，不代表当前离线模型失效。</p> : null}
          <Link href="/admin/semantic-index">打开语义索引诊断 <ChevronRight size={14} /></Link>
        </section>
      </div>
      <section className="processing-list admin-panel" aria-labelledby="workload-controls-title">
        <header className="processing-job-toolbar">
          <div>
            <h2 id="workload-controls-title">NAS 负载控制</h2>
            <p>暂停不会强制终止 worker。OCR 会先保存当前页批次，联网补充会在下一个来源请求前停下。</p>
          </div>
        </header>
        <div className="admin-action-row">
          {(["ocr", "external_enrichment"] as const).map((type) => {
            const paused = Boolean(workloads[type]?.paused);
            return (
              <button
                className="button secondary"
                type="button"
                key={type}
                onClick={() => void workloadAction(type, !paused)}
              >
                {paused ? <Play size={15} /> : <PauseCircle size={15} />}
                {paused ? `恢复${jobLabels[type]}` : `暂停${jobLabels[type]}`}
              </button>
            );
          })}
        </div>
      </section>
      {loading ? <p className="admin-list-state"><LoaderCircle className="spin" size={18} />读取进度……</p> : null}
      {error ? <p className="review-error" role="alert">{error}</p> : null}
      <section className="processing-list admin-panel processing-review-queue" aria-labelledby="processing-review-title">
        <header className="processing-job-toolbar">
          <div><h2 id="processing-review-title">人工审核队列</h2><p>元数据冲突、同名人物、实体消歧和页码问题集中在这里处理。</p></div>
          <span>{reviewTasks.length} 项</span>
        </header>
        <nav className="processing-status-tabs" aria-label="审核任务状态筛选">
          {Object.entries(reviewStatusLabels).map(([value, label]) => (
            <button type="button" className={reviewStatus === value ? `active ${value}` : value} aria-pressed={reviewStatus === value} onClick={() => setReviewStatus(value)} key={value}>
              {label} <strong>{reviewCounts[value] ?? 0}</strong>
            </button>
          ))}
        </nav>
        <div className="processing-review-cards">
          {reviewTasks.map((task) => (
            <article key={task.id}>
              <header><span><ClipboardCheck size={15} />{reviewTypeLabels[task.task_type] ?? task.task_type}</span><b>{reviewStatusLabels[task.status] ?? task.status}</b></header>
              <h3>{task.title}</h3>
              <p>{task.item_title || task.source_filename || "系统级审核任务"}</p>
              <dl>
                <div><dt>优先级</dt><dd>{task.priority}</dd></div>
                <div><dt>负责人</dt><dd>{task.assigned_to_name || "尚未领取"}</dd></div>
                <div><dt>创建</dt><dd>{timeLabel(task.created_at)}</dd></div>
                <div><dt>截止</dt><dd>{timeLabel(task.due_at)}</dd></div>
              </dl>
              <footer>
                {task.upload_item ? <Link href={`/admin/intake/${task.upload_item}#bibliography`}>进入工作流</Link> : null}
                {canManageReviewTasks && task.status === "pending" ? <button type="button" onClick={() => void reviewTaskAction(task, "assign_self")}>领取任务</button> : null}
                {canManageReviewTasks && task.status === "in_progress" && task.task_type !== "entity_resolution" ? <button type="button" onClick={() => void reviewTaskAction(task, "complete")}>标记完成</button> : null}
                {canManageReviewTasks && (task.status === "completed" || task.status === "cancelled") ? <button type="button" onClick={() => void reviewTaskAction(task, "reopen")}>恢复待办</button> : null}
              </footer>
            </article>
          ))}
          {!loading && !reviewTasks.length ? <p className="admin-list-state">当前状态下没有人工审核任务。</p> : null}
        </div>
      </section>
      <section className="processing-list admin-panel processing-job-list">
        <header className="processing-job-toolbar"><div><h2>后台任务</h2><p>先选择类型，再按运行状态缩小范围。</p></div><span>{filteredJobs.length} / {jobs.length} 项</span></header>
        <nav className="processing-type-tabs" aria-label="任务类型筛选">
          <button type="button" className={!jobType ? "active" : ""} aria-pressed={!jobType} onClick={() => setJobType("")}>全部 <strong>{jobs.length}</strong></button>
          {Object.entries(jobLabels).map(([value, label]) => <button type="button" className={jobType === value ? "active" : ""} aria-pressed={jobType === value} onClick={() => setJobType(value)} key={value}>{label} <strong>{typeCounts[value] ?? 0}</strong></button>)}
        </nav>
        <nav className="processing-status-tabs" aria-label="任务状态筛选">
          <button type="button" className={!jobStatus ? "active" : ""} aria-pressed={!jobStatus} onClick={() => setJobStatus("")}>全部状态</button>
          {Object.entries(statusLabels).map(([value, label]) => <button type="button" className={jobStatus === value ? `active ${value}` : value} aria-pressed={jobStatus === value} onClick={() => setJobStatus(value)} key={value}>{label} <strong>{statusCounts[value] ?? 0}</strong></button>)}
        </nav>
        <div className="processing-job-cards">
          {filteredJobs.map((job) => (
            <article className={`processing-job-card ${job.status}`} key={`${job.source}-${job.id}`}>
              <header><span>{jobLabels[job.job_type] ?? job.job_type}</span><b>{statusLabels[job.status] ?? job.status}</b></header>
              <div className="processing-job-title"><div><strong>{job.title || "全库任务"}</strong><small>{job.item_id ? <Link href={`/admin/intake/${job.item_id}#file`}>打开馆藏</Link> : job.asset_id ? "资产级任务" : "系统任务"}</small></div><strong>{job.progress}%</strong></div>
              <div className="processing-job-progress" aria-label={`进度 ${job.progress}%`}><i style={{ width: `${Math.min(100, Math.max(0, job.progress))}%` }} /></div>
              <dl><div><dt>引擎</dt><dd>{job.engine || "未记录"}</dd></div><div><dt>配置</dt><dd>{job.settings_version || "环境默认"}</dd></div><div><dt>尝试</dt><dd>{job.attempt}/{job.max_attempts}</dd></div><div><dt>耗时</dt><dd>{durationLabel(job.duration_seconds)}</dd></div><div><dt>开始</dt><dd>{timeLabel(job.started_at || job.created_at)}</dd></div><div><dt>结束</dt><dd>{timeLabel(job.finished_at)}</dd></div></dl>
              {job.last_error ? <details className="processing-job-error" open={job.status === "failed"}><summary>{job.error_code || "查看错误"}</summary><p>{job.last_error}</p></details> : null}
              {(job.status === "failed" || job.status === "pending" || job.status === "running" || job.status === "paused") ? (
                <footer>
                  {job.status === "failed" ? <button type="button" onClick={() => void jobAction(job, "retry")}><RotateCcw size={14} />重试</button> : null}
                  {(job.status === "pending" || job.status === "running") && (job.job_type === "ocr" || job.job_type === "external_enrichment") ? <button type="button" onClick={() => void jobAction(job, "pause")}><PauseCircle size={14} />安全暂停</button> : null}
                  {job.status === "paused" ? <button type="button" onClick={() => void jobAction(job, "resume")}><Play size={14} />继续</button> : null}
                  {(job.status === "pending" || job.status === "paused") ? <button type="button" onClick={() => void jobAction(job, "cancel")}><XCircle size={14} />取消等待</button> : null}
                </footer>
              ) : null}
            </article>
          ))}
          {!loading && !filteredJobs.length ? <p className="admin-list-state">当前筛选条件下没有任务。</p> : null}
        </div>
      </section>
      <section className="processing-list admin-panel processing-upload-list">
        <header><div><h2>上传流程记录</h2><p>这里保留文件入库、复核和发布入口，处理任务在上方查看。</p></div></header>
        {items.map((item) => {
          const latest = item.attempts[0];
          return (
            <article key={item.id}>
              <div className="processing-item-heading"><FileText size={17} /><p><strong>{item.review_data?.title || item.source_filename}</strong><small>{item.source_filename}</small></p><b>{stageLabels[item.status] ?? item.status}</b><span>{item.stage_progress}%</span></div>
              <div className="processing-bar"><i style={{ width: `${item.stage_progress}%` }} /></div>
              <div className="processing-item-detail"><span>{item.is_stalled ? `已停滞 ${Math.max(1, Math.floor(item.stalled_seconds / 60))} 分钟` : latest ? `${latest.stage} · ${latest.status}` : "尚无处理日志"}</span><span>{item.error_message || item.dispatch_error || latest?.error_message || new Date(item.updated_at).toLocaleString("zh-CN")}</span><span><Link href={`/admin/intake/${item.id}#file`}>查看详情</Link>{item.edition ? <Link href={`/admin/intake/${item.id}#publication`}>发布检查</Link> : null}{item.suggested_action === "retry" || item.suggested_action === "resume" ? <button type="button" onClick={() => void retry(item)}><RotateCcw size={13} />重新处理</button> : null}<button className="danger-link" type="button" onClick={() => setRemoveTarget(item)}><Trash2 size={13} />移除</button></span></div>
            </article>
          );
        })}
        {!loading && !items.length ? <p className="admin-list-state">当前没有待处理上传记录。</p> : null}
      </section>
      {message ? <p className="form-message" role="status">{message}</p> : null}
      <ConfirmDialog open={Boolean(removeTarget)} title={`移除“${removeTarget?.review_data?.title || removeTarget?.source_filename || "馆藏记录"}”`} description="这会把记录从处理中心和复核队列移除。NAS 原始 PDF、衍生文件和审计记录不会被物理删除。" confirmLabel="确认移除" tone="danger" pending={actionPending} onCancel={() => setRemoveTarget(null)} onConfirm={() => void removeConfirmed()} />
    </div>
  );
}
