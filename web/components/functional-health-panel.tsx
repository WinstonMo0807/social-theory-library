"use client";

import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  Clock3,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Wrench,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import {
  ActionButton,
  AsyncStatus,
  ToastHost,
  type ActionState,
} from "./action-feedback";
import {
  ProcessingDiagnosticsPanel,
  type ProcessingDiagnosticAction,
  type ProcessingDiagnosticItem,
  type ProcessingDiagnosticsPayload,
} from "./processing-diagnostics";
import { ResearchSourceRegistryPanel } from "./research-source-registry";

type HealthStatus = "healthy" | "degraded" | "failed" | "recovering" | "paused" | "unknown";
type DimensionValue = boolean | null;
export type FunctionalHealthSurface = "overview" | "research-sources" | "ai-models" | "workers" | "projections" | "faults";

type HealthDependency = {
  probe_key: string;
  label: string;
  status: HealthStatus;
  configured: DimensionValue;
  reachable: DimensionValue;
  functional: DimensionValue;
  productive: DimensionValue;
  summary: string;
  last_checked_at: string | null;
  latency_ms: number | null;
  error_code: string;
  details: Record<string, unknown>;
};

type HealthCapability = {
  key: string;
  label: string;
  status: HealthStatus;
  configured: DimensionValue;
  reachable: DimensionValue;
  functional: DimensionValue;
  productive: DimensionValue;
  last_checked_at: string | null;
  dependencies: HealthDependency[];
  incident_count: number;
};

type HealthIncident = {
  id: string;
  incident_key: string;
  capability: string;
  probe_key: string;
  status: "open" | "recovering" | "resolved";
  severity: "info" | "warning" | "critical";
  error_code: string;
  error_category: string;
  error_message: string;
  first_seen_at: string;
  last_seen_at: string;
  last_success_at: string | null;
  occurrence_count: number;
  recovery_attempt_count: number;
  affected_features: string[];
  probable_causes: string[];
  safe_recovery_actions: string[];
  manual_guidance: string;
  details: Record<string, unknown>;
};

type HealthRecovery = {
  id: string;
  incident_id: string;
  action: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled";
  attempt: number;
  max_attempts: number;
  next_retry_at: string | null;
  details: Record<string, unknown>;
  error_code: string;
  created_at: string;
  finished_at: string | null;
};

type FunctionalHealthPayload = {
  version: string;
  generated_at: string;
  overall_status: HealthStatus;
  capabilities: HealthCapability[];
  incidents: HealthIncident[];
  recoveries: HealthRecovery[];
  probe_count: number;
  page_load_performs_live_probes: boolean;
  diagnostics?: ProcessingDiagnosticsPayload;
};

type RunProbeResponse = {
  id: string;
  probe_key: string;
  status: HealthStatus;
  snapshot: FunctionalHealthPayload;
};

type RecoveryResponse = {
  id: string;
  status: HealthRecovery["status"];
  action: string;
  created: boolean;
};

type ActionFeedback = {
  state: ActionState;
  message: string;
  actionKey: string;
};

const EMPTY_ACTION_FEEDBACK: ActionFeedback = { state: "idle", message: "", actionKey: "" };

const STATUS_LABELS: Record<string, string> = {
  healthy: "正常",
  degraded: "降级",
  failed: "故障",
  recovering: "恢复中",
  paused: "已暂停",
  unknown: "待探测",
  open: "待处理",
  resolved: "已恢复",
  queued: "等待执行",
  running: "执行中",
  succeeded: "恢复成功",
  canceled: "已取消",
};

const DIMENSION_LABELS = {
  configured: "已配置",
  reachable: "可连接",
  functional: "可工作",
  productive: "有产出",
} as const;

const RECOVERY_LABELS: Record<string, string> = {
  rerun_probe: "重新探测",
  recover_ingestion_queue: "恢复入库队列",
  recover_semantic_queue: "恢复语义队列",
  recover_query_lexicon: "恢复 QueryLexicon",
  retry_failed_research: "重试失败研究",
};

function statusLabel(value: string) {
  return STATUS_LABELS[value] ?? value;
}

function timeLabel(value: string | null) {
  if (!value) return "尚未探测";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}

function dimensionLabel(value: DimensionValue) {
  if (value === true) return "通过";
  if (value === false) return "未通过";
  return "待探测";
}

function detailLabel(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.length ? value.map(detailLabel).join("、") : "无";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function DimensionList({ source }: { source: Pick<HealthCapability, keyof typeof DIMENSION_LABELS> }) {
  return (
    <ul className="functional-health-dimensions" aria-label="功能健康四项检查">
      {Object.entries(DIMENSION_LABELS).map(([key, label]) => {
        const value = source[key as keyof typeof DIMENSION_LABELS];
        return (
          <li className={value === true ? "pass" : value === false ? "fail" : "unknown"} key={key}>
            <span>{label}</span>
            <strong>{dimensionLabel(value)}</strong>
          </li>
        );
      })}
    </ul>
  );
}

function StatusIcon({ status }: { status: HealthStatus }) {
  if (status === "healthy") return <CheckCircle2 aria-hidden="true" size={17} />;
  if (status === "failed") return <ShieldAlert aria-hidden="true" size={17} />;
  if (status === "degraded" || status === "recovering") return <AlertTriangle aria-hidden="true" size={17} />;
  return <CircleHelp aria-hidden="true" size={17} />;
}

export function FunctionalHealthPanel({
  revision = 0,
  surface = "overview",
}: {
  revision?: number;
  surface?: FunctionalHealthSurface;
}) {
  const [payload, setPayload] = useState<FunctionalHealthPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState<ActionFeedback>(EMPTY_ACTION_FEEDBACK);
  const [pendingAction, setPendingAction] = useState("");
  const mountedRef = useRef(false);
  const snapshotRequestRef = useRef<Promise<void> | null>(null);
  const snapshotAbortRef = useRef<AbortController | null>(null);
  const actionInFlightRef = useRef("");
  const actionAbortRef = useRef<AbortController | null>(null);

  const loadSnapshot = useCallback((allowDuringAction = false): Promise<void> => {
    if (actionInFlightRef.current && !allowDuringAction) return Promise.resolve();
    if (snapshotRequestRef.current) return snapshotRequestRef.current;
    const request = (async () => {
      const token = getServerSessionCredential();
      if (!token) {
        if (mountedRef.current) {
          setLoading(false);
          setError("登录状态尚未就绪，请重新登录后再试。");
        }
        return;
      }
      const controller = new AbortController();
      snapshotAbortRef.current = controller;
      if (mountedRef.current) setLoading(true);
      try {
        const result = await apiRequest<FunctionalHealthPayload>(
          "/catalog/admin/functional-health/",
          { signal: controller.signal },
          token,
        );
        if (!mountedRef.current || controller.signal.aborted) return;
        setPayload(result);
        setError("");
      } catch (reason) {
        if (!mountedRef.current || controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "功能健康快照读取失败。");
      } finally {
        if (snapshotAbortRef.current === controller) snapshotAbortRef.current = null;
        if (mountedRef.current && !controller.signal.aborted) setLoading(false);
      }
    })();
    snapshotRequestRef.current = request;
    void request.finally(() => {
      if (snapshotRequestRef.current === request) snapshotRequestRef.current = null;
    });
    return request;
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      snapshotAbortRef.current?.abort();
      actionAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void loadSnapshot(), 0);
    const refreshTimer = window.setInterval(() => void loadSnapshot(), 30000);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(refreshTimer);
    };
  }, [loadSnapshot, revision]);

  async function runProbe(probeKey: string, label: string) {
    const token = getServerSessionCredential();
    if (!token) {
      if (mountedRef.current) setFeedback({ state: "error", message: "登录状态尚未就绪，无法运行探测。", actionKey: "auth" });
      return;
    }
    if (actionInFlightRef.current) return;
    const actionKey = `probe:${probeKey}`;
    actionInFlightRef.current = actionKey;
    const controller = new AbortController();
    actionAbortRef.current = controller;
    if (mountedRef.current) {
      setPendingAction(actionKey);
      setFeedback({ state: "pending", message: `正在探测${label}。`, actionKey });
    }
    try {
      snapshotAbortRef.current?.abort();
      if (snapshotRequestRef.current) await snapshotRequestRef.current;
      if (!mountedRef.current || controller.signal.aborted) return;
      setLoading(false);
      const result = await apiRequest<RunProbeResponse>(
        "/catalog/admin/functional-health/",
        {
          method: "POST",
          body: JSON.stringify({ action: "run_probe", probe_key: probeKey }),
          signal: controller.signal,
        },
        token,
      );
      if (!mountedRef.current || controller.signal.aborted) return;
      setPayload(result.snapshot);
      setError("");
      setFeedback({ state: "success", message: `${label}探测完成，结果为${statusLabel(result.status)}。`, actionKey });
    } catch (reason) {
      if (!mountedRef.current || controller.signal.aborted) return;
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : `${label}探测失败。`, actionKey });
    } finally {
      if (actionAbortRef.current === controller) actionAbortRef.current = null;
      if (actionInFlightRef.current === actionKey) actionInFlightRef.current = "";
      if (mountedRef.current) setPendingAction("");
    }
  }

  async function recoverIncident(incident: HealthIncident, action: string) {
    const token = getServerSessionCredential();
    if (!token) {
      if (mountedRef.current) setFeedback({ state: "error", message: "登录状态尚未就绪，无法请求恢复。", actionKey: "auth" });
      return;
    }
    if (actionInFlightRef.current) return;
    const actionKey = `recover:${incident.id}:${action}`;
    actionInFlightRef.current = actionKey;
    const controller = new AbortController();
    actionAbortRef.current = controller;
    if (mountedRef.current) {
      setPendingAction(actionKey);
      setFeedback({ state: "pending", message: `正在请求${RECOVERY_LABELS[action] ?? action}。`, actionKey });
    }
    try {
      snapshotAbortRef.current?.abort();
      if (snapshotRequestRef.current) await snapshotRequestRef.current;
      if (!mountedRef.current || controller.signal.aborted) return;
      setLoading(false);
      const result = await apiRequest<RecoveryResponse>(
        "/catalog/admin/functional-health/",
        {
          method: "POST",
          body: JSON.stringify({
            action: "recover",
            incident_id: incident.id,
            recovery_action: action,
            idempotency_key: `incident:${incident.id}:occurrence:${incident.occurrence_count}:${action}`,
          }),
          signal: controller.signal,
        },
        token,
      );
      if (!mountedRef.current || controller.signal.aborted) return;
      setFeedback({
        state: "success",
        message: result.created
          ? `${RECOVERY_LABELS[action] ?? action}已进入安全恢复队列。`
          : "同一故障发生次数下已有相同恢复请求，不会重复执行。",
        actionKey,
      });
      await loadSnapshot(true);
    } catch (reason) {
      if (!mountedRef.current || controller.signal.aborted) return;
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : "恢复请求失败。", actionKey });
    } finally {
      if (actionAbortRef.current === controller) actionAbortRef.current = null;
      if (actionInFlightRef.current === actionKey) actionInFlightRef.current = "";
      if (mountedRef.current) setPendingAction("");
    }
  }

  async function runDiagnosticAction(item: ProcessingDiagnosticItem, action: ProcessingDiagnosticAction) {
    const token = getServerSessionCredential();
    if (!token) {
      if (mountedRef.current) setFeedback({ state: "error", message: "登录状态尚未就绪，无法提交诊断恢复动作。", actionKey: "auth" });
      return;
    }
    if (Boolean(actionInFlightRef.current)) return;
    const actionKey = `diagnostic:${item.id}:${action.key}`;
    actionInFlightRef.current = String(actionKey);
    const diagnosticController = new AbortController();
    actionAbortRef.current = diagnosticController;
    if (mountedRef.current) {
      setPendingAction(actionKey);
      setFeedback({ state: "pending", message: `正在提交${action.label}。`, actionKey });
    }
    try {
      snapshotAbortRef.current?.abort();
      if (snapshotRequestRef.current) await snapshotRequestRef.current;
      if (!mountedRef.current || diagnosticController.signal.aborted) return;
      await apiRequest(
        action.endpoint,
        {
          method: action.method,
          body: JSON.stringify(action.body),
          signal: diagnosticController.signal,
        },
        token,
      );
      if (!mountedRef.current || diagnosticController.signal.aborted) return;
      setFeedback({ state: "success", message: `${action.label}已提交，请观察下一次 revision 快照。`, actionKey });
      await loadSnapshot(true);
    } catch (reason) {
      if (!mountedRef.current || diagnosticController.signal.aborted) return;
      setFeedback({ state: "error", message: reason instanceof Error ? reason.message : `${action.label}失败。`, actionKey });
    } finally {
      if (actionAbortRef.current === diagnosticController) actionAbortRef.current = null;
      if (actionInFlightRef.current === actionKey) actionInFlightRef.current = "";
      if (mountedRef.current) {
        setPendingAction("");
      }
    }
  }

  const capabilityLabels = useMemo(
    () => new Map((payload?.capabilities ?? []).map((row) => [row.key, row.label])),
    [payload?.capabilities],
  );

  function actionState(actionKey: string): ActionState {
    if (pendingAction === actionKey) return "pending";
    return feedback.actionKey === actionKey ? feedback.state : "idle";
  }

  const surfaceCopy = surface === "research-sources"
    ? ["Research Sources", "检查来源用途、配置要求、最近成功和受影响功能。页面不会回显 Secret。"]
    : surface === "ai-models"
      ? ["AI 与模型", "检查 runtime profile、Provider、Prompt 和人工接受表现。"]
      : surface === "workers"
        ? ["任务与 Worker", "检查 capability 缺口、executor heartbeat、backlog 和负载。"]
        : surface === "projections"
          ? ["Projection 一致性", "检查 source revision、projected revision 和公开功能影响。"]
          : surface === "faults"
            ? ["故障与恢复", "保留真实故障、探测依据和后端允许的安全恢复动作。"]
            : ["从读者功能查看系统是否真正可用", "页面读取最近一次探测结果，不会在打开时连接外部服务。探测和恢复只在明确点击后执行。"];
  const diagnosticsView = surface === "ai-models" || surface === "workers" || surface === "projections"
    ? surface
    : surface === "overview"
      ? "overview"
      : null;

  return (
    <section className="functional-health-panel admin-panel" aria-labelledby="functional-health-title" aria-busy={loading || Boolean(pendingAction)}>
      <header>
        <div>
          <p className="functional-health-kicker">功能健康</p>
          <h2 id="functional-health-title">{surfaceCopy[0]}</h2>
          <span>{surfaceCopy[1]}</span>
        </div>
        <div className="functional-health-header-actions">
          {payload ? (
            <span className={`functional-health-status ${payload.overall_status}`}>
              <StatusIcon status={payload.overall_status} />
              整体{statusLabel(payload.overall_status)}
            </span>
          ) : null}
          <ActionButton
            className="button secondary"
            state={loading ? "pending" : error ? "error" : "idle"}
            pendingLabel="正在刷新"
            errorLabel="重新刷新"
            onClick={() => void loadSnapshot()}
            disabled={Boolean(pendingAction)}
          ><RefreshCw size={15} />刷新快照</ActionButton>
        </div>
      </header>

      <AsyncStatus state="error" message={error} className="functional-health-inline-status" assertive />
      {loading && !payload ? <AsyncStatus state="pending" message="正在读取最近的功能健康记录……" className="functional-health-inline-status" /> : null}
      <ToastHost
        items={feedback.message ? [{ id: feedback.actionKey || "functional-health", state: feedback.state === "idle" ? "success" : feedback.state, message: feedback.message }] : []}
        onDismiss={() => setFeedback(EMPTY_ACTION_FEEDBACK)}
        label="功能健康操作反馈"
      />

      {payload ? (
        <>
          {surface === "overview" ? <div className="functional-health-overview" aria-label="功能健康摘要">
            <div><Activity size={16} /><span>功能</span><strong>{payload.capabilities.length}</strong></div>
            <div><ShieldAlert size={16} /><span>待处理事件</span><strong>{payload.incidents.length}</strong></div>
            <div><Clock3 size={16} /><span>快照时间</span><strong>{timeLabel(payload.generated_at)}</strong></div>
            <div><Wrench size={16} /><span>已登记探测</span><strong>{payload.probe_count}</strong></div>
          </div> : null}

          {payload.diagnostics && diagnosticsView ? (
            <ProcessingDiagnosticsPanel
              diagnostics={payload.diagnostics}
              pendingAction={pendingAction}
              actionState={actionState}
              onAction={(item, action) => void runDiagnosticAction(item, action)}
              view={diagnosticsView}
            />
          ) : null}

          {surface === "research-sources" ? <ResearchSourceRegistryPanel revision={revision} /> : null}

          {surface === "faults" ? <div className="functional-health-capability-grid">
            {payload.capabilities.map((capability) => (
              <article className={`functional-health-capability ${capability.status}`} key={capability.key}>
                <header>
                  <div>
                    <h3>{capability.label}</h3>
                    <span>最近检查 {timeLabel(capability.last_checked_at)}</span>
                  </div>
                  <span className={`functional-health-status ${capability.status}`}>
                    <StatusIcon status={capability.status} />
                    {statusLabel(capability.status)}
                  </span>
                </header>
                <DimensionList source={capability} />
                <div className="functional-health-card-meta">
                  <span>{capability.dependencies.length} 项依赖</span>
                  <span>{capability.incident_count ? `${capability.incident_count} 个待处理事件` : "无待处理事件"}</span>
                </div>
                <div className="functional-health-dependencies">
                  {capability.dependencies.map((dependency) => (
                    <details key={dependency.probe_key}>
                      <summary>
                        <span><StatusIcon status={dependency.status} />{dependency.label}</span>
                        <b>{statusLabel(dependency.status)}</b>
                      </summary>
                      <p>{dependency.summary || "本次探测没有附加说明。"}</p>
                      <DimensionList source={dependency} />
                      <dl>
                        <div><dt>探测键</dt><dd>{dependency.probe_key}</dd></div>
                        <div><dt>最近探测</dt><dd>{timeLabel(dependency.last_checked_at)}</dd></div>
                        <div><dt>耗时</dt><dd>{dependency.latency_ms === null ? "—" : `${dependency.latency_ms} ms`}</dd></div>
                        <div><dt>错误代码</dt><dd>{dependency.error_code || "无"}</dd></div>
                        {Object.entries(dependency.details ?? {}).slice(0, 8).map(([key, value]) => (
                          <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{detailLabel(value)}</dd></div>
                        ))}
                      </dl>
                      <ActionButton
                        className="button secondary functional-health-probe-button"
                        state={actionState(`probe:${dependency.probe_key}`)}
                        pendingLabel="探测中"
                        successLabel="探测完成"
                        errorLabel="重试探测"
                        disabled={Boolean(pendingAction)}
                        onClick={() => void runProbe(dependency.probe_key, dependency.label)}
                      >
                        <RefreshCw size={14} />立即探测
                      </ActionButton>
                    </details>
                  ))}
                </div>
              </article>
            ))}
          </div> : null}

          {surface === "faults" ? <section className="functional-health-incidents" id="processing-faults-recovery" aria-labelledby="functional-health-incidents-title">
            <header>
              <div><h3 id="functional-health-incidents-title">待处理事件</h3><p>保留故障发生次数、可能原因和受影响功能。恢复动作来自后端允许清单。</p></div>
              <strong>{payload.incidents.length}</strong>
            </header>
            {payload.incidents.length ? (
              <div className="functional-health-incident-list">
                {payload.incidents.map((incident) => (
                  <article className={`functional-health-incident ${incident.severity}`} key={incident.id}>
                    <header>
                      <div>
                        <span>{capabilityLabels.get(incident.capability) ?? incident.capability}</span>
                        <h4>{incident.error_message || incident.error_code || "功能探测异常"}</h4>
                      </div>
                      <b>{incident.status === "recovering" ? "恢复中" : incident.severity === "critical" ? "严重" : incident.severity === "warning" ? "警告" : "提示"}</b>
                    </header>
                    <dl>
                      <div><dt>探测项</dt><dd>{incident.probe_key}</dd></div>
                      <div><dt>错误代码</dt><dd>{incident.error_code || "未记录"}</dd></div>
                      <div><dt>首次发现</dt><dd>{timeLabel(incident.first_seen_at)}</dd></div>
                      <div><dt>最近发现</dt><dd>{timeLabel(incident.last_seen_at)}</dd></div>
                      <div><dt>发生次数</dt><dd>{incident.occurrence_count}</dd></div>
                      <div><dt>恢复尝试</dt><dd>{incident.recovery_attempt_count}</dd></div>
                    </dl>
                    {incident.affected_features.length ? <p><strong>受影响功能</strong>{incident.affected_features.join("、")}</p> : null}
                    {incident.probable_causes.length ? <div><strong>可能原因</strong><ul>{incident.probable_causes.map((cause) => <li key={cause}>{cause}</li>)}</ul></div> : null}
                    {incident.manual_guidance ? <p><strong>人工处理提示</strong>{incident.manual_guidance}</p> : null}
                    {incident.safe_recovery_actions.length ? (
                      <footer>
                        {incident.safe_recovery_actions.map((action) => (
                          <ActionButton
                            className="button secondary"
                            key={action}
                            state={actionState(`recover:${incident.id}:${action}`)}
                            pendingLabel="正在请求恢复"
                            successLabel="恢复已排队"
                            errorLabel="重试恢复"
                            disabled={Boolean(pendingAction) || incident.status === "recovering"}
                            onClick={() => void recoverIncident(incident, action)}
                          >
                            <RotateCcw size={14} />{RECOVERY_LABELS[action] ?? action}
                          </ActionButton>
                        ))}
                      </footer>
                    ) : null}
                  </article>
                ))}
              </div>
            ) : <p className="functional-health-empty"><CheckCircle2 size={17} />当前没有待处理的功能健康事件。</p>}
          </section> : null}

          {surface === "faults" ? <section className="functional-health-recoveries" aria-labelledby="functional-health-recoveries-title">
            <header><div><h3 id="functional-health-recoveries-title">最近恢复记录</h3><p>显示最近请求及其执行结果，不会因刷新页面重复执行。</p></div><strong>{payload.recoveries.length}</strong></header>
            {payload.recoveries.length ? (
              <div className="functional-health-recovery-list">
                {payload.recoveries.slice(0, 12).map((recovery) => (
                  <article key={recovery.id}>
                    <div><strong>{RECOVERY_LABELS[recovery.action] ?? recovery.action}</strong><span>{timeLabel(recovery.created_at)}</span></div>
                    <span className={`functional-health-recovery-status ${recovery.status}`}>{statusLabel(recovery.status)}</span>
                    <span>尝试 {recovery.attempt}/{recovery.max_attempts}</span>
                    {recovery.error_code ? <span className="error">{recovery.error_code}</span> : null}
                  </article>
                ))}
              </div>
            ) : <p className="functional-health-empty">尚无恢复操作记录。</p>}
          </section> : null}
        </>
      ) : null}
    </section>
  );
}
