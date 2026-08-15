import type { Metadata } from "next";
import { MetadataReview } from "@/components/metadata-review";

export const metadata: Metadata = { title: "元数据复核" };

export default async function MetadataReviewPage({ params }: { params: Promise<{ itemId: string }> }) {
  const { itemId } = await params;
  return <MetadataReview itemId={itemId} />;
}
