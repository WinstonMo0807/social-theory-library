import type { Metadata } from "next";
import { KnowledgeWorkspace } from "@/components/knowledge-workspace";

export const metadata: Metadata = { title: "知识工作台" };

export default function KnowledgePage() {
  return <KnowledgeWorkspace />;
}
