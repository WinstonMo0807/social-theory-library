import type { Metadata } from "next";
import { TheoryNodesAdmin } from "@/components/theory-system-admin";

export const metadata: Metadata = { title: "理论传统工作区" };

export default async function Page({ params }: { params: Promise<{ nodeId: string }> }) {
  const { nodeId } = await params;
  return <TheoryNodesAdmin initialNodeId={nodeId} />;
}
