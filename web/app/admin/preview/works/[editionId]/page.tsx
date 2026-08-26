import type { Metadata } from "next";
import { AdminWorkPagePreview } from "@/components/admin/preview/work-page-preview";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = {
  title: "管理员页面预览",
  robots: { index: false, follow: false },
};

export default async function AdminWorkPreviewPage({
  params,
}: {
  params: Promise<{ editionId: string }>;
}) {
  const { editionId } = await params;
  return <AdminWorkPagePreview editionId={editionId} footer={<SiteFooter />} />;
}
