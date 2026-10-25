import type { Metadata } from "next";
import ExplorePage from "../page";
import { CatalogSearchWorkspace } from "@/components/catalog-search-workspace";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = { title: "原文检索" };

type SearchParams = Record<string, string | string[] | undefined>;

export default async function OriginalSearchPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  // Existing category links retain the global result groups; the atlas catalog
  // entry uses one row per Work with its actual published editions.
  if (params.type && params.type !== "catalog") return <ExplorePage searchParams={Promise.resolve({ ...params, mode: "exact" })} />;
  const query = new URLSearchParams();
  for (const [name, values] of Object.entries(params)) for (const value of Array.isArray(values) ? values : values ? [values] : []) query.append(name, value);
  return <><CatalogSearchWorkspace queryString={query.toString()} /><SiteFooter reference="catalog" /></>;
}
