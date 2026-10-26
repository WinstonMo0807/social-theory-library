import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { CounterEvidenceWorkspace } from "@/components/research/counter-evidence-workspace";

export const metadata: Metadata = { title: "学术反证：检验一个判断" };
export default async function CounterEvidencePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ turn?: string }> }) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return <><CounterEvidenceWorkspace id={id} initialTurnId={query.turn} /><SiteFooter reference="research-workspace" /></>;
}
