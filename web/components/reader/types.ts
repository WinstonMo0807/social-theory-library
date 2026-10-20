import type { CanonicalBlock } from "../pdf-canvas";
import type { ReaderGeometryBox } from "@/lib/reader-coordinates";

export type PagePayload = {
  asset_id?: string;
  document_revision_id?: string | null;
  page_id: string;
  page_index: number;
  printed_label: string;
  chapter_title: string;
  text_source: "none" | "embedded" | "ocr" | "hybrid";
  width: number;
  height: number;
  text: string;
  blocks: CanonicalBlock[];
  geometry?: Record<string, unknown>;
};

export type ReaderAnnotation = {
  id: string;
  asset?: string;
  page: string;
  kind: "highlight" | "underline" | "note";
  selector: {
    type?: string;
    page_index?: number;
    exact?: string;
    bboxes?: number[][];
  };
  quote: string;
  body_text: string;
  tags?: string[];
  color?: string;
  created_at: string;
  updated_at: string;
};

export type ReaderBookmark = {
  id: string;
  page: string;
  page_index: number;
  label: string;
  created_at?: string;
};

export type AnnotationDraft = {
  kind: "highlight" | "underline" | "note";
  pageIndex: number;
  pageId: string;
  quote: string;
  bboxes: number[][];
  body: string;
  tags?: string[];
};

export type SelectionSnapshot = Omit<AnnotationDraft, "kind" | "body" | "tags"> & {
  x: number;
  y: number;
};

export type SidebarTab = "outline" | "search" | "thumbnails" | "highlights" | "bookmarks" | "notes";

export type AccessPayload = {
  url: string;
  download_url: string;
  original_download_url?: string;
  download_rendition?: "normalized" | "ocr_pdf" | "web_derivative";
  source: string;
  expires_in: number | null;
  download_filename: string;
  edition_id: string;
  page_count: number;
  requested_asset_id: string;
  served_asset_id: string;
  source_artifact_id: string | null;
  rendition: "normalized" | "ocr_pdf" | "web_derivative";
  reader_rendition_policy: "auto" | "original" | "ocr";
  reader_fallback_reason: string;
  sha256: string;
  ocr_status: "not_required" | "pending" | "running" | "succeeded" | "failed" | "disabled";
  ocr_text_available: boolean;
  page_label_status: "pending" | "ready" | "needs_review";
  semantic_index_status: "not_indexed" | "pending" | "running" | "ready" | "failed";
};

export type SearchMatch = {
  rank: number;
  occurrence_count: number;
  page_id: string;
  page_index: number;
  printed_label: string;
  snippet: string;
  width: number;
  height: number;
  blocks: (ReaderGeometryBox & { bbox: number[]; text: string; order: number })[];
  highlights?: (ReaderGeometryBox & { bbox: number[]; text: string; source: "pdf-text" | "ocr-estimate" })[];
};

export type PassageFocus = ReaderGeometryBox & {
  id: string;
  asset_id: string;
  document_revision_id?: string | null;
  coordinate_space?: "displayed" | "pymupdf_unrotated";
  title: string;
  page_index: number;
  printed_label: string;
  width: number;
  height: number;
  bbox: number[];
  text: string;
  text_source?: string;
};

export type CitationStyle = "gbt7714-2025" | "apa" | "chicago" | "mla" | "harvard";
export type CitationBundle = Record<CitationStyle, string> & {
  page?: {
    pdf_page: number;
    printed_label: string;
    citation_label: string;
    source: "pdf-label" | "pdf-index" | "legacy" | "none";
  };
};
