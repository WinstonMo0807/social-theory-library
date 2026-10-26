import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { CitationAuditIssue } from "@/components/research/citation-audit-issue";

export const metadata: Metadata = { title: "引文问题与原文核验" };
export default async function CitationIssuePage({ params }: { params: Promise<{ id: string; issueId: string }> }) {
  const { id, issueId } = await params;
  return <><CitationAuditIssue id={id} issueId={issueId} /><SiteFooter reference="citation-issue" /></>;
}
