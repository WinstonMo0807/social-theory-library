import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ResearchSessionList } from "@/components/research/research-session-list";

export const metadata: Metadata = { title: "研究会话" };

export default function ResearchPage() {
  return <><ResearchSessionList /><SiteFooter /></>;
}
