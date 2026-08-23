import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { WorkDetailView } from "@/components/work-detail-view";
import { loadWork, loadWorks } from "@/lib/server-api";

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
  const [work, works] = await Promise.all([loadWork(slug), loadWorks()]);
  if (!work) notFound();
  const relatedWorks = works.filter((item) => (
    item.id !== work.id
    && (
      (item.theories ?? []).some((candidate) => (work.theories ?? []).some((current) => current.slug === candidate.slug))
      || (item.topics ?? []).some((candidate) => (work.topics ?? []).some((current) => current.slug === candidate.slug))
    )
  ));
  return <WorkDetailView work={work} relatedWorks={relatedWorks} footer={<SiteFooter />} />;
}
