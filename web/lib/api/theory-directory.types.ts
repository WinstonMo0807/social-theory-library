import type { components } from "./generated/schema";
export const theoryDirectoryKinds = [
  "theory_tradition", "subdiscipline", "concept", "debate", "research_problem",
] as const;
export type TheoryDirectoryKind = typeof theoryDirectoryKinds[number];
export const theoryDirectoryLabels: Record<TheoryDirectoryKind, string> = {
  theory_tradition: "理论传统", subdiscipline: "研究领域", concept: "概念",
  debate: "关键争论", research_problem: "研究问题",
};

export type TheoryDirectoryReference = {
  id: string;
  name: string;
  slug: string;
  kind: TheoryDirectoryKind;
  href: string;
};
export type TheoryDirectoryItem = TheoryDirectoryReference & {
  summary: string;
  cover_url: string;
  parent_id: string | null;
  child_count: number;
};
export type TheoryDirectoryResponse = {
  disciplines: { id: string; name: string; slug: string }[];
  kind: TheoryDirectoryKind;
  discipline: string | null;
  parent: TheoryDirectoryReference | null;
  breadcrumbs: TheoryDirectoryReference[];
  hierarchy_truncated?: boolean;
  count: number;
  page: number;
  total_pages: number;
  groups: {
    id: string | null;
    title: string;
    parent: TheoryDirectoryReference | null;
    items: TheoryDirectoryItem[];
  }[];
};
export type TheoryDirectoryFilters = {
  type: TheoryDirectoryKind;
  discipline: string;
  parent: string;
  q: string;
  page: number;
  selected: string;
};
export type TheoryDirectorySelection = TheoryDirectoryReference & {
  foreign_name: string;
  summary: string;
  period_label: string;
  scholars: { id: string; name: string; original_name: string; href: string; portrait_url: string; portrait_media?: components["schemas"]["PublicCoverMedia"] | null }[];
  concepts: { id: string; name: string; href: string }[];
  source_href: string | null;
  source_title: string;
  source_kind: "evidence" | "work" | null;
};
export type TheoryDirectorySelectionState =
  | { status: "none" }
  | { status: "available"; data: TheoryDirectorySelection }
  | { status: "unavailable" }
  | { status: "error" };
export type TheoryDirectoryFailure = "unavailable" | "invalid" | "error" | null;

export function theoryDirectoryHref(
  filters: TheoryDirectoryFilters,
  changes: Partial<TheoryDirectoryFilters> = {},
) {
  const values = { ...filters, ...changes };
  const query = new URLSearchParams({ type: values.type });
  for (const key of ["discipline", "parent", "q", "selected"] as const) {
    if (values[key]) query.set(key, values[key]);
  }
  if (values.page > 1) query.set("page", String(values.page));
  return `/theories/directory?${query}`;
}
