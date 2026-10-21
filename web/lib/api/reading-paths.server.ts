import { cache } from "react";
import { serverRequest } from "./server-request";
import { readingPathFilters, type PublicReadingPath, type ReadingPathPage, type ReadingPathSearchParams } from "./reading-paths.types";

export const loadPublicReadingPath = cache((slug: string, revision = "") => serverRequest<PublicReadingPath>(`/catalog/theory-system/reading-paths/${encodeURIComponent(slug)}/${revision ? `?${new URLSearchParams({ revision })}` : ""}`));
export function loadPublicReadingPaths(params: ReadingPathSearchParams) {
  const query = new URLSearchParams(readingPathFilters(params));
  return serverRequest<ReadingPathPage>(`/catalog/theory-system/reading-paths/${query.size ? `?${query}` : ""}`);
}
