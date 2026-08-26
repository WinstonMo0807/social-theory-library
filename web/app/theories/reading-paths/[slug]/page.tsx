import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ReadingPathPublicView } from "@/components/public/reading-path-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadNormalizedReadingPath } from "@/lib/server-api";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const path = await loadNormalizedReadingPath(slug);
  return { title: path?.title || "阅读路径", description: path?.introduction || "经管理员策展的理论阅读路径。" };
}

export default async function ReadingPathPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = await loadNormalizedReadingPath(slug);
  if (!path) notFound();

  return <ReadingPathPublicView path={path} footer={<SiteFooter />} />;
}
