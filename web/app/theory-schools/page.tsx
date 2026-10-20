import type { Metadata } from "next";
import { TheoryOverviewPage, type TheoryOverviewSearchParams } from "@/components/theory/theory-overview";

export const metadata: Metadata = {
  title: "理论流派",
  description: "梳理社会理论发展的主要流派与传统，理解不同理论取向的核心观点、历史脉络及其在当代的影响与对话。",
};

export default function TheorySchoolsPage({ searchParams }: { searchParams: Promise<TheoryOverviewSearchParams> }) {
  return <TheoryOverviewPage searchParams={searchParams} actionPath="/theory-schools" />;
}
