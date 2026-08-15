import type { SemanticSearchResult } from "@/lib/server-api";

const responseTypeLabels: Record<string, string> = {
  direct_response: "可能直接回应",
  partial_response: "具有回答价值",
  semantic_related: "相关论述",
  background_context: "背景讨论",
};

const legacyRankLabels: Record<string, string> = {
  高度相关: "优先候选",
  较为相关: "补充候选",
  可能相关: "延伸候选",
};

export function semanticResponseLabel(
  item: Pick<SemanticSearchResult, "response_label" | "response_type" | "relevance">,
) {
  const explicit = item.response_label?.trim();
  if (explicit) return explicit;
  if (item.response_type && responseTypeLabels[item.response_type]) {
    return responseTypeLabels[item.response_type];
  }
  return legacyRankLabels[item.relevance] ?? "候选原文";
}
