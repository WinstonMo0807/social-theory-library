import { PublishedPlacements } from "@/components/public/published-placements";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { KnowledgeNodePublicView } from "@/components/public/knowledge-node-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadKnowledgeNode, loadNormalizedReadingPathsPage, loadNormalizedTheoryTimelinePage } from "@/lib/api/knowledge.server";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const node = await loadKnowledgeNode(slug);
  return { title: node?.canonical_name_zh || "理论条目", description: node?.summary || node?.definition || "理论条目详情" };
}

export default async function KnowledgeNodePage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{ compare?: string | string[] }> }) {
  const { slug } = await params;
  const [node, timeline, paths, query] = await Promise.all([
    loadKnowledgeNode(slug), loadNormalizedTheoryTimelinePage({ node: slug, page: "1" }),
    loadNormalizedReadingPathsPage({ node: slug }, 1), searchParams,
  ]);
  if (!node) notFound();

  return <KnowledgeNodePublicView key={`${node.id}:${node.public_detail?.revision_id || ""}`} node={node}
    timeline={timeline.results} allPaths={paths.results} slug={slug} publicDesign initialCompare={Array.isArray(query.compare) ? query.compare[0] : query.compare}
    footer={<><PublishedPlacements type="node" id={node.id}/><SiteFooter /></>} />;
}
