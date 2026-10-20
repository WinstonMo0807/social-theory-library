import { notFound } from "next/navigation";
import { KnowledgeNodePublicView } from "@/components/public/knowledge-node-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadKnowledgeNode, loadNormalizedReadingPathsPage, loadNormalizedTheoryTimelinePage } from "@/lib/api/knowledge.server";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { searchPage } from "@/lib/search-context";
import { directoryPage } from "@/lib/api/pagination";

export default async function TheorySectionPage({ params, searchParams }: { params: Promise<{ slug: string; section: string }>; searchParams: Promise<{page?: string | string[]; compare?: string | string[]}> }) {
  const { slug, section } = await params;
  if (!["timeline", "concepts", "works", "evidence", "relations", "propositions", "usages", "debates", "paths", "contexts", "research", "scholars"].includes(section)) notFound();
  const query = await searchParams;
  const page = searchPage(query.page);
  const [node, timeline, paths] = await Promise.all([loadKnowledgeNode(slug), section === "timeline" ? loadNormalizedTheoryTimelinePage({node: slug, page: String(page)}).then(payload => directoryPage(payload,page)) : Promise.resolve(null), ["works", "paths"].includes(section) ? loadNormalizedReadingPathsPage({node: slug},page) : Promise.resolve(null)]);
  if (!node) notFound();
  const currentPage = timeline || paths;
  return <KnowledgeNodePublicView key={`${node.id}:${section}:${node.public_detail?.revision_id || ""}`} node={node} timeline={timeline?.results || []} allPaths={paths?.results || []} slug={slug} section={section} publicDesign initialCompare={Array.isArray(query.compare) ? query.compare[0] : query.compare} pagination={currentPage ? <ScopedSearchPagination path={`/theories/nodes/${slug}/${section}`} context="theories" page={page} totalPages={currentPage.totalPages}/> : undefined} footer={<SiteFooter/>}/>;
}
