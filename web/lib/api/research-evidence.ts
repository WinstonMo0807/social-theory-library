import type { EvidenceReference, QueryScope, ResolvedEvidence } from "./research.client";
import { readerContextHref } from "./research-navigation";

/** Keep distinct passages on the same page distinct; use the server's composite identity. */
export function researchEvidenceKey(reference: ResolvedEvidence): string {
  return reference.reference_id || reference.evidence_span_id || `${reference.asset_id}:${reference.pdf_page}`;
}

export function researchEvidenceReference(reference: EvidenceReference): EvidenceReference {
  if (reference.anchors?.length) return { anchors: reference.anchors.map(researchEvidenceReference) };
  const anchor = { asset_id: reference.asset_id, document_revision_id: reference.document_revision_id,
    pdf_page: reference.pdf_page, evidence_span_id: reference.evidence_span_id, content_hash: reference.content_hash,
    ...(reference.selection_start !== undefined ? { selection_start: reference.selection_start, selection_end: reference.selection_end } : {}) };
  return Object.fromEntries(Object.entries(anchor).filter(([, value]) => value !== null && value !== undefined)) as EvidenceReference;
}

export function researchScopeLabel(scope?: QueryScope): string {
  if (scope?.kind === "passages") return "指定原文段落";
  if (scope?.kind === "works") return "指定文献";
  if (scope?.kind === "filtered") return "已保存的筛选范围";
  return "全馆可访问文献";
}

/** Resolved scope responses may contain quotations; commands retain only the original identities. */
export function researchScopeInput(scope: QueryScope): QueryScope {
  return { kind: scope.kind, filters: scope.filters || {}, allow_neighbors: Boolean(scope.allow_neighbors),
    ...(scope.references ? { references: scope.references.map(ref => researchEvidenceReference(ref as ResolvedEvidence)) } : {}) };
}

export function researchReaderHref(reference: ResolvedEvidence, context?: { projectId?: string; turnId?: string; returnTo?: string }): string {
  const url = reference.reader_url || "";
  return reference.source_status === "available" ? readerContextHref(url, { ...context, ...(context?.projectId || context?.turnId ? { referenceId: reference.reference_id } : {}) }) : "";
}
