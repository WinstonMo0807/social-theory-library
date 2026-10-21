import type { NormalizedKnowledgeRelation, NormalizedTimelineEvent, TheoryWorkCompact } from "./knowledge.types";

export type TimelineTopic = { id: string; name: string; slug: string; href: string };
export type TimelineAuthor = TimelineTopic & { person_id: string; portrait_url: string };
export type TimelineSource = {
  asset_id: string; edition_id: string; work_id: string; document_revision_id: string;
  title: string; edition_label: string; pdf_page: number; printed_page_label: string;
  quote: string; reader_href: string;
};
export type TimelineEvent = Omit<NormalizedTimelineEvent, "relations"> & {
  origin_kind: "timeline_event";
  date_precision: "unknown" | "year" | "approximate" | "range";
  subject_edition: (TheoryWorkCompact & { version_label: string }) | null;
  subject_status: "available" | "unavailable" | "unspecified";
  subject_work: { id: string; title: string; detail_href: string | null } | null;
  image_url: string;
  scholars: TimelineAuthor[];
  topics: TimelineTopic[];
  source_status: "available" | "unavailable" | "citation_only" | "missing";
  evidence_source: TimelineSource | null;
  relations: (NormalizedTimelineEvent["relations"][number] & { href?: string | null; node_type?: string | null; description?: string })[];
};
export type TimelineEventDetail = TimelineEvent & {
  related_events: TimelineEvent[]; related_count: number;
  knowledge_relations: NormalizedKnowledgeRelation[]; knowledge_relation_count: number;
};
export type TimelinePage = {
  count: number; next: string | null; previous: string | null; results: TimelineEvent[];
  page: number; page_size: number; total_pages: number; scope_count: number;
  year_groups: { year: number | null; count: number; event_types: { event_type: string; count: number }[] }[];
  bounds: { min_year: number | null; max_year: number | null; undated_count: number };
  focus_id: string | null; selected_topics: TimelineTopic[]; selected_authors: TimelineAuthor[];
};
export type TimelineSearchParams = Record<string, string | string[] | undefined>;
export type TimelineFilters = Record<string, string>;
export const timelineFilterKeys = ["discipline", "node", "topic", "author", "event_type", "sort", "q", "year_from", "year_to", "year", "focus", "page", "has_collection", "related_to"] as const;
export const timelineViewKeys = ["scale", "window_start", "view"] as const;

export function timelineFilters(params: TimelineSearchParams): TimelineFilters {
  return Object.fromEntries([...timelineFilterKeys, ...timelineViewKeys].flatMap(key => {
    const raw = params[key];
    const value = ["topic", "author", "event_type"].includes(key)
      ? [...new Set((Array.isArray(raw) ? raw : [raw || ""]).flatMap(item => item.split(",")).map(item => item.trim()).filter(Boolean))].join(",")
      : (Array.isArray(raw) ? raw[0] : raw)?.trim() || "";
    return value ? [[key, value]] : [];
  }));
}

export function timelineHref(path: string, filters: TimelineFilters, changes: Record<string, string | number | null | undefined> = {}) {
  const next = { ...filters, ...changes };
  const params = new URLSearchParams();
  for (const key of [...timelineFilterKeys, ...timelineViewKeys]) {
    const value = next[key];
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  return `${path}${params.size ? `?${params}` : ""}`;
}

export function timelineDate(event: Pick<NormalizedTimelineEvent, "date_label" | "start_year" | "end_year" | "date_precision">) {
  if (event.date_label) return event.date_label;
  const from = event.start_year, to = event.end_year;
  const year = from ?? to;
  if (year === null) return "时间未详";
  if (event.date_precision === "range" && from !== null && to !== null) return `${from}—${to} 年`;
  if (event.date_precision === "approximate") return `约 ${year} 年`;
  if (event.date_precision === "unknown") return `${year} 年（时间待确认）`;
  return `${year} 年`;
}

export const timelineTypeLabels: Record<string, string> = {
  publication: "作品出版", concept_proposed: "概念使用", translation: "译本出版",
  scholar: "学者生平", school_formation: "学派形成", institution: "学术机构",
  debate: "学术争论", theoretical_turn: "理论转向", china_reception: "学术传播",
  institutionalization: "学科制度化", formation: "形成", development: "发展",
};
