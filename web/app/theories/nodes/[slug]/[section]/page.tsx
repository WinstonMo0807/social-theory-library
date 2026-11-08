import { notFound } from "next/navigation";
import { KnowledgeNodePublicView } from "@/components/public/knowledge-node-public-view";
import { TheoryTimelinePage } from "@/components/public/theory-timeline-page";
import { SiteFooter } from "@/components/site-footer";
import { loadKnowledgeNode, loadNormalizedReadingPathsPage } from "@/lib/api/knowledge.server";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { searchPage } from "@/lib/search-context";
import type { TimelineSearchParams } from "@/lib/api/timeline.types";

export default async function TheorySectionPage({ params, searchParams }: { params: Promise<{ slug: string; section: string }>; searchParams: Promise<TimelineSearchParams> }) {
  const { slug, section } = await params;
  if (!["timeline", "concepts", "works", "evidence", "relations", "propositions", "usages", "debates", "paths", "contexts", "research", "scholars"].includes(section)) notFound();
  const query = await searchParams;
  const page = searchPage(query.page);
  const [node, paths] = await Promise.all([loadKnowledgeNode(slug), ["works", "paths"].includes(section) ? loadNormalizedReadingPathsPage({node: slug},page) : Promise.resolve(null)]);
  if (!node) notFound();
  if (section === "timeline") return <TheoryTimelinePage searchParams={query} actionPath={`/theories/nodes/${slug}/timeline`} scope={{ slug, name: node.canonical_name_zh, href: `/theories/nodes/${slug}` }} />;
  return <KnowledgeNodePublicView key={`${node.id}:${section}:${node.public_detail?.revision_id || ""}`} node={node} timeline={[]} allPaths={paths?.results || []} section={section} initialCompare={Array.isArray(query.compare) ? query.compare[0] : query.compare} pagination={paths ? <ScopedSearchPagination path={`/theories/nodes/${slug}/${section}`} context="theories" page={page} totalPages={paths.totalPages}/> : undefined} footer={<SiteFooter/>}/>;
}
