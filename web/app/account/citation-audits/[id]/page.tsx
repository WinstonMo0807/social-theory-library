import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { CitationAuditReport } from "@/components/research/citation-audit-report";

export const metadata: Metadata = { title: "论文体检报告" };
export default async function CitationAuditPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><CitationAuditReport id={id} /><SiteFooter reference="citation-issue" /></>;
}
