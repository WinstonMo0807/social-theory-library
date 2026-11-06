import type { SiteConfig } from "../site-config";
import type { AboutPageBlock } from "./site.types";
import type { PublicScholarCard } from "./scholars.types";
import type { MediaDisplayUse } from "../media-usage";

export type IssueSourceReference = { type: "work" | "edition" | "span" | "node" | "person" | "timeline" | "reading_path"; id: string; edition_id?: string; document_revision_id?: string };
export type IssueResolvedSource = IssueSourceReference & { title: string; text?: string; reader_url?: string; work_url?: string; printed_label?: string; page_start?: number; source_type?: string; asset_id?: string; work_id?: string; href?: string; summary?: string; edition_label?: string; public_eligible?: boolean; edit_url?: string; image_url?:string;authors?:string[];publication_year?:number|null;publisher?:string;section?:string };
export type IssueTextMark = {start:number;end:number;kind:"strong"|"em"|"underline"|"link";href?:string};
export type IssueBlock = {
  id?: string;
  type: "paragraph" | "heading" | "quote" | "link" | "image" | "evidence" | "work" | "person" | "concept" | "node" | "timeline" | "reading_path" | "analysis" | "comparison";
  image_rendition_id?: string | null; image_url?: string; alt_text?: string;
  text: string; url?: string; source?: string; target?: IssueSourceReference; references?: IssueSourceReference[];
  text_style?: "paragraph"|"ordered"|"unordered"|"quote"; text_marks?:IssueTextMark[];
  heading_level?:1|2|3;
  style?: "paragraph" | "heading"; source_status?: "available" | "unavailable"; resolved_sources?: IssueResolvedSource[];
  dimensions?: string[]; rows?: Array<{ person_id: string; cells: Array<{ dimension: string; text: string; evidence: IssueSourceReference[]; missing: boolean }> }>;
};
export type IssueItem = {
  section_id?: string;
  id: string; kind: "catalog" | "planned"; work_id?: string | null; edition_id?: string | null;
  title: string; authors: string; version_note: string; isbn: string; doi: string; note: string; position: number;
  cataloging_session_id?: string | null; status?: string; work_url?: string; reader_url?: string; cover_url?: string;
  cover_display_uses?: MediaDisplayUse[];
  match_candidates?: { work_id: string; edition_id: string; title: string; version_label: string; publication_year: number | null; match_basis: string }[];
  linked_edition_id?: string | null;
};
export type RecommendationIssue = {
  is_public?: boolean;
  project_id?: string | null; project_title?: string; project_archived?: boolean;
  selection_workspace?: IssueSelection;
  id: string; slug: string; title: string; issue_label: string; introduction: string;
  body_blocks: IssueBlock[]; public_byline: string; cover_url: string; display_from: string | null;
  published_at: string | null; items: IssueItem[]; edit_version: string; draft_revision_id?: string | null;
  has_unpublished_changes?: boolean; status?: string;
  article_metadata?: ArticleMetadata; curator?: EditorialCurator;
  public_revision_id?: string; reading_minutes?: number | null; related?: EditorialDirectory["related"];
  saved_at?: string | null; saved_by?: string; saved_revision?: number; body_source_problems?: Array<{block_id?:string;detail?:string}>;
  viewed_revision_id?: string; viewed_revision?: number; request_found?: boolean; applied_revision_id?: string; is_current_revision?: boolean;
  restore_revision_id?: string;
};
export type IssueSelection = {question:string;query:string;filters:Record<string,string|string[]|number>;references:IssueSourceReference[];materials?:Array<{target:IssueSourceReference;source:IssueResolvedSource|null;available:boolean;public_eligible:boolean}>};
export type ArticleMetadata = {
  kind: "article" | "research" | "exhibition"; keywords: string[]; topic_ids: string[]; theory_ids?: string[]; scholar_ids: string[]; reading_path_ids: string[];
  curator_role: string; curator_affiliation: string; curator_portrait_id: string | null; curator_account_id?: number | null;
};
export type EditorialCurator = { name: string; role: string; affiliation: string; portrait_url: string };
export type EditorialCard = Pick<RecommendationIssue, "id" | "slug" | "title" | "issue_label" | "introduction" | "public_byline" | "cover_url" | "published_at" | "display_from"> & {
  curator: EditorialCurator; article_metadata: ArticleMetadata; href: string; reading_minutes: number | null; reading_time_notice: string;
};
export type EditorialSearchParams = Record<string, string | string[] | undefined>;
export type EditorialDirectory = { count: number; page: number; page_size: number; total_pages: number; next: string | null; previous: string | null;
  results: EditorialCard[]; query: string;
  filters: { topic: string; theory?: string; kind: string; curator: string; sort: "newest" | "oldest" | "title"; year_from: number | null; year_to: number | null };
  facets: { theories?: { id: string; slug: string; name: string }[]; topics: { id: string; slug: string; name: string; href: string }[]; curators: string[]; years: number[]; kinds: { id: string; label: string }[] };
  related: { scholars: PublicScholarCard[]; materials: {id:string;title:string;authors:string;href:string;cover_url:string;cover_display_uses?:MediaDisplayUse[];article_href:string;source_status:string}[]; paths:{id:string;title:string;href:string}[]; notice:string };
};
export type IssuePage = { count: number; next: string | null; previous: string | null; results: RecommendationIssue[]; current: RecommendationIssue | null; summary?: { total: number; published: number; drafts: number; scheduled: number }; upcoming?: RecommendationIssue[] };
export type SiteContentDraft = { config: SiteConfig; about_blocks: AboutPageBlock[]; edit_version: string; has_unpublished_changes: boolean;
  home_layout: import("./home.types").HomeLayout; home_preview: import("./home.types").HomeLayoutPreview; site_id: string;
  history: {id:string;revision:number;state:string;saved_at:string;saved_by:string;published_at:string|null;published_by:string}[];
  receipt?: {request_id:string;actor_id:string;action:"save"|"publish"|"restore"|"cancelled";saved_version:string;created_at:string}; replayed?:boolean;
};
