import { requireReaderSession } from "@/lib/reader-access.server";
import type { Metadata } from "next";
import { DiscoverySearchWorkspace } from "@/components/discovery-search-workspace";
import type { DiscoveryFilters } from "@/lib/api/discovery.types";
import { opinionFilterKeys } from "@/lib/api/opinion-entry.client";

export const metadata: Metadata = { title: "原文证据" };

export default async function EvidencePage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  await requireReaderSession(`/explore/evidence`, params);
  const first = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] || "" : value || "";
  const query = first(params.q).trim();
  const filters: DiscoveryFilters = {};
  for (const name of opinionFilterKeys) {
    if (params[name]) filters[name] = params[name]!;
  }
  if (!filters.work_id && params.work) filters.work_id = params.work;
  return <><DiscoverySearchWorkspace key={JSON.stringify([query, filters])} initialQuery={query} initialFilters={filters} legacyRelation={Boolean(params.relation)} /></>;
}
