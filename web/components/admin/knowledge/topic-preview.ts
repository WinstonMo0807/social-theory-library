import type { PublicTopicDetail, TopicPage } from "@/lib/api/topics.types";
import { topicCuration, type TopicCurationFields } from "./topic-fields";

type Row = Record<string, unknown>;
const text = (value: unknown) => typeof value === "string" ? value : "";
const lines = (value: unknown): string[] => typeof value === "string" ? value.split(/\r?\n/).map(row => row.trim()).filter(Boolean) : Array.isArray(value) ? value.filter((row): row is string => typeof row === "string") : [];
const emptyPage = <T>(): TopicPage<T> => ({ count: 0, page: 1, page_size: 12, total_pages: 0, next: null, previous: null, results: [] });

export function topicPreviewBody(draft: TopicCurationFields): string {
  return JSON.stringify({ curation: topicCuration(draft), parent: draft.parentId || null });
}

/** Local prose plus the server's exact selected identities; no guessed public associations. */
export function projectTopic(base: Row, draft: Row): PublicTopicDetail {
  const saved = base as Partial<PublicTopicDetail>;
  return {
    ...saved, id: text(draft.id) || "preview", slug: text(draft.slug) || "draft-preview", name: text(draft.name), href: "",
    description: text(draft.description), problem_statement: text(draft.problemStatement), hero_image: saved.hero_image || "",
    tags: lines(draft.terms), matched_alias: "", parent: saved.parent || null, breadcrumbs: saved.breadcrumbs || [], children: saved.children || [],
    work_count: saved.work_count || 0, edition_count: saved.edition_count || 0, scholar_count: saved.scholar_count || 0, question_count: saved.question_count || 0,
    profile_state: text(draft.description) ? "available" : "sparse",
    public_revision: { token: "preview", id: null, number: null, published_at: null, change_note: "当前表单草稿，尚未公开。" },
    introduction: { description: text(draft.description), problem_statement: text(draft.problemStatement), formation_context: text(draft.formationContext),
      core_questions: lines(draft.coreQuestions), research_dimensions: lines(draft.researchDimensions), methods: lines(draft.methods) },
    questions: saved.questions || emptyPage(), works: saved.works || emptyPage(), scholars: saved.scholars || emptyPage(),
    concepts: saved.concepts || emptyPage(), articles: saved.articles || emptyPage(), paths: saved.paths || emptyPage(), evidence: saved.evidence || emptyPage(),
    counts: saved.counts || { questions: 0, works: 0, scholars: 0, concepts: 0, articles: 0, paths: 0, evidence: 0 },
    featured_quote: saved.featured_quote || null, unavailable_links: saved.unavailable_links || [], unavailable_notice: saved.unavailable_notice || "",
    discussion_notice: saved.discussion_notice || "", feedback_href: "", graph_href: "", research_href: "",
    filters: saved.filters || { section: "overview", question_type: "all", availability: "all", reading: "all", sort: "relevance" },
    work_facets: saved.work_facets || { all: 0, readable: 0, no_fulltext: 0, planned: 0 },
    legacy: { ...saved.legacy, timeline: lines(draft.timeline).map(line => { const [year = "", title = "", description = ""] = line.split(/[｜|]/); return { year, title, description }; }),
      research_dimensions: lines(draft.researchDimensions), methods: lines(draft.methods), subdisciplines: saved.legacy?.subdisciplines || [],
      linked_theories: saved.legacy?.linked_theories || [], theory_nodes: saved.legacy?.theory_nodes || [],
      curated_works: saved.legacy?.curated_works || { foundational: [], recent: [] }, reading_paths: saved.legacy?.reading_paths || [],
      related_scholars: saved.legacy?.related_scholars || [] },
  };
}
