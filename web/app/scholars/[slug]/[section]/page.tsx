import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ScholarSectionPublicView, scholarSectionTitles } from "@/components/public/scholar-section-public-view";
import { ScholarLoadError } from "@/components/public/scholar-load-error";
import { SiteFooter } from "@/components/site-footer";
import { loadPublicScholar } from "@/lib/api/scholars.server";
import { scholarSection } from "@/lib/api/scholars.params";
import type { ScholarSearchParams } from "@/lib/api/scholars.types";

export async function generateMetadata({ params }: { params: Promise<{ slug: string; section: string }> }): Promise<Metadata> {
  const { section } = await params; return { title: scholarSectionTitles[section] || "学者资料" };
}
export default async function ScholarSectionPage({ params, searchParams }: { params: Promise<{ slug: string; section: string }>; searchParams: Promise<ScholarSearchParams> }) {
  const { slug, section } = await params, current = scholarSection(section), query = await searchParams;
  if (!current) notFound();
  let data;
  try { data = await loadPublicScholar(slug, current, query); } catch { return <><ScholarLoadError slug={slug} /><SiteFooter /></>; }
  if (!data) notFound();
  return <ScholarSectionPublicView data={data} section={current} params={query} footer={<SiteFooter />} />;
}
