import type { Metadata } from "next";
import { CandidateReview } from "@/components/candidate-review";

export const metadata: Metadata = { title: "建议数据诊断" };

export default function CandidateDiagnosticsPage() {
  return <CandidateReview />;
}
