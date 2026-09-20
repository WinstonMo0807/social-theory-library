// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { type TheorySchool, theorySchools as demoTheorySchools, type Work, type Scholar, works as demoWorks, scholars as demoScholars } from "../data";
import { adaptApiWork as adaptWork, adaptApiScholar as adaptScholar } from "../public-data-adapters";
import { type Paginated, type DirectoryPage, directoryPage } from "./pagination";
import { serverRequest, allowDemoFallback, ServerApiError } from "./server-request";
import type { TheoryTimelineEvent, TheoryGraph, TheoryDirectoryFilters, ApiTheorySchool } from "./theories.types";

export async function loadTheoryTimeline(discipline = ""): Promise<TheoryTimelineEvent[]> {
  try {
    const query = discipline ? `?discipline=${encodeURIComponent(discipline)}` : "";
    const payload = await serverRequest<Paginated<TheoryTimelineEvent>>(`/catalog/theory-timeline/${query}`);
    return payload.results;
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return [];
  }
}

export async function loadTheoryGraph(discipline = ""): Promise<TheoryGraph> {
  try {
    const query = discipline ? `?discipline=${encodeURIComponent(discipline)}` : "";
    return await serverRequest<TheoryGraph>(`/catalog/theory-graph/${query}`);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return { nodes: [], edges: [] };
  }
}

export async function loadTheorySchools(
  query = "",
  filters: TheoryDirectoryFilters = {},
): Promise<TheorySchool[]> {
  return (await loadTheorySchoolPage(query, filters)).results;
}

export async function loadTheorySchoolPage(
  query = "",
  filters: TheoryDirectoryFilters = {},
  page = 1,
): Promise<DirectoryPage<TheorySchool>> {
  try {
    const parameters = new URLSearchParams();
    parameters.set("page", String(page));
    if (query) parameters.set("q", query);
    if (filters.theme) parameters.set("theme", filters.theme);
    if (filters.discipline) parameters.set("discipline", filters.discipline);
    if (filters.hasWorks) parameters.set("has_works", "true");
    if (filters.hasScholars) parameters.set("has_scholars", "true");
    if (filters.sort && filters.sort !== "name") parameters.set("sort", filters.sort);
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<ApiTheorySchool>>(`/catalog/theory-schools/${suffix}`);
    const results = payload.results.map((school, index) => ({
      slug: school.slug,
      name: school.name,
      description: school.description || "馆藏关联理论流派",
      books: school.work_count,
      scholars: school.scholar_count,
      symbol: school.symbol || school.name.slice(0, 2) || String(index + 1),
    }));
    return directoryPage({ ...payload, results }, page);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return directoryPage({ count: demoTheorySchools.length, results: demoTheorySchools }, page);
  }
}

export async function loadTheoryEntity(slug: string): Promise<ApiTheorySchool | null> {
  try {
    return await serverRequest<ApiTheorySchool>(
      `/catalog/theory-schools/${encodeURIComponent(slug)}/`,
    );
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) return null;
    if (!allowDemoFallback) throw error;
    return null;
  }
}

export async function loadTheorySchool(slug: string): Promise<{
  school: TheorySchool;
  works: Work[];
  scholars: Scholar[];
  keyThemes: string[];
  curated: {
    heroCaption: string;
    foundationalWorks: Work[];
    curatedReadingWorks: Work[];
    keyScholars: { id: string; name: string; slug: string }[];
    neighbors: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      relation?: string;
      source?: string;
    }[];
    coreConcepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    conceptualMap: Array<{
      source?: string;
      target?: string;
      relation?: string;
      description?: string;
      label?: string;
    } | string>;
  };
} | null> {
  try {
    const payload = await serverRequest<ApiTheorySchool>(
      `/catalog/theory-schools/${encodeURIComponent(slug)}/`,
    );
    return {
      school: {
        slug: payload.slug,
        name: payload.name,
        description: payload.description,
        books: payload.work_count,
        scholars: payload.scholars?.length ?? 0,
        symbol: payload.symbol || payload.name.slice(0, 2),
      },
      works: (payload.works ?? []).map(adaptWork),
      scholars: (payload.scholars ?? []).map(adaptScholar),
      keyThemes: payload.key_themes ?? [],
      curated: {
        heroCaption: payload.curated?.hero_caption ?? "",
        foundationalWorks: (payload.curated?.foundational_works ?? []).map(adaptWork),
        curatedReadingWorks: (payload.curated?.curated_reading_works ?? []).map(adaptWork),
        keyScholars: payload.curated?.key_scholars ?? [],
        neighbors: payload.curated?.neighbors ?? [],
        coreConcepts: payload.curated?.core_concepts ?? [],
        conceptualMap: payload.curated?.conceptual_map ?? [],
      },
    };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const school = demoTheorySchools.find((item) => item.slug === slug);
    return school
      ? {
          school,
          works: demoWorks.filter((work) => work.school.includes(school.name.slice(0, 2))),
          scholars: demoScholars.filter((scholar) => scholar.school === school.name),
          keyThemes: [],
          curated: {
            heroCaption: "",
            foundationalWorks: [],
            curatedReadingWorks: [],
            keyScholars: [],
            neighbors: [],
            coreConcepts: [],
            conceptualMap: [],
          },
        }
      : null;
  }
}
