import type { Metadata } from "next";
import { KnowledgeWorkspace } from "@/components/knowledge-workspace";

export const metadata: Metadata = { title: "Knowledge Studio" };

export default function KnowledgePage() {
  return <KnowledgeWorkspace />;
}
