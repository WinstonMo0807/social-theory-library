import { requireReaderSession } from "@/lib/reader-access.server";
import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { redirect } from "next/navigation";
import { OpinionSearchEntry } from "@/components/opinion-search-entry";
import { opinionFilterKeys } from "@/lib/api/opinion-entry.client";
import type { DiscoveryFilters } from "@/lib/api/discovery.types";

export const metadata: Metadata = { title: "观点检索" };

export default async function OpinionSearchPage({ searchParams }: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  await requireReaderSession(`/explore/opinions`, params);
  const first = (value: string | string[] | undefined) => Array.isArray(value) ? value[0] || "" : value || "";
  const query = first(params.q).trim();
  if (query) {
    const preserved = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) for (const part of Array.isArray(value) ? value : value === undefined ? [] : [value]) preserved.append(key, part);
    redirect(`/explore/evidence?${preserved}`);
  }
  const filters: DiscoveryFilters = {};
  for (const name of opinionFilterKeys) {
    if (params[name]) filters[name] = params[name]!;
  }
  return <>
    <OpinionSearchEntry key={JSON.stringify(filters)} initialFilters={filters} />
    <SiteFooter reference="opinion" />
  </>;
}
