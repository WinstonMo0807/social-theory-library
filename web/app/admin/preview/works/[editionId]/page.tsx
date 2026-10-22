import type { Metadata } from "next";
import { AdminWorkPagePreview } from "@/components/admin/preview/work-page-preview";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { loadSiteChromeConfig } from "@/lib/api/site.server";

export const metadata: Metadata = {
  title: "管理员页面预览",
  robots: { index: false, follow: false },
};

export default async function AdminWorkPreviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ editionId: string }>;
  searchParams: Promise<Record<string,string|string[]|undefined>>;
}) {
  const [{ editionId },query] = await Promise.all([params, searchParams]);
  if (query.frame === "1") {
    const {config} = await loadSiteChromeConfig();
    return <><SiteHeader config={config} preview/><AdminWorkPagePreview key={`${editionId}:${query.version}:${query.fingerprint}`} editionId={editionId} footer={<SiteFooter />} /></>;
  }
  return <AdminWorkPagePreview editionId={editionId} footer={<SiteFooter />} />;
}
