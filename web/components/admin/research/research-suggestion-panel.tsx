"use client";

import { Check, ExternalLink, FlaskConical, Pencil, Search, ShieldCheck, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ActionButton, AsyncStatus, ToastHost, type ActionState, type ToastItem } from "@/components/action-feedback";
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
  is_current?: boolean;
  stale_reason?: string;
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

function adoptionAction(candidate: WorkflowCandidate): string {
  const actions = candidate.available_actions ?? [];
  return ["accept", "link_existing", "use_value", "create_draft", "keep_unresolved"].find((action) => actions.includes(action)) ?? "";
}

function adoptionLabel(action: string, candidate: WorkflowCandidate): string {
  if (action === "apply_draft") return "采用到草稿";
  if (action === "link_existing") return candidate.entity_type === "person" ? "关联已有学者" : "关联馆内实体";
  if (action === "create_draft") return candidate.entity_type === "person" ? "创建新学者主页" : "采用为实体草稿";
  if (action === "keep_unresolved") return "仅添加为责任者";
  if (action === "use_value") return "采用规范文本";
  return "采用";
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

  const runCandidateAction = useCallback(async (candidate: WorkflowCandidate, action: string) => {
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
      if (action === "apply_draft") {
        const applied = workspace?.onCandidateApply?.(candidate);
        if (!applied) throw new Error("该候选不能作为普通字段直接填入。");
        setToast(key, "success", "候选已填入未保存草稿。");
        return;
      }
      if (action === "verify") {
        const verifyUrl = String(candidate.verify_url ?? `/catalog/admin/research/candidates/${encodeURIComponent(String(candidate.id))}/verify/`);
        const verifyPayload = candidate.verify_payload && typeof candidate.verify_payload === "object"
          ? candidate.verify_payload
          : {};
        const result = await apiRequest<Record<string, unknown>>(verifyUrl, { method: "POST", body: JSON.stringify(verifyPayload) }, credential);
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
      const decided = await workspace?.onCandidateDecision?.(candidate, action);
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
                    const actions = candidate.available_actions ?? [];
                    const directAction = adoptionAction(candidate);
                    const adopt = directAction || (candidate.proposed_value !== undefined || candidate.value !== undefined ? "apply_draft" : "");
                    const leadOnly = isLeadOnly(candidate);
                    const inspect = () => onInspect?.([candidate], `${candidate.label ?? "候选"} · 来源检查`);
                    return (
                      <article className="workflow-research-candidate" key={String(candidate.id)}>
                        <button type="button" className="workflow-research-card" onClick={inspect}>
                          <span><strong>{String(candidate.label ?? candidate.field_name ?? "候选")}</strong><small>{String(candidate.source_class ?? candidate.source ?? "")} · {Math.round(Number(candidate.confidence ?? 0) * 100)}% · {Number(candidate.evidence_count ?? 0)} 条证据</small></span>
                          <span>{leadOnly ? <ExternalLink size={13} /> : <Search size={13} />}</span>
                        </button>
                        <div className="workflow-research-card-actions">
                          {leadOnly && canVerifyLead(candidate) ? <ActionButton state={candidateAction === `${candidate.id}:verify` ? "pending" : "idle"} pendingLabel="核实中" disabled={Boolean(candidateAction)} onClick={() => void runCandidateAction(candidate, "verify")}><ShieldCheck size={12} />核实此结果</ActionButton> : null}
                          {!leadOnly && adopt && (candidate.decision_url || adopt === "apply_draft") ? <ActionButton state={candidateAction === `${candidate.id}:${adopt}` ? "pending" : "idle"} pendingLabel="采用中" disabled={Boolean(candidateAction)} onClick={() => void runCandidateAction(candidate, adopt)}><Check size={12} />{adoptionLabel(adopt, candidate)}</ActionButton> : null}
                          {!leadOnly && actions.includes("accept_with_edit") ? <ActionButton disabled={Boolean(candidateAction)} onClick={inspect}><Pencil size={12} />修改后采用</ActionButton> : null}
                          <ActionButton disabled={Boolean(candidateAction)} onClick={inspect}><Search size={12} />查看依据</ActionButton>
                          {actions.includes("reject") ? <ActionButton className="danger" state={candidateAction === `${candidate.id}:${candidate.decision_url ? "reject" : "dismiss"}` ? "pending" : "idle"} pendingLabel="记录中" disabled={Boolean(candidateAction)} onClick={() => void runCandidateAction(candidate, candidate.decision_url ? "reject" : "dismiss")}><X size={12} />拒绝/不采用</ActionButton> : null}
                        </div>
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
      ) : !loading ? <p className="workflow-research-empty">当前步骤尚无候选。可以继续编辑，或强制重跑本节。</p> : null}
      <ToastHost items={toasts} onDismiss={(id) => setToasts((current) => current.filter((item) => item.id !== id))} label="候选操作反馈" />
    </section>
  );
}
