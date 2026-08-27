import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  ScholarSectionPublicView,
  scholarSectionTitles,
} from "@/components/public/scholar-section-public-view";
import { loadScholar, loadTheorySchools } from "@/lib/server-api";

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
}: {
  params: Promise<{ slug: string; section: string }>;
}) {
  const { slug, section } = await params;
  if (!scholarSectionTitles[section]) notFound();
  const [data, schools] = await Promise.all([loadScholar(slug), loadTheorySchools()]);
  if (!data) notFound();
  return <ScholarSectionPublicView data={data} schools={schools} section={section} slug={slug} />;
}
