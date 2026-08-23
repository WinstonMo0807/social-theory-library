"use client";

import { Check, ExternalLink, LoaderCircle, Plus, Search, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { type EntityValue } from "../forms/workflow-fields";
import type { WorkflowCandidate } from "../workflow/workflow-types";
import { prefixedResearchChangedFields, RESEARCH_SUGGESTION_REFRESH_EVENT } from "./research-suggestion-state";
import { useResearchWorkspace } from "./research-workspace-context";

type DiscoveryGroup = "local" | "local_draft" | "authority" | "external_web" | "unresolved";

type DiscoveryCandidate = WorkflowCandidate & {
  candidate_group: DiscoveryGroup;
  entity_type?: string;
  entity_id?: string | null;
  primary_name?: string;
  secondary_identity?: string;
  entity_status?: string;
  available_actions?: string[];
  source_url?: string;
};

type DiscoveryPayload = {
  status?: string;
  results?: DiscoveryCandidate[];
  groups?: Array<{ key: DiscoveryGroup; label: string; count: number }>;
  warnings?: Array<{ code?: string; detail?: string }>;
};

type DiscoveryState = "idle" | "healthy" | "degraded" | "failed";

const ENTITY_DISCOVERY_ENDPOINT = "/catalog/admin/research/entity-discovery/";
const ENTITY_DECISION_ENDPOINT = "/catalog/admin/research/entity-decisions/";
const DISCOVERY_DEBOUNCE_MS = 400;
const EMPTY_CHANGED_FIELDS: readonly string[] = [];
export const UNIVERSAL_ENTITY_TYPES = [
  "person",
  "work",
  "theory",
  "topic",
  "knowledge_node",
  "discipline",
  "subdiscipline",
  "organization",
  "institution",
  "publisher",
  "journal",
  "reading_path",
] as const;
const GROUP_ORDER: DiscoveryGroup[] = ["local", "local_draft", "authority", "external_web", "unresolved"];
const GROUP_LABELS: Record<DiscoveryGroup, string> = {
  local: "馆内已有",
  local_draft: "馆内草稿 / 待审核",
  authority: "权威来源候选",
  external_web: "一般网络候选",
  unresolved: "保留未解析",
};
const ACTION_LABELS: Record<string, string> = {
  inspect: "核对来源",
  link_existing: "关联馆内实体",
  use_value: "使用规范文本",
  create_draft: "创建实体草稿",
  keep_unresolved: "保留未解析",
  reject: "不采用",
  accept: "接受候选",
  reopen: "恢复待审",
};
const DIRECT_ENTITY_DECISION_ACTIONS = new Set(["create_draft", "keep_unresolved", "reject"]);
const DIRECT_ENTITY_DECISION_TYPES = new Set(["person", "work", "knowledge_node", "organization", "publisher"]);

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function normalizedEntityType(value: unknown): string {
  const entityType = String(value ?? "").trim().toLocaleLowerCase().replace(/_draft$/, "");
  if (entityType === "institution") return "organization";
  if (entityType === "theory_school") return "theory";
  return entityType;
}

function candidateGroup(candidate: WorkflowCandidate): DiscoveryGroup {
  const explicit = String(candidate.candidate_group ?? "");
  if (GROUP_ORDER.includes(explicit as DiscoveryGroup)) return explicit as DiscoveryGroup;
  const tier = String(candidate.source_tier ?? "");
  if (tier === "structured_source") return "authority";
  if (tier === "web_evidence" || tier === "research_lead") return "external_web";
  return String(candidate.entity_status ?? candidate.status) === "draft" ? "local_draft" : "local";
}

function stringRows(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((row) => String(row ?? "").trim()).filter(Boolean)
    : [];
}

function normalizeCandidate(candidate: WorkflowCandidate, index: number): DiscoveryCandidate | null {
  const proposed = asRecord(candidate.proposed_value);
  const label = String(candidate.label ?? candidate.primary_name ?? proposed.name ?? candidate.value ?? "").trim();
  if (!label) return null;
  const group = candidateGroup(candidate);
  const entityId = candidate.entity_id ?? candidate.candidate_entity_id ?? proposed.id ?? null;
  const entityType = normalizedEntityType(candidate.entity_type ?? candidate.target_type ?? candidate.candidate_entity_type);
  const actions = Array.isArray(candidate.available_actions)
    ? candidate.available_actions.map(String)
    : group === "local" || group === "local_draft"
      ? ["inspect", entityId ? "link_existing" : "use_value"]
      : ["inspect", "keep_unresolved", "reject"];
  return {
    ...candidate,
    id: String(candidate.id ?? `entity-suggestion-${index}`),
    label,
    primary_name: label,
    entity_id: entityId ? String(entityId) : null,
    entity_type: entityType || undefined,
    candidate_group: group,
    available_actions: actions,
  } as DiscoveryCandidate;
}

function candidateValue(candidate: DiscoveryCandidate, status = "selected"): EntityValue {
  return {
    id: candidate.entity_id ? String(candidate.entity_id) : null,
    name: String(candidate.primary_name ?? candidate.label ?? ""),
    status,
    candidate_id: candidate.id,
    candidate_group: candidate.candidate_group,
    entity_type: candidate.entity_type,
    source: candidate.source,
  };
}

function candidateIdentity(candidate: DiscoveryCandidate): string {
  if (candidate.entity_id) return `${candidate.entity_type ?? "entity"}:${candidate.entity_id}`;
  if (candidate.candidate_group === "authority" || candidate.candidate_group === "external_web") {
    const externalIds = Object.entries(asRecord(candidate.external_ids))
      .filter(([, value]) => String(value ?? "").trim())
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, value]) => `${key}:${String(value)}`)
      .join("|");
    const metadata = asRecord(candidate.metadata);
    const sourceIdentity = externalIds
      || String(candidate.source_record_id ?? "").trim()
      || String(candidate.source_url ?? metadata.url ?? "").trim()
      || candidate.id;
    return `${candidate.candidate_group}:${String(candidate.provider ?? candidate.source ?? "")}:${sourceIdentity}:${String(candidate.primary_name ?? candidate.label ?? "").trim().toLocaleLowerCase()}`;
  }
  return `${candidate.candidate_group}:${String(candidate.primary_name ?? candidate.label ?? "").trim().toLocaleLowerCase()}`;
}

function mergeCandidates(primary: DiscoveryCandidate[], fallback: DiscoveryCandidate[]): DiscoveryCandidate[] {
  const seen = new Set<string>();
  return [...primary, ...fallback].filter((candidate) => {
    const identity = candidateIdentity(candidate);
    if (seen.has(identity)) return false;
    seen.add(identity);
    return true;
  });
}

function stableDraftFingerprint(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return "draft-not-serializable";
  }
}

export function ResearchEntityPicker({
  label,
  endpoint,
  values,
  onChange,
  suggestions = [],
  onInspect,
  placeholder,
  entityType,
  field = "entity",
  step = "contributors",
  queryHint = "",
  disabled = false,
  textValue = "",
  onUseValue,
  multiple = false,
}: {
  label: string;
  endpoint: string;
  values: EntityValue[];
  onChange: (values: EntityValue[]) => void;
  suggestions?: WorkflowCandidate[];
  onInspect?: (candidate: WorkflowCandidate) => void;
  idField?: string;
  nameField?: string;
  queryParam?: string;
  placeholder?: string;
  allowUnresolved?: boolean;
  entityType?: string;
  field?: string;
  step?: string;
  queryHint?: string;
  disabled?: boolean;
  textValue?: string;
  onUseValue?: (value: string, candidate: WorkflowCandidate) => void;
  multiple?: boolean;
}) {
  const workspace = useResearchWorkspace();
  const inputId = useId();
  const listboxId = useId();
  const liveId = useId();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [remoteCandidates, setRemoteCandidates] = useState<DiscoveryCandidate[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [discoveryState, setDiscoveryState] = useState<DiscoveryState>("idle");
  const [discoveryNotice, setDiscoveryNotice] = useState("");
  const [hiddenCandidates, setHiddenCandidates] = useState<Set<string>>(() => new Set());
  const [announcement, setAnnouncement] = useState("");
  const [inspectedCandidate, setInspectedCandidate] = useState<DiscoveryCandidate | null>(null);
  const requestRevision = useRef(0);
  const decisionInFlight = useRef("");
  const localCandidatesByQuery = useRef(new Map<string, DiscoveryCandidate[]>());

  const inferredEntityType = entityType ?? (
    endpoint.includes("subdisciplines") ? "subdiscipline"
      : endpoint.includes("disciplines") ? "discipline"
        : endpoint.includes("topics") ? "topic"
          : endpoint.includes("theory-system/nodes") ? "knowledge_node"
            : endpoint.includes("theory-schools") ? "theory"
              : endpoint.includes("scholars") ? "person"
                : "work"
  );
  const normalizedRequestedEntityType = normalizedEntityType(inferredEntityType);
  const resolvedEntityType = UNIVERSAL_ENTITY_TYPES.includes(normalizedRequestedEntityType as typeof UNIVERSAL_ENTITY_TYPES[number])
    ? normalizedRequestedEntityType
    : "work";
  const seedCandidates = useMemo(() => suggestions.flatMap((candidate, index) => {
    const normalized = normalizeCandidate(candidate, index);
    if (!normalized) return [];
    const candidateType = normalizedEntityType(normalized.entity_type);
    return !candidateType || candidateType === resolvedEntityType ? [normalized] : [];
  }), [resolvedEntityType, suggestions]);
  const visibleCandidates = useMemo(
    () => {
      const candidates = hasSearched
        ? discoveryState === "degraded" || discoveryState === "failed"
          ? mergeCandidates(remoteCandidates, seedCandidates)
          : remoteCandidates
        : seedCandidates;
      return candidates.filter((candidate) => !hiddenCandidates.has(candidate.id));
    },
    [discoveryState, hasSearched, hiddenCandidates, remoteCandidates, seedCandidates],
  );
  const grouped = useMemo(() => GROUP_ORDER.flatMap((group) => {
    const rows = visibleCandidates.filter((candidate) => candidate.candidate_group === group);
    return rows.length ? [{ group, rows }] : [];
  }), [visibleCandidates]);
  const orderedCandidates = useMemo(() => grouped.flatMap(({ rows }) => rows), [grouped]);
  const candidateIndexes = useMemo(
    () => new Map(orderedCandidates.map((candidate, index) => [candidate.id, index])),
    [orderedCandidates],
  );
  const changedFieldsByStep = workspace?.changedFields as Partial<Record<string, readonly string[]>> | undefined;
  const stepChangedFields = changedFieldsByStep?.[step] ?? EMPTY_CHANGED_FIELDS;
  const changedFields = useMemo(
    () => prefixedResearchChangedFields(step, stepChangedFields),
    [step, stepChangedFields],
  );
  const changedKey = changedFields.join("\u001f");
  const draftFingerprint = useMemo(() => stableDraftFingerprint(workspace?.draftData), [workspace?.draftData]);
  const authToken = workspace?.token ?? getServerSessionCredential();
  const canDiscover = Boolean(
    authToken
    && (workspace ? workspace.canRun : true),
  );

  useEffect(() => {
    const revision = ++requestRevision.current;
    if (!open || !canDiscover || query.trim().length < 2 || !authToken) return;
    const timer = window.setTimeout(() => {
      setLoading(true);
      void apiRequest<DiscoveryPayload>(ENTITY_DISCOVERY_ENDPOINT, {
        method: "POST",
        body: JSON.stringify({
          item_id: workspace?.itemId,
          work_id: workspace?.workId,
          edition_id: workspace?.editionId,
          entity_type: resolvedEntityType,
          field,
          query: query.trim(),
          step,
          draft: workspace?.draftData,
          changed_fields: changedFields,
          include_external: true,
          include_web: true,
          limit: 12,
        }),
      }, authToken)
        .then((result) => {
          if (requestRevision.current !== revision) return;
          const candidates = (result.results ?? []).flatMap((candidate, index) => {
            const normalized = normalizeCandidate(candidate, index);
            return normalized ? [normalized] : [];
          });
          const queryKey = `${step}:${field}:${resolvedEntityType}:${query.trim().toLocaleLowerCase()}`;
          localCandidatesByQuery.current.set(
            queryKey,
            candidates.filter((candidate) => candidate.candidate_group === "local" || candidate.candidate_group === "local_draft"),
          );
          if (localCandidatesByQuery.current.size > 8) {
            const oldest = localCandidatesByQuery.current.keys().next().value;
            if (oldest) localCandidatesByQuery.current.delete(oldest);
          }
          setRemoteCandidates(candidates);
          setHasSearched(true);
          const nextState: DiscoveryState = result.status === "failed"
            ? "failed"
            : result.status === "degraded" || Boolean(result.warnings?.length)
              ? "degraded"
              : "healthy";
          setDiscoveryState(nextState);
          setDiscoveryNotice(nextState === "degraded"
            ? "部分外部来源暂时不可用，馆内候选仍可选择。"
            : nextState === "failed"
              ? "外部实体发现暂时不可用，馆内候选仍保留在列表中。"
              : "");
          setActiveIndex(0);
          setAnnouncement(result.warnings?.length
            ? `${candidates.length} 个候选，部分外部来源暂时不可用`
            : `${candidates.length} 个候选`);
        })
        .catch((reason) => {
          if (requestRevision.current !== revision) return;
          const queryKey = `${step}:${field}:${resolvedEntityType}:${query.trim().toLocaleLowerCase()}`;
          setRemoteCandidates(localCandidatesByQuery.current.get(queryKey) ?? []);
          setHasSearched(true);
          setDiscoveryState("failed");
          const detail = reason instanceof Error ? reason.message : "实体发现暂时不可用";
          setDiscoveryNotice("外部实体发现暂时不可用，馆内候选仍保留在列表中。");
          setAnnouncement(`${detail}。馆内候选仍可使用。`);
        })
        .finally(() => {
          if (requestRevision.current === revision) setLoading(false);
        });
    }, DISCOVERY_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      if (requestRevision.current === revision) requestRevision.current += 1;
    };
  }, [authToken, canDiscover, changedFields, changedKey, draftFingerprint, field, open, query, resolvedEntityType, step, workspace]);

  useEffect(() => () => { requestRevision.current += 1; }, []);

  const closePicker = () => {
    requestRevision.current += 1;
    setLoading(false);
    setOpen(false);
    setInspectedCandidate(null);
  };

  const inspectCandidate = (candidate: DiscoveryCandidate) => {
    if (onInspect) onInspect(candidate);
    else setInspectedCandidate(candidate);
    setAnnouncement(`正在核对${String(candidate.primary_name ?? candidate.label ?? "候选")}的来源与冲突。`);
  };

  const selectExisting = (candidate: DiscoveryCandidate) => {
    if (disabled) return;
    const name = String(candidate.primary_name ?? candidate.label ?? "").trim();
    if (onUseValue) {
      onUseValue(name, candidate);
      setAnnouncement(`已把${name}填入未保存表单，尚未写入馆藏。`);
      closePicker();
      return;
    }
    if (!candidate.entity_id) {
      inspectCandidate(candidate);
      return;
    }
    const next = candidateValue(candidate, candidate.candidate_group === "local_draft" ? "draft" : "selected");
    if (!values.some((value) => value.id === next.id)) onChange(multiple ? [...values, next] : [next]);
    setAnnouncement(`已把${next.name}加入未保存表单，尚未写入馆藏。`);
    closePicker();
  };

  const hideCandidate = (candidate: DiscoveryCandidate) => {
    setHiddenCandidates((current) => new Set(current).add(candidate.id));
  };

  const decideExternal = async (candidate: DiscoveryCandidate, action: string) => {
    if (disabled) return;
    if (action === "inspect") {
      inspectCandidate(candidate);
      return;
    }
    if (action === "use_value") {
      if (onUseValue) selectExisting(candidate);
      return;
    }
    if (candidate.decision_url && workspace?.onCandidateDecision) {
      const actionKey = `${candidate.id}:${action}`;
      if (decisionInFlight.current) return;
      decisionInFlight.current = actionKey;
      setActing(actionKey);
      try {
        const succeeded = await workspace.onCandidateDecision(candidate, action);
        if (!succeeded) {
          setAnnouncement("候选决定未写入，候选仍保留。请查看页面提示后重试。");
          return;
        }
        hideCandidate(candidate);
      } finally {
        if (decisionInFlight.current === actionKey) {
          decisionInFlight.current = "";
          setActing("");
        }
      }
      return;
    }
    if (action === "link_existing") {
      selectExisting(candidate);
      return;
    }
    if (!workspace?.itemId) {
      if (action === "reject") hideCandidate(candidate);
      const message = "馆藏维护模式不会直接创建外部实体。请先到权威数据维护页建立或核对实体，再返回关联。";
      setAnnouncement(message);
      workspace?.onMessage?.(message);
      return;
    }
    const actionKey = `${candidate.id}:${action}`;
    if (decisionInFlight.current) return;
    decisionInFlight.current = actionKey;
    setActing(actionKey);
    try {
      await apiRequest(ENTITY_DECISION_ENDPOINT, {
        method: "POST",
        body: JSON.stringify({
          item_id: workspace.itemId,
          work_id: workspace.workId,
          edition_id: workspace.editionId,
          entity_type: candidate.entity_type ?? resolvedEntityType,
          field,
          query: query.trim() || queryHint.trim() || String(candidate.label ?? ""),
          candidate_id: candidate.id,
          action,
          step,
          draft: workspace.draftData,
          changed_fields: changedFields,
          reason: "管理员在 Universal Entity Picker 中明确决定",
        }),
      }, workspace.token);
      hideCandidate(candidate);
      await workspace.onUpdated?.();
      window.dispatchEvent(new Event(RESEARCH_SUGGESTION_REFRESH_EVENT));
      const message = action === "create_draft"
        ? "实体草稿已创建，但尚未自动关联。刷新候选后请明确选择馆内草稿。"
        : action === "keep_unresolved"
          ? "已保留为未解析决定，正式关系没有改变。"
          : "已记录不采用决定，正式关系没有改变。";
      setAnnouncement(message);
      workspace?.onMessage?.(message);
    } catch (reason) {
      const base = reason instanceof Error ? reason.message : "实体决定失败。";
      const message = `${base} 如需建立实体，请到权威数据维护页继续处理。`;
      setAnnouncement(message);
      workspace?.onMessage?.(message);
    } finally {
      if (decisionInFlight.current === actionKey) {
        decisionInFlight.current = "";
        setActing("");
      }
    }
  };

  const primaryAction = (candidate: DiscoveryCandidate) => {
    if (disabled) return;
    const actions = candidate.available_actions ?? [];
    const canUseLocalValue = Boolean(onUseValue && actions.some((action) => action === "use_value" || action === "link_existing"));
    if ((candidate.candidate_group === "local" || candidate.candidate_group === "local_draft") && !candidate.decision_url && (candidate.entity_id || canUseLocalValue)) {
      selectExisting(candidate);
    } else {
      inspectCandidate(candidate);
    }
  };

  const onComboboxKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      closePicker();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => Math.min(current + 1, Math.max(orderedCandidates.length - 1, 0)));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => Math.max(current - 1, 0));
      return;
    }
    if (event.key === "Enter" && open && orderedCandidates.length) {
      event.preventDefault();
      primaryAction(orderedCandidates[Math.min(activeIndex, orderedCandidates.length - 1)]);
      return;
    }
    if (event.key === "Tab") return;
  };

  const openPicker = () => {
    if (!query && queryHint.trim()) setQuery(queryHint.trim());
    setOpen(true);
  };
  return (
    <div className="workflow-research-entity-picker" onKeyDown={(event) => { if (event.key === "Escape") closePicker(); }}>
      <label htmlFor={inputId}>{label}</label>
      <div className="workflow-entity-values">{values.map((value, index) => <button type="button" disabled={disabled || Boolean(acting)} aria-label={`移除${value.name}`} key={`${value.id ?? value.name}-${index}`} onClick={() => onChange(values.filter((_row, rowIndex) => rowIndex !== index))}>{value.name}{value.id ? "" : " · 未解析"} ×</button>)}</div>
      <div className="workflow-universal-entity-combobox">
        <Search size={14} aria-hidden="true" />
        <input
          id={inputId}
          value={query}
          disabled={disabled || Boolean(acting)}
          placeholder={placeholder ?? "搜索馆内实体、权威来源和外部线索"}
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listboxId}
          aria-describedby={liveId}
          aria-activedescendant={open && orderedCandidates.length ? `${listboxId}-option-${activeIndex}` : undefined}
          onFocus={openPicker}
          onKeyDown={onComboboxKeyDown}
          onChange={(event) => { requestRevision.current += 1; setLoading(false); setQuery(event.target.value); setHasSearched(false); setDiscoveryState("idle"); setDiscoveryNotice(""); setInspectedCandidate(null); setActiveIndex(0); setOpen(true); }}
        />
        {loading ? <LoaderCircle className="spin" size={14} aria-hidden="true" /> : <span>{visibleCandidates.length}</span>}
      </div>
      <span className="sr-only" id={liveId} role="status" aria-live="polite" aria-atomic="true">{loading ? "正在搜索实体" : announcement || `${visibleCandidates.length} 个候选`}</span>
      {open ? <div className="workflow-universal-entity-popover" id={listboxId} role="listbox" aria-label={`${label}候选`}>
        <header><strong>{query.trim() ? `“${query.trim()}”的候选` : "研究候选"}</strong><button type="button" aria-label="关闭候选" onClick={closePicker}><X size={14} /></button></header>
        {discoveryNotice ? <p className="workflow-universal-entity-degraded" role="status">{discoveryNotice}</p> : null}
        {grouped.map(({ group, rows }) => <section className={`workflow-universal-entity-group group-${group}`} key={group} aria-label={GROUP_LABELS[group]}><h4>{GROUP_LABELS[group]} <span>{rows.length}</span></h4>{rows.map((candidate) => {
          const index = candidateIndexes.get(candidate.id) ?? 0;
          const selected = onUseValue
            ? Boolean(textValue.trim() && textValue.trim().toLocaleLowerCase() === String(candidate.primary_name ?? candidate.label ?? "").trim().toLocaleLowerCase())
            : Boolean(candidate.entity_id && values.some((value) => value.id === String(candidate.entity_id)));
          const candidateEntityType = normalizedEntityType(candidate.entity_type ?? resolvedEntityType);
          const actions = (candidate.available_actions ?? []).filter((action, actionIndex, all) => {
            if (all.indexOf(action) !== actionIndex) return false;
            if (action === "inspect") return true;
            if (action === "use_value") return Boolean(onUseValue);
            if (action === "link_existing") {
              if (candidate.decision_url) return Boolean(workspace?.onCandidateDecision);
              return Boolean(candidate.entity_id || onUseValue);
            }
            if (candidate.decision_url) return Boolean(workspace?.onCandidateDecision);
            return Boolean(
              workspace?.itemId
              && DIRECT_ENTITY_DECISION_ACTIONS.has(action)
              && DIRECT_ENTITY_DECISION_TYPES.has(candidateEntityType),
            );
          });
          const reasons = stringRows(candidate.match_reasons ?? candidate.reasons);
          const conflicts = stringRows(candidate.conflicts);
          const entityStatus = String(candidate.entity_status ?? candidate.status ?? "待核对");
          const source = String(candidate.source ?? candidate.provider ?? candidate.source_class ?? "来源待核对");
          return <article id={`${listboxId}-option-${index}`} role="option" aria-selected={selected} className={index === activeIndex ? "is-active" : ""} key={candidate.id} onMouseEnter={() => setActiveIndex(index)}>
            <button className="workflow-universal-entity-summary" type="button" tabIndex={-1} disabled={disabled || Boolean(acting)} onClick={() => primaryAction(candidate)}>
              <span><strong>{String(candidate.primary_name ?? candidate.label ?? "候选")}</strong><small>{String(candidate.secondary_identity ?? "")}</small><span className="workflow-universal-entity-meta"><em>{entityStatus}</em><em>{source}</em>{reasons[0] ? <em>{reasons[0]}</em> : null}{conflicts.length ? <em className="has-conflict">冲突 {conflicts.length}</em> : null}</span></span>
              <span>{Math.round(Number(candidate.confidence ?? 0) * 100)}%</span>
            </button>
            {inspectedCandidate?.id === candidate.id ? <div className="workflow-universal-entity-inline-inspector" role="region" aria-label={`${String(candidate.primary_name ?? candidate.label ?? "候选")}详情`}><dl><div><dt>实体状态</dt><dd>{entityStatus}</dd></div><div><dt>来源</dt><dd>{source}</dd></div></dl>{reasons.length ? <div><strong>匹配依据</strong><ul>{reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></div> : null}{conflicts.length ? <div className="has-conflict"><strong>冲突</strong><ul>{conflicts.map((conflict) => <li key={conflict}>{conflict}</li>)}</ul></div> : null}{candidate.source_url ? <a href={candidate.source_url} target="_blank" rel="noreferrer">打开来源 <ExternalLink size={12} /></a> : null}</div> : null}
            <div className="workflow-universal-entity-actions">
              {actions.map((action) => {
                const pending = acting === `${candidate.id}:${action}`;
                const selfReference = field === "translation_of" && Boolean(candidate.entity_id && String(candidate.entity_id) === workspace?.workId) && ["link_existing", "use_value"].includes(action);
                const unavailable = selfReference;
                const disabledReason = selfReference ? "当前作品不能作为自己的原作" : undefined;
                const baseLabel = action === "link_existing" && onUseValue ? "使用规范文本" : ACTION_LABELS[action] ?? action;
                const selectedLabel = action === "link_existing" && selected ? onUseValue ? "已使用该文本" : "已加入表单" : action === "use_value" && selected ? "已使用该文本" : baseLabel;
                return <button type="button" data-action={action} disabled={disabled || Boolean(acting) || pending || unavailable || (["link_existing", "use_value"].includes(action) && selected)} title={disabledReason} key={action} onClick={() => void decideExternal(candidate, action)}>{pending ? <LoaderCircle className="spin" size={12} /> : ["link_existing", "use_value"].includes(action) && selected ? <Check size={12} /> : action === "create_draft" ? <Plus size={12} /> : action === "inspect" ? <Search size={12} /> : action === "reject" ? <X size={12} /> : <ExternalLink size={12} />}{unavailable ? `${selectedLabel}（当前不可用）` : selectedLabel}</button>;
              })}
            </div>
          </article>;
        })}</section>)}
        {!loading && !visibleCandidates.length ? <p>{query.trim().length < 2 ? "输入至少 2 个字符开始发现。" : "没有找到候选。可以保留当前文本，稍后继续核对。"}</p> : null}
        {!workspace?.itemId ? <p className="workflow-universal-entity-maintenance-note">维护模式可以关联馆内实体并核对外部候选。需要 UploadItem 的创建、保留和拒绝决定在这里不可记录。</p> : null}
      </div> : null}
    </div>
  );
}
