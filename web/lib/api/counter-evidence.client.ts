import { privateRequest, researchRecordPath, type AnalysisRelation, type ResearchRecord, type ResolvedEvidence, type Statement, type TurnData } from "./research.client";

export type CounterRelation = AnalysisRelation | "unrelated";
export type CounterAttribution = "author_claim" | "quoted_claim" | "reported_claim" | "criticized_claim" | "historical_description" | "uncertain";
export type CounterReference = ResolvedEvidence & { cover_url?: string | null; publication_year?: number | null };
export type CounterDecision = { by: string; at: string; relation?: CounterRelation; note?: string; attribution?: CounterAttribution; scope_note?: string; memory_id?: string | null };
export type CounterAnalysis = {
  id: string; reference: CounterReference; relation: CounterRelation; status: string; reason?: string;
  candidate_statement?: Statement & { attribution?: CounterAttribution; claim_type?: string };
  model_suggestion?: { relation?: CounterRelation; reason?: string; attribution?: string; scope_difference?: string };
  rule_signal?: { stance?: string; reasons?: string[] }; decision?: CounterDecision | null;
  decision_history?: Array<{ revision: number; at: string; relation: CounterRelation; decision: CounterDecision | null; action: string }>;
};
export type CounterTurnData = Omit<TurnData, "analysis"> & {
  question: string; mode: "search" | "counterargument"; scope: TurnData["scope"]; analysis?: CounterAnalysis[];
  statement?: Statement; analysis_statement?: Statement; subclaims?: Array<Statement & { id: string }>;
  result_refs?: CounterReference[];
  active_subclaim_id?: string | null; analysis_notice?: string; subclaim_notice?: string;
  analysis_model?: { status?: string; message?: string }; warnings?: Array<{ code?: string; message?: string }>;
};
export type CounterDecisionInput = { expected_revision: number; request_id: string; id: string; action?: "confirm" | "clear";
  relation?: CounterRelation; note?: string; attribution?: CounterAttribution; scope_note?: string; save_as_note?: boolean };
export function saveCounterDecision(id: string, data: CounterDecisionInput) {
  return privateRequest<ResearchRecord<CounterTurnData>>(`${researchRecordPath("research-turns", id)}decision/`, { method: "POST", body: JSON.stringify(data) });
}

export const counterRelations: Record<CounterRelation, string> = { support: "支持", different_conclusion: "不同结论", qualification: "限定条件", reframe: "转换解释", insufficient_evidence: "待复核", unrelated: "不相关" };
export const counterAttributions: Record<CounterAttribution, string> = { author_claim: "作者本人的主张", quoted_claim: "引述他人主张", reported_claim: "转述他人主张", criticized_claim: "正在批评的主张", historical_description: "历史描述", uncertain: "归属尚不确定" };
export function counterAvailable(reference: ResolvedEvidence) {
  return reference.source_status === "available" && (!reference.anchors?.length || reference.anchors.every(anchor => anchor.source_status === "available"));
}
export function counterRelation(row: CounterAnalysis): CounterRelation {
  if (!counterAvailable(row.reference) || row.status === "source_unavailable") return "insufficient_evidence";
  const relation = row.decision && row.status === "user_confirmed" ? row.relation : row.model_suggestion?.relation || "insufficient_evidence";
  return relation in counterRelations ? relation : "insufficient_evidence";
}
