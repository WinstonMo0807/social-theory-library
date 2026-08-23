import type { WorkflowCandidate } from "../workflow/workflow-types";

export const RESEARCH_SUGGESTION_REFRESH_EVENT = "workflow-research-suggestions-refresh";

export const RESEARCH_SOURCE_TIER_ORDER = [
  "in_library",
  "query_lexicon",
  "pdf_evidence",
  "structured_source",
  "web_evidence",
  "research_lead",
] as const;

export type ResearchSourceTier = typeof RESEARCH_SOURCE_TIER_ORDER[number];

type ResearchRunLike = {
  status?: string;
  local_results?: unknown;
  external_results?: unknown;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asRows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(asRecord).filter((row) => Object.keys(row).length > 0) : [];
}

function discoveryRows(value: Record<string, unknown>): Record<string, unknown>[] {
  const query = String(value.query ?? "").trim();
  return asRows(value.results).map((row) => (
    query && !row.source_name ? { ...row, source_name: query } : row
  ));
}

function discoverySourceTier(group: string): ResearchSourceTier {
  if (group === "authority") return "structured_source";
  if (group === "external_web" || group === "unresolved") return "research_lead";
  return "in_library";
}

function normalizeResearchCandidate(row: Record<string, unknown>, index: number): WorkflowCandidate {
  const rawField = String(row.field_name ?? row.field ?? "");
  const fieldName = rawField.includes(".") ? rawField.split(".").at(-1) ?? rawField : rawField;
  const candidateGroup = String(row.candidate_group ?? "");
  return {
    ...row,
    id: String(row.id ?? `research-run-${index}`),
    field_name: fieldName,
    source_tier: String(row.source_tier ?? discoverySourceTier(candidateGroup)),
  } as WorkflowCandidate;
}

/**
 * ResearchRun keeps local, entity, enrichment, and evidence results separate so
 * their provenance remains inspectable. The editor consumes a flat, deduped
 * view while preserving every source field on each row.
 */
export function researchRunSuggestions(payload: ResearchRunLike | null | undefined): WorkflowCandidate[] {
  if (!payload) return [];
  const local = asRecord(payload.local_results);
  const external = asRecord(payload.external_results);
  const output: Record<string, unknown>[] = [];
  output.push(...asRows(asRecord(local.workflow).suggestions));
  for (const group of asRows(local.entities)) output.push(...discoveryRows(group));
  output.push(...asRows(external.enrichment));
  for (const group of asRows(external.entities)) output.push(...discoveryRows(group));
  for (const group of asRows(external.editorial_evidence)) output.push(...asRows(group.suggestions));
  output.push(...asRows(asRecord(external.active_step_candidates).suggestions));

  const unique = new Map<string, WorkflowCandidate>();
  output.forEach((row, index) => {
    const candidate = normalizeResearchCandidate(row, index);
    unique.set(String(candidate.id), candidate);
  });
  return [...unique.values()];
}

export function prefixedResearchChangedFields(step: string, fields: readonly string[]): string[] {
  const qualifiedStep = /^(file|work|bibliography|contributors|classification|knowledge|reader|curation|publication)\./;
  return [...new Set(fields.map((field) => String(field).trim()).filter(Boolean).map((field) => (
    qualifiedStep.test(field) ? field : `${step}.${field}`
  )))];
}

export function isTerminalResearchStatus(status: unknown): boolean {
  return ["completed", "degraded", "failed", "canceled"].includes(String(status ?? ""));
}

export function groupResearchSuggestions(
  suggestions: WorkflowCandidate[],
  field?: string,
): Array<[string, WorkflowCandidate[]]> {
  const groups = new Map<string, WorkflowCandidate[]>();
  suggestions
    .filter((row) => !field || String(row.field_name ?? row.field ?? "") === field)
    .forEach((row) => {
      const key = String(row.source_tier ?? "in_library");
      groups.set(key, [...(groups.get(key) ?? []), row]);
    });
  return [...groups.entries()].sort(([left], [right]) => {
    const leftIndex = RESEARCH_SOURCE_TIER_ORDER.indexOf(left as ResearchSourceTier);
    const rightIndex = RESEARCH_SOURCE_TIER_ORDER.indexOf(right as ResearchSourceTier);
    return (leftIndex < 0 ? 99 : leftIndex) - (rightIndex < 0 ? 99 : rightIndex);
  });
}

export function isSelectableResearchSuggestion(candidate: WorkflowCandidate): boolean {
  const value = candidate.proposed_value && typeof candidate.proposed_value === "object"
    ? candidate.proposed_value as Record<string, unknown>
    : {};
  const entityId = String(candidate.entity_id ?? value.id ?? "").trim();
  if (!entityId) return false;
  return candidate.source_tier !== "research_lead" && candidate.evidence_status !== "lead_only";
}

export function canDirectlySelectResearchSuggestion(candidate: WorkflowCandidate): boolean {
  if (!isSelectableResearchSuggestion(candidate)) return false;
  if (candidate.source_tier === "query_lexicon") return true;
  return candidate.source_tier === "in_library" && !candidate.decision_url;
}

export function isEvidenceSuggestion(candidate: WorkflowCandidate): boolean {
  return candidate.evidence_status === "evidence"
    || candidate.source_tier === "pdf_evidence"
    || candidate.source_tier === "structured_source"
    || candidate.source_tier === "web_evidence";
}
