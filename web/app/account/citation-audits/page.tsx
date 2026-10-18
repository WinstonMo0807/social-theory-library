import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { CitationAuditUpload } from "@/components/research/citation-audit-upload";
export const metadata: Metadata = { title: "引文体检：提交与任务" };
export default function CitationAuditsPage() { return <><CitationAuditUpload /><SiteFooter /></>; }
