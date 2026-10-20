import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { WorkDetailView } from "@/components/work-detail-view";
import { loadWork } from "@/lib/api/catalog.server";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const work = await loadWork(slug);
  return { title: work?.title ?? "文献详情" };
}

export default async function WorkDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const work = await loadWork(slug);
  if (!work) notFound();
  return <WorkDetailView key={work.editionId || work.slug} work={work} footer={<SiteFooter />} />;
}
