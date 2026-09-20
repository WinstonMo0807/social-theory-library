import { serverRequest } from "./server-request";
import { directoryPage, type DirectoryPage, type Paginated } from "./pagination";
import type { ScholarRelation } from "./scholar-relations.types";

export async function loadScholarRelations(scholarId: string, page = 1): Promise<DirectoryPage<ScholarRelation>> {
  const payload = await serverRequest<Paginated<ScholarRelation>>(`/catalog/scholar-relations/?scholar=${encodeURIComponent(scholarId)}&page=${page}`);
  return directoryPage(payload,page);
}
