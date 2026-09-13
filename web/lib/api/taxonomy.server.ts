// Server-side public API domain. Browser components use pure adapters and type-only imports.
import type { Work } from "../data";
import { adaptApiWork as adaptWork } from "../public-data-adapters";
import { type Paginated, type DirectoryPage, directoryPage } from "./pagination";
import { serverRequest, allowDemoFallback } from "./server-request";
import type { Discipline, Subdiscipline } from "./taxonomy.types";

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
): Promise<DirectoryPage<Subdiscipline>> {
  try {
    const parameters = new URLSearchParams({ page: String(page) });
    if (discipline) parameters.set("discipline", discipline);
    if (query.trim()) parameters.set("q", query.trim());
    const payload = await serverRequest<Paginated<Subdiscipline>>(`/catalog/subdisciplines/?${parameters.toString()}`);
    return directoryPage(payload, page);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return directoryPage({ count: 0, results: [] }, page);
  }
}

export async function loadSubdisciplines(discipline = "", query = ""): Promise<Subdiscipline[]> {
  return (await loadSubdisciplinePage(discipline, query)).results;
}

export async function loadSubdiscipline(slug: string): Promise<(Omit<Subdiscipline, "works"> & { works: Work[] }) | null> {
  try {
    const payload = await serverRequest<Subdiscipline>(
      `/catalog/subdisciplines/${encodeURIComponent(slug)}/`,
    );
    return { ...payload, works: payload.works.map(adaptWork) };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return null;
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
