import { RecyclePagePreview } from "@/components/admin/preview/recycle-page-preview";

export const metadata = { title: "恢复效果预览", robots: { index: false, follow: false } };

export default async function RecyclePreviewPage({ params }: { params: Promise<{ entryId: string }> }) {
  const { entryId } = await params;
  return <RecyclePagePreview entryId={entryId}/>;
}
