import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SubdisciplinePublicView } from "@/components/public/subdiscipline-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadSubdiscipline } from "@/lib/server-api";

export const metadata: Metadata = { title: "子学科详情" };

export default async function SubdisciplinePage({ params }: { params: Promise<{ slug: string }> }) {
  const item = await loadSubdiscipline((await params).slug);
  if (!item) notFound();

  return <SubdisciplinePublicView item={item} footer={<SiteFooter />} />;
}
