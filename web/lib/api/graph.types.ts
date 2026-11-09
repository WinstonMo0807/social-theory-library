import type { components } from "./generated/schema";
import type { TheoryWorkCompact } from "./knowledge.types";

export type GraphKind = "knowledge_node" | "scholar" | "topic" | "subdiscipline";
export type GraphMode = "graph" | "list" | "topics" | "scholars" | "works";
export type GraphNode = {
  id: string; entity_id: string; kind: GraphKind; node_type: string; name: string; foreign_name: string;
  slug: string; href: string; summary: string; image_url: string; image_media?: components["schemas"]["PublicCoverMedia"] | null; period_label: string;
  start_year: number | null; end_year: number | null; is_center: boolean; depth: number;
};
export type GraphEvidence = {
  id: string; work_id: string; edition_id: string; asset_id: string; document_revision_id: string;
  title: string; edition_label: string; quote: string; pdf_page: number; printed_page_label: string; reader_href: string;
};
export type GraphEdge = {
  id: string; entity_id: string; model: string; source: string; target: string; relation_type: string; relation_label: string;
  direction: "directed" | "bidirectional" | "undirected"; description: string; evidence_source: string;
  status: string; evidence: GraphEvidence[]; evidence_truncated: boolean; conditions?: Record<string, string>; sources?: { work_id: string | null; work__title: string | null; document_revision_id: string | null; citation: string; attribution__label: string | null }[]; source_quality?: string; source_status: "login_required" | "available" | "citation_only" | "missing" | "unverified";
};
export type GraphViewState = {
  center_kind: GraphKind; center: string; depth: number; limit: number; edge_limit: number;
  node_type: string[]; relation_type: string[]; discipline: string; start_year: number | null; end_year: number | null;
  has_collection: boolean | null; selected_node: string; selected_edge: string; view_mode: GraphMode;
  zoom: number; offset: { x: number; y: number };
};
export type PublicTheoryGraph = {
  center: string | null; center_kind: GraphKind; nodes: GraphNode[]; edges: GraphEdge[];
  depth: number; limit: number; edge_limit: number; truncated: boolean; state: "empty" | "isolated" | "filtered" | "ready";
  counts: { nodes: number; edges: number; scholars: number; topics: number };
  filters: Pick<GraphViewState, "center_kind" | "center" | "depth" | "limit" | "edge_limit" | "relation_type" | "node_type" | "discipline" | "start_year" | "end_year" | "has_collection"> & { scope_note: string; include_candidates: boolean };
  relation_types: { value: string; label: string }[];
  candidate_access: { mode: string; can_review: boolean; review_href: string | null; detail: string };
  candidate_edges: GraphEdge[]; candidate_count: number | null; candidates_truncated: boolean;
  selected_node: string | null; related_works: (TheoryWorkCompact & { version_label: string })[]; related_works_count: number; related_works_truncated: boolean;
  related_works_page: number; related_works_page_size: number; related_works_total_pages: number;
};
export type GraphParams = Record<string, string>;
export type GraphSearchParams = Record<string, string | string[] | undefined>;
export const graphFilterKeys = ["center", "center_kind", "depth", "limit", "edge_limit", "node_type", "relation_type", "discipline", "start_year", "end_year", "has_collection", "selected_node", "works_page", "include_candidates", "source_work", "source_revision", "assertion_direction", "context"] as const;
export const graphViewKeys = ["selected_edge", "view", "zoom", "offset_x", "offset_y"] as const;
export const graphKindLabels: Record<GraphKind, string> = { knowledge_node: "理论与概念", scholar: "学者", topic: "主题", subdiscipline: "子学科" };
export const graphNodeLabels: Record<string, string> = { theory_tradition: "理论流派", concept: "核心概念", debate: "学术争论", research_problem: "研究问题", subdiscipline: "子学科" };
export function graphParams(params: GraphSearchParams): GraphParams {
  return Object.fromEntries([...graphFilterKeys, ...graphViewKeys].flatMap(key => {
    const raw = params[key];
    const value = ["node_type", "relation_type"].includes(key) ? [...new Set((Array.isArray(raw) ? raw : [raw || ""]).flatMap(item => item.split(",")).map(item => item.trim()).filter(Boolean))].join(",") : (Array.isArray(raw) ? raw[0] : raw)?.trim() || "";
    return value ? [[key, value]] : [];
  }));
}
export function graphHref(params: GraphParams, changes: Record<string, string | number | null | undefined> = {}) {
  const values = { ...params, ...changes }, query = new URLSearchParams();
  for (const key of [...graphFilterKeys, ...graphViewKeys]) if (values[key] !== undefined && values[key] !== null && values[key] !== "") query.set(key, String(values[key]));
  return `/theories/graph${query.size ? `?${query}` : ""}`;
}
export function graphParamsForView(view: GraphViewState): GraphParams {
  return graphParams({ ...Object.fromEntries(Object.entries(view).filter(([, value]) => value !== null && typeof value !== "object").map(([key, value]) => [key, String(value)])), node_type: view.node_type.join(","), relation_type: view.relation_type.join(","), view: view.view_mode, offset_x: String(view.offset.x), offset_y: String(view.offset.y) });
}
