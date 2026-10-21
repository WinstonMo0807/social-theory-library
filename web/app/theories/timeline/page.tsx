import type { Metadata } from "next";
import { TheoryTimelinePage } from "@/components/public/theory-timeline-page";
import type { TimelineSearchParams } from "@/lib/api/timeline.types";

export const metadata: Metadata = { title: "学科与概念时间线", description: "按时间理解作品、概念使用和学术事件的变化，查看真实版本与原文来源。" };

export default async function TimelinePage({ searchParams }: { searchParams: Promise<TimelineSearchParams> }) {
  return <TheoryTimelinePage searchParams={await searchParams} />;
}
