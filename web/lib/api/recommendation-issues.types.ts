import type { SiteConfig } from "../site-config";
import type { AboutPageBlock } from "./site.types";

export type IssueBlock = { type: "paragraph" | "heading" | "quote" | "link"; text: string; url?: string; source?: string };
export type IssueItem = {
  id: string; kind: "catalog" | "planned"; work_id?: string | null; edition_id?: string | null;
  title: string; authors: string; version_note: string; isbn: string; doi: string; note: string; position: number;
  cataloging_session_id?: string | null; status?: string; work_url?: string; reader_url?: string; cover_url?: string;
  match_candidates?: { work_id: string; edition_id: string; title: string; version_label: string; publication_year: number | null; match_basis: string }[];
  linked_edition_id?: string | null;
};
export type RecommendationIssue = {
  id: string; slug: string; title: string; issue_label: string; introduction: string;
  body_blocks: IssueBlock[]; public_byline: string; cover_url: string; display_from: string | null;
  published_at: string | null; items: IssueItem[]; edit_version: string; draft_revision_id?: string | null;
  has_unpublished_changes?: boolean; status?: string;
};
export type IssuePage = { count: number; next: string | null; previous: string | null; results: RecommendationIssue[]; current: RecommendationIssue | null; summary?: { total: number; published: number; drafts: number; scheduled: number }; upcoming?: RecommendationIssue[] };
export type SiteContentDraft = { config: SiteConfig; about_blocks: AboutPageBlock[]; edit_version: string; has_unpublished_changes: boolean };
