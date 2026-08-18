import type { Metadata } from "next";
import { CandidateReview } from "@/components/candidate-review";

export const metadata: Metadata = { title: "候选审核" };

export default function CandidateReviewPage() {
  return <CandidateReview />;
}
