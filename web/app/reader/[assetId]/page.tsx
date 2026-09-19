import type { Metadata } from "next";
import { ReaderShell } from "@/components/reader-shell";
import { ReaderRouteFailure } from "@/components/reader/reader-route-failure";
import { loadReaderManifestResult } from "@/lib/api/reader.server";
import { readerReturnPath } from "@/lib/api/reader-failure";

export const metadata: Metadata = {
  title: "在线阅读",
};

export default async function ReaderPage({
  params,
  searchParams,
}: {
  params: Promise<{ assetId: string }>;
  searchParams: Promise<{ page?: string; q?: string; focus?: string; passage?: string; evidence?: string }>;
}) {
  const [{ assetId }, query] = await Promise.all([params, searchParams]);
  const result = await loadReaderManifestResult(assetId);
  if (!result.ok) {
    return <ReaderRouteFailure failure={result.failure} returnPath={readerReturnPath(assetId, query)} />;
  }
  const manifest = result.manifest;
  return (
    <ReaderShell
      work={manifest.work}
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
