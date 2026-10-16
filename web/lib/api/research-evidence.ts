import type { EvidenceReference, QueryScope, ResolvedEvidence } from "./research.client";

/** Keep distinct passages on the same page distinct; use the server's composite identity. */
export function researchEvidenceKey(reference: ResolvedEvidence): string {
  return reference.reference_id || reference.evidence_span_id || `${reference.asset_id}:${reference.pdf_page}`;
}

export function researchEvidenceReference(reference: ResolvedEvidence): EvidenceReference {
  if (reference.anchors?.length) return { anchors: reference.anchors.map(researchEvidenceReference) };
  return { asset_id: reference.asset_id, document_revision_id: reference.document_revision_id,
    pdf_page: reference.pdf_page, evidence_span_id: reference.evidence_span_id, content_hash: reference.content_hash };
}

export function researchScopeLabel(scope?: QueryScope): string {
  if (scope?.kind === "passages") return "指定原文段落";
  if (scope?.kind === "works") return "指定文献";
  if (scope?.kind === "filtered") return "已保存的筛选范围";
  return "全馆可访问文献";
}

export function researchReaderHref(reference: ResolvedEvidence): string {
  const url = reference.reader_url || "";
  return reference.source_status === "available" && url.startsWith("/") && !url.startsWith("//") && !url.includes("\\") ? url : "";
}
