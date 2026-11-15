import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { WorkDetailView } from "@/components/work-detail-view";
import { loadWork } from "@/lib/api/catalog.server";
import { publicImageMetadata } from "@/lib/public-image-metadata";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const work = await loadWork(slug, true);
  return { title: work?.title ?? "文献详情", ...await publicImageMetadata(work?.shareImage, work?.shareImageAlt || work?.title || "") };
}

export default async function WorkDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const work = await loadWork(slug, true);
  if (!work) notFound();
  return <WorkDetailView key={work.editionId || work.slug} work={work} footer={work.kind === "期刊论文" || work.readerHref ? <SiteFooter reference={work.kind === "期刊论文" ? "journal" : "work"} /> : null} />;
}
