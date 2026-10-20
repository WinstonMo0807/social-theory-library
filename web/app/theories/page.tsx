import type { Metadata } from "next";
import { TheoryOverviewPage, type TheoryOverviewSearchParams } from "@/components/theory/theory-overview";

export const metadata: Metadata = {
  title: "理论流派",
  description: "从学科、理论传统、概念与馆藏原文进入社会理论。",
};

export default function TheoriesPage({ searchParams }: { searchParams: Promise<TheoryOverviewSearchParams> }) {
  return <TheoryOverviewPage searchParams={searchParams} actionPath="/theories" />;
}
