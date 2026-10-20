// Server-side public API domain. Browser components use pure adapters and type-only imports.
import type { Work } from "../data";
import { adaptApiWork as adaptWork } from "../public-data-adapters";
import { type Paginated, type DirectoryPage, directoryPage } from "./pagination";
import { serverRequest, allowDemoFallback, ServerApiError } from "./server-request";
import type { Discipline, Subdiscipline, SubdisciplineListItem } from "./taxonomy.types";

export class SubdisciplineWorksPageError extends Error {
  constructor(readonly reason: "invalid" | "out_of_range") {
    super(reason === "invalid" ? "Invalid subdiscipline works page" : "Subdiscipline works page out of range");
    this.name = "SubdisciplineWorksPageError";
  }
}

export async function loadDisciplines(): Promise<Discipline[]> {
  try {
    const payload = await serverRequest<Paginated<Discipline>>("/catalog/disciplines/");
    return payload.results;
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return [];
  }
}

export async function loadSubdisciplinePage(
  discipline = "",
  query = "",
  page = 1,
  options: { featured?: boolean } = {},
): Promise<DirectoryPage<SubdisciplineListItem>> {
  const parameters = new URLSearchParams({ page: String(page) });
  if (discipline) parameters.set("discipline", discipline);
  if (query.trim()) parameters.set("q", query.trim());
  if (options.featured !== undefined) parameters.set("featured", String(options.featured));
  const payload = await serverRequest<Paginated<SubdisciplineListItem>>(`/catalog/subdisciplines/?${parameters.toString()}`);
  return directoryPage(payload, page);
}

export async function loadSubdisciplines(discipline = "", query = ""): Promise<SubdisciplineListItem[]> {
  return (await loadSubdisciplinePage(discipline, query)).results;
}

export async function loadSubdiscipline(slug: string, worksPage: string | number = 1): Promise<(Omit<Subdiscipline, "works"> & { works: Work[] }) | null> {
  const path = `/catalog/subdisciplines/${encodeURIComponent(slug)}/`;
  const paginationQuery = String(worksPage) === "1" ? "" : `?${new URLSearchParams({ works_page: String(worksPage) })}`;
  try {
    const payload = await serverRequest<Subdiscipline>(`${path}${paginationQuery}`);
    return { ...payload, works: payload.works.map(adaptWork) };
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 400 && paginationQuery) {
      throw new SubdisciplineWorksPageError("invalid");
    }
    if (error instanceof ServerApiError && error.status === 404) {
      if (!paginationQuery) return null;
      // A paginated 404 may mean either a missing entity or a page that no
      // longer exists. Recheck only this failure, without guessing from HTML.
      try {
        await serverRequest<Subdiscipline>(path);
      } catch (firstPageError) {
        if (firstPageError instanceof ServerApiError && firstPageError.status === 404) return null;
        throw firstPageError;
      }
      throw new SubdisciplineWorksPageError("out_of_range");
    }
    throw error;
  }
}

export async function loadKnowledgeMatrix(): Promise<{
  disciplines: Discipline[];
  entry_modes: { key: string; title: string; description: string; href: string }[];
  counts: { disciplines: number; theories: number; subdisciplines: number; topics: number };
}> {
  try {
    return await serverRequest<{
      disciplines: Discipline[];
      entry_modes: { key: string; title: string; description: string; href: string }[];
      counts: { disciplines: number; theories: number; subdisciplines: number; topics: number };
    }>("/catalog/knowledge-matrix/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      disciplines: [],
      entry_modes: [],
      counts: { disciplines: 0, theories: 0, subdisciplines: 0, topics: 0 },
    };
  }
}
