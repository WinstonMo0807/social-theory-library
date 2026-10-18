import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { CitationAuditParse } from "@/components/research/citation-audit-parse";

export const metadata: Metadata = { title: "引文解析与核对" };
export default async function CitationParsePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ occurrence?: string; entry?: string }> }) {
  const [{ id }, query] = await Promise.all([params, searchParams]);
  return <><CitationAuditParse id={id} initialSelection={query.occurrence ? `occurrence:${query.occurrence}` : query.entry ? `entry:${query.entry}` : ""} /><SiteFooter /></>;
}
