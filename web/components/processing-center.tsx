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
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { hasAdminCapability, useAdminSession } from "@/lib/admin-session";
import {
  ActionButton,
  ActionLink,
  AsyncStatus,
  ToastHost,
  type ActionState,
} from "./action-feedback";
import { ConfirmDialog } from "./confirm-dialog";
import { CatalogOcrPicker, OcrProgressDisplay, ocrPageRanges as pageRanges, type OcrProgress } from "./admin/workflow/edition-ocr-control";
import { OcrTaskMonitor } from "./ocr-task-monitor";
import { FunctionalHealthPanel, type FunctionalHealthSurface } from "./functional-health-panel";
import { WorkflowInspector } from "./admin/inspector/workflow-inspector";
import { DiscoveryIndexPanel } from "./discovery-index-panel";

type Attempt = {
  id: string;
  stage: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  error_message: string;
};

type DocumentStage = { status: string; job_id: string | null; progress: number | null; updated_at: string | null; error: string; kind: string; source: string };

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
  document_stages?: { file: DocumentStage | null; ocr: DocumentStage | null; index: DocumentStage | null };
};

type Paginated<T> = { count: number; results: T[]; next?: string | null; previous?: string | null };
type QueueHealth = {
  mode: "inline" | "worker";
  worker_required: boolean;
  stalled_count: number;
  pending_dispatches: number;
  healthy: boolean | null;
  checked_at?: string | null;
  stale?: boolean;
  broker_reachable: boolean | null;
  worker_online: boolean | null;
  ocr: { configured: boolean | null; reachable: boolean | null; detail: string };
  search: { configured: boolean | null; reachable: boolean | null; detail: string };
  message: string;
};

type ProcessingJob = {
  workbench_url?: string;
  edition_id?: string | null;
  work_id?: string | null;
  id: string;
  source: "processing_job" | "semantic_index_job";
  job_type: string;
  item_id: string | null;
  asset_id: string | null;
  title: string;
  edition_label?: string;
  title_has_unpublished_changes?: boolean;
  status: "pending" | "running" | "paused" | "succeeded" | "failed" | "canceled";
  progress: number;
  ocr_progress?: OcrProgress | null;
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
  count: number;
  page: number;
  pages: number;
  next_page: number | null;
  previous_page: number | null;
  total: number;
  total_counts: Record<string, number>;
  type_counts: Record<string, number>;
  can_manage: boolean;
  results: ProcessingJob[];
  counts: Record<string, number>;
  workloads: Record<string, { paused: boolean }>;
  paused_ocr_inventory?: PausedOCRInventory;
};
type PausedOCRInventoryItem = {
  title_has_unpublished_changes?: boolean;
  title: string;
  edition_label: string;
  workbench_url: string;
  target_pages: number;
  completed_pages: number;
  remaining_pages: number;
  updated_at: string;
  created_at: string;
  can_manage: boolean;
  permission_reason: string;
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
  page: number;
  pages: number;
  next_page: number | null;
  previous_page: number | null;
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
  page: number;
  pages: number;
  next_page: number | null;
  previous_page: number | null;
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
  ocr: "文字识别（OCR）",
  external_enrichment: "联网补充",
  text_extraction: "文本提取",
  page_labels: "页码识别",
  semantic_index: "语义索引",
  thumbnail: "缩略图",
  cache_refresh: "缓存刷新",
  projection_refresh: "公开内容更新",
  query_lexicon_candidates: "检索词建议",
  query_lexicon_reconcile: "检索词更新",
  r2_staging: "上传中转",
};

const statusLabels: Record<string, string> = {
  completed: "完成",
  queued: "已排队",
  skipped: "已跳过",
  pending: "等待",
  running: "运行中",
  paused: "已暂停",
  succeeded: "成功",
  failed: "失败",
  canceled: "已取消",
};

const ocrCategoryLabels: Record<PausedOCRInventoryItem["category"], string> = {
  obsolete: "旧任务已不适用",
  superseded: "已有更新的任务或文件",
  completed_by_newer_revision: "已有更新的识别结果",
  recoverable: "可继续识别",
  genuinely_failed: "需要人工处理",
};

const ocrReasonLabels: Record<string, string> = {
  asset_missing: "原任务关联的文件已不存在",
  asset_is_not_normalized: "任务目标不是可识别的阅读版本",
  document_has_no_pages: "文档没有可处理页面",
  no_ocr_targets: "没有待识别页面",
  normalized_asset_superseded: "阅读版本已被替换",
  newer_ocr_job_present: "已有更新的 OCR 任务",
  all_target_pages_completed: "目标页面均已完成",
  newer_ocr_result_present: "已有更新的文字识别结果",
  current_asset_has_unprocessed_targets: "当前阅读版本仍有未处理页面",
  non_retryable_error: "错误不可重试",
  attempts_exhausted: "已达到最大尝试次数",
  source_changed: "阅读文件已经更换，这个旧任务不能继续覆盖新文件",
  attempts_exhausted_or_permanent: "已达到重试上限或需要人工处理错误",
  manual_full_rerun_remaining: "本次重新识别尚未结束，已完成的页面会保留",
  finish_remaining_processing: "文字已识别完，还需整理结果",
};

const reviewStatusLabels: Record<string, string> = {
  pending: "待领取",
  in_progress: "处理中",
  completed: "已完成",
  cancelled: "已取消",
};

const reviewTypeLabels: Record<string, string> = {
  entity_resolution: "核对对象身份",
  metadata_conflict: "书目信息不一致",
  duplicate_person: "同名人物",
  page_labels: "页码校对",
  publication: "发布检查",
};

const PROCESSING_SURFACES = [
  { key: "overview", label: "总览" },
  { key: "research-sources", label: "资料来源" },
  { key: "ai-models", label: "AI 与模型" },
  { key: "documents", label: "OCR 与文档" },
  { key: "workers", label: "后台任务" },
  { key: "projections", label: "公开内容更新" },
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
  metadata: "识别书目信息",
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

function TaskPagination({ page, pages, count, busy, onChange, label }: { page: number; pages: number; count: number; busy: boolean; onChange: (page: number) => void; label: string }) {
  return <nav className="processing-pagination" aria-label={label}>
    <span>共 {count} 项 · 第 {page} / {Math.max(1, pages)} 页</span>
    <button type="button" disabled={busy || page <= 1} onClick={() => onChange(page - 1)}>上一页</button>
    <button type="button" disabled={busy || page >= pages} onClick={() => onChange(page + 1)}>下一页</button>
  </nav>;
}

export function ProcessingCenter() {
  const user = useAdminSession();
  const canRemoveRecords = hasAdminCapability(user, "can_run_destructive_maintenance");
  const [items, setItems] = useState<ProcessingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState<ProcessingFeedback>(EMPTY_PROCESSING_FEEDBACK);
  const [queueHealth, setQueueHealth] = useState<QueueHealth | null>(null);
  const [semanticHealth, setSemanticHealth] = useState<SemanticHealthPayload | null>(null);
  const [jobs, setJobs] = useState<ProcessingJob[]>([]);
  const [taskMeta, setTaskMeta] = useState<ProcessingJobsPayload | null>(null);
  const [jobPage, setJobPage] = useState(1);
  const [jobQuery, setJobQuery] = useState("");
  const [jobQueryInput, setJobQueryInput] = useState("");
  const [ocrPage, setOcrPage] = useState(1);
  const [ocrQuery, setOcrQuery] = useState("");
  const [ocrQueryInput, setOcrQueryInput] = useState("");
  const [itemPage, setItemPage] = useState(1);
  const [itemMeta, setItemMeta] = useState<Paginated<ProcessingItem> | null>(null);
  const [reviewPage, setReviewPage] = useState(1);
  const [reviewMeta, setReviewMeta] = useState<ReviewTasksPayload | null>(null);
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
  const [activeSurface, setActiveSurface] = useState<ProcessingSurface>("documents");
  const [revision, setRevision] = useState(0);
  const [removeTarget, setRemoveTarget] = useState<ProcessingItem | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState("");
  const selectedDocument = items.find(item => item.id === selectedDocumentId) ?? null;
  const [actionPending, setActionPending] = useState(false);
  const [pendingOperation, setPendingOperation] = useState("");
  const operationInFlightRef = useRef("");
  const loadRequestRef = useRef<{ key: string; controller: AbortController; promise: Promise<boolean> } | null>(null);

  const load = useCallback((): Promise<boolean> => {
    const key = JSON.stringify([reviewStatus, jobType, jobStatus, jobPage, jobQuery, ocrPage, ocrQuery, itemPage, reviewPage]);
    if (loadRequestRef.current?.key === key) return loadRequestRef.current.promise;
    loadRequestRef.current?.controller.abort();
    const controller = new AbortController();
    const options = { signal: controller.signal };
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, 20000);
    const current = () => !controller.signal.aborted;
    const request = (async () => {
      const token = getServerSessionCredential();
      if (!token) {
        window.clearTimeout(timeout);
        setLoading(false);
        setError("登录状态尚未就绪，请重新登录后再试。");
        return false;
      }
      try {
      const [itemsResult, healthResult, jobsResult, semanticResult, reviewResult] = await Promise.allSettled([
        apiRequest<Paginated<ProcessingItem>>(
          `/ingestion/items/?scope=processing&ordering=-updated_at,-id&page=${itemPage}`,
          options,
          token,
        ),
        apiRequest<QueueHealth>("/ingestion/queue-health/", options, token),
        apiRequest<ProcessingJobsPayload>(`/ingestion/processing-center/?${new URLSearchParams({ job_type: jobType, status: jobStatus, page: String(jobPage), q: jobQuery, ocr_inventory_page: String(ocrPage), ocr_query: ocrQuery })}`, options, token).then((result) => {
          // Job feedback must not wait for slow provider/worker health checks.
          if (!current()) return result;
          setJobs(result.results);
          setTaskMeta(result);
          setJobPage(result.page);
          if (result.paused_ocr_inventory) setOcrPage(result.paused_ocr_inventory.page);
          setWorkloads(result.workloads ?? {});
          setPausedOCRInventory(result.paused_ocr_inventory ?? null);
          return result;
        }),
        apiRequest<SemanticHealthPayload>("/catalog/admin/semantic-index/", options, token),
        apiRequest<ReviewTasksPayload>(
          `/ingestion/review-tasks/?page_size=30&page=${reviewPage}${reviewStatus ? `&status=${encodeURIComponent(reviewStatus)}` : ""}`,
          options,
          token,
        ),
      ]);
      if (!current()) {
        if (timedOut && loadRequestRef.current?.controller === controller) setError("部分状态读取超时，已保留最近结果；可点击刷新重试。不会重新启动识别。");
        return false;
      }
      const failures: string[] = [];
      if (itemsResult.status === "fulfilled") {
        setItems(itemsResult.value.results);
        setItemMeta(itemsResult.value);
      } else {
        failures.push("上传记录暂时读取失败，保留上次结果。");
      }
      setQueueHealth(healthResult.status === "fulfilled" ? healthResult.value : null);
      setSemanticHealth(semanticResult.status === "fulfilled" ? semanticResult.value : null);
      if (jobsResult.status === "rejected") failures.push("任务进度暂时读取失败，保留上次结果。");
      if (healthResult.status === "rejected" || semanticResult.status === "rejected") failures.push("部分服务状态未能读取，不能据此判断正常。");
      if (reviewResult.status === "fulfilled") {
        setReviewTasks(reviewResult.value.results);
        setReviewMeta(reviewResult.value);
        setReviewPage(reviewResult.value.page);
        setReviewCounts(reviewResult.value.counts);
        setCanManageReviewTasks(reviewResult.value.can_manage);
      } else {
        failures.push("人工待办暂时读取失败，保留上次结果。");
      }
        setError(failures.length ? `${failures.join(" ")}可点击刷新重试，不会重新启动任务。` : "");
        return failures.length === 0;
      } catch (reason) {
        if (!current()) return false;
        setError(reason instanceof Error ? reason.message : "处理中心加载失败。");
        return false;
      } finally {
        window.clearTimeout(timeout);
        if (loadRequestRef.current?.controller === controller) setLoading(false);
      }
    })();
    loadRequestRef.current = { key, controller, promise: request };
    void request.finally(() => {
      if (loadRequestRef.current?.promise === request) loadRequestRef.current = null;
    });
    return request;
  }, [reviewStatus, jobType, jobStatus, jobPage, jobQuery, ocrPage, ocrQuery, itemPage, reviewPage]);

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
      const readPage = (name: string) => { const value = Number(parameters.get(name)); return Number.isSafeInteger(value) && value > 0 ? value : 1; };
      setJobPage(readPage("page")); setOcrPage(readPage("ocr_page")); setItemPage(readPage("upload_page")); setReviewPage(readPage("review_page"));
      setJobQuery(parameters.get("q") ?? ""); setJobQueryInput(parameters.get("q") ?? "");
      setOcrQuery(parameters.get("ocr_q") ?? ""); setOcrQueryInput(parameters.get("ocr_q") ?? "");
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
    for (const [name, value] of Object.entries({ page: jobPage, ocr_page: ocrPage, upload_page: itemPage, review_page: reviewPage })) {
      if (value > 1) url.searchParams.set(name, String(value)); else url.searchParams.delete(name);
    }
    for (const [name, value] of Object.entries({ q: jobQuery, ocr_q: ocrQuery })) {
      if (value) url.searchParams.set(name, value); else url.searchParams.delete(name);
    }
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }, [activeSurface, filtersReady, jobStatus, jobType, reviewStatus, jobPage, jobQuery, ocrPage, ocrQuery, itemPage, reviewPage]);

  useEffect(() => {
    if (!filtersReady) return;
    const initialTimer = window.setTimeout(() => { setLoading(true); void load(); }, 0);
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 15000);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
      loadRequestRef.current?.controller.abort();
      loadRequestRef.current = null;
    };
  }, [load, revision, filtersReady]);

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
    if (!removeTarget || !canRemoveRecords) return;
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

  async function resolvePausedOCR(item: PausedOCRInventoryItem, decision: "close" | "resume" | "acknowledge_failure" | "cancel") {
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
    if (decision === "cancel" && !window.confirm(`取消《${item.title}》这一次文字识别？已保存文字、PDF 和阅读记录都会保留。`)) return;
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
      setFeedback({ state: "success", message: decision === "resume" ? "已提交继续识别，实际运行进度请查看本馆藏。" : decision === "cancel" ? "本次识别已取消；原文件和已保存结果仍保留。" : decision === "close" ? "旧识别任务已结束，历史记录保留。" : "失败原因已记录，没有更改已保存文字。", actionKey });
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

  const statusCounts = taskMeta?.counts ?? {};
  const typeCounts = taskMeta?.type_counts ?? {};
  const totalCounts = taskMeta?.total_counts ?? {};
  const filteredJobs = jobs;
  const canManageTasks = taskMeta?.can_manage === true;
  const historicalNetworkFailures = useMemo(() => jobs.filter((job) => (
    job.job_type === "semantic_index"
    && job.status === "failed"
    && /huggingface|dns|name or service|network unreachable|resolve/i.test(`${job.error_code} ${job.last_error}`)
  )).length, [jobs]);
  const summary = {
    active: taskMeta ? (totalCounts.pending ?? 0) + (totalCounts.running ?? 0) : null,
    review: reviewMeta ? (reviewCounts.pending ?? 0) + (reviewCounts.in_progress ?? 0) : null,
    failed: taskMeta ? totalCounts.failed ?? 0 : null,
    succeeded: taskMeta ? totalCounts.succeeded ?? 0 : null,
  };
  const healthSurface: FunctionalHealthSurface | null = activeSurface === "documents" ? null : activeSurface;

  return (
    <div className="admin-page processing-center-page" aria-busy={loading || Boolean(pendingOperation)}>
      <header className="admin-page-title">
        <div><p>管理后台 / 文档与任务</p><h1>Processing Center</h1><span>管理文档处理，查看真实任务进度和需要处理的问题。</span></div>
        <div className="admin-action-row">
          <ActionLink className="button secondary" href="/admin/review?category=publication_ready">待发布馆藏 <ChevronRight size={15} /></ActionLink>
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
      <nav className="processing-type-tabs processing-center-surfaces" aria-label="处理中心分类" role="tablist">
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
      <section className="processing-v307-maintenance" aria-label="高级维护与配置"><strong>高级维护与配置</strong><nav><Link href="/admin/processing/settings">处理服务设置</Link><Link href="/admin/processing/query-lexicon">检索词典</Link><Link href="/admin/processing/semantic-index">语义索引</Link><Link href="/admin/processing/status">运行状态</Link><Link href="/admin/processing/health">专业自检</Link></nav></section>
      <div
        className="processing-center-surface"
        id={`processing-surface-${activeSurface}`}
        role="tabpanel"
        aria-labelledby={`processing-surface-tab-${activeSurface}`}
        tabIndex={0}
      >
      {healthSurface ? <FunctionalHealthPanel revision={revision} surface={healthSurface} /> : null}
      {activeSurface === "documents" || activeSurface === "projections" ? <DiscoveryIndexPanel revision={revision} /> : null}
      {activeSurface === "overview" || activeSurface === "documents" ? <section className="processing-summary">
        <article><Clock3 size={18} /><strong>{summary.active ?? "—"}</strong><span>等待或运行</span></article>
        <article><FileText size={18} /><strong>{summary.review ?? "—"}</strong><span>待复核</span></article>
        <article><AlertCircle size={18} /><strong>{summary.failed ?? "—"}</strong><span>失败</span></article>
        <article><CheckCircle2 size={18} /><strong>{summary.succeeded ?? "—"}</strong><span>成功</span></article>
      </section> : null}
      {activeSurface === "documents" ? <section className="processing-list admin-panel processing-v307-documents">
        <header><div><h2>文档处理</h2><p>每一步来自实际上传与后台任务记录；未记录的阶段不会标记成功。</p></div><span>{itemMeta?.count ?? "—"} 个文档</span></header>
        <div className="admin-v307-table-scroll"><table><thead><tr><th>文档</th><th>文件与识别</th><th>OCR</th><th>索引</th><th>最近更新</th><th>操作</th></tr></thead><tbody>{items.map(item => {
          const stageCell = (stage: DocumentStage | null | undefined) => stage ? <><span className={`processing-v307-state state-${stage.status}`}>{statusLabels[stage.status] ?? stageLabels[stage.status] ?? stage.status}</span>{stage.progress !== null ? <progress value={stage.progress} max={100} aria-label={`${stage.kind}任务进度`} /> : null}{stage.error ? <small className="processing-v307-stage-error">{stage.error}</small> : null}</> : <span className="muted">尚无任务记录</span>;
          return <tr key={item.id}><td><strong>{item.review_data?.title || item.source_filename}</strong><small>{item.source_filename}</small></td><td>{stageCell(item.document_stages?.file)}</td><td>{stageCell(item.document_stages?.ocr)}</td><td>{stageCell(item.document_stages?.index)}</td><td>{timeLabel(item.updated_at)}</td><td><button type="button" className="button secondary" onClick={() => setSelectedDocumentId(item.id)}>查看详情</button></td></tr>;        })}</tbody></table></div>
        {!loading && itemMeta && !items.length ? <p className="admin-list-state">当前没有待处理上传记录。</p> : null}
        {itemMeta ? <TaskPagination label="上传记录翻页" page={itemPage} pages={Math.max(1, Math.ceil(itemMeta.count / 24))} count={itemMeta.count} busy={loading} onChange={setItemPage} /> : null}
        {selectedDocument ? <section className="processing-v307-document-detail" aria-label="文档处理详情"><header><div><small>文档详情</small><h3>{selectedDocument.review_data?.title || selectedDocument.source_filename}</h3></div><button type="button" className="button secondary" onClick={() => setSelectedDocumentId("")}>返回文档列表</button></header><div className="processing-v307-document-columns"><div><h4>处理进度</h4><p>{stageLabels[selectedDocument.status] ?? selectedDocument.status} · {selectedDocument.stage_progress}%</p><progress value={selectedDocument.stage_progress} max={100} aria-label="文档处理进度" /><dl><div><dt>原始文件</dt><dd>{selectedDocument.source_filename}</dd></div><div><dt>最近更新</dt><dd>{timeLabel(selectedDocument.updated_at)}</dd></div><div><dt>调度状态</dt><dd>{selectedDocument.dispatch_status}</dd></div></dl>{selectedDocument.error_message || selectedDocument.dispatch_error ? <p role="alert">{selectedDocument.error_message || selectedDocument.dispatch_error}</p> : null}<h4>各阶段最新任务</h4><dl>{(["file", "ocr", "index"] as const).map(stageKey => { const stage = selectedDocument.document_stages?.[stageKey]; return <div key={stageKey}><dt>{{file:"文件与文本",ocr:"OCR 识别",index:"检索索引"}[stageKey]}</dt><dd>{stage ? <><strong>{statusLabels[stage.status] ?? stageLabels[stage.status] ?? stage.status}</strong>{stage.progress !== null ? <span> · {stage.progress}%</span> : null}<small>{stage.updated_at ? `更新于 ${timeLabel(stage.updated_at)}` : ""}</small>{stage.error ? <p role="status">{stage.error}</p> : null}</> : "尚无任务记录"}</dd></div>; })}</dl><h4>处理历史</h4>{selectedDocument.attempts.length ? <ol>{selectedDocument.attempts.map(attempt => <li key={attempt.id}><strong>{stageLabels[attempt.stage] ?? jobLabels[attempt.stage] ?? attempt.stage}</strong><span>{statusLabels[attempt.status] ?? attempt.status} · {timeLabel(attempt.started_at)}</span>{attempt.error_message ? <p>{attempt.error_message}</p> : null}</li>)}</ol> : <p>尚无处理历史。</p>}<div className="admin-action-row"><Link className="button" href={`/admin/intake/${selectedDocument.id}#file`}>打开馆藏工作页</Link>{selectedDocument.suggested_action === "retry" || selectedDocument.suggested_action === "resume" ? <ActionButton state={operationState(`item-retry:${selectedDocument.id}`)} disabled={Boolean(pendingOperation)} onClick={() => void retry(selectedDocument)}>重试失败处理</ActionButton> : null}{canRemoveRecords ? <button className="danger-link" type="button" disabled={Boolean(pendingOperation)} onClick={() => setRemoveTarget(selectedDocument)}>移除流程记录</button> : null}</div></div><WorkflowInspector selection={{kind:"pdf",title:"PDF 文件预览",pdfUrl:`/ingestion/items/${selectedDocument.id}/preview/`}} token={getServerSessionCredential()} onClose={() => setSelectedDocumentId("")} /></div></section> : null}
      </section> : null}
      {activeSurface === "overview" || activeSurface === "workers" || activeSurface === "ai-models" || activeSurface === "documents" ? (
      <div className={`processing-health-grid ${activeSurface === "overview" ? "" : "single"}`}>
        {(activeSurface === "overview" || activeSurface === "workers" || activeSurface === "documents") && queueHealth ? (
          <section className={`processing-health ${!queueHealth.healthy || queueHealth.stalled_count ? "warning" : ""}`} role="status">
            <Cpu size={18} /><div><strong>{queueHealth.mode === "inline" ? "本地同步处理" : "后台处理服务"}</strong><span>{queueHealth.message}</span><small>检查时间：{queueHealth.checked_at ? new Date(queueHealth.checked_at).toLocaleString("zh-CN") : "尚无记录"}{queueHealth.stale ? " · 结果已过期" : ""}。刷新任务进度不会重新检测服务。</small></div>
            <dl><div><dt>任务服务</dt><dd>{queueHealth.worker_online ? "在线" : "未确认"}</dd></div><div><dt>OCR</dt><dd>{queueHealth.ocr.reachable ? "可用" : queueHealth.ocr.detail}</dd></div></dl>
          </section>
        ) : null}
        {activeSurface === "overview" || activeSurface === "ai-models" ? <section className={`processing-semantic-health ${semanticHealth?.model_health.available === false ? "warning" : ""}`}>
          <Search size={18} />
          <div><strong>{semanticHealth?.model_health.available === true ? "当前语义模型可用" : semanticHealth?.model_health.available === false ? "当前语义模型不可用" : "语义模型状态待确认"}</strong><span>{semanticHealth?.model_health.reason || "未能读取当前运行配置。"}</span></div>
          {semanticHealth ? <dl><div><dt>模型</dt><dd>{semanticHealth.runtime.model_repo_id || semanticHealth.runtime.model}</dd></div><div><dt>混合检索权重</dt><dd>{Math.round(semanticHealth.runtime.semantic_ratio * 100)}%</dd></div><div><dt>运行方式</dt><dd>{semanticHealth.runtime.offline_mode ? "NAS 离线模型" : "允许联网"}</dd></div></dl> : null}
          {semanticHealth ? <p>混合检索权重只表示关键词与语义结果的融合参数，不是检索质量分数。</p> : null}
          {semanticHealth?.model_health.available === true && historicalNetworkFailures ? <p>下方仍有 {historicalNetworkFailures} 条旧的 Hugging Face 网络错误。它们是历史任务记录，不代表当前离线模型失效。</p> : null}
          <Link href="/admin/processing/semantic-index">打开语义索引诊断 <ChevronRight size={14} /></Link>
        </section> : null}
      </div>
      ) : null}
      {activeSurface === "documents" ? <><OcrTaskMonitor /><details className="admin-panel"><summary>选择另一份馆藏 PDF，重新识别整本</summary><CatalogOcrPicker /></details></> : null}
      {activeSurface === "documents" || activeSurface === "research-sources" ? <section className="processing-list admin-panel" aria-labelledby="workload-controls-title">
        <header className="processing-job-toolbar">
          <div>
            <h2 id="workload-controls-title">{activeSurface === "documents" ? "全库文字识别开关" : "全库联网查找开关"}</h2>
            <p>{activeSurface === "documents" ? "此开关影响全库，不只当前馆藏。暂停时先保存正在识别的页面；重新允许运行不会自动恢复下方旧任务。只想管理一本馆藏，请使用它的识别操作。" : "此开关影响全库。暂停会在下一次查找前生效，已取得的资料保留。"}</p>
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
                disabled={Boolean(pendingOperation) || !canManageTasks}
                onClick={() => void workloadAction(type, !paused)}
              >
                {paused ? <Play size={15} /> : <PauseCircle size={15} />}
                {paused ? type === "ocr" ? "允许新 OCR 任务" : `恢复${jobLabels[type]}` : `暂停${jobLabels[type]}`}
              </ActionButton>
            );
          })}
        </div>
        {!canManageTasks ? <p>当前账户可查看记录；只有管理员或系统所有者可以启停任务。</p> : null}
      </section> : null}
      {activeSurface === "documents" ? <section className="processing-list admin-panel processing-ocr-inventory" aria-labelledby="paused-ocr-inventory-title">
        <header className="processing-job-toolbar">
          <div><h2 id="paused-ocr-inventory-title">暂停的文字识别</h2><p>按馆藏找到尚未结束的识别。可继续剩余页面，或取消这一次识别；两者都保留 PDF、已保存文字和阅读记录。名称随馆藏资料更新。</p></div>
          <span>{pausedOCRInventory?.total ?? 0} 项</span>
        </header>
        <form className="processing-search" onSubmit={(event) => { event.preventDefault(); setOcrPage(1); setOcrQuery(ocrQueryInput.trim()); }}>
          <label>查找馆藏<input value={ocrQueryInput} onChange={(event) => setOcrQueryInput(event.target.value)} placeholder="输入馆藏名称或来源文件名" /></label>
          <button type="submit">查找</button>
        </form>
        <div className="processing-job-cards">
          {(pausedOCRInventory?.items ?? []).map((item) => {
            const decision = item.category === "recoverable" ? "resume" : item.category === "genuinely_failed" ? "acknowledge_failure" : "close";
            const actionLabel = decision === "resume" ? "继续剩余识别" : decision === "close" ? "结束这个旧任务" : "记录为处理失败";
            const percent = item.target_pages > 0 ? Math.round(item.completed_pages * 100 / item.target_pages) : null;
            return (
              <article className={`processing-job-card paused ocr-inventory-${item.category}`} key={item.job_id}>
                <header><div><h3>{item.workbench_url ? <Link href={item.workbench_url}>{item.title}</Link> : item.title}</h3><p>{item.edition_label}</p>{item.title_has_unpublished_changes ? <small>显示已保存的新名称，尚未发布；仍是同一馆藏和文件。</small> : null}</div><b>{ocrCategoryLabels[item.category]}</b></header>
                <p>{item.reasons.map((reason) => ocrReasonLabels[reason] ?? (reason.startsWith("error:") ? `错误代码 ${reason.slice(6)}` : reason)).join("；")}</p>
                <p className="ocr-page-summary"><strong>已完成 {item.completed_pages} / {item.target_pages} 页</strong><span>剩余 {item.remaining_pages} 页</span></p>
                {percent !== null ? <progress value={item.completed_pages} max={item.target_pages} aria-label={`${item.title}已保存的识别页数`}>{percent}%</progress> : <p>暂无可识别页数，请先打开馆藏处理文件问题。</p>}
                <small>任务更新于 {timeLabel(item.updated_at)}。页数完成不等于后续公开更新已完成。</small>
                {decision === "resume" && workloads.ocr?.paused ? <p>全库识别当前暂停。先允许运行，再继续这一本馆藏。</p> : null}
                <details className="ocr-task-details"><summary>查看页码范围和任务记录</summary>
                  <dl><div><dt>本次识别范围</dt><dd>{pageRanges(item.target_page_indexes)}</dd></div><div><dt>剩余页码范围</dt><dd>{pageRanges(item.remaining_page_indexes)}</dd></div><div><dt>创建时间</dt><dd>{timeLabel(item.created_at)}</dd></div><div><dt>任务编号</dt><dd>{item.job_id}</dd></div>{item.newer_job_id ? <div><dt>替代任务编号</dt><dd>{item.newer_job_id}</dd></div> : null}{item.newer_revision_id ? <div><dt>后续文字记录编号</dt><dd>{item.newer_revision_id}</dd></div> : null}</dl>
                </details>
                {item.can_manage ? <details className="ocr-task-actions"><summary>处理这一次识别</summary>
                  <label><span>操作说明（留在处理记录中）</span><input value={ocrDecisionReasons[item.job_id] ?? ""} onChange={(event) => setOCRDecisionReasons((current) => ({ ...current, [item.job_id]: event.target.value }))} placeholder="例如：继续补齐可检索文字，或暂时不需要识别" /></label>
                  <footer><ActionButton state={operationState(`ocr-inventory:${decision}:${item.job_id}`)} pendingLabel="正在处理" disabled={Boolean(pendingOperation) || !(ocrDecisionReasons[item.job_id] ?? "").trim() || (decision === "resume" && Boolean(workloads.ocr?.paused))} onClick={() => void resolvePausedOCR(item, decision)}>{decision === "resume" ? <Play size={14} /> : decision === "close" ? <XCircle size={14} /> : <AlertCircle size={14} />}{actionLabel}</ActionButton>
                  {decision === "resume" ? <ActionButton state={operationState(`ocr-inventory:cancel:${item.job_id}`)} pendingLabel="正在取消" disabled={Boolean(pendingOperation) || !(ocrDecisionReasons[item.job_id] ?? "").trim()} onClick={() => void resolvePausedOCR(item, "cancel")}>取消本次识别</ActionButton> : null}</footer>
                </details> : <p>{item.permission_reason}</p>}
                {item.workbench_url ? <Link href={item.workbench_url}>打开馆藏，查看当前 PDF 和完整进度</Link> : <p>这条记录尚未关联馆藏，不会自动选用其他馆藏。</p>}
              </article>
            );
          })}
          {!loading && !(pausedOCRInventory?.items.length) ? <p className="admin-list-state">当前范围内没有暂停的识别任务。</p> : null}
        </div>
        <TaskPagination label="暂停识别翻页" page={pausedOCRInventory?.page ?? ocrPage} pages={pausedOCRInventory?.pages ?? 1} count={pausedOCRInventory?.total ?? 0} busy={loading} onChange={setOcrPage} />
      </section> : null}
      {loading && !items.length && !jobs.length ? <AsyncStatus state="pending" message="正在读取处理进度……" /> : null}
      <AsyncStatus state="error" message={error} assertive />
      {activeSurface === "workers" ? <section className="processing-list admin-panel processing-review-queue" aria-labelledby="processing-review-title">
        <header className="processing-job-toolbar">
          <div><h2 id="processing-review-title">人工审核队列</h2><p>元数据冲突、同名人物、实体消歧和页码问题集中在这里处理。</p></div>
          <span>共 {reviewMeta?.count ?? 0} 项</span>
        </header>
        <nav className="processing-status-tabs" aria-label="审核任务状态筛选">
          {Object.entries(reviewStatusLabels).map(([value, label]) => (
            <button type="button" className={reviewStatus === value ? `active ${value}` : value} aria-pressed={reviewStatus === value} onClick={() => { setReviewPage(1); setReviewStatus(value); }} key={value}>
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
                {canManageReviewTasks && task.status === "in_progress" && task.upload_item ? <Link href={`/admin/intake/${task.upload_item}#bibliography`}>打开问题并核对</Link> : null}
                {canManageReviewTasks && (task.status === "completed" || task.status === "cancelled") ? <ActionButton state={operationState(`review:reopen:${task.id}`)} pendingLabel="正在恢复" disabled={Boolean(pendingOperation)} onClick={() => void reviewTaskAction(task, "reopen")}>恢复待办</ActionButton> : null}
              </footer>
            </article>
          ))}
          {!loading && !reviewTasks.length ? <p className="admin-list-state">当前状态下没有人工审核任务。</p> : null}
        </div>
        <TaskPagination label="人工待办翻页" page={reviewMeta?.page ?? reviewPage} pages={reviewMeta?.pages ?? 1} count={reviewMeta?.count ?? 0} busy={loading} onChange={setReviewPage} />
      </section> : null}
      {activeSurface === "workers" ? <section className="processing-list admin-panel processing-job-list" id="processing-task-list">
        <header className="processing-job-toolbar"><div><h2>后台任务</h2><p>从全部任务中筛选，按创建时间由新到旧排列。计数来自完整查询，不只本页。</p></div><span>符合条件 {taskMeta?.count ?? 0} 项</span></header>
        <form className="processing-search" onSubmit={(event) => { event.preventDefault(); setJobPage(1); setJobQuery(jobQueryInput.trim()); }}><label>查找馆藏<input value={jobQueryInput} onChange={(event) => setJobQueryInput(event.target.value)} placeholder="馆藏名称或来源文件名" /></label><button type="submit">查找</button></form>
        <nav className="processing-type-tabs" aria-label="任务类型筛选">
          <button type="button" className={!jobType ? "active" : ""} aria-pressed={!jobType} onClick={() => { setJobPage(1); setJobType(""); }}>全部 <strong>{Object.values(typeCounts).reduce((sum, count) => sum + count, 0)}</strong></button>
          {Object.entries(jobLabels).map(([value, label]) => <button type="button" className={jobType === value ? "active" : ""} aria-pressed={jobType === value} onClick={() => { setJobPage(1); setJobType(value); }} key={value}>{label} <strong>{typeCounts[value] ?? 0}</strong></button>)}
        </nav>
        <nav className="processing-status-tabs" aria-label="任务状态筛选">
          <button type="button" className={!jobStatus ? "active" : ""} aria-pressed={!jobStatus} onClick={() => { setJobPage(1); setJobStatus(""); }}>全部状态</button>
          {Object.entries(statusLabels).map(([value, label]) => <button type="button" className={jobStatus === value ? `active ${value}` : value} aria-pressed={jobStatus === value} onClick={() => { setJobPage(1); setJobStatus(value); }} key={value}>{label} <strong>{statusCounts[value] ?? 0}</strong></button>)}
        </nav>
        <div className="processing-job-cards">
          {filteredJobs.map((job) => (
            <article className={`processing-job-card ${job.status}`} key={`${job.source}-${job.id}`}>
              <header><span>{jobLabels[job.job_type] ?? job.job_type}</span><b>{statusLabels[job.status] ?? job.status}</b></header>
              <div className="processing-job-title"><div><strong>{job.title || "全库任务"}</strong><p>{job.edition_label}</p>{job.title_has_unpublished_changes ? <small>显示已保存的新名称，尚未发布。</small> : null}<small>{job.workbench_url ? <Link href={job.workbench_url}>查看当前版本与文件影响</Link> : job.item_id ? <Link href={`/admin/intake/${job.item_id}#file`}>打开来源记录</Link> : job.asset_id ? "文件归属尚未明确" : "系统任务"}</small></div>{!job.ocr_progress ? <strong>{job.progress}%</strong> : null}</div>
              {job.ocr_progress ? <OcrProgressDisplay job={job.ocr_progress} /> : <div className="processing-job-progress" role="progressbar" aria-label="处理进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}><i style={{ width: `${Math.min(100, Math.max(0, job.progress))}%` }} /></div>}
              <p>已用时 {durationLabel(job.duration_seconds)} · {job.finished_at ? `结束于 ${timeLabel(job.finished_at)}` : `创建于 ${timeLabel(job.created_at)}`}</p>
              <details className="ocr-task-details"><summary>查看任务记录与技术信息</summary><dl><div><dt>处理服务</dt><dd>{job.engine || "未记录"}</dd></div><div><dt>配置版本</dt><dd>{job.settings_version || "环境默认"}</dd></div><div><dt>尝试次数</dt><dd>{job.attempt}/{job.max_attempts}</dd></div><div><dt>开始时间</dt><dd>{timeLabel(job.started_at)}</dd></div><div><dt>任务编号</dt><dd>{job.id}</dd></div></dl></details>
              {job.last_error ? <details className="processing-job-error" open={job.status === "failed"}><summary>{job.error_code || "查看错误"}</summary><p>{job.last_error}</p></details> : null}
              {canManageTasks && (job.status === "failed" || job.status === "pending" || job.status === "running" || job.status === "paused") ? (
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
        <TaskPagination label="后台任务翻页" page={taskMeta?.page ?? jobPage} pages={taskMeta?.pages ?? 1} count={taskMeta?.count ?? 0} busy={loading} onChange={setJobPage} />
        {!canManageTasks ? <p>当前账户只读。任务启停与恢复需要管理员或系统所有者权限。</p> : null}
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
