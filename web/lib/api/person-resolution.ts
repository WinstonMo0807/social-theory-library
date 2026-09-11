import { apiRequest } from "../api";
import type { components } from "./generated/schema";

export type PersonSummary = components["schemas"]["PersonResolutionSummary"];
export type PersonSearch = components["schemas"]["PersonSearchResponse"];
export type PersonDuplicates = components["schemas"]["PersonDuplicateResponse"];
export type PersonPreview = components["schemas"]["PersonMergePreviewResponse"];
export type PersonMerge = components["schemas"]["PersonMergeRecord"];
export type MergeHistory = components["schemas"]["PersonMergeHistoryItem"];
export type MergeInput = components["schemas"]["PersonMergeRequestRequest"];
type RollbackInput = components["schemas"]["PersonMergeRollbackRequestRequest"];

export const isPersonId = (value: string) => /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value);
const isFingerprint = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);

export function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

export function textValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "未填写";
  if (typeof value === "boolean") return value ? "是" : "否";
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}

export function canConfirmPersonMerge(preview: PersonPreview, sourceId: string, targetId: string) {
  return sourceId !== targetId && isPersonId(sourceId) && isPersonId(targetId)
    && asRecord(preview.source).id === sourceId && asRecord(preview.target).id === targetId
    && preview.execution_policy === "person-merge-noncolliding-v1"
    && preview.merge_execution_available === true && preview.complete_reference_listing === true
    && preview.review_issues.length === 0 && preview.identity_conflicts.length === 0
    && isFingerprint(preview.fingerprint);
}

export function rollbackState(record: PersonMerge) {
  const value = asRecord(record.rollback);
  const blockers = Array.isArray(value.blockers) ? value.blockers.filter((item): item is string => typeof item === "string") : [];
  return {
    canRollback: record.status === "applied" && value.can_rollback === true
      && Array.isArray(value.blockers) && value.blockers.length === 0 && isFingerprint(value.fingerprint),
    fingerprint: isFingerprint(value.fingerprint) ? value.fingerprint : "",
    blockers,
  };
}

export function personPage(source = "", target = "", record = "") {
  const query = new URLSearchParams();
  if (source) query.set("source", source);
  if (target) query.set("target", target);
  if (record) query.set("record", record);
  return `/admin/people${query.size ? `?${query}` : ""}`;
}

export const personApi = {
  search: (query: string) => `/catalog/admin/people/?search=${encodeURIComponent(query)}&limit=20`,
  duplicates: (source: string) => `/catalog/admin/people/${encodeURIComponent(source)}/duplicates/?limit=20`,
  preview: (source: string, target: string) => `/catalog/admin/people/${encodeURIComponent(source)}/merge-preview/?target_person=${encodeURIComponent(target)}`,
  history: (source: string) => `/catalog/admin/people/merge-records/?source_person=${encodeURIComponent(source)}`,
  record: (id: string) => `/catalog/admin/people/merge-records/${encodeURIComponent(id)}/`,
};

export function mergePerson(source: string, input: MergeInput, credential: string) {
  return apiRequest<PersonMerge>(`/catalog/admin/people/${encodeURIComponent(source)}/merge/`, {
    method: "POST", body: JSON.stringify(input),
  }, credential);
}

export function rollbackPerson(id: string, input: RollbackInput, credential: string) {
  return apiRequest<PersonMerge>(`${personApi.record(id)}rollback/`, {
    method: "POST", body: JSON.stringify(input),
  }, credential);
}
