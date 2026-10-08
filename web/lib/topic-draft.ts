const fields = {
  name: "name", slug: "slug", description: "description",
  problem_statement: "problemStatement", core_questions: "coreQuestions",
  research_dimensions: "researchDimensions", methods: "methods",
  formation_context: "formationContext", key_concepts: "terms", timeline: "timeline",
} as const;

const curatedFields = {
  hero_caption: "heroCaption", foundational_work_ids: "primaryWorkIds",
  recent_work_ids: "secondaryWorkIds", related_scholar_ids: "scholarIds",
  linked_theory_ids: "theoryIds", reading_paths: "readingPaths",
} as const;

type TrackedField = (typeof fields)[keyof typeof fields]
  | (typeof curatedFields)[keyof typeof curatedFields]
  | "featuredPassageIds" | "baseCuration" | "status";
type TopicDraft = Partial<Record<TrackedField, unknown>>;

const different = (left: unknown, right: unknown) => JSON.stringify(left) !== JSON.stringify(right);

/** A form's normalized labels/defaults must not rewrite fields the user left alone. */
export function buildTopicSavePayload(
  body: Record<string, unknown>, draft: TopicDraft, baseline?: TopicDraft | null,
): Record<string, unknown> {
  if (!baseline) return body;
  const patch: Record<string, unknown> = {};
  for (const [field, source] of Object.entries(fields)) {
    if (different(draft[source], baseline[source])) patch[field] = body[field];
  }
  if (different(body.editorial_status, baseline.status)) patch.editorial_status = body.editorial_status;

  const proposed = (body.curation ?? {}) as Record<string, unknown>;
  const curation = { ...((draft.baseCuration ?? {}) as Record<string, unknown>) };
  let curationChanged = false;
  for (const [field, source] of Object.entries(curatedFields)) {
    if (!different(draft[source], baseline[source])) continue;
    curation[field] = proposed[field];
    curationChanged = true;
  }
  if (different(draft.featuredPassageIds, baseline.featuredPassageIds)) {
    for (const field of ["featured_passage_id", "featured_passage_reason", "featured_passage_evidence"]) {
      curation[field] = proposed[field];
    }
    curationChanged = true;
  }
  if (curationChanged) patch.curation = curation;
  return patch;
}
