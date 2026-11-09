"use client";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePublicSession } from "./public-session-provider";
import { KnowledgePageContent, type KnowledgePageData } from "./public/knowledge-page-content";

export function WorkKnowledge({ workId }: { workId: string }) {
  return <ObjectKnowledge path={`/knowledge/works/${workId}/`} />;
}

export function EntityKnowledge({ kind, id }: { kind: "person" | "node" | "topic" | "discipline" | "subdiscipline"; id: string }) {
  return <ObjectKnowledge path={`/knowledge/objects/${kind}/${id}/`} />;
}

function ObjectKnowledge({ path }: { path: string }) {
  const { state } = usePublicSession();
  const [page, setPage] = useState<KnowledgePageData | null>(null), [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setError(""); setPage(null);
    void apiRequest<{ page: KnowledgePageData | null }>(path, { signal: controller.signal, cache: "no-store" }, getServerSessionCredential())
      .then(data => setPage(data.page)).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [path, state.status]);
  if (error) return <p role="alert">知识导读暂时无法读取。{error}</p>;
  if (!page?.blocks.length) return null;
  return <KnowledgePageContent page={page} />;
}
