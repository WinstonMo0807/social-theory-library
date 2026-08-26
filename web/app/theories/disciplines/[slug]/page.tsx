import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { DisciplinePublicView } from "@/components/public/discipline-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadTheoryDisciplinePage } from "@/lib/server-api";

const allowedTypes = new Set(["theory_tradition", "subdiscipline", "debate"]);

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const payload = await loadTheoryDisciplinePage(slug);
  return { title: payload?.discipline.name || "学科详情", description: payload?.discipline.description || "从学科浏览理论条目和馆藏。" };
}

export default async function TheoryDisciplinePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ type?: string }>;
}) {
  const { slug } = await params;
  const query = await searchParams;
  const activeType = allowedTypes.has(query.type || "") ? query.type! : "theory_tradition";
  const payload = await loadTheoryDisciplinePage(slug, activeType);
  if (!payload) notFound();

  return <DisciplinePublicView payload={payload} activeType={activeType} slug={slug} footer={<SiteFooter />} />;
}
