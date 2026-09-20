import { notFound } from "next/navigation";
import { KnowledgeNodePublicView } from "@/components/public/knowledge-node-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadKnowledgeNode, loadNormalizedReadingPathsPage, loadNormalizedTheoryTimelinePage } from "@/lib/api/knowledge.server";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { searchPage } from "@/lib/search-context";
import { directoryPage } from "@/lib/api/pagination";

export default async function TheorySectionPage({ params, searchParams }: { params: Promise<{ slug: string; section: string }>; searchParams: Promise<{page?: string}> }) {
  const { slug, section } = await params;
  if (!["timeline", "concepts", "works", "evidence", "relations", "propositions"].includes(section)) notFound();
  const page = searchPage((await searchParams).page);
  const [node, timeline, paths] = await Promise.all([loadKnowledgeNode(slug), section === "timeline" ? loadNormalizedTheoryTimelinePage({node: slug, page: String(page)}).then(payload => directoryPage(payload,page)) : Promise.resolve(null), section === "works" ? loadNormalizedReadingPathsPage({node: slug},page) : Promise.resolve(null)]);
  if (!node) notFound();
  const currentPage = timeline || paths;
  return <KnowledgeNodePublicView node={node} timeline={timeline?.results || []} allPaths={paths?.results || []} slug={slug} section={section} pagination={currentPage ? <ScopedSearchPagination path={`/theories/nodes/${slug}/${section}`} context="theories" page={page} totalPages={currentPage.totalPages}/> : undefined} footer={<SiteFooter/>}/>;
}
