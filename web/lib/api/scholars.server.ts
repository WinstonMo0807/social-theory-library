import { serverRequest, ServerApiError } from "./server-request";
import { scholarQuery } from "./scholars.params";
import type { PublicScholarDetail, PublicScholarDirectory, ScholarSearchParams, ScholarSection } from "./scholars.types";

export function loadPublicScholars(params: ScholarSearchParams = {}) {
  const query = scholarQuery(params); query.delete("view"); query.delete("layout");
  return serverRequest<PublicScholarDirectory>(`/catalog/scholars/${query.size ? `?${query}` : ""}`);
}
export async function loadPublicScholar(slug: string, section: ScholarSection = "overview", params: ScholarSearchParams = {}) {
  const query = scholarQuery(params, { section }); query.delete("view"); query.delete("layout");
  try { return await serverRequest<PublicScholarDetail>(`/catalog/scholars/${encodeURIComponent(slug)}/?${query}`, { forwardSession: true }); }
  catch (error) { if (error instanceof ServerApiError && error.status === 404) return null; throw error; }
}
