import type { Metadata } from "next";
import Link from "next/link";
import { BookOpen } from "lucide-react";
import { ReaderShell } from "@/components/reader-shell";
import { loadReaderManifest } from "@/lib/server-api";

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
  const manifest = await loadReaderManifest(assetId);
  if (!manifest) {
    return (
      <main className="reader-route-error">
        <BookOpen size={32} />
        <h1>暂时无法打开这份 PDF</h1>
        <p>文献可能仍在全文索引或发布处理中，也可能已经下架。请从馆藏详情重新进入。</p>
        <Link className="button" href="/explore">返回馆藏检索</Link>
      </main>
    );
  }
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
