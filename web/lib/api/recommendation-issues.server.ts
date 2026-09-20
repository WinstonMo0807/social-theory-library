import { serverRequest } from "./server-request";
import type { IssuePage, RecommendationIssue } from "./recommendation-issues.types";

export function loadRecommendationIssues(query = "", page = 1) {
  return serverRequest<IssuePage>(`/catalog/recommendation-issues/?${new URLSearchParams({ q: query, page: String(page) })}`);
}

export function loadRecommendationIssue(slug: string) {
  return serverRequest<RecommendationIssue>(`/catalog/recommendation-issues/${encodeURIComponent(slug)}/`);
}
