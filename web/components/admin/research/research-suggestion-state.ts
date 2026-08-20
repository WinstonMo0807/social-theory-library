import type { WorkflowCandidate } from "../workflow/workflow-types";

export const RESEARCH_SOURCE_TIER_ORDER = [
  "in_library",
  "query_lexicon",
  "pdf_evidence",
  "structured_source",
  "web_evidence",
  "research_lead",
] as const;

export type ResearchSourceTier = typeof RESEARCH_SOURCE_TIER_ORDER[number];

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
