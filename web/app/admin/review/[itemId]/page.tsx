import { redirect } from "next/navigation";

export default async function MetadataReviewPage({ params }: { params: Promise<{ itemId: string }> }) {
  const { itemId } = await params;
  redirect(`/admin/intake/${encodeURIComponent(itemId)}#bibliography`);
}
