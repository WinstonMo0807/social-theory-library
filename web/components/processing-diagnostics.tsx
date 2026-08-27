"use client";

import {
  AlertTriangle,
  CheckCircle2,
  Cpu,
  DatabaseZap,
  RefreshCw,
  ServerCog,
} from "lucide-react";
import { ActionButton, type ActionState } from "./action-feedback";

export type ProcessingDiagnosticAction = {
  key: string;
  label: string;
  endpoint: string;
  method: "POST";
  body: Record<string, unknown>;
};

export type ProcessingDiagnosticItem = {
  id: string;
  kind: "projection" | "capability" | "provider";
  status: string;
  severity: "info" | "warning" | "critical";
  title: string;
  reason: string;
  affected_features: string[];
  publication_blocking: boolean;
  suggested_action: string;
  guidance: string;
  safe_actions: ProcessingDiagnosticAction[];
  details: Record<string, unknown>;
};

type DiagnosticSection = {
  key: "projections" | "capabilities" | "providers";
  label: string;
  description: string;
  items: ProcessingDiagnosticItem[];
  summary: Record<string, number>;
};

export type ProcessingDiagnosticsView = "overview" | "ai-models" | "workers" | "projections";

type ExecutorSnapshot = {
  id: string;
  executor_id: string;
  display_name: string;
  kind: string;
  status: string;
  heartbeat_fresh: boolean;
  last_heartbeat_at: string | null;
  heartbeat_expires_at: string | null;
  capabilities: string[];
  model_revisions: Record<string, string>;
  current_load: number;
  concurrency: number;
  backlog?: {
    compatible_ready: number;
    compatible_waiting: number;
    claimed: number;
  };
};

type ProviderProfileSnapshot = {
  capability: string;
  profile: string;
  provider: string;
  model: string;
  status: string;
  fallback_profile?: string;
  fallback_available: boolean;
  management_url?: string;
};

export type ProcessingDiagnosticsPayload = {
  version: string;
  generated_at: string;
  page_load_performs_live_probes: false;
  summary: {
    issue_count: number;
    blocking_count: number;
    stale_projection_count: number;
    missing_capability_count: number;
    provider_degradation_count: number;
    research_source_degradation_count?: number;
  };
  functional_impacts?: Array<{
    id: string;
    title: string;
    reason: string;
    affected_features: string[];
    publication_blocking: boolean;
    severity: "info" | "warning" | "critical";
  }>;
  sections: DiagnosticSection[];
  executors: ExecutorSnapshot[];
  provider_profiles: ProviderProfileSnapshot[];
  prompt_registry?: {
    active: Array<{
      id: string;
      key: string;
      version: number;
      capability: string;
      task_profile_key: string;
      content_hash: string;
      schema_hash: string;
      activated_at: string | null;
    }>;
    draft_count: number;
    retired_count: number;
    missing_active_for_task_profiles: string[];
    management_endpoint: string;
  };
  feedback_calibration?: Array<{
    task_profile_key: string;
    provider: string;
    prompt_key: string;
    decisions: Record<string, number>;
    total: number;
    acceptance_rate: number | null;
  }>;
};

const SECTION_ICONS = {
  projections: DatabaseZap,
  capabilities: Cpu,
  providers: ServerCog,
} as const;

const STATUS_LABELS: Record<string, string> = {
  stale: "落后",
  waiting_for_capability: "等待能力",
  failed: "失败",
  unknown: "待确认",
  open: "降级",
  recovering: "恢复中",
  degraded: "降级",
};

function timeLabel(value: string | null) {
  if (!value) return "尚无 heartbeat";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString("zh-CN", { hour12: false });
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

export function ProcessingDiagnosticsPanel({
  diagnostics,
  pendingAction,
  actionState,
  onAction,
  view = "overview",
}: {
  diagnostics: ProcessingDiagnosticsPayload;
  pendingAction: string;
  actionState: (actionKey: string) => ActionState;
  onAction: (item: ProcessingDiagnosticItem, action: ProcessingDiagnosticAction) => void;
  view?: ProcessingDiagnosticsView;
}) {
  const visibleSections = view === "ai-models"
    ? diagnostics.sections.filter((section) => section.key === "providers")
    : view === "workers"
      ? diagnostics.sections.filter((section) => section.key === "capabilities")
      : view === "projections"
        ? diagnostics.sections.filter((section) => section.key === "projections")
        : [];
  const visibleItems = visibleSections.flatMap((section) => section.items);
  const issueCount = view === "overview" ? diagnostics.summary.issue_count : visibleItems.length;
  const blockingCount = view === "overview"
    ? diagnostics.summary.blocking_count
    : visibleItems.filter((item) => item.publication_blocking).length;
  const title = view === "overview"
    ? "知识与智能新鲜度"
    : view === "ai-models"
      ? "AI Runtime 与模型配置"
      : view === "workers"
        ? "任务能力与 Worker"
        : "Projection 一致性";
  const description = view === "overview"
    ? "从持久化 revision、任务需求和脱敏 Provider 配置判断下游是否真的可用。"
    : view === "ai-models"
      ? "查看模型 profile、Provider 状态、Prompt 和真实人工接受表现。Secret 不会返回前端。"
      : view === "workers"
        ? "查看 capability 缺口、executor heartbeat、当前负载和可领取 backlog。"
        : "比较 source revision 与 projected revision，定位落后或失败的公开投影。";
  const titleId = `processing-diagnostics-title-${view}`;

  return (
    <section className="processing-diagnostics admin-panel" aria-labelledby={titleId}>
      <header>
        <div>
          <p>Processing Center 3.0</p>
          <h2 id={titleId}>{title}</h2>
          <span>{description}</span>
        </div>
        <span className={blockingCount ? "blocking" : issueCount ? "warning" : "healthy"}>
          {blockingCount
            ? `${blockingCount} 项阻断`
            : issueCount
              ? `${issueCount} 项需处理`
              : "当前一致"}
        </span>
      </header>

      {view === "overview" ? <div className="processing-diagnostics-summary" aria-label="处理中心诊断摘要">
        <div><DatabaseZap size={17} /><span>落后投影</span><strong>{diagnostics.summary.stale_projection_count}</strong></div>
        <div><Cpu size={17} /><span>缺少能力</span><strong>{diagnostics.summary.missing_capability_count}</strong></div>
        <div><ServerCog size={17} /><span>Provider 降级</span><strong>{diagnostics.summary.provider_degradation_count}</strong></div>
        <div>{diagnostics.summary.blocking_count ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}<span>发布阻断</span><strong>{diagnostics.summary.blocking_count}</strong></div>
      </div> : null}

      {view === "overview" && (diagnostics.functional_impacts ?? []).length ? (
        <section className="processing-diagnostic-section" id="processing-overview" aria-labelledby="processing-functional-impact-title">
          <header><div><AlertTriangle size={17} /><h3 id="processing-functional-impact-title">当前用户功能影响</h3></div><span>先判断读者和编辑者会遇到什么，再查看依赖详情。</span><strong>{diagnostics.functional_impacts?.length ?? 0}</strong></header>
          <div className="processing-diagnostic-list">
            {(diagnostics.functional_impacts ?? []).map((impact) => (
              <article className={`processing-diagnostic-item ${impact.severity}`} key={impact.id}>
                <header><div><span>{impact.publication_blocking ? "影响发布" : "可降级继续"}</span><h4>{impact.title}</h4></div><b>{impact.publication_blocking ? "阻断" : "非阻断"}</b></header>
                <p>{impact.reason}</p>
                <dl><div><dt>受影响功能</dt><dd>{impact.affected_features.join("、") || "未记录"}</dd></div><div><dt>发布</dt><dd>{impact.publication_blocking ? "相关发布需要先恢复" : "上传、编辑和发布可继续"}</dd></div></dl>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {visibleSections.length ? <div className="processing-diagnostic-sections">
        {visibleSections.map((section) => {
          const SectionIcon = SECTION_ICONS[section.key];
          return (
            <section className="processing-diagnostic-section" id={section.key === "projections" ? "processing-projections" : section.key === "capabilities" ? "processing-workers" : "processing-ai-models"} key={section.key} aria-labelledby={`diagnostic-${section.key}`}>
              <header>
                <div><SectionIcon size={17} /><h3 id={`diagnostic-${section.key}`}>{section.label}</h3></div>
                <span>{section.description}</span>
                <strong>{section.items.length}</strong>
              </header>
              {section.items.length ? (
                <div className="processing-diagnostic-list">
                  {section.items.map((item) => (
                    <article className={`processing-diagnostic-item ${item.severity}`} key={item.id}>
                      <header>
                        <div><span>{item.kind}</span><h4>{item.title}</h4></div>
                        <b>{STATUS_LABELS[item.status] ?? item.status}</b>
                      </header>
                      <dl>
                        <div><dt>原因</dt><dd>{item.reason}</dd></div>
                        <div><dt>受影响功能</dt><dd>{item.affected_features.join("、") || "未记录"}</dd></div>
                        <div><dt>是否阻断</dt><dd className={item.publication_blocking ? "blocking" : "non-blocking"}>{item.publication_blocking ? "阻断相关发布" : "不阻断发布"}</dd></div>
                        <div><dt>建议动作</dt><dd>{item.suggested_action}</dd></div>
                      </dl>
                      <p><strong>{item.safe_actions.length ? "安全恢复说明" : "处理指引"}</strong>{item.guidance}</p>
                      {Object.keys(item.details).length ? (
                        <details>
                          <summary>查看 revision 与任务信息</summary>
                          <dl className="processing-diagnostic-details">
                            {Object.entries(item.details).slice(0, 12).map(([key, value]) => (
                              <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{detailLabel(value)}</dd></div>
                            ))}
                          </dl>
                        </details>
                      ) : null}
                      {item.safe_actions.length ? (
                        <footer>
                          {item.safe_actions.map((action) => {
                            const actionKey = `diagnostic:${item.id}:${action.key}`;
                            return (
                              <ActionButton
                                className="button secondary"
                                key={action.key}
                                state={actionState(actionKey)}
                                pendingLabel="正在提交安全恢复"
                                successLabel="恢复已提交"
                                errorLabel="重试恢复"
                                disabled={Boolean(pendingAction)}
                                onClick={() => onAction(item, action)}
                              >
                                <RefreshCw size={14} />{action.label}
                              </ActionButton>
                            );
                          })}
                        </footer>
                      ) : null}
                      {item.kind === "capability" ? (
                        <footer>
                          <a className="button secondary" href="/admin/settings#ai-runtime">配置模型</a>
                          <a className="button secondary" href="#processing-worker-inventory">连接 4070</a>
                        </footer>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : <p className="processing-diagnostic-empty"><CheckCircle2 size={16} />当前没有{section.label}问题。</p>}
            </section>
          );
        })}
      </div> : null}

      {view === "workers" ? <div className="processing-runtime-inventory">
        <details id="processing-worker-inventory" open>
          <summary>Executor heartbeat <strong>{diagnostics.executors.length}</strong></summary>
          <div className="processing-runtime-rows">
            {diagnostics.executors.map((executor) => (
              <article key={executor.id}>
                <div><strong>{executor.display_name || executor.executor_id}</strong><span>{executor.kind}</span></div>
                <b className={executor.heartbeat_fresh ? "healthy" : "offline"}>{executor.heartbeat_fresh ? "在线" : "离线或过期"}</b>
                <span>{executor.capabilities.join("、") || "未声明能力"}</span>
                <span>负载 {executor.current_load}/{executor.concurrency} · {timeLabel(executor.last_heartbeat_at)}</span>
                <span>Backlog 可领取 {executor.backlog?.compatible_ready ?? 0} · 等待能力 {executor.backlog?.compatible_waiting ?? 0} · 已领取 {executor.backlog?.claimed ?? 0}</span>
              </article>
            ))}
            {!diagnostics.executors.length ? <p>尚无已登记 executor。</p> : null}
          </div>
        </details>
      </div> : null}

      {view === "ai-models" ? <div className="processing-runtime-inventory">
        <p className="processing-configuration-boundary" role="note">
          此处只显示脱敏状态和可安全修改的入口。Provider Secret、AI endpoint 与运行时敏感配置需由 System Owner 在服务器环境或受保护设置中完成，页面不会读取或回显密钥。
        </p>
        <details id="processing-ai-runtime" open>
          <summary>AI Runtime profiles <strong>{diagnostics.provider_profiles.length}</strong></summary>
          <div className="processing-runtime-rows">
            {diagnostics.provider_profiles.map((profile) => (
              <article key={`${profile.capability}:${profile.profile}`}>
                <div><strong>{profile.capability}</strong><span>{profile.profile}</span></div>
                <b>{profile.status}</b>
                <span>{profile.provider || "none"} · {profile.model || "未配置模型"}</span>
                <span>{profile.fallback_available ? `fallback ${profile.fallback_profile} 可用` : "无已确认可用 fallback"}</span>
                {profile.management_url ? <a href={profile.management_url}>配置模型</a> : null}
              </article>
            ))}
          </div>
        </details>
        <details>
          <summary>Prompt Registry <strong>{diagnostics.prompt_registry?.active.length ?? 0}</strong></summary>
          <div className="processing-runtime-rows">
            {(diagnostics.prompt_registry?.active ?? []).map((prompt) => (
              <article key={prompt.id}>
                <div><strong>{prompt.key}</strong><span>v{prompt.version}</span></div>
                <b>{prompt.capability}</b>
                <span>{prompt.task_profile_key || "未限定 Task Profile"}</span>
                <span>内容 {prompt.content_hash.slice(0, 12)} · schema {prompt.schema_hash.slice(0, 12) || "无"}</span>
              </article>
            ))}
            {diagnostics.prompt_registry?.missing_active_for_task_profiles.length ? (
              <p>缺少 active Prompt：{diagnostics.prompt_registry.missing_active_for_task_profiles.join("、")}</p>
            ) : null}
            {!(diagnostics.prompt_registry?.active.length) ? <p>尚无已启用 Prompt。</p> : null}
          </div>
        </details>
        <details>
          <summary>人工接受表现 <strong>{(diagnostics.feedback_calibration ?? []).length}</strong></summary>
          <div className="processing-runtime-rows">
            {(diagnostics.feedback_calibration ?? []).map((row) => (
              <article key={`${row.task_profile_key}:${row.provider}:${row.prompt_key}`}>
                <div><strong>{row.task_profile_key || "未标注任务"}</strong><span>{row.prompt_key || "未标注 Prompt"}</span></div>
                <b>{row.acceptance_rate === null ? "样本不足" : `接受率 ${Math.round(row.acceptance_rate * 100)}%`}</b>
                <span>{row.provider || "未标注 Provider"} · {row.total} 次人工决定</span>
                <span>采用 {row.decisions.accept ?? 0} · 修改后采用 {row.decisions.accept_with_edit ?? 0} · 拒绝 {row.decisions.reject ?? 0} · 稍后 {row.decisions.defer ?? 0}</span>
              </article>
            ))}
            {!(diagnostics.feedback_calibration ?? []).length ? <p>尚无可校准的人工决定。</p> : null}
          </div>
        </details>
      </div> : null}
    </section>
  );
}
