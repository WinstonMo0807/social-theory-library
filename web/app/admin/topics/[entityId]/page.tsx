import type { Metadata } from "next";
import { TaxonomyAdmin } from "@/components/admin-sections";

export const metadata: Metadata = { title: "编辑主题" };

export default async function TopicEditorPage({
  params,
}: {
  params: Promise<{ entityId: string }>;
}) {
  const { entityId } = await params;
  return <TaxonomyAdmin mode="topic" entityId={entityId} />;
}
