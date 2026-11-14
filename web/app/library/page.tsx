import type { Metadata } from "next";
import { LibraryBrowse } from "@/components/public/library-browse";
import { SiteFooter } from "@/components/site-footer";
import { serverRequest, ServerApiError } from "@/lib/api/server-request";
import type { Paginated } from "@/lib/api/pagination";
import type { ApiWork } from "@/lib/api/public-catalog";
import { adaptApiWork } from "@/lib/public-data-adapters";
import { libraryApiQuery, libraryParams } from "@/lib/library-browse";

export const metadata: Metadata = { title: "书库" };
export default async function LibraryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const values = await searchParams, query = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (typeof value === "string") query.set(key, value);
  const params = libraryParams(query);
  let payload: Paginated<ApiWork> | null = null, error = "";
  try { payload = await serverRequest<Paginated<ApiWork>>(`/catalog/works/?${libraryApiQuery(params)}`); }
  catch (reason) { error = reason instanceof ServerApiError && reason.status === 404 ? "这一页当前没有书目，请返回第一页。" : "馆藏暂时无法读取，筛选条件已保留。"; }
  return <><LibraryBrowse queryString={params.toString()} works={payload?.results.map(adaptApiWork) ?? []} count={payload?.count ?? null} hasNext={Boolean(payload?.next)} error={error} /><SiteFooter /></>;
}
