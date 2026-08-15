import type { Metadata } from "next";
import { ReviewQueue } from "@/components/review-queue";

export const metadata: Metadata = { title: "元数据复核" };

export default function ReviewQueuePage() {
  return <ReviewQueue />;
}
