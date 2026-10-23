import type { EvidenceReference, ResolvedEvidence } from "./research.client";

export async function evidenceIdentity(reference: EvidenceReference): Promise<string> {
  if (reference.anchors?.length) {
    const identities = await Promise.all(reference.anchors.map(evidenceIdentity));
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(identities.join("|")));
    return `anchors:${Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("")}`;
  }
  const identity = reference.evidence_span_id || `${reference.asset_id}:${reference.pdf_page}`;
  return reference.selection_start !== undefined && reference.selection_end !== undefined
    ? `${identity}:range:${reference.selection_start}:${reference.selection_end}` : identity;
}

export function safeResearchReturn(value?: string) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(value)) return "";
  const url = new URL(value, "https://library.invalid");
  if (url.origin !== "https://library.invalid" || !/^\/(account|research|explore|recommendations|topics|theories\/reading-paths)(\/|$)/.test(url.pathname)) return "";
  return `${url.pathname}${url.search}${url.hash}`;
}

export function readerContextHref(href: string, context: { projectId?: string; turnId?: string; referenceId?: string; returnTo?: string }) {
  if (!href.startsWith("/reader/") || /[\\\u0000-\u001f\u007f]/.test(href)) return "";
  const url = new URL(href, "https://library.invalid");
  if (url.origin !== "https://library.invalid" || !url.pathname.startsWith("/reader/")) return "";
  const returnTo = safeResearchReturn(context.returnTo);
  if (returnTo) url.searchParams.set("return_to", returnTo);
  if (context.projectId) url.searchParams.set("research_project", context.projectId);
  if (context.turnId) url.searchParams.set("research_turn", context.turnId);
  if (context.referenceId) url.searchParams.set("reference", context.referenceId);
  return `${url.pathname}${url.search}${url.hash}`;
}

export async function researchReaderHref(reference: ResolvedEvidence, context: { projectId?: string; turnId?: string; returnTo?: string }) {
  if (reference.source_status !== "available" || !reference.asset_id || !reference.document_revision_id) return null;
  const params = new URLSearchParams({ page: String(reference.pdf_page || 1), revision: reference.document_revision_id,
    reference: await evidenceIdentity(reference) });
  if (context.projectId) params.set("research_project", context.projectId);
  if (context.turnId) params.set("research_turn", context.turnId);
  const returnTo = safeResearchReturn(context.returnTo);
  if (returnTo) params.set("return_to", returnTo);
  return `/reader/${encodeURIComponent(reference.asset_id)}?${params}`;
}

export function availableEvidenceAnchors(reference: ResolvedEvidence, assetId: string, revisionId: string) {
  if (reference.source_status !== "available" || !revisionId) return [];
  const anchors = reference.anchors?.length ? reference.anchors : [reference];
  if (anchors.some(anchor => anchor.source_status !== "available" || anchor.asset_id !== assetId ||
      anchor.document_revision_id !== revisionId || !Number.isInteger(anchor.pdf_page) || (anchor.pdf_page || 0) < 1)) return [];
  return anchors;
}
