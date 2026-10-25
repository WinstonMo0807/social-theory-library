import type { EvidenceReference, QueryScope, ResearchTurnCommand } from "./api/research.client";

export type PendingResearchTurn = { command: ResearchTurnCommand; branch: boolean };
export type ResearchBranchDraft = { question: string; parent_id: string; scope: QueryScope };
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const filterKeys = new Set("work work_id work_ids scholar author authors theory theory_node_ids topic topic_ids concept tag concepts document_type document_types language languages year years year_min year_max access source_type source_types theories topics".split(" "));
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("暂存内容格式无法核对。");
  return value as Record<string, unknown>;
}
function uuid(value: unknown): string {
  if (typeof value !== "string" || !uuidPattern.test(value)) throw new Error("暂存的来源或请求标识无法核对。");
  return value;
}
function positive(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 1) throw new Error("暂存的修订号或页序无法核对。");
  return value;
}
export function parseResearchReferenceDraft(value: unknown, single = false): EvidenceReference {
  const raw = object(value);
  if (raw.anchors !== undefined) {
    if (single || !Array.isArray(raw.anchors) || !raw.anchors.length || raw.anchors.length > 20) throw new Error("暂存的跨页引用无法核对。");
    return { anchors: raw.anchors.map(anchor => parseResearchReferenceDraft(anchor, true)) };
  }
  const ref: Record<string, unknown> = {};
  for (const key of ["asset_id", "document_revision_id", "evidence_span_id"]) {
    if (raw[key] !== undefined) ref[key] = raw[key] === null ? null : uuid(raw[key]);
  }
  if (raw.pdf_page !== undefined) ref.pdf_page = raw.pdf_page === null ? null : positive(raw.pdf_page);
  if (!ref.evidence_span_id && !(ref.asset_id && ref.document_revision_id && ref.pdf_page)) throw new Error("暂存的引用缺少原始位置，不会自动替换来源。");
  if (raw.content_hash !== undefined) {
    if (raw.content_hash !== null && (typeof raw.content_hash !== "string" || !/^[0-9a-f]{64}$/i.test(raw.content_hash))) throw new Error("暂存的原文校验标识无法核对。");
    ref.content_hash = raw.content_hash;
  }
  if (raw.selection_start !== undefined || raw.selection_end !== undefined) {
    const start = raw.selection_start, end = raw.selection_end;
    if (typeof start !== "number" || typeof end !== "number" || !Number.isSafeInteger(start) || !Number.isSafeInteger(end)
      || start < 0 || start >= end || end - start > 20000 || !ref.content_hash) throw new Error("暂存的选文范围无法核对。");
    ref.selection_start = start; ref.selection_end = end;
  }
  return ref as EvidenceReference;
}
export function parseResearchScopeDraft(value: unknown): QueryScope {
  const raw = object(value);
  if (!["library", "works", "passages", "filtered"].includes(String(raw.kind))) throw new Error("暂存的检索范围无法核对。");
  const filters: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(object(raw.filters || {}))) {
    if (!filterKeys.has(key)) throw new Error("暂存包含不支持的筛选条件，不会自动扩大范围。");
    const values = Array.isArray(value) ? value : [value];
    if (values.length > 30 || values.some(item => !(typeof item === "string" && item.length <= 4800 || typeof item === "number" && Number.isSafeInteger(item)))) throw new Error("暂存的筛选条件无法核对。");
    filters[key] = value;
  }
  if (raw.allow_neighbors !== undefined && typeof raw.allow_neighbors !== "boolean") throw new Error("暂存的范围扩展选项无法核对。");
  let references: EvidenceReference[] | undefined;
  if (raw.references !== undefined) {
    if (!Array.isArray(raw.references) || raw.references.length > 400) throw new Error("暂存选材超过读取范围。");
    references = raw.references.map(ref => parseResearchReferenceDraft(ref));
  }
  if (raw.kind === "passages" && !references?.length || raw.kind === "works" && !filters.work_ids && !filters.work_id && !filters.work) throw new Error("暂存的限定范围为空，不会改用全馆。");
  return { kind: raw.kind as QueryScope["kind"], filters: filters as QueryScope["filters"], allow_neighbors: Boolean(raw.allow_neighbors), ...(references ? { references } : {}) };
}
export function parsePendingResearchTurn(value: unknown, projectId?: string): PendingResearchTurn {
  const raw = object(value), command = object(raw.command), data = object(command.data);
  const project = uuid(command.projectId);
  if (projectId && project !== projectId || typeof raw.branch !== "boolean" || raw.branch && (!data.parent_id || command.expandTurnId) || data.mode !== "search"
    || typeof data.question !== "string" || data.question.trim().length < 2 || data.question.length > 1200) throw new Error("暂存请求与当前研究不匹配，原记录未覆盖。");
  return { branch: raw.branch, command: { projectId: project, ...(command.expandTurnId !== undefined ? { expandTurnId: uuid(command.expandTurnId) } : {}),
    data: { expected_revision: positive(data.expected_revision), request_id: uuid(data.request_id), question: data.question, mode: "search",
      ...(data.parent_id !== undefined ? { parent_id: uuid(data.parent_id) } : {}), scope: parseResearchScopeDraft(data.scope) } } };
}
export function parseResearchBranchDraft(value: unknown): ResearchBranchDraft {
  const raw = object(value);
  if (typeof raw.question !== "string" || raw.question.length > 1200) throw new Error("分支草稿文字无法核对，原记录未覆盖。");
  return { question: raw.question, parent_id: uuid(raw.parent_id), scope: parseResearchScopeDraft(raw.scope) };
}
