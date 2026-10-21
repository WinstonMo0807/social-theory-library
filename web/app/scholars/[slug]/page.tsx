import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ScholarPublicView } from "@/components/public/scholar-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadPublicScholar } from "@/lib/api/scholars.server";
import type { ScholarSearchParams } from "@/lib/api/scholars.types";
import { ScholarLoadError } from "@/components/public/scholar-load-error";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  try { const data = await loadPublicScholar(slug); return { title: data?.person.preferred_name || "学者" }; } catch { return { title: "学者" }; }
}
export default async function ScholarDetailPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<ScholarSearchParams> }) {
  const { slug } = await params, query = await searchParams;
  let data;
  try { data = await loadPublicScholar(slug, "overview", query); } catch { return <><ScholarLoadError slug={slug} /><SiteFooter /></>; }
  if (!data) notFound();
  return <ScholarPublicView data={data} params={query} footer={<SiteFooter />} />;
}
