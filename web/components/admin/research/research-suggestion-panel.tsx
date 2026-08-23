"use client";

import { ExternalLink, FlaskConical, Search } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ActionButton, AsyncStatus, type ActionState } from "@/components/action-feedback";
import { apiRequest } from "@/lib/api";
import type { WorkflowCandidate } from "../workflow/workflow-types";
import {
  groupResearchSuggestions,
  isTerminalResearchStatus,
  prefixedResearchChangedFields,
  researchRunSuggestions,
  RESEARCH_SUGGESTION_REFRESH_EVENT,
} from "./research-suggestion-state";
import { useResearchWorkspace } from "./research-workspace-context";

export type ResearchRunPayload = {
  id?: string;
  status?: string;
  trigger?: string;
  active_step?: string;
  changed_fields?: string[];
  plan?: Array<Record<string, unknown>>;
  local_results?: Record<string, unknown>;
  external_results?: Record<string, unknown>;
  diagnostics?: Record<string, unknown>;
  error?: { code?: string; message?: string } | null;
  created?: boolean;
};

export const ResearchSuggestionCapabilityContext = createContext(false);

const EMPTY_DRAFT: Record<string, unknown> = {};
const EMPTY_CHANGED_FIELDS: readonly string[] = [];
const FAST_POLL_INTERVAL_MS = 1_000;
const SLOW_POLL_INTERVAL_MS = 5_000;
const FAST_POLL_ATTEMPTS = 45;
const SLOW_POLL_ATTEMPTS = 24;
const MAX_CONSECUTIVE_POLL_FAILURES = 3;

const tierLabels: Record<string, string> = {
  in_library: "本馆实体",
  query_lexicon: "QueryLexicon 匹配",
  pdf_evidence: "当前 PDF / OCR",
  structured_source: "权威与结构化来源",
  web_evidence: "已打开的联网证据",
  research_lead: "联网发现线索",
};

const statusLabels: Record<string, string> = {
  not_started: "尚未开始",
  queued: "等待研究",
  running: "研究中",
  completed: "已完成",
  degraded: "部分来源不可用",
  failed: "研究失败",
  canceled: "已取消",
};

function endpointFor(mode: "intake" | "maintenance", itemId?: string, workId?: string, editionId?: string) {
  const endpoint = mode === "intake"
    ? `/catalog/admin/intake/${encodeURIComponent(itemId ?? "")}/research/`
    : `/catalog/admin/library/works/${encodeURIComponent(workId ?? "")}/research/`;
  return editionId
    ? `${endpoint}?edition_id=${encodeURIComponent(editionId)}`
    : endpoint;
}

function runDetailEndpoint(runId: string) {
  return `/catalog/admin/research/runs/${encodeURIComponent(runId)}/`;
}

function diagnosticErrors(payload: ResearchRunPayload | null): Array<Record<string, unknown>> {
  const value = payload?.diagnostics?.errors;
  return Array.isArray(value)
    ? value.filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === "object")
    : [];
}

function stableDraftFingerprint(draft: Record<string, unknown>): string {
  try {
    return JSON.stringify(draft);
  } catch {
    return "draft-not-serializable";
  }
}

export function ResearchSuggestionPanel({
  mode,
  itemId,
  workId,
  step,
  field,
  token,
  canRun,
  onInspect,
  onMessage,
}: {
  mode: "intake" | "maintenance";
  itemId?: string;
  workId?: string;
  step: string;
  field?: string;
  token: string | null;
  canRun?: boolean;
  onInspect?: (items: WorkflowCandidate[], title: string) => void;
  onUpdated?: () => void;
  onMessage?: (message: string) => void;
}) {
  const workspace = useResearchWorkspace();
  const inheritedCanRun = useContext(ResearchSuggestionCapabilityContext);
  const canRunResearch = canRun ?? workspace?.canRun ?? inheritedCanRun;
  const credential = token ?? workspace?.token ?? null;
  const draftData = (workspace?.draftData ?? EMPTY_DRAFT) as Record<string, unknown>;
  const editionId = workspace?.editionId;
  const changedFieldsByStep = workspace?.changedFields as Partial<Record<string, readonly string[]>> | undefined;
  const rawChangedFields = changedFieldsByStep?.[step] ?? EMPTY_CHANGED_FIELDS;
  const changedFields = useMemo(
    () => prefixedResearchChangedFields(step, rawChangedFields),
    [rawChangedFields, step],
  );
  const changedKey = changedFields.join("\u001f");
  const draftFingerprint = useMemo(() => stableDraftFingerprint(draftData), [draftData]);
  const endpoint = endpointFor(mode, itemId, workId, editionId);
  const [payload, setPayload] = useState<ResearchRunPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const requestRevision = useRef(0);
  const requestInFlightRevision = useRef<number | null>(null);
  const lastAutomaticRequest = useRef("");
  const hasAutomaticResearch = useRef(false);
  const messageHandler = useRef(onMessage ?? workspace?.onMessage);
  useEffect(() => { messageHandler.current = onMessage ?? workspace?.onMessage; }, [onMessage, workspace?.onMessage]);

  const suggestions = useMemo(() => researchRunSuggestions(payload), [payload]);
  const grouped = useMemo(() => groupResearchSuggestions(suggestions, field), [field, suggestions]);
  const publishSuggestions = useCallback((rows: WorkflowCandidate[]) => {
    window.dispatchEvent(new CustomEvent("workflow-research-suggestions", { detail: { step, suggestions: rows } }));
  }, [step]);

  const applyPayload = useCallback((result: ResearchRunPayload) => {
    setPayload(result);
    publishSuggestions(researchRunSuggestions(result));
  }, [publishSuggestions]);

  const pollRun = useCallback(async (initial: ResearchRunPayload, revision: number) => {
    let result = initial;
    if (!result.id) return result;
    const runId = result.id;
    let attempt = 0;
    let consecutiveFailures = 0;
    const maxAttempts = FAST_POLL_ATTEMPTS + SLOW_POLL_ATTEMPTS;
    while (!isTerminalResearchStatus(result.status) && attempt < maxAttempts) {
      const interval = attempt < FAST_POLL_ATTEMPTS
        ? FAST_POLL_INTERVAL_MS
        : SLOW_POLL_INTERVAL_MS;
      attempt += 1;
      await new Promise<void>((resolve) => window.setTimeout(resolve, interval));
      if (requestRevision.current !== revision || !credential) return result;
      try {
        result = await apiRequest<ResearchRunPayload>(runDetailEndpoint(runId), {}, credential);
      } catch (reason) {
        if (requestRevision.current !== revision) return result;
        consecutiveFailures += 1;
        const message = reason instanceof Error ? reason.message : "ResearchRun 状态读取暂时失败。";
        const unavailable = {
          ...result,
          error: { code: "research_poll_failed", message },
        };
        setPayload((current) => ({
          ...(current ?? result),
          error: unavailable.error,
        }));
        if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) return unavailable;
        continue;
      }
      consecutiveFailures = 0;
      if (requestRevision.current !== revision) return result;
      applyPayload(result);
    }
    if (!isTerminalResearchStatus(result.status) && requestRevision.current === revision) {
      result = {
        ...result,
        error: {
          code: "research_poll_budget_exhausted",
          message: "研究仍在后台队列或 Worker 中。已停止自动轮询，请稍后使用刷新状态，不要重复创建任务。",
        },
      };
      applyPayload(result);
    }
    return result;
  }, [applyPayload, credential]);

  const requestResearch = useCallback(async ({
    trigger,
    fields,
    force,
    manual,
  }: {
    trigger: "auto_load" | "field_change" | "manual";
    fields: string[];
    force: boolean;
    manual: boolean;
  }) => {
    if (!credential || (mode === "intake" ? !itemId : !workId)) return;
    if (requestInFlightRevision.current !== null) {
      if (manual) messageHandler.current?.("已有 ResearchRun 正在提交或读取，未创建重复任务。");
      return;
    }
    const revision = ++requestRevision.current;
    requestInFlightRevision.current = revision;
    if (manual) setRunning(true);
    else setLoading(true);
    try {
      const initial = await apiRequest<ResearchRunPayload>(endpoint, {
        method: "POST",
        body: JSON.stringify({
          edition_id: editionId,
          step,
          draft: draftData,
          changed_fields: fields,
          trigger,
          mode: "full",
          force,
          include_background: false,
        }),
      }, credential);
      if (requestRevision.current !== revision) return;
      applyPayload(initial);
      const finalPayload = await pollRun(initial, revision);
      if (requestRevision.current !== revision) return;
      if (manual) {
        messageHandler.current?.(
          isTerminalResearchStatus(finalPayload.status) && finalPayload.status !== "failed"
            ? "本节已按当前未保存草稿重新研究。候选仍需人工决定。"
            : "本节重新研究未完成，已有表单数据没有变化。",
        );
      }
    } catch (reason) {
      if (requestRevision.current !== revision) return;
      const message = reason instanceof Error ? reason.message : "自动研究暂时不可用。";
      setPayload((current) => ({
        ...(current ?? {}),
        status: current?.status ?? "failed",
        error: { code: "research_request_failed", message },
      }));
      if (manual) messageHandler.current?.(message);
    } finally {
      if (requestInFlightRevision.current === revision) {
        requestInFlightRevision.current = null;
      }
      if (requestRevision.current === revision) {
        setLoading(false);
        setRunning(false);
      }
    }
  }, [applyPayload, credential, draftData, editionId, endpoint, itemId, mode, pollRun, step, workId]);

  const loadLatest = useCallback(async () => {
    if (!credential || (mode === "intake" ? !itemId : !workId)) return;
    if (requestInFlightRevision.current !== null) return;
    const revision = ++requestRevision.current;
    requestInFlightRevision.current = revision;
    setLoading(true);
    try {
      const latestEndpoint = `${endpoint}${endpoint.includes("?") ? "&" : "?"}step=${encodeURIComponent(step)}`;
      const result = await apiRequest<ResearchRunPayload>(latestEndpoint, {}, credential);
      if (requestRevision.current !== revision) return;
      applyPayload(result);
      if (result.id && !isTerminalResearchStatus(result.status)) await pollRun(result, revision);
    } catch {
      if (requestRevision.current === revision) {
        setPayload((current) => current ?? { status: "not_started" });
      }
    } finally {
      if (requestInFlightRevision.current === revision) {
        requestInFlightRevision.current = null;
        setLoading(false);
        setRunning(false);
      }
    }
  }, [applyPayload, credential, endpoint, itemId, mode, pollRun, step, workId]);

  useEffect(() => {
    const reload = () => { void loadLatest(); };
    window.addEventListener(RESEARCH_SUGGESTION_REFRESH_EVENT, reload);
    return () => window.removeEventListener(RESEARCH_SUGGESTION_REFRESH_EVENT, reload);
  }, [loadLatest]);

  useEffect(() => {
    requestRevision.current += 1;
    requestInFlightRevision.current = null;
    lastAutomaticRequest.current = "";
    hasAutomaticResearch.current = false;
    const timer = window.setTimeout(() => {
      setPayload(null);
      setLoading(false);
      setRunning(false);
      publishSuggestions([]);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [endpoint, publishSuggestions, step]);

  useEffect(() => {
    if (!credential || (mode === "intake" ? !itemId : !workId)) return;
    if (loading || running || requestInFlightRevision.current !== null) return;
    if (!canRunResearch) {
      const readOnlyTimer = window.setTimeout(() => { void loadLatest(); }, 0);
      return () => window.clearTimeout(readOnlyTimer);
    }
    if (!changedFields.length && hasAutomaticResearch.current) return;
    const trigger = changedFields.length ? "field_change" as const : "auto_load" as const;
    const requestKey = `${endpoint}:${step}:${trigger}:${changedKey}:${draftFingerprint}`;
    const delay = trigger === "field_change" ? 800 : 0;
    const timer = window.setTimeout(() => {
      if (lastAutomaticRequest.current === requestKey) return;
      if (requestInFlightRevision.current !== null) return;
      lastAutomaticRequest.current = requestKey;
      hasAutomaticResearch.current = true;
      void requestResearch({ trigger, fields: changedFields, force: false, manual: false });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [canRunResearch, changedFields, changedKey, credential, draftFingerprint, endpoint, itemId, loadLatest, loading, mode, requestResearch, running, step, workId]);

  useEffect(() => () => {
    requestRevision.current += 1;
    requestInFlightRevision.current = null;
  }, []);

  const errors = diagnosticErrors(payload);
  const status = String(payload?.status ?? (loading ? "running" : "not_started"));
  const nonTerminalRun = Boolean(payload?.id && !isTerminalResearchStatus(status));
  const pollingStopped = nonTerminalRun && [
    "research_poll_budget_exhausted",
    "research_poll_failed",
  ].includes(String(payload?.error?.code ?? ""));
  const statusState: ActionState = loading || running
    ? "pending"
    : status === "failed" || Boolean(payload?.error?.message)
      ? "error"
      : isTerminalResearchStatus(status)
        ? "success"
        : "idle";
  const statusMessage = pollingStopped
    ? "自动读取已经停止。任务仍在后台时，请使用刷新状态继续读取，不要重复创建任务。"
    : status === "queued"
    ? "仍在研究队列中等待，页面会继续读取结果。"
    : status === "running"
      ? "研究 Worker 正在处理，页面会继续读取结果。"
      : loading || running
        ? running ? "正在重新研究……" : "正在按草稿研究……"
    : `${statusLabels[status] ?? status} · ${suggestions.length} 个候选`;
  return (
    <section className="workflow-research-suggestions" aria-label={`${step} 社科研究候选`} aria-busy={loading || running}>
      <header>
        <div>
          <small>自动研究</small>
          <h3>本节建议与证据</h3>
          <p>页面打开后会自动研究；修改字段后等待 800ms，只重查受影响字段。如需联网补充本节，可强制重跑。研究建议不会自动写入正式字段。</p>
        </div>
        <div className="workflow-research-header-actions">
          <ActionButton
            className="button secondary"
            state={loading && !running ? "pending" : "idle"}
            pendingLabel="正在刷新"
            disabled={loading || running || !credential}
            onClick={() => void loadLatest()}
          >
            刷新状态
          </ActionButton>
          <ActionButton
            className="button secondary"
            state={running ? "pending" : "idle"}
            pendingLabel="正在重跑"
            disabled={!canRunResearch || loading || running || nonTerminalRun || !credential}
            onClick={() => void requestResearch({ trigger: "manual", fields: [], force: true, manual: true })}
          >
            <FlaskConical size={14} />强制重跑本节
          </ActionButton>
        </div>
      </header>
      <AsyncStatus state={statusState} message={statusMessage} className="workflow-research-live" />
      <AsyncStatus state="error" message={payload?.error?.message ?? ""} className="workflow-research-error" assertive />
      {errors.map((error, index) => <AsyncStatus state="error" message={String(error.detail ?? error.message ?? "候选来源暂时不可用。")} className="workflow-research-error" key={`${String(error.code ?? "error")}-${index}`} />)}
      {grouped.length ? <div className="workflow-research-group-counts">{grouped.map(([tier, rows]) => <span key={tier}>{tierLabels[tier] ?? tier} {rows.length}</span>)}</div> : null}
      {Array.isArray(payload?.plan) && payload.plan.length ? <div className="workflow-research-run-status">{payload.plan.slice(0, 8).map((task, index) => <span key={`${String(task.step)}-${String(task.field)}-${index}`} data-status={isTerminalResearchStatus(status) ? "complete" : "running"}>{String(task.step)} · {String(task.field)}</span>)}</div> : null}
      {grouped.length ? <div className="workflow-research-groups">{grouped.map(([tier, rows]) => <section key={tier}><h4>{tierLabels[tier] ?? tier}</h4>{rows.slice(0, 5).map((candidate) => <button type="button" className="workflow-research-card" key={String(candidate.id)} onClick={() => onInspect?.([candidate], `${candidate.label ?? "候选"} · 来源检查`)}><span><strong>{String(candidate.label ?? candidate.field_name ?? "候选")}</strong><small>{String(candidate.source_class ?? candidate.source ?? "")} · {Math.round(Number(candidate.confidence ?? 0) * 100)}% · {Number(candidate.evidence_count ?? 0)} 条证据</small></span><span>{tier === "research_lead" ? <ExternalLink size={13} /> : <Search size={13} />}</span></button>)}</section>)}</div> : !loading ? <p className="workflow-research-empty">当前步骤尚无候选。可以继续编辑，或强制重跑本节。</p> : null}
    </section>
  );
}
