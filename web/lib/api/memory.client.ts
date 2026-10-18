import { privateRequest, researchRecordPath, type EvidenceReference, type MemoryData, type ResearchRecord, type ResolvedEvidence } from "./research.client";
import type { Paginated } from "./pagination";

export type MemoryKind = MemoryData["kind"] | "concept" | "method" | "observation";
export type MemoryState = "proposed" | "confirmed" | "ignored";
export type MemoryScope = { kind: "project" | "plan"; id: string; title: string; revision: number; enabled: boolean; selected: boolean };
export type MemoryNote = { id: string; body?: string; body_text?: string; quote?: string; asset_id?: string; reader_url?: string | null; source_status?: string; title?: string; updated_at?: string };
export type ConfirmedMemoryData = {
  body: string; kind: MemoryKind; source_status?: string; origin_note?: MemoryNote | null;
  sources: Array<ResolvedEvidence & { cover_url?: string | null }>;
  source_summaries?: Array<{ title?: string; authors?: string[]; edition?: string; publication_year?: number | null; cover_url?: string | null; printed_label?: string; current_reader_url?: string | null }>;
  usage_scopes?: MemoryScope[];
  history?: Array<{ revision: number; at: string; data: { body: string; kind: MemoryKind; sources: ResolvedEvidence[] }; state?: string }>;
  [key: string]: unknown;
};
export type ConfirmedMemory = ResearchRecord<ConfirmedMemoryData>;
export type MemoryPage = Paginated<ConfirmedMemory> & { counts?: Record<string, number | Record<string, number>> };
export type MemoryUsage = { memory_id: string; revision: number; targets: MemoryScope[]; notice?: string };
export type AnnotationChoice = { id: string; asset: string; kind: string; body_text?: string; quote?: string; work?: { title?: string; cover_url?: string | null }; selector?: { page_index?: number }; orphaned: boolean; updated_at: string };

export function saveMemory(id: string, data: { expected_revision: number; body?: string; kind?: MemoryKind; state?: MemoryState; sources?: EvidenceReference[]; refresh_origin?: boolean }) {
  return privateRequest<ConfirmedMemory>(researchRecordPath("research-memories", id), { method: "PATCH", body: JSON.stringify(data) });
}
export function proposeMemory(data: { request_id: string; annotation_id: string; body: string; kind: MemoryKind }) {
  return privateRequest<ConfirmedMemory>(researchRecordPath("research-memories"), { method: "POST", body: JSON.stringify(data) });
}
export function changeMemoryUsage(id: string, data: { expected_revision: number; action: "grant" | "revoke" | "revoke_all"; targets?: Array<{ kind: MemoryScope["kind"]; id: string; expected_revision: number }> }) {
  return privateRequest<ConfirmedMemory>(`${researchRecordPath("research-memories", id)}usage/`, { method: "POST", body: JSON.stringify(data) });
}
