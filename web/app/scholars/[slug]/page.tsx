import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ScholarPublicView } from "@/components/public/scholar-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadScholar, loadTheorySchools } from "@/lib/server-api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const data = await loadScholar(slug);
  return { title: data?.scholar.name ?? "学者" };
}

export default async function ScholarDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const [data, theorySchools] = await Promise.all([
    loadScholar(slug),
    loadTheorySchools(),
  ]);
  if (!data) notFound();

  return (
    <ScholarPublicView
      data={data}
      footer={<SiteFooter />}
      slug={slug}
      theorySchools={theorySchools}
    />
  );
}
