import type { ParallelSegment, ParallelVersion } from "./parallel-reader.client";
import type { ResolvedEvidence } from "./research.client";

/** Open the recorded file revision; the reader must not silently accept a replacement. */
export function parallelEvidenceHref(reference: ResolvedEvidence, target?: ParallelVersion) {
  const first = reference.anchors?.[0] || reference;
  if (reference.source_status !== "available" || !first.asset_id || !first.document_revision_id || !Number.isInteger(first.pdf_page) || (first.pdf_page || 0) < 1) return "";
  const params = new URLSearchParams({ mode: "parallel", page: String(first.pdf_page), revision: first.document_revision_id });
  if (first.evidence_span_id) params.set("focus", first.evidence_span_id);
  else if (first.selection_start !== undefined && first.selection_end !== undefined) params.set("focus", `${first.asset_id}:${first.pdf_page}:range:${first.selection_start}:${first.selection_end}`);
  if (target?.asset_id && target.document_revision_id && target.state === "available" && target.asset_id !== first.asset_id) {
    params.set("right_asset", target.asset_id); params.set("right_revision", target.document_revision_id);
  }
  return `/reader/${encodeURIComponent(first.asset_id)}?${params}`;
}

export function parallelSourceMatches(version: ParallelVersion | undefined, assetId: string, revisionId: string) {
  return Boolean(version && version.asset_id === assetId && version.document_revision_id === revisionId && version.state === "available");
}

/** A subrange may fall inside a larger returned paragraph; never fall back to an unrelated first row. */
export function parallelFocusMatches(segment: ParallelSegment, focus: string) {
  if (!focus) return false;
  if (segment.id === focus || segment.reference.evidence_span_id === focus.split(":")[0]) return true;
  const [asset, page, kind, start, end, extra] = focus.split(":");
  const ref = segment.reference;
  return extra === undefined && kind === "range" && asset === ref.asset_id && page === String(ref.pdf_page)
    && /^\d+$/.test(start || "") && /^\d+$/.test(end || "") && Number(start) < Number(end)
    && ref.selection_start !== undefined && ref.selection_end !== undefined
    && ref.selection_start <= Number(start) && Number(start) < ref.selection_end;
}
