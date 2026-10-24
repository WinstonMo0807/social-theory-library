import { apiRequest, getServerSessionCredential } from "../api";
import type { QueryScope, ResolvedEvidence } from "./research.client";

export type ReplayTurn = { id: string; parent_id: string | null; revision: number; title: string; question: string; status: string; created_at: string; updated_at: string; material_count: number; snapshot_available: boolean };
export type ReplayTimeline = { owner_id: string; project: { id: string; title: string; revision: number; archived: boolean }; count: number; page: number; total_pages: number; current_turn_id: string | null; results: ReplayTurn[] };
export type ReplayDetail = { owner_id: string; project_id: string; project_revision: number; turn: ReplayTurn; scope: QueryScope; materials: Array<ResolvedEvidence & { cover_url?: string | null; publication_year?: number | null }>; added_ids: string[]; unchanged_ids: string[]; removed: ResolvedEvidence[]; compared: ReplayTurn | null; scope_changed: boolean; previous_scope: QueryScope | null; notes: string; snapshot_notes: string | null; snapshot_title: string | null; unavailable_count: number; notice: string };
export type ReplayFork = { turn_id: string; expected_revision: number; expected_project_revision: number; request_id: string; title: string; question: string; reference_ids: string[]; include_notes: boolean };
export type ReplayReceipt = { owner_id: string; request_id: string; project_id: string | null; deleted: boolean; state: "applied" | "cancelled" };
export const replayPath = (id: string) => `/reading/research-projects/${encodeURIComponent(id)}/replay/`;
export function replayRequest<T extends { owner_id: string }>(owner: string, path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers); headers.set("X-Reader-Owner", owner);
  const signal = AbortSignal.any([AbortSignal.timeout(30000), ...(options.signal ? [options.signal] : [])]);
  return apiRequest<T>(path, { ...options, headers, signal, cache: "no-store" }, getServerSessionCredential(), false).then(result => {
    if (result.owner_id !== owner) throw Error("登录账户已变化，请重新核对研究。");
    return result;
  });
}
