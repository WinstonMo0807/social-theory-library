import type { PublicScholarDetail, ScholarPage, ScholarProfileSource } from "@/lib/api/scholars.types";

type Row = Record<string, unknown>;
const text = (value: unknown) => typeof value === "string" ? value : "";
const strings = (value: unknown): string[] => Array.isArray(value) ? value.filter((row): row is string => typeof row === "string").map(row => row.trim()).filter(Boolean) : typeof value === "string" ? value.split(/\r?\n/).map(row => row.trim()).filter(Boolean) : [];
const emptyPage = <T>(): ScholarPage<T> => ({ count: 0, page: 1, page_size: 12, total_pages: 0, next: null, previous: null, results: [] });
const safeUrl = (value: unknown) => { try { const url = new URL(text(value)); return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : ""; } catch { return ""; } };

export function scholarPreviewQuery(draft: Row): string {
  return new URLSearchParams({ featured_source_id: text(draft.featuredSourceId), reading_path_ids: strings(draft.readingPathIds).join(",") }).toString();
}

/** Form-only draft projection; it never upgrades free-text notes into verified public evidence. */
export function projectScholar(base: Row, draft: Row): PublicScholarDetail {
  const saved = base as Partial<PublicScholarDetail>, person = saved.person;
  const sourceRows = Array.isArray(draft.profileSources) ? draft.profileSources as ScholarProfileSource[] : [];
  const sources = sourceRows.map(row => ({ ...row, url: safeUrl(row.url) }));
  // Both selections are resolved by the protected preview endpoint, across all pages.
  const paths = saved.paths || emptyPage<PublicScholarDetail["paths"]["results"][number]>();
  const quote = saved.featured_quote;
  return {
    id: text(draft.id) || saved.id || "preview", person_id: text(draft.personId) || saved.person_id || "",
    slug: text(draft.slug), href: "", short_description: text(draft.description),
    person: { id: text(draft.personId) || person?.id || "", preferred_name: text(draft.name), original_name: text(draft.originalName),
      aliases: strings(draft.aliases), birth_year: draft.birthYear ? Number(draft.birthYear) : null, death_year: draft.deathYear ? Number(draft.deathYear) : null,
      biography: text(draft.biography), portrait: person?.portrait || "", portrait_media: person?.portrait_media || null },
    nationalities: strings(draft.nationalities), occupations: strings(draft.occupations), affiliations: strings(draft.affiliations), key_concerns: strings(draft.concerns),
    fields: saved.fields || [], schools: saved.schools || [], work_count: saved.work_count || 0, authored_work_count: saved.authored_work_count || 0,
    matched_alias: "", profile_state: text(draft.biography) ? "available" : "sparse", graph_href: "", research_href: "",
    public_revision: { token: "preview", id: null, number: null, published_at: null, change_note: "当前表单草稿，尚未公开。" }, period_notice: saved.period_notice || "",
    works: saved.works || emptyPage(), concepts: saved.concepts || emptyPage(), questions: saved.questions || emptyPage(),
    timeline: saved.timeline || emptyPage(), relations: saved.relations || emptyPage(), topics: saved.topics || emptyPage(),
    paths, sources: { ...emptyPage(), count: sources.length, results: sources }, evidence: saved.evidence || emptyPage(),
    featured_quote: quote?.source.public_eligible ? quote : null, disambiguation: [],
    candidate_access: { allowed: false, requested: false, notice: "候选与历史文字不在草稿预览中充当正式资料。", review_href: "" }, candidate_relations: null,
    counts: { works: saved.works?.count || 0, concepts: saved.concepts?.count || 0, questions: saved.questions?.count || 0, timeline: saved.timeline?.count || 0,
      relations: saved.relations?.count || 0, topics: saved.topics?.count || 0, paths: paths.count, sources: sources.length, evidence: saved.evidence?.count || 0 },
    filters: saved.filters || { section: "overview", role: [], relation_type: [], relation_direction: "all" },
    facets: saved.facets || { roles: [], relation_types: [] },
  };
}
