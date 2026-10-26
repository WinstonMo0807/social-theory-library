import { serverRequest } from "./server-request";
import type { EditorialDirectory, EditorialSearchParams, IssuePage, RecommendationIssue } from "./recommendation-issues.types";

export function loadRecommendationIssues(query = "", page = 1) {
  return serverRequest<IssuePage>(`/catalog/recommendation-issues/?${new URLSearchParams({ q: query, page: String(page) })}`);
}

export function loadRecommendationIssue(slug: string) {
  return serverRequest<RecommendationIssue>(`/catalog/recommendation-issues/${encodeURIComponent(slug)}/`);
}

export function loadEditorialDirectory(params: EditorialSearchParams) {
  const query = new URLSearchParams({ view: "directory" });
  for (const key of ["q", "topic", "theory", "kind", "curator", "year_from", "year_to", "sort", "page", "page_size"]) {
    const value = params[key];
    if (value) query.set(key, Array.isArray(value) ? value[0] : value);
  }
  return serverRequest<EditorialDirectory>(`/catalog/recommendation-issues/?${query}`);
}
