// Legacy card consumers share the same formal scholar endpoints as the new directory.
import type { Scholar } from "../data";
import { adaptApiScholar } from "../public-data-adapters";
import { type DirectoryPage, directoryPage } from "./pagination";
import type { PublicScholarDetail, PublicScholarDirectory } from "./scholars.types";
import { serverRequest, ServerApiError } from "./server-request";

export async function loadScholarPage(query = "", page = 1): Promise<DirectoryPage<Scholar>> {
  const parameters = new URLSearchParams({ page: String(page) });
  if (query) parameters.set("q", query);
  const payload = await serverRequest<PublicScholarDirectory>(`/catalog/scholars/?${parameters}`);
  return directoryPage({ ...payload, results: payload.results.map(adaptApiScholar) }, page);
}
export async function loadScholars(query = ""): Promise<Scholar[]> {
  return (await loadScholarPage(query)).results;
}
export async function loadScholar(slug: string) {
  const path = `/catalog/scholars/${encodeURIComponent(slug)}/`;
  try {
    const payload = await serverRequest<PublicScholarDetail>(path);
    return { profileId: payload.id, scholar: adaptApiScholar(payload) };
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404 && error.path === path) return null;
    throw error;
  }
}
