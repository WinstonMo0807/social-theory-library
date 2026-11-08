import type { Metadata } from "next";
import { AdminKnowledgePagePreview } from "@/components/admin/preview/knowledge-page-preview";
import { KnowledgePublicationReview } from "@/components/admin/knowledge/knowledge-publication-review";
import { SiteHeader } from "@/components/site-header";
import { SiteFooter } from "@/components/site-footer";
import { loadSiteChromeConfig } from "@/lib/api/site.server";

export const metadata: Metadata = {
  title: "知识对象草稿预览",
  robots: { index: false, follow: false },
};

export default async function AdminKnowledgePreviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ objectType: string; objectId: string }>;
  searchParams: Promise<Record<string,string|string[]|undefined>>;
}) {
  const [{ objectType, objectId },query] = await Promise.all([params,searchParams]);
  if(query.review==="1")return <KnowledgePublicationReview objectType={objectType} objectId={objectId}/>;
  if(query.frame==="1"){
    const {config}=await loadSiteChromeConfig();
    const sections: Record<string, string> = { scholar: "/scholars", topic: "/topics", discipline: "/theories/disciplines", subdiscipline: "/subdisciplines", reading_path: "/theories/reading-paths" };
    const previewPathname = objectType === "theory" && query.page === "graph" ? "/theories/graph"
      : objectType === "theory" && query.page === "timeline" ? "/theories/timeline"
      : `${sections[objectType] || "/theories/nodes"}/${objectId}`;
    return <><SiteHeader config={config} preview previewPathname={previewPathname}/><AdminKnowledgePagePreview objectType={objectType} objectId={objectId}/><div inert><SiteFooter/></div></>;
  }
  return <AdminKnowledgePagePreview objectType={objectType} objectId={objectId} />;
}
