import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ResearchReplay } from "@/components/research/research-replay";

export const metadata: Metadata = { title: "研究过程回放" };
export default async function ResearchHistoryPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ turn?: string }> }) {
  const { id } = await params;
  const { turn } = await searchParams;
  const initialTurn = typeof turn === "string" && /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(turn) ? turn : "";
  return <><ResearchReplay id={id} initialTurn={initialTurn} /><SiteFooter reference="research-replay" /></>;
}
