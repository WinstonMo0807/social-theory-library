import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ResearchSessionCompare } from "@/components/research/research-session-compare";

export const metadata: Metadata = { title: "证据比较" };

export default async function ResearchComparePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><ResearchSessionCompare id={id} /><SiteFooter reference="research-compare" /></>;
}
