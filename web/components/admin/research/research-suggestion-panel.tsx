"use client";

import { ExternalLink, FlaskConical, Search } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ActionButton, AsyncStatus, ToastHost, type ActionState, type ToastItem } from "@/components/action-feedback";
import { apiRequest } from "@/lib/api";
import type { WorkflowCandidate } from "../workflow/workflow-types";
import { type CandidateActionDescriptor, resolveCandidateActionDescriptors } from "./candidate-action-contract";
import { CandidateDecisionBar } from "./candidate-decision-bar";
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
  is_current?: boolean;
  stale_reason?: string;
};

type FieldOutcome = {
  field: string;
  status: "candidates_available" | "no_reliable_candidate" | "producer_unavailable" | string;
  reason: string;
  producer_capability?: {
    state?: string;
    reason?: string;
    channels?: Record<string, { state?: string; reason?: string; sources?: string[] }>;
  } | null;
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
  stale: "草稿已变化，旧候选失效",
  superseded: "已由新草稿研究取代",
};

function isLeadOnly(candidate: WorkflowCandidate): boolean {
  return candidate.source_tier === "research_lead"
    || candidate.evidence_status === "lead_only"
    || (Number(candidate.evidence_count ?? 0) === 0 && ["general_web", "searching", "searxng"].includes(String(candidate.source_class ?? candidate.source ?? "").toLocaleLowerCase()));
}

function canVerifyLead(candidate: WorkflowCandidate): boolean {
  if (candidate.verify_url) return true;
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(String(candidate.id));
}

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

function fieldOutcomes(payload: ResearchRunPayload | null): FieldOutcome[] {
  const value = payload?.external_results?.field_outcomes;
  if (!Array.isArray(value)) return [];
  return value.filter((row): row is FieldOutcome => (
    Boolean(row)
    && typeof row === "object"
    && typeof (row as FieldOutcome).field === "string"
    && typeof (row as FieldOutcome).status === "string"
  ));
}

const producerChannelLabels: Record<string, string> = {
  pdf_native: "PDF 原生文本",
  ocr: "选择性 OCR",
  local_catalog: "本馆目录",
  authority: "Authority",
  structured_provider: "结构化来源",
  verified_web: "已核实网页",
  ai_synthesis: "馆藏综合",
};

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
  onUpdated,
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
  const draftSessionId = workspace?.draftSessionId;
  const endpoint = endpointFor(mode, itemId, workId, editionId);
  const [payload, setPayload] = useState<ResearchRunPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [candidateAction, setCandidateAction] = useState("");
  const [expandedTiers, setExpandedTiers] = useState<Set<string>>(() => new Set());
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [dismissedCandidateIds, setDismissedCandidateIds] = useState<Set<string>>(() => new Set());
  const requestRevision = useRef(0);
  const requestInFlightRevision = useRef<number | null>(null);
  const lastAutomaticRequest = useRef("");
  const hasAutomaticResearch = useRef(false);
  const lastDraftFingerprint = useRef("");
  const messageHandler = useRef(onMessage ?? workspace?.onMessage);
  useEffect(() => { messageHandler.current = onMessage ?? workspace?.onMessage; }, [onMessage, workspace?.onMessage]);

  const suggestions = useMemo(() => researchRunSuggestions(payload).filter((candidate) => !dismissedCandidateIds.has(String(candidate.id))), [dismissedCandidateIds, payload]);
  const grouped = useMemo(() => groupResearchSuggestions(suggestions, field), [field, suggestions]);
  const unresolvedOutcomes = useMemo(
    () => fieldOutcomes(payload).filter((row) => row.status !== "candidates_available").slice(0, 12),
    [payload],
  );
  const publishSuggestions = useCallback((rows: WorkflowCandidate[]) => {
    window.dispatchEvent(new CustomEvent("workflow-research-suggestions", { detail: { step, suggestions: rows } }));
  }, [step]);

  const applyPayload = useCallback((result: ResearchRunPayload) => {
    setPayload(result);
    publishSuggestions(result.is_current === false ? [] : researchRunSuggestions(result));
  }, [publishSuggestions]);

  const setToast = useCallback((id: string, state: ToastItem["state"], message: string) => {
    setToasts((current) => [...current.filter((item) => item.id !== id), { id, state, message }]);
  }, []);

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
    if (force) setDismissedCandidateIds(new Set());
    requestInFlightRevision.current = revision;
    if (manual) setRunning(true);
    else setLoading(true);
    try {
      const initial = await apiRequest<ResearchRunPayload>(endpoint, {
        method: "POST",
        body: JSON.stringify({
          edition_id: editionId,
          draft_session_id: draftSessionId,
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
  }, [applyPayload, credential, draftData, draftSessionId, editionId, endpoint, itemId, mode, pollRun, step, workId]);

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

  const runCandidateAction = useCallback(async (
    candidate: WorkflowCandidate,
    descriptor: CandidateActionDescriptor,
    editedValue?: unknown,
  ) => {
    const action = descriptor.action;
    if (!credential || candidateAction) return;
    const key = `${candidate.id}:${action}`;
    setCandidateAction(key);
    setToast(key, "pending", action === "verify" ? "正在取得并核实正文证据……" : action === "reject" ? "正在记录不采用决定……" : "正在采用候选……");
    try {
      if (action === "dismiss") {
        setDismissedCandidateIds((current) => new Set(current).add(String(candidate.id)));
        publishSuggestions(suggestions.filter((row) => String(row.id) !== String(candidate.id)));
        setToast(key, "success", "已在本次研究中标记不采用。正式内容没有变化。");
        return;
      }
      if (["apply_to_draft", "apply_draft", "use_value"].includes(action)) {
        const appliedCandidate = editedValue === undefined ? candidate : { ...candidate, proposed_value: editedValue };
        const applied = workspace?.onCandidateApply?.(appliedCandidate);
        if (!applied) throw new Error("该候选不能作为普通字段直接填入。");
        setToast(key, "success", "候选已填入未保存草稿。");
        return;
      }
      if (action === "verify") {
        const verifyUrl = descriptor.url || String(candidate.verify_url ?? `/catalog/admin/research/candidates/${encodeURIComponent(String(candidate.id))}/verify/`);
        const legacyPayload = candidate.verify_payload && typeof candidate.verify_payload === "object"
          ? candidate.verify_payload as Record<string, unknown>
          : {};
        const verifyPayload = { ...legacyPayload, ...descriptor.payload };
        const result = await apiRequest<Record<string, unknown>>(verifyUrl, { method: descriptor.method || "POST", body: JSON.stringify(verifyPayload) }, credential);
        const resultStatus = String(result.status ?? "verified");
        if (resultStatus !== "verified") {
          const detail = String(result.detail ?? "没有取得可核实的正文证据。该结果仍不可采用。");
          setToast(key, resultStatus === "failed" ? "error" : "success", detail);
        } else {
          setToast(key, "success", "已取得正文证据，候选现在可以进入人工采用。");
        }
        if (onUpdated) await onUpdated();
        else await workspace?.onUpdated?.();
        await loadLatest();
        return;
      }
      const decisionCandidate: WorkflowCandidate = {
        ...candidate,
        decision_descriptor: descriptor,
        ...(editedValue === undefined ? {} : {
          edited_value: editedValue,
          ...(candidate.kind === "derived_claim_curation" ? { edited_proposition: editedValue } : {}),
        }),
      };
      const decided = await workspace?.onCandidateDecision?.(decisionCandidate, action);
      if (decided === false) throw new Error("候选决定没有完成。");
      setToast(key, "success", action === "reject" ? "已记录不采用。" : action === "defer" ? "已标记稍后处理。" : "候选已采用并记录审计。");
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "候选操作失败。";
      setToast(key, "error", message);
      messageHandler.current?.(message);
    } finally {
      setCandidateAction("");
    }
  }, [candidateAction, credential, loadLatest, onUpdated, publishSuggestions, setToast, suggestions, workspace]);

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
      setDismissedCandidateIds(new Set());
      publishSuggestions([]);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [endpoint, publishSuggestions, step]);

  useEffect(() => {
    const previous = lastDraftFingerprint.current;
    lastDraftFingerprint.current = draftFingerprint;
    if (!previous || previous === draftFingerprint || !changedFields.length) return;
    requestRevision.current += 1;
    requestInFlightRevision.current = null;
    lastAutomaticRequest.current = "";
    setPayload({ status: "stale", stale_reason: "当前未保存草稿已经变化。" });
    setLoading(false);
    setRunning(false);
    publishSuggestions([]);
  }, [changedFields.length, draftFingerprint, publishSuggestions]);

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
      : status === "stale" || status === "superseded"
        ? "idle"
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
      {unresolvedOutcomes.length ? (
        <section className="workflow-field-outcomes" aria-label="字段候选生产状态">
          <header><h4>字段生产能力</h4><span>{unresolvedOutcomes.length} 个字段暂无可靠候选</span></header>
          {unresolvedOutcomes.map((outcome) => {
            const channels = Object.entries(outcome.producer_capability?.channels ?? {})
              .filter(([, value]) => value.state !== "unavailable");
            return (
              <article key={outcome.field} data-status={outcome.status}>
                <strong>{outcome.field}</strong>
                <p>没有可靠候选。{outcome.reason || outcome.producer_capability?.reason || "当前来源没有达到该字段的证据要求。"}</p>
                {channels.length ? <div>{channels.map(([key, value]) => <span data-state={value.state} title={value.reason || "已连接字段 producer"} key={key}>{producerChannelLabels[key] ?? key} · {value.state === "productive" ? "可生产" : "降级"}</span>)}</div> : null}
              </article>
            );
          })}
        </section>
      ) : null}
      {grouped.length ? (
        <div className="workflow-research-groups">
          {grouped.map(([tier, rows]) => {
            const expanded = expandedTiers.has(tier);
            const visibleRows = expanded ? rows : rows.slice(0, 5);
            return (
              <section key={tier}>
                <header><h4>{tierLabels[tier] ?? tier}</h4><span>{rows.length} 项</span></header>
                <div className="workflow-research-result-area" data-expanded={expanded}>
                  {visibleRows.map((candidate) => {
                    const leadOnly = isLeadOnly(candidate);
                    const inspect = () => onInspect?.([candidate], `${candidate.label ?? "候选"} · 来源检查`);
                    const resolved = resolveCandidateActionDescriptors(candidate);
                    const hasExplicitDescriptors = resolved.some((descriptor) => descriptor.source === "descriptor");
                    const hasAdoption = resolved.some((descriptor) => ["accept", "accept_with_edit", "link_existing", "use_value", "create_draft", "keep_unresolved", "apply_to_draft", "apply_draft"].includes(descriptor.action));
                    const decisionCandidate = !leadOnly && !hasExplicitDescriptors && !hasAdoption && (candidate.proposed_value !== undefined || candidate.value !== undefined)
                      ? { ...candidate, available_actions: [...(candidate.available_actions ?? []), "apply_to_draft"] }
                      : candidate;
                    return (
                      <article className="workflow-research-candidate" key={String(candidate.id)}>
                        <button type="button" className="workflow-research-card" onClick={inspect}>
                          <span><strong>{String(candidate.label ?? candidate.field_name ?? "候选")}</strong><small>{String(candidate.source_class ?? candidate.source ?? "")} · {Math.round(Number(candidate.confidence ?? 0) * 100)}% · {Number(candidate.evidence_count ?? 0)} 条证据</small></span>
                          <span>{leadOnly ? <ExternalLink size={13} /> : <Search size={13} />}</span>
                        </button>
                        <CandidateDecisionBar
                          candidate={decisionCandidate}
                          className="workflow-research-card-actions"
                          busyAction={candidateAction.startsWith(`${candidate.id}:`) ? candidateAction.slice(String(candidate.id).length + 1) : ""}
                          disabled={Boolean(candidateAction)}
                          onInspect={inspect}
                          actionFilter={(descriptor) => leadOnly
                            ? descriptor.action === "inspect"
                              || descriptor.action === "reject"
                              || (descriptor.action === "verify" && canVerifyLead(candidate))
                            : descriptor.action !== "verify" || canVerifyLead(candidate)}
                          onAction={(descriptor, editedValue) => void runCandidateAction(
                            candidate,
                            descriptor.action === "reject" && !descriptor.url && !candidate.decision_url
                              ? { ...descriptor, action: "dismiss" }
                              : descriptor,
                            editedValue,
                          )}
                        />
                        {candidate.no_reliable_candidate_reason ? <p className="workflow-no-reliable-candidate">没有可靠候选。{String(candidate.no_reliable_candidate_reason)}</p> : null}
                      </article>
                    );
                  })}
                </div>
                {rows.length > 5 ? <button className="workflow-research-expand" type="button" onClick={() => setExpandedTiers((current) => { const next = new Set(current); if (next.has(tier)) next.delete(tier); else next.add(tier); return next; })}>{expanded ? "收起" : `展开全部 ${rows.length} 项`}</button> : null}
              </section>
            );
          })}
        </div>
      ) : !loading && !unresolvedOutcomes.length ? <p className="workflow-research-empty">当前步骤尚无候选。可以继续编辑，或强制重跑本节。</p> : null}
      <ToastHost items={toasts} onDismiss={(id) => setToasts((current) => current.filter((item) => item.id !== id))} label="候选操作反馈" />
    </section>
  );
}
