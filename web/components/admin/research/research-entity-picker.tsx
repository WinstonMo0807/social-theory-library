"use client";

import { Check, Search } from "lucide-react";
import { EntityPicker, type EntityValue } from "../forms/workflow-fields";
import type { WorkflowCandidate } from "../workflow/workflow-types";
import { canDirectlySelectResearchSuggestion } from "./research-suggestion-state";

export function ResearchEntityPicker({
  label,
  endpoint,
  values,
  onChange,
  suggestions = [],
  onInspect,
  idField,
  nameField,
  placeholder,
  allowUnresolved = false,
}: {
  label: string;
  endpoint: string;
  values: EntityValue[];
  onChange: (values: EntityValue[]) => void;
  suggestions?: WorkflowCandidate[];
  onInspect?: (candidate: WorkflowCandidate) => void;
  idField?: string;
  nameField?: string;
  placeholder?: string;
  allowUnresolved?: boolean;
}) {
  const candidates = suggestions.filter((row) => row.entity_id || row.proposed_value);
  return <div className="workflow-research-entity-picker"><EntityPicker label={label} endpoint={endpoint} values={values} onChange={onChange} idField={idField} nameField={nameField} placeholder={placeholder ?? "搜索馆内实体、别名或研究建议"} allowUnresolved={allowUnresolved} /><div className="workflow-research-entity-candidates" aria-label={`${label}研究建议`}>{candidates.slice(0, 6).map((candidate) => { const value = candidate.proposed_value && typeof candidate.proposed_value === "object" ? candidate.proposed_value as Record<string, unknown> : {}; const id = String(candidate.entity_id ?? value.id ?? ""); const name = String(candidate.label ?? value.name ?? candidate.value ?? ""); const selected = Boolean(id && values.some((row) => row.id === id)); const directSelection = canDirectlySelectResearchSuggestion(candidate); const actionLabel = selected ? "已选择" : directSelection ? "选择" : "核对"; return <div className="workflow-research-entity-row" key={String(candidate.id)}><span><Search size={13} /><strong>{name}</strong><small>{String(candidate.source_tier_label ?? candidate.source_tier ?? "建议")} · {Math.round(Number(candidate.confidence ?? 0) * 100)}%</small></span><button type="button" onClick={() => { if (directSelection && id && name && !selected) onChange([...values, { id, name, status: "suggested" }]); else onInspect?.(candidate); }} aria-label={selected ? `${name}已选择` : `${actionLabel}${name}`}><Check size={13} />{actionLabel}</button></div>; })}</div></div>;
}
