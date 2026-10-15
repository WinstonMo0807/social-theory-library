import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ResearchSessionDetail } from "@/components/research/research-session-detail";

export const metadata: Metadata = { title: "研究会话" };

export default async function ResearchDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><ResearchSessionDetail id={id} /><SiteFooter /></>;
}
