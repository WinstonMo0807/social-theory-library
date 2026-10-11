import type { KnowledgePreviewPayload } from "@/components/admin/preview/knowledge-page-preview";
import type { ApiWork } from "./public-catalog";
import type { RecommendationIssue } from "./recommendation-issues.types";

export type RecycleEntry = { id: string; kind: string; object_id: string; name: string; deleted_at: string; reason: string; thumbnail_url?: string; subtitle?: string; display_warning?: string };
export type RecycleCollection = { count: number; total_count: number; kind_counts: Record<string, number>; results: RecycleEntry[] };
export type RecyclePreview = { entry: RecycleEntry; can_restore: boolean; blocked_reason: string; detail: string } & (
  { preview_kind: "work"; preview: { work: ApiWork } }
  | { preview_kind: "knowledge"; preview: KnowledgePreviewPayload }
  | { preview_kind: "issue"; preview: RecommendationIssue }
  | { preview_kind: "record"; preview: { message: string; name: string; kind: string } }
);
