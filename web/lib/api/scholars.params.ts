import type { ScholarSearchParams, ScholarSection } from "./scholars.types";

export const scholarSections: { id: ScholarSection; label: string; editor: string }[] = [
  { id: "overview", label: "概览", editor: "identity" }, { id: "works", label: "主要作品", editor: "works" },
  { id: "concepts", label: "核心概念", editor: "concepts" }, { id: "questions", label: "理论问题", editor: "questions" },
  { id: "timeline", label: "生平与时间线", editor: "timeline" }, { id: "relations", label: "相关争论与学者", editor: "network" },
  { id: "paths", label: "专题与阅读路径", editor: "paths" }, { id: "sources", label: "人物资料来源", editor: "sources" },
  { id: "evidence", label: "代表原文", editor: "passages" },
];
const aliases: Record<string, ScholarSection> = { network: "relations", biography: "sources", theories: "concepts", "concept-map": "concepts", "frequently-read": "relations", passages: "evidence", reading: "paths", "reading-paths": "paths", identity: "overview" };
export function scholarSection(value = "overview"): ScholarSection | null {
  return aliases[value] || (scholarSections.some(row => row.id === value) || value === "topics" ? value as ScholarSection : null);
}
export function scholarValues(params: ScholarSearchParams, name: string): string[] {
  const raw = params[name]; return [...new Set((Array.isArray(raw) ? raw : [raw || ""]).flatMap(value => value.split(",")).map(value => value.trim()).filter(Boolean))];
}
export function scholarValue(params: ScholarSearchParams, name: string) { const raw = params[name]; return (Array.isArray(raw) ? raw[0] : raw)?.trim() || ""; }
const keys = ["q", "field", "period", "school", "sort", "page", "page_size", "view", "layout", "section", "role", "relation_type", "relation_direction", "relation", "include_candidates"];
export function scholarQuery(params: ScholarSearchParams, changes: ScholarSearchParams = {}) {
  const next = { ...params, ...changes }, query = new URLSearchParams();
  for (const key of keys) for (const value of Array.isArray(next[key]) ? next[key] as string[] : [next[key] || ""]) if (value) query.append(key, value);
  return query;
}
export function scholarHref(path: string, params: ScholarSearchParams = {}, changes: ScholarSearchParams = {}) { const query = scholarQuery(params, changes); return `${path}${query.size ? `?${query}` : ""}`; }
export function scholarSectionHref(slug: string, section: ScholarSection) { return `/scholars/${encodeURIComponent(slug)}${section === "overview" ? "" : `/${section}`}`; }
export function scholarYears(person: { birth_year: number | null; death_year: number | null }) {
  if (person.birth_year !== null) return `${person.birth_year}${person.death_year !== null ? ` — ${person.death_year}` : " —"}`;
  return person.death_year !== null ? `卒于 ${person.death_year}` : "生卒年未详";
}
