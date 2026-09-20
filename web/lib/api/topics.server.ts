// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { topic as demoTopic, works as demoWorks, scholars as demoScholars, theorySchools as demoTheorySchools } from "../data";
import { adaptApiTopic } from "../public-data-adapters";
import { type DirectoryPage, type Paginated, directoryPage } from "./pagination";
import { serverRequest, allowDemoFallback, ServerApiError } from "./server-request";
import type { LibraryTopic, ApiTopic } from "./topics.types";
import type { PublishedEvidenceCuration } from "./evidence-curation.types";

const adaptTopic = adaptApiTopic;

export async function loadTopics(
  query = "",
  filters: { discipline?: string; subdiscipline?: string; theory?: string; sort?: "name" | "works" } = {},
): Promise<LibraryTopic[]> {
  return (await loadTopicPage(query, filters)).results;
}

export async function loadTopicPage(
  query = "",
  filters: { discipline?: string; subdiscipline?: string; theory?: string; sort?: "name" | "works" } = {},
  page = 1,
): Promise<DirectoryPage<LibraryTopic>> {
  try {
    const parameters = new URLSearchParams();
    parameters.set("page", String(page));
    if (query) parameters.set("q", query);
    if (filters.discipline) parameters.set("discipline", filters.discipline);
    if (filters.subdiscipline) parameters.set("subdiscipline", filters.subdiscipline);
    if (filters.theory) parameters.set("theory", filters.theory);
    if (filters.sort) parameters.set("sort", filters.sort);
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<ApiTopic>>(`/catalog/topics/${suffix}`);
    return directoryPage(
      { ...payload, results: payload.results.map(adaptTopic) },
      page,
    );
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const results = [{
      ...demoTopic,
      id: demoTopic.slug,
      problemStatement: demoTopic.description,
      coreQuestions: [],
      researchDimensions: [],
      methods: [],
      formationContext: "",
      heroImage: "",
      disciplines: [],
      subdisciplines: [],
      linkedTheories: [],
      knowledgeNodes: [],
      works: demoWorks.slice(0, 3),
      scholars: demoScholars.slice(0, 4),
      theories: demoTheorySchools.slice(0, 5),
      passages: [],
      workCount: demoWorks.length,
      curated: {
        heroCaption: "",
        foundationalWorks: [],
        recentWorks: [],
        relatedScholars: [],
        linkedTheories: [],
        readingPaths: [],
        featuredPassageId: "",
        featuredPassageReason: "",
        featuredPassageEvidence: {},
      },
      curatedClaims: {
        core_viewpoint: [],
        major_criticism: [],
        major_response: [],
      },
    }];
    return directoryPage({ count: results.length, results }, page);
  }
}

export async function loadTopic(slug: string): Promise<LibraryTopic | null> {
  try {
    const payload = await serverRequest<ApiTopic>(`/catalog/topics/${encodeURIComponent(slug)}/`);
    const evidenceCuration = await serverRequest<PublishedEvidenceCuration>(`/catalog/evidence-curation/topic/${payload.id}/`);
    return { ...adaptTopic(payload), evidenceCuration };
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404 && error.path === `/catalog/topics/${encodeURIComponent(slug)}/`) return null;
    if (!allowDemoFallback) throw error;
    return slug === demoTopic.slug
      ? {
          ...demoTopic,
          id: demoTopic.slug,
          problemStatement: demoTopic.description,
          coreQuestions: [],
          researchDimensions: [],
          methods: [],
          formationContext: "",
          heroImage: "",
          disciplines: [],
          subdisciplines: [],
          linkedTheories: [],
          knowledgeNodes: [],
          works: demoWorks.slice(0, 6),
          scholars: demoScholars.slice(0, 4),
          theories: demoTheorySchools.slice(0, 5),
          passages: [],
          workCount: demoWorks.length,
          curated: {
            heroCaption: "",
            foundationalWorks: [],
            recentWorks: [],
            relatedScholars: [],
            linkedTheories: [],
            readingPaths: [],
            featuredPassageId: "",
            featuredPassageReason: "",
            featuredPassageEvidence: {},
          },
          curatedClaims: {
            core_viewpoint: [],
            major_criticism: [],
            major_response: [],
          },
        }
      : null;
  }
}
