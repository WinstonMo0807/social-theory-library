import type { TopicSearchParams, TopicSection } from "./topics.types";

export const topicSections: { id: TopicSection; label: string; editor: string }[] = [
  { id: "overview", label: "导读", editor: "identity" }, { id: "questions", label: "核心问题", editor: "questions" },
  { id: "works", label: "相关作品", editor: "works" }, { id: "scholars", label: "相关学者", editor: "scholars" },
  { id: "concepts", label: "核心概念", editor: "concepts" }, { id: "articles", label: "策划文章", editor: "articles" },
  { id: "paths", label: "研究路径", editor: "paths" }, { id: "evidence", label: "原文线索", editor: "passages" },
];
export const topicLegacySections = { history: "形成与发展", dimensions: "研究维度", methods: "研究方法", timeline: "概念时间线", subdisciplines: "相关子学科", "theory-schools": "关联理论流派" };
export type TopicViewSection = TopicSection | keyof typeof topicLegacySections;
const aliases: Record<string, TopicSection> = { identity: "overview", guide: "overview", recent: "works", "reading-paths": "paths", passages: "evidence", sources: "evidence", relations: "scholars" };
export function topicSection(value = "overview"): TopicViewSection | null { return Object.hasOwn(aliases, value) ? aliases[value] : topicSections.some(row => row.id === value) || Object.hasOwn(topicLegacySections, value) ? value as TopicViewSection : null; }
export function topicValue(params: TopicSearchParams, key: string) { const raw = params[key]; return (Array.isArray(raw) ? raw[0] : raw)?.trim() || ""; }
const keys = ["q", "search", "parent", "discipline", "subdiscipline", "theory", "sort", "page", "page_size", "view", "layout", "section", "question_type", "availability", "reading"];
export function topicQuery(params: TopicSearchParams, changes: TopicSearchParams = {}) { const next = { ...params, ...changes }, query = new URLSearchParams(); for (const key of keys) for (const value of Array.isArray(next[key]) ? next[key] as string[] : [next[key] || ""]) if (value) query.append(key, value); return query; }
export function topicHref(path: string, params: TopicSearchParams = {}, changes: TopicSearchParams = {}) { const query = topicQuery(params, changes); return `${path}${query.size ? `?${query}` : ""}`; }
export function topicSectionHref(slug: string, section: TopicViewSection) { return `/topics/${encodeURIComponent(slug)}${section === "overview" ? "" : `/${section}`}`; }
