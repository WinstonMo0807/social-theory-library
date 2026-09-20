import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  ScholarSectionPublicView,
  scholarSectionTitles,
} from "@/components/public/scholar-section-public-view";
import { loadScholar } from "@/lib/api/people.server";
import { loadTheorySchools } from "@/lib/api/theories.server";
import { loadScholarRelations } from "@/lib/api/scholar-relations.server";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { searchPage } from "@/lib/search-context";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; section: string }>;
}): Promise<Metadata> {
  const { slug, section } = await params;
  const data = await loadScholar(slug);
  return { title: data ? `${scholarSectionTitles[section] ?? "学者资料"} · ${data.scholar.name}` : "学者资料" };
}

export default async function ScholarSectionPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; section: string }>;
  searchParams: Promise<{page?: string;relation?:string}>;
}) {
  const { slug, section } = await params;
  if (!scholarSectionTitles[section]) notFound();
  const [data, schools] = await Promise.all([loadScholar(slug), loadTheorySchools()]);
  if (!data) notFound();
  const query = await searchParams;
  const page = searchPage(query.page);
  const relationPage = section === "network" && data.profileId ? await loadScholarRelations(data.profileId,page) : null;
  return <ScholarSectionPublicView data={data} schools={schools} section={section} slug={slug} relations={relationPage?.results} selectedRelationId={query.relation} relationPagination={relationPage ? <ScopedSearchPagination path={`/scholars/${slug}/network`} context="scholars" page={page} totalPages={relationPage.totalPages}/> : null} />;
}
