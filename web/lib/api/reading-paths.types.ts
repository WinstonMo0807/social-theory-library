export type PathRevision = { id: string | null; token: string; number: number | null; published_at: string | null; change_note: string; legacy: boolean };
export type PathLink = { id: string; slug: string; title: string; href: string };
export type PathSubstitute = { work_id: string; edition_id: string; title: string; version_label: string; publication_year: number | null; authors: string[]; href: string; cover_url: string };
export type PathMaterial = {
  learning_goal?:string;
  dependencies?: {title?:string;item_id:string;kind:"learning_order"|"theory_related";reason:string}[];
  id: string; stage_id: string; kind: "work" | "chapter" | "paper" | "node"; title: string;
  work_id: string | null; edition_id: string | null; node_id: string | null; asset_id: string | null; document_revision_id: string | null;
  chapter_title: string; page_start: number | null; page_end: number | null; printed_page_label: string;
  version_label: string; authors: string[]; publication_year: number | null; cover_url: string; href: string | null; reader_url: string | null;
  source_status: "available" | "no_fulltext" | "unavailable" | "withdrawn" | "revision_changed";
  source_notice?: string; acquisition_status?: string; reason: string; prerequisite: string;
  is_required: boolean; position: number; reading_order: number; substitutes: PathSubstitute[];
};
export type PathStage = { id: string; name: string; description: string; position: number; estimated_reading: string; learning_questions: string[]; related_debates: PathLink[]; items: PathMaterial[] };
export type PublicReadingPath = {
  id: string; slug: string; title: string; introduction: string; learning_goal: string; audience: string; difficulty: string;
  estimated_reading: string; estimated_weeks: number | null; prerequisite: string; curator_note: string;
  credits: { name: string; role: string }[]; topics: PathLink[]; learning_questions: string[]; related_debates: PathLink[];
  revision: PathRevision; latest_revision: PathRevision; is_current_revision: boolean; versions: PathRevision[]; versions_truncated: boolean; stages: PathStage[]; items: PathMaterial[];
  counts: { stages: number; items: number; required: number; readable: number }; cover_url: string;
  cover_media?: unknown; next_paths?: PathLink[]; diff?: PathVersionDiff;
};
export type PathVersionDiff = { from_revision: PathRevision; to_revision: PathRevision } & Record<"added_items" | "removed_items" | "changed_items" | "added_stages" | "removed_stages" | "changed_stages", { id: string; title: string; source_status: string | null; change_note: string }[]>;
export type ReadingPathPage = { count: number; next: string | null; previous: string | null; results: PublicReadingPath[] };
export type ReadingPathSearchParams = Record<string, string | string[] | undefined>;
export type ReadingPathFilters = Record<string, string>;
export const readingPathFilterKeys = ["q", "topic", "discipline", "difficulty", "node", "page"] as const;
export const pathDifficultyLabels: Record<string, string> = { beginner: "初级", intermediate: "进阶", advanced: "深入" };
export function readingPathFilters(raw: ReadingPathSearchParams): ReadingPathFilters {
  return Object.fromEntries(readingPathFilterKeys.flatMap(key => { const value = raw[key], text = (Array.isArray(value) ? value[0] : value)?.trim(); return text ? [[key, text]] : []; }));
}
export function readingPathsHref(filters: ReadingPathFilters, patch: Record<string, string | number | null> = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries({ ...filters, ...patch })) if (value && readingPathFilterKeys.includes(key as typeof readingPathFilterKeys[number])) query.set(key, String(value));
  return `/theories/reading-paths${query.size ? `?${query}` : ""}`;
}
export function pathRevisionLabel(revision: PathRevision) { return revision.legacy ? "既有公开版" : revision.number ? `第 ${revision.number} 版` : "公开版"; }
export const readingPathHref = (path: Pick<PublicReadingPath, "slug">) => `/theories/reading-paths/${encodeURIComponent(path.slug)}`;

export type PathProgress = { status: "pending" | "reading" | "completed" | "skipped"; note: string };
export type PathFollowRecord = {
  id: string; revision: number; type: "path_follow" | "personal_plan"; path_id: string; path_slug: string; bookmarked: boolean;
  source_revision: PathRevision; latest_source_revision: PathRevision | null; source_status: "available" | "unavailable" | "revision_changed";
  path: PublicReadingPath | null; progress: Record<string, PathProgress>; completed_items: number; total_items: number;
  completed_stages: number; total_stages: number; updated_at: string; created_at: string;
  history: { from_revision?: string; to_revision?: string; upgraded_at?: string; [key: string]: unknown }[];
};
export type PathFollowReceipt = { request_id: string; applied_revision: number; deleted: boolean };
export type PathFollowResponse = { owner_id: string; record: PathFollowRecord | null; receipt: PathFollowReceipt | null };
export type PathUpgradePreview = { owner_id: string; record_id: string; expected_revision: number; source_revision: PathRevision; target_revision: PathRevision;
  diff: { added: string[]; removed: string[]; changed: string[]; unchanged: string[] }; retained_completed: string[]; retained_notes: string[] };
export type PathFollowCommand = { request_id: string } & (
  { action: "create"; path_id: string; expected_source_revision: string; bookmarked?: boolean }
  | { action: "bookmark"; id: string; expected_revision: number; bookmarked: boolean }
  | { action: "progress"; id: string; expected_revision: number; item_id: string; status: PathProgress["status"] }
  | { action: "note"; id: string; expected_revision: number; item_id: string; note: string }
  | { action: "copy-plan"; id: string; expected_revision: number; title?: string }
  | { action: "upgrade"; id: string; expected_revision: number; target_revision: string }
  | { action: "delete"; id: string; expected_revision: number }
);
