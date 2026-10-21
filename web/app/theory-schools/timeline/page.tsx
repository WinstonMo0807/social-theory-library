import type { Metadata } from "next";
import { TheoryTimelinePage } from "@/components/public/theory-timeline-page";
import type { TimelineSearchParams } from "@/lib/api/timeline.types";

export const metadata: Metadata = { title: "学科与概念时间线" };

export default async function LegacyTimelinePage({ searchParams }: { searchParams: Promise<TimelineSearchParams> }) {
  // Both routes keep the same published TheoryTimelineEvent identities.
  return <TheoryTimelinePage searchParams={await searchParams} actionPath="/theory-schools/timeline" />;
}
