import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { KnowledgeNodePublicView } from "@/components/public/knowledge-node-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadKnowledgeNode } from "@/lib/api/knowledge.server";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const node = await loadKnowledgeNode(slug);
  return { title: node?.canonical_name_zh || "理论条目", description: node?.summary || node?.definition || "理论条目详情" };
}

export default async function KnowledgeNodePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const node = await loadKnowledgeNode(slug);
  if (!node) notFound();

  return <KnowledgeNodePublicView node={node} timeline={[]} allPaths={[]} slug={slug} footer={<SiteFooter />} />;
}
