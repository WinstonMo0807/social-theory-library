import { notFound, redirect } from "next/navigation";
import { loadKnowledgeNode } from "@/lib/api/knowledge.server";

export default async function ConceptPage({ params }: { params: Promise<{ slug: string }> }) {
  const {slug} = await params;
  const node = await loadKnowledgeNode(slug);
  if (!node || !["concept", "debate", "research_problem"].includes(node.node_type)) notFound();
  redirect(`/theories/nodes/${encodeURIComponent(slug)}`);
}
