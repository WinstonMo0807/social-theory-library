import type { Metadata } from "next";
import { DocumentOutlineWorkspace } from "@/components/admin/library/document-outline-workspace";

export const metadata: Metadata = { title: "目录校准" };
export default async function DocumentOutlinePage({ params }: { params: Promise<{ assetId: string }> }) {
  const { assetId } = await params;
  return <DocumentOutlineWorkspace assetId={assetId} />;
}
