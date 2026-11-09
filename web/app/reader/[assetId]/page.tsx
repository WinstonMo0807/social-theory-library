import { requireReaderSession } from "@/lib/reader-access.server";
import type { Metadata } from "next";
import { ReaderShell } from "@/components/reader-shell";
import { ReaderRouteFailure } from "@/components/reader/reader-route-failure";
import { ParallelReader } from "@/components/reader/parallel-reader";
import { loadReaderManifestResult } from "@/lib/api/reader.server";
import { loadSiteChromeConfig } from "@/lib/api/site.server";
import { readerReturnPath } from "@/lib/api/reader-failure";

export const metadata: Metadata = {
  title: "在线阅读",
};

export default async function ReaderPage({
  params,
  searchParams,
}: {
  params: Promise<{ assetId: string }>;
  searchParams: Promise<{ anchor?: string; preview?: string; mode?: string; alignment?: string; right_asset?: string; right_revision?: string; page?: string; q?: string; focus?: string; passage?: string; evidence?: string; research_project?: string; research_turn?: string; reference?: string; revision?: string; return_to?: string }>;
}) {
  const [{ assetId }, query] = await Promise.all([params, searchParams]);
  await requireReaderSession(`/reader/${encodeURIComponent(assetId)}`, query);
  const [result, { config }] = await Promise.all([loadReaderManifestResult(assetId, query.revision || "", query.preview === "1"), loadSiteChromeConfig()]);
  if (query.mode === "parallel") {
    return <ParallelReader assetId={assetId} work={result.ok ? result.manifest.work : undefined} siteConfig={config}
      taskId={query.alignment} initialRevision={query.revision} initialFocus={query.focus || query.evidence}
      initialRight={query.right_asset && query.right_revision ? { assetId: query.right_asset, revisionId: query.right_revision } : undefined} initialPage={Number.isSafeInteger(Number(query.page)) && Number(query.page) > 0 ? Number(query.page) : 1} />;
  }
  if (!result.ok) {
    return <ReaderRouteFailure failure={result.failure} siteConfig={config} returnPath={readerReturnPath(assetId, query)} />;
  }
  const manifest = result.manifest;
  return (
    <ReaderShell
      key={`${manifest.work.id}:${manifest.documentRevisionId || ""}`}
      work={manifest.work}
      siteConfig={config}
      documentRevisionId={manifest.documentRevisionId || ""}
      requestedRevisionId={query.revision || ""}
      knowledgeAnchorId={query.anchor || ""}
      sourcePreview={query.preview === "1"}
      researchProjectId={query.research_project || ""}
      researchTurnId={query.research_turn || ""}
      researchReferenceId={query.reference || ""}
      returnTo={query.return_to || ""}
      initialPage={Number(query.page) || 1}
      initialQuery={query.q ?? ""}
      initialFocus={query.focus ?? ""}
      initialPassage={query.passage ?? ""}
      initialEvidence={query.evidence ?? ""}
      outline={manifest.outline}
      relatedScholars={manifest.scholars}
      relatedTheories={manifest.theories}
      relatedTopics={manifest.topics}
    />
  );
}
