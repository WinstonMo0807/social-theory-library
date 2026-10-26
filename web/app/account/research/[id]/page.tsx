import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ResearchSessionDetail } from "@/components/research/research-session-detail";

export const metadata: Metadata = { title: "研究会话" };

export default async function ResearchDetailPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ turn?: string | string[] }> }) {
  const [{ id }, search] = await Promise.all([params, searchParams]);
  const initialTurn = typeof search.turn === "string" ? search.turn : "";
  return <><ResearchSessionDetail id={id} initialTurn={initialTurn} /><SiteFooter reference="research-workspace" /></>;
}
