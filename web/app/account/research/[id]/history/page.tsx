import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ResearchReplay } from "@/components/research/research-replay";

export const metadata: Metadata = { title: "研究过程回放" };
export default async function ResearchHistoryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><ResearchReplay id={id} /><SiteFooter /></>;
}
