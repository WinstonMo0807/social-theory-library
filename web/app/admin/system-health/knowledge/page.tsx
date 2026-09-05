import type { Metadata } from "next";
import { KnowledgeWorkspaceDiagnostics } from "@/components/knowledge-workspace-diagnostics";

export const metadata: Metadata = { title: "知识处理诊断" };

export default function KnowledgeDiagnosticsPage() {
  return <KnowledgeWorkspaceDiagnostics />;
}
