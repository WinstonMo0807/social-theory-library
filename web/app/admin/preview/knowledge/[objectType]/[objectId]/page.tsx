import type { Metadata } from "next";
import { AdminKnowledgePagePreview } from "@/components/admin/preview/knowledge-page-preview";

export const metadata: Metadata = {
  title: "知识对象草稿预览",
  robots: { index: false, follow: false },
};

export default async function AdminKnowledgePreviewPage({
  params,
}: {
  params: Promise<{ objectType: string; objectId: string }>;
}) {
  const { objectType, objectId } = await params;
  return <AdminKnowledgePagePreview objectType={objectType} objectId={objectId} />;
}
