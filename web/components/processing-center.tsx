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
  PauseCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import {
  ActionButton,
  ActionLink,
  AsyncStatus,
  ToastHost,
  type ActionState,
} from "./action-feedback";
import { ConfirmDialog } from "./confirm-dialog";
import { FunctionalHealthPanel, type FunctionalHealthSurface } from "./functional-health-panel";

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
  paused_ocr_inventory?: PausedOCRInventory;
};
type PausedOCRInventoryItem = {
  job_id: string;
  asset_id: string;
  category: "obsolete" | "superseded" | "completed_by_newer_revision" | "recoverable" | "genuinely_failed";
  reasons: string[];
  target_page_indexes: number[];
  remaining_page_indexes: number[];
  newer_job_id: string;
  newer_revision_id: string;
};
type PausedOCRInventory = {
  total: number;
  returned: number;
  truncated: boolean;
  counts: Record<string, number>;
  items: PausedOCRInventoryItem[];
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

type ProcessingFeedback = {
  state: ActionState;
  message: string;
  actionKey: string;
};

const EMPTY_PROCESSING_FEEDBACK: ProcessingFeedback = { state: "idle", message: "", actionKey: "" };

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

const ocrCategoryLabels: Record<PausedOCRInventoryItem["category"], string> = {
  obsolete: "已失去执行条件",
  superseded: "已被较新任务或文件取代",
  completed_by_newer_revision: "已由较新识别结果完成",
  recoverable: "仍可安全恢复",
  genuinely_failed: "确认不可恢复",
};

const ocrReasonLabels: Record<string, string> = {
  asset_missing: "资产已不存在",
  asset_is_not_normalized: "任务目标不是可识别的阅读版本",
  document_has_no_pages: "文档没有可处理页面",
  no_ocr_targets: "没有待识别页面",
  normalized_asset_superseded: "阅读版本已被替换",
  newer_ocr_job_present: "已有更新的 OCR 任务",
  all_target_pages_completed: "目标页面均已完成",
  newer_ocr_result_present: "已有更新的 OCR 修订",
  current_asset_has_unprocessed_targets: "当前阅读版本仍有未处理页面",
  non_retryable_error: "错误不可重试",
  attempts_exhausted: "已达到最大尝试次数",
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

const PROCESSING_SURFACES = [
  { key: "overview", label: "总览" },
  { key: "research-sources", label: "Research Sources" },
  { key: "ai-models", label: "AI 与模型" },
  { key: "documents", label: "OCR 与文档" },
  { key: "workers", label: "任务与 Worker" },
  { key: "projections", label: "Projection 一致性" },
  { key: "faults", label: "故障与恢复" },
] as const;

type ProcessingSurface = (typeof PROCESSING_SURFACES)[number]["key"];

function isProcessingSurface(value: string | null): value is ProcessingSurface {
  return PROCESSING_SURFACES.some((surface) => surface.key === value);
}

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
  const [feedback, setFeedback] = useState<ProcessingFeedback>(EMPTY_PROCESSING_FEEDBACK);
  const [queueHealth, setQueueHealth] = useState<QueueHealth | null>(null);
  const [semanticHealth, setSemanticHealth] = useState<SemanticHealthPayload | null>(null);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [workloads, setWorkloads] = useState<Record<string, { paused: boolean }>>({});
  const [pausedOCRInventory, setPausedOCRInventory] = useState<PausedOCRInventory | null>(null);
  const [ocrDecisionReasons, setOCRDecisionReasons] = useState<Record<string, string>>({});
  const [reviewTasks, setReviewTasks] = useState<ReviewTask[]>([]);
  const [reviewCounts, setReviewCounts] = useState<Record<string, number>>({});
  const [canManageReviewTasks, setCanManageReviewTasks] = useState(false);
  const [reviewStatus, setReviewStatus] = useState("pending");
  const [jobType, setJobType] = useState("");
  const [jobStatus, setJobStatus] = useState("");
  const [filtersReady, setFiltersReady] = useState(false);
  const [activeSurface, setActiveSurface] = useState<ProcessingSurface>("overview");
  const [revision, setRevision] = useState(0);
  const [removeTarget, setRemoveTarget] = useState<ProcessingItem | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [pendingOperation, setPendingOperation] = useState("");
  const operationInFlightRef = useRef("");
  const loadRequestRef = useRef<Promise<boolean> | null>(null);

  const load = useCallback((): Promise<boolean> => {
    if (loadRequestRef.current) return loadRequestRef.current;
    const request = (async () => {
      const token = getServerSessionCredential();
      if (!token) {
        setLoading(false);
        setError("登录状态尚未就绪，请重新登录后再试。");
        return false;
      }
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
      setPausedOCRInventory(jobsResult.status === "fulfilled" ? (jobsResult.value.paused_ocr_inventory ?? null) : null);
      if (reviewResult.status === "fulfilled") {
        setReviewTasks(reviewResult.value.results);
        setReviewCounts(reviewResult.value.counts);
        setCanManageReviewTasks(reviewResult.value.can_manage);
      } else {
        setReviewTasks([]);
      }
        return true;
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "处理中心加载失败。");
        return false;
      } finally {
        setLoading(false);
      }
    })();
    loadRequestRef.current = request;
    void request.finally(() => {
      if (loadRequestRef.current === request) loadRequestRef.current = null;
    });
    return request;
  }, [reviewStatus]);

  function beginOperation(actionKey: string, pendingMessage: string) {
    if (operationInFlightRef.current) return false;
    operationInFlightRef.current = actionKey;
    setPendingOperation(actionKey);
    setFeedback({ state: "pending", message: pendingMessage, actionKey });
    return true;
  }

  function finishOperation(actionKey: string) {
    if (operationInFlightRef.current === actionKey) operationInFlightRef.current = "";
    setPendingOperation((current) => current === actionKey ? "" : current);
  }

  function operationState(actionKey: string): ActionState {
    if (pendingOperation === actionKey) return "pending";
    return feedback.actionKey === actionKey ? feedback.state : "idle";
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const parameters = new URLSearchParams(window.location.search);
      setJobType(parameters.get("type") ?? "");
      setJobStatus(parameters.get("status") ?? "");
      setReviewStatus(parameters.get("review_status") ?? "pending");
      const requestedSurface = parameters.get("surface");
      if (isProcessingSurface(requestedSurface)) setActiveSurface(requestedSurface);
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
    if (activeSurface === "overview") url.searchParams.delete("surface"); else url.searchParams.set("surface", activeSurface);
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [activeSurface, filtersReady, jobStatus, jobType, reviewStatus]);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void load(), 0);
    const timer = window.setInterval(load, 10000);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
  }, [load, revision]);

  async function refreshNow() {
    const actionKey = "refresh";
    if (!beginOperation(actionKey, "正在刷新处理中心。")) return;
    setLoading(true);
    try {
      const succeeded = await load();
      setFeedback({
        state: succeeded ? "success" : "error",
        message: succeeded ? "处理中心已刷新。" : "处理中心刷新失败，请查看页面错误。",
        actionKey,
      });
    } finally {
      finishOperation(actionKey);
    }
  }

  async function retry(item: ProcessingItem) {
    const token = getServerSessionCredential();
    const actionKey = `item-retry:${item.id}`;
    if (!token) {
      setFeedback({ state: "error", message: "登录状态尚未就绪，无法重新处理。", actionKey });
      return;
    }
    if (!beginOperation(actionKey, `正在重新处理${item.source_filename}。`)) return;
    try {
      const action = item.suggested_action === "resume" && item.edition ? "resume" : "retry";
      await apiRequest(`/ingestion/items/${item.id}/${action}/`, { method: "POST" }, token);
      setFeedback({ state: "success", message: `${item.source_filename} 已重新进入处理队列。`, actionKey });
      setRevision((value) => value + 1);
    } catch (reason) {
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : "重试失败。", actionKey });
    } finally {
      finishOperation(actionKey);
    }
  }

  async function removeConfirmed() {
    const token = getServerSessionCredential();
    if (!removeTarget) return;
    const actionKey = `remove:${removeTarget.id}`;
    if (!token) {
      setFeedback({ state: "error", message: "登录状态尚未就绪，无法移除处理记录。", actionKey });
      return;
    }
    if (!beginOperation(actionKey, `正在移除${removeTarget.source_filename}的处理记录。`)) return;
    const label = removeTarget.review_data?.title || removeTarget.source_filename;
    setActionPending(true);
    try {
      await apiRequest(`/ingestion/items/${removeTarget.id}/delete/`, {
        method: "POST",
        body: JSON.stringify({ confirmed: true }),
      }, token);
      setFeedback({ state: "success", message: `${label} 已从处理队列移除。NAS 原文件和审计记录仍保留。`, actionKey });
      setRemoveTarget(null);
      setRevision((value) => value + 1);
    } catch (reason) {
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : "移除失败。", actionKey });
    } finally {
      setActionPending(false);
      finishOperation(actionKey);
    }
  }

  async function jobAction(job: ProcessingJob, action: "retry" | "cancel" | "pause" | "resume") {
    const token = getServerSessionCredential();
    const actionKey = `job:${action}:${job.source}:${job.id}`;
    if (!token) {
      setFeedback({ state: "error", message: "登录状态尚未就绪，无法操作任务。", actionKey });
      return;
    }
    if (!beginOperation(actionKey, "正在提交任务操作。")) return;
    try {
      await apiRequest("/ingestion/processing-center/", {
        method: "POST",
        body: JSON.stringify({ action, source: job.source, job_id: job.id }),
      }, token);
      setFeedback({
        state: "success",
        message: action === "retry" ? "处理任务已经重新排队。"
          : action === "pause" ? "暂停请求已记录，运行中的任务会在安全检查点暂停。"
            : action === "resume" ? "已暂停任务从保存进度恢复。"
              : "等待中的任务已经取消。",
        actionKey,
      });
      setRevision((value) => value + 1);
    } catch (reason) {
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : "任务操作失败。", actionKey });
    } finally {
      finishOperation(actionKey);
    }
  }

  async function workloadAction(type: "ocr" | "external_enrichment", paused: boolean) {
    const token = getServerSessionCredential();
    const actionKey = `workload:${type}`;
    if (!token) {
      setFeedback({ state: "error", message: "登录状态尚未就绪，无法调整负载。", actionKey });
      return;
    }
    if (!beginOperation(actionKey, `正在${paused ? "暂停" : "恢复"}${jobLabels[type]}。`)) return;
    try {
      await apiRequest("/ingestion/processing-center/", {
        method: "POST",
        body: JSON.stringify({
          action: paused ? "pause_workload" : "resume_workload",
          job_type: type,
        }),
      }, token);
      setFeedback({ state: "success", message: paused
        ? `${jobLabels[type]} 已请求暂停。当前批次保存后生效。`
        : type === "ocr"
          ? "已允许新的 OCR 任务运行。历史暂停任务仍需逐条核对后处理。"
          : `${jobLabels[type]} 已恢复，已保存任务会继续运行。`, actionKey });
      setRevision((value) => value + 1);
    } catch (reason) {
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : "任务负载操作失败。", actionKey });
    } finally {
      finishOperation(actionKey);
    }
  }

  async function resolvePausedOCR(item: PausedOCRInventoryItem, decision: "close" | "resume" | "acknowledge_failure") {
    const token = getServerSessionCredential();
    const actionKey = `ocr-inventory:${decision}:${item.job_id}`;
    const reason = (ocrDecisionReasons[item.job_id] ?? "").trim();
    if (!token) {
      setFeedback({ state: "error", message: "登录状态尚未就绪，无法处理 OCR 任务。", actionKey });
      return;
    }
    if (!reason) {
      setFeedback({ state: "error", message: "请先填写本次处理理由。", actionKey });
      return;
    }
    if (!beginOperation(actionKey, "正在记录 OCR 任务决定。")) return;
    try {
      await apiRequest("/ingestion/processing-center/", {
        method: "POST",
        body: JSON.stringify({
          action: "resolve_paused_ocr",
          source: "processing_job",
          job_id: item.job_id,
          decision,
          reason,
        }),
      }, token);
      setFeedback({ state: "success", message: decision === "resume" ? "OCR 任务已按当前运行配置恢复。" : decision === "close" ? "历史 OCR 任务已安全关闭。" : "OCR 失败已确认并留下审计记录。", actionKey });
      setRevision((value) => value + 1);
    } catch (reasonValue) {
      setFeedback({ state: "error", message: reasonValue instanceof Error ? reasonValue.message : "OCR 任务处理失败。", actionKey });
    } finally {
      finishOperation(actionKey);
    }
  }

  async function reviewTaskAction(task: ReviewTask, action: "assign_self" | "complete" | "reopen") {
    const token = getServerSessionCredential();
    const actionKey = `review:${action}:${task.id}`;
    if (!token) {
      setFeedback({ state: "error", message: "登录状态尚未就绪，无法操作审核任务。", actionKey });
      return;
    }
    if (!beginOperation(actionKey, "正在提交审核操作。")) return;
    try {
      await apiRequest(`/ingestion/review-tasks/${task.id}/action/`, {
        method: "POST",
        body: JSON.stringify({ action }),
      }, token);
      setFeedback({ state: "success", message: action === "assign_self" ? "审核任务已领取。" : action === "complete" ? "审核任务已完成。" : "审核任务已恢复。", actionKey });
      setRevision((value) => value + 1);
    } catch (reason) {
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : "审核任务操作失败。", actionKey });
    } finally {
      finishOperation(actionKey);
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
  const healthSurface: FunctionalHealthSurface | null = activeSurface === "documents" ? null : activeSurface;

  return (
    <div className="admin-page processing-center-page" aria-busy={loading || Boolean(pendingOperation)}>
      <header className="admin-page-title">
        <div><p>Processing Center</p><h1>处理中心</h1><span>先看用户功能影响，再按任务类型检查 Research、AI、OCR、Worker 与 Projection，并保留每次失败的完整记录。</span></div>
        <div className="admin-action-row">
          <ActionLink className="button secondary" href="/admin/publication">前往发布台 <ChevronRight size={15} /></ActionLink>
          <ActionButton
            className="button secondary"
            state={pendingOperation === "refresh" || (loading && !items.length) ? "pending" : error ? "error" : "idle"}
            pendingLabel="正在刷新"
            errorLabel="重新刷新"
            disabled={Boolean(pendingOperation) && pendingOperation !== "refresh"}
            onClick={() => void refreshNow()}
          ><RefreshCw size={15} />刷新</ActionButton>
        </div>
      </header>
      <nav className="processing-type-tabs processing-center-surfaces" aria-label="Processing Center 工作面" role="tablist">
        {PROCESSING_SURFACES.map((surface) => (
          <button
            type="button"
            id={`processing-surface-tab-${surface.key}`}
            className={activeSurface === surface.key ? "active" : ""}
            aria-controls={`processing-surface-${surface.key}`}
            aria-selected={activeSurface === surface.key}
            role="tab"
            key={surface.key}
            onClick={() => setActiveSurface(surface.key)}
          >
            {surface.label}
          </button>
        ))}
      </nav>
      <div
        className="processing-center-surface"
        id={`processing-surface-${activeSurface}`}
        role="tabpanel"
        aria-labelledby={`processing-surface-tab-${activeSurface}`}
        tabIndex={0}
      >
      {healthSurface ? <FunctionalHealthPanel revision={revision} surface={healthSurface} /> : null}
      {activeSurface === "overview" ? <section className="processing-summary">
        <article><Clock3 size={18} /><strong>{summary.active}</strong><span>等待或运行</span></article>
        <article><FileText size={18} /><strong>{summary.review}</strong><span>待复核</span></article>
        <article><AlertCircle size={18} /><strong>{summary.failed}</strong><span>失败</span></article>
        <article><CheckCircle2 size={18} /><strong>{summary.succeeded}</strong><span>成功</span></article>
      </section> : null}
      {activeSurface === "overview" || activeSurface === "workers" || activeSurface === "ai-models" || activeSurface === "documents" ? (
      <div className={`processing-health-grid ${activeSurface === "overview" ? "" : "single"}`}>
        {(activeSurface === "overview" || activeSurface === "workers" || activeSurface === "documents") && queueHealth ? (
          <section className={`processing-health ${!queueHealth.healthy || queueHealth.stalled_count ? "warning" : ""}`} role="status">
            <Cpu size={18} /><div><strong>{queueHealth.mode === "inline" ? "本地同步处理" : "后台工作者"}</strong><span>{queueHealth.message}</span></div>
            <dl><div><dt>worker</dt><dd>{queueHealth.worker_online ? "在线" : "未确认"}</dd></div><div><dt>OCR</dt><dd>{queueHealth.ocr.reachable ? "可用" : queueHealth.ocr.detail}</dd></div></dl>
          </section>
        ) : null}
        {activeSurface === "overview" || activeSurface === "ai-models" ? <section className={`processing-semantic-health ${semanticHealth?.model_health.available === false ? "warning" : ""}`}>
          <Search size={18} />
          <div><strong>{semanticHealth?.model_health.available === true ? "当前语义模型可用" : semanticHealth?.model_health.available === false ? "当前语义模型不可用" : "语义模型状态待确认"}</strong><span>{semanticHealth?.model_health.reason || "未能读取当前运行配置。"}</span></div>
          {semanticHealth ? <dl><div><dt>模型</dt><dd>{semanticHealth.runtime.model_repo_id || semanticHealth.runtime.model}</dd></div><div><dt>混合检索权重</dt><dd>{Math.round(semanticHealth.runtime.semantic_ratio * 100)}%</dd></div><div><dt>运行方式</dt><dd>{semanticHealth.runtime.offline_mode ? "NAS 离线模型" : "允许联网"}</dd></div></dl> : null}
          {semanticHealth ? <p>混合检索权重只表示关键词与语义结果的融合参数，不是检索质量分数。</p> : null}
          {semanticHealth?.model_health.available === true && historicalNetworkFailures ? <p>下方仍有 {historicalNetworkFailures} 条旧的 Hugging Face 网络错误。它们是历史任务记录，不代表当前离线模型失效。</p> : null}
          <Link href="/admin/semantic-index">打开语义索引诊断 <ChevronRight size={14} /></Link>
        </section> : null}
      </div>
      ) : null}
      {activeSurface === "documents" || activeSurface === "research-sources" ? <section className="processing-list admin-panel" aria-labelledby="workload-controls-title">
        <header className="processing-job-toolbar">
          <div>
            <h2 id="workload-controls-title">{activeSurface === "documents" ? "OCR 负载控制" : "联网研究负载"}</h2>
            <p>{activeSurface === "documents" ? "暂停不会强制终止 worker。OCR 会先保存当前页批次。" : "联网补充会在下一个来源请求前停下，不会丢失已取得的 Evidence。"}</p>
          </div>
        </header>
        <div className="admin-action-row">
          {(activeSurface === "documents" ? ["ocr"] as const : ["external_enrichment"] as const).map((type) => {
            const paused = Boolean(workloads[type]?.paused);
            return (
              <ActionButton
                className="button secondary"
                key={type}
                state={operationState(`workload:${type}`)}
                pressed={paused}
                pendingLabel={paused ? `正在允许${jobLabels[type]}` : `正在暂停${jobLabels[type]}`}
                successLabel="操作已提交"
                errorLabel="重试操作"
                disabled={Boolean(pendingOperation)}
                onClick={() => void workloadAction(type, !paused)}
              >
                {paused ? <Play size={15} /> : <PauseCircle size={15} />}
                {paused ? type === "ocr" ? "允许新 OCR 任务" : `恢复${jobLabels[type]}` : `暂停${jobLabels[type]}`}
              </ActionButton>
            );
          })}
        </div>
      </section> : null}
      {activeSurface === "documents" ? <section className="processing-list admin-panel processing-ocr-inventory" aria-labelledby="paused-ocr-inventory-title">
        <header className="processing-job-toolbar">
          <div><h2 id="paused-ocr-inventory-title">历史暂停 OCR</h2><p>系统按当前文件、页面和 DocumentRevision 事实逐条分类。每项决定都需要理由并写入审计记录。</p></div>
          <span>{pausedOCRInventory?.total ?? 0} 项</span>
        </header>
        <div className="processing-job-cards">
          {(pausedOCRInventory?.items ?? []).map((item) => {
            const decision = item.category === "recoverable" ? "resume" : item.category === "genuinely_failed" ? "acknowledge_failure" : "close";
            const actionLabel = decision === "resume" ? "按当前配置恢复" : decision === "close" ? "安全关闭" : "确认失败";
            return (
              <article className={`processing-job-card paused ocr-inventory-${item.category}`} key={item.job_id}>
                <header><span>OCR · {item.job_id.slice(0, 8)}</span><b>{ocrCategoryLabels[item.category]}</b></header>
                <p>{item.reasons.map((reason) => ocrReasonLabels[reason] ?? (reason.startsWith("error:") ? `错误代码 ${reason.slice(6)}` : reason)).join("；")}</p>
                <dl>
                  <div><dt>目标页</dt><dd>{item.target_page_indexes.join("、") || "无"}</dd></div>
                  <div><dt>待处理页</dt><dd>{item.remaining_page_indexes.join("、") || "无"}</dd></div>
                  <div><dt>较新任务</dt><dd>{item.newer_job_id ? item.newer_job_id.slice(0, 8) : "无"}</dd></div>
                  <div><dt>较新修订</dt><dd>{item.newer_revision_id ? item.newer_revision_id.slice(0, 8) : "无"}</dd></div>
                </dl>
                <label><span>处理理由</span><input value={ocrDecisionReasons[item.job_id] ?? ""} onChange={(event) => setOCRDecisionReasons((current) => ({ ...current, [item.job_id]: event.target.value }))} placeholder="说明依据，保存到审计记录" /></label>
                <footer><ActionButton state={operationState(`ocr-inventory:${decision}:${item.job_id}`)} pendingLabel="正在处理" disabled={Boolean(pendingOperation) || !(ocrDecisionReasons[item.job_id] ?? "").trim()} onClick={() => void resolvePausedOCR(item, decision)}>{decision === "resume" ? <Play size={14} /> : decision === "close" ? <XCircle size={14} /> : <AlertCircle size={14} />}{actionLabel}</ActionButton></footer>
              </article>
            );
          })}
          {!loading && !(pausedOCRInventory?.items.length) ? <p className="admin-list-state">当前没有来源不明的历史暂停 OCR 任务。</p> : null}
        </div>
      </section> : null}
      {loading && !items.length && !jobs.length ? <AsyncStatus state="pending" message="正在读取处理进度……" /> : null}
      <AsyncStatus state="error" message={error} assertive />
      {activeSurface === "workers" ? <section className="processing-list admin-panel processing-review-queue" aria-labelledby="processing-review-title">
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
                {canManageReviewTasks && task.status === "pending" ? <ActionButton state={operationState(`review:assign_self:${task.id}`)} pendingLabel="正在领取" disabled={Boolean(pendingOperation)} onClick={() => void reviewTaskAction(task, "assign_self")}>领取任务</ActionButton> : null}
                {canManageReviewTasks && task.status === "in_progress" && task.task_type !== "entity_resolution" ? <ActionButton state={operationState(`review:complete:${task.id}`)} pendingLabel="正在完成" disabled={Boolean(pendingOperation)} onClick={() => void reviewTaskAction(task, "complete")}>标记完成</ActionButton> : null}
                {canManageReviewTasks && (task.status === "completed" || task.status === "cancelled") ? <ActionButton state={operationState(`review:reopen:${task.id}`)} pendingLabel="正在恢复" disabled={Boolean(pendingOperation)} onClick={() => void reviewTaskAction(task, "reopen")}>恢复待办</ActionButton> : null}
              </footer>
            </article>
          ))}
          {!loading && !reviewTasks.length ? <p className="admin-list-state">当前状态下没有人工审核任务。</p> : null}
        </div>
      </section> : null}
      {activeSurface === "workers" ? <section className="processing-list admin-panel processing-job-list" id="processing-task-list">
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
                  {job.status === "failed" ? <ActionButton state={operationState(`job:retry:${job.source}:${job.id}`)} pendingLabel="正在重试" disabled={Boolean(pendingOperation)} onClick={() => void jobAction(job, "retry")}><RotateCcw size={14} />重试</ActionButton> : null}
                  {(job.status === "pending" || job.status === "running") && (job.job_type === "ocr" || job.job_type === "external_enrichment") ? <ActionButton state={operationState(`job:pause:${job.source}:${job.id}`)} pendingLabel="正在暂停" disabled={Boolean(pendingOperation)} onClick={() => void jobAction(job, "pause")}><PauseCircle size={14} />安全暂停</ActionButton> : null}
                  {job.status === "paused" && job.job_type !== "ocr" ? <ActionButton state={operationState(`job:resume:${job.source}:${job.id}`)} pendingLabel="正在继续" disabled={Boolean(pendingOperation)} onClick={() => void jobAction(job, "resume")}><Play size={14} />继续</ActionButton> : null}
                  {(job.status === "pending" || (job.status === "paused" && job.job_type !== "ocr")) ? <ActionButton state={operationState(`job:cancel:${job.source}:${job.id}`)} pendingLabel="正在取消" disabled={Boolean(pendingOperation)} onClick={() => void jobAction(job, "cancel")}><XCircle size={14} />取消等待</ActionButton> : null}
                </footer>
              ) : null}
            </article>
          ))}
          {!loading && !filteredJobs.length ? <p className="admin-list-state">当前筛选条件下没有任务。</p> : null}
        </div>
      </section> : null}
      {activeSurface === "documents" ? <section className="processing-list admin-panel processing-upload-list">
        <header><div><h2>上传流程记录</h2><p>这里保留文件入库、复核和发布入口，处理任务在上方查看。</p></div></header>
        {items.map((item) => {
          const latest = item.attempts[0];
          return (
            <article key={item.id}>
              <div className="processing-item-heading"><FileText size={17} /><p><strong>{item.review_data?.title || item.source_filename}</strong><small>{item.source_filename}</small></p><b>{stageLabels[item.status] ?? item.status}</b><span>{item.stage_progress}%</span></div>
              <div className="processing-bar"><i style={{ width: `${item.stage_progress}%` }} /></div>
              <div className="processing-item-detail"><span>{item.is_stalled ? `已停滞 ${Math.max(1, Math.floor(item.stalled_seconds / 60))} 分钟` : latest ? `${latest.stage} · ${latest.status}` : "尚无处理日志"}</span><span>{item.error_message || item.dispatch_error || latest?.error_message || new Date(item.updated_at).toLocaleString("zh-CN")}</span><span><Link href={`/admin/intake/${item.id}#file`}>查看详情</Link>{item.edition ? <Link href={`/admin/intake/${item.id}#publication`}>发布检查</Link> : null}{item.suggested_action === "retry" || item.suggested_action === "resume" ? <ActionButton state={operationState(`item-retry:${item.id}`)} pendingLabel="正在处理" disabled={Boolean(pendingOperation)} onClick={() => void retry(item)}><RotateCcw size={13} />重新处理</ActionButton> : null}<button className="danger-link" type="button" onClick={() => setRemoveTarget(item)}><Trash2 size={13} />移除</button></span></div>
            </article>
          );
        })}
        {!loading && !items.length ? <p className="admin-list-state">当前没有待处理上传记录。</p> : null}
      </section> : null}
      </div>
      <ToastHost
        items={feedback.message ? [{ id: feedback.actionKey || "processing", state: feedback.state === "idle" ? "success" : feedback.state, message: feedback.message }] : []}
        onDismiss={() => setFeedback(EMPTY_PROCESSING_FEEDBACK)}
        label="处理中心操作反馈"
      />
      <ConfirmDialog open={Boolean(removeTarget)} title={`移除“${removeTarget?.review_data?.title || removeTarget?.source_filename || "馆藏记录"}”`} description="这会把记录从处理中心和复核队列移除。NAS 原始 PDF、衍生文件和审计记录不会被物理删除。" confirmLabel="确认移除" tone="danger" pending={actionPending} onCancel={() => setRemoveTarget(null)} onConfirm={() => void removeConfirmed()} />
    </div>
  );
}
