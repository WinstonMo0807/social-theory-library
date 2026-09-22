import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { DiscoverySearchWorkspace } from "@/components/discovery-search-workspace";
import type { DiscoveryFilters } from "@/lib/api/discovery.types";

export const metadata: Metadata = { title: "观点检索" };

export default async function OpinionSearchPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const first = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] || "" : value || "";
  const query = first(params.q).trim();
  const filters: DiscoveryFilters = {};
  for (const name of ["document_type", "source_type", "scholar", "author", "theory", "topic", "concept", "language", "year", "year_min", "year_max", "work_id", "access"]) {
    if (params[name]) filters[name] = params[name]!;
  }
  if (!filters.work_id && params.work) filters.work_id = params.work;
  return <>
    <DiscoverySearchWorkspace key={JSON.stringify([query, filters])} initialQuery={query} initialFilters={filters} legacyRelation={Boolean(params.relation)} />
    <SiteFooter />
  </>;
}
