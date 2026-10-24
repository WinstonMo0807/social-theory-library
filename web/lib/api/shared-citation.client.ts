import type { components } from "./generated/schema";
import { apiRequest } from "../api";
import type { EvidenceReference, ResolvedEvidence } from "./research.client";

export type SharedCitationInput = { editionId?: string; reference?: EvidenceReference; selectedText?: string };
export const citationFormats = [
  ["quote", "引用文本"], ["apa", "APA"], ["mla", "MLA"], ["gbt7714-2025", "GB/T 7714"],
  ["chicago", "Chicago"], ["harvard", "Harvard"], ["csl", "CSL JSON"],
] as const;
export type CitationFormat = typeof citationFormats[number][0];
export type SharedCitationPreview = {
  reference: ResolvedEvidence | null;
  source: { edition_id: string; work_id: string; title: string; authors: string[]; publication_year: number | null;
    publisher: string; cover_url: string | null; cover_media?: components["schemas"]["PublicCoverMedia"] | null; work_url: string; reader_url: string | null; pdf_page: number | null; printed_label: string; source_status: "available" };
  citations: Record<Exclude<CitationFormat, "quote" | "csl">, string> & { csl: Record<string, unknown> };
};
export function previewSharedCitation(input: SharedCitationInput, signal?: AbortSignal) {
  return apiRequest<SharedCitationPreview>("/reading/citation-preview/", { method: "POST", cache: "no-store",
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000),
    body: JSON.stringify({ edition_id: input.editionId, reference: input.reference, selected_text: input.selectedText }) });
}
export function citationText(preview: SharedCitationPreview, format: CitationFormat) {
  if (format === "csl") return JSON.stringify(preview.citations.csl, null, 2);
  if (format === "quote") return [preview.reference?.quote, preview.citations["gbt7714-2025"]].filter(Boolean).join("\n\n");
  return preview.citations[format];
}
export function citationDownload(text: string, filename = "书库引用.txt") {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
