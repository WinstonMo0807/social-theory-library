import { serverRequest, ServerApiError } from "./server-request";
import { topicQuery, type TopicViewSection } from "./topics.params";
import type { PublicTopicDetail, TopicDirectory, TopicSearchParams } from "./topics.types";

export function loadTopicDirectory(params: TopicSearchParams = {}) {
  const query = topicQuery(params); query.delete("view"); query.delete("layout");
  return serverRequest<TopicDirectory>(`/catalog/topics/${query.size ? `?${query}` : ""}`);
}
export async function loadTopic(slug: string, section: TopicViewSection = "overview", params: TopicSearchParams = {}) {
  const query = topicQuery(params, { section: ["history", "dimensions", "methods", "timeline", "subdisciplines", "theory-schools"].includes(section) ? "overview" : section });
  query.delete("view"); query.delete("layout");
  try { return await serverRequest<PublicTopicDetail>(`/catalog/topics/${encodeURIComponent(slug)}/?${query}`); }
  catch (error) { if (error instanceof ServerApiError && error.status === 404) return null; throw error; }
}
export function loadTopicPage(query = "", filters: TopicSearchParams = {}, page = 1) { return loadTopicDirectory({ ...filters, q: query, page: String(page) }); }
export async function loadTopics(query = "", filters: TopicSearchParams = {}) { return (await loadTopicPage(query, filters)).results; }
