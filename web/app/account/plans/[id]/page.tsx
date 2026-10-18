import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ReadingPlanDetail } from "@/components/research/reading-plan-detail";

export const metadata: Metadata = { title: "我的阅读计划" };

export default async function ReadingPlanPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><ReadingPlanDetail id={id} /><SiteFooter /></>;
}
