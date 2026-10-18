import type { Metadata } from "next";
import { PageMappingWorkspace } from "@/components/admin/library/page-mapping-workspace";

export const metadata: Metadata = { title: "印刷页与物理页映射" };
export default async function PageMappingPage({ params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return <PageMappingWorkspace assetId={assetId} />;
}
