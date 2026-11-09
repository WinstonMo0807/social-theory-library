"use client";

import { KnowledgeWorkspace } from "@/components/admin/knowledge-workspace";
import { KnowledgeLegacyRedirect } from "@/components/admin/knowledge/knowledge-legacy-redirect";
import { useSearchParams } from "next/navigation";

export default function KnowledgePage() {
  const query = useSearchParams();
  return query.has("selected_type") || query.has("object_type") || query.has("selected_id") || query.has("object_id")
    ? <KnowledgeLegacyRedirect /> : <KnowledgeWorkspace />;
}
