import { PublishedPlacements } from "@/components/public/published-placements";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { ReadingPathPublicView } from "@/components/public/reading-path-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadPublicReadingPath } from "@/lib/api/reading-paths.server";
import { ServerApiError } from "@/lib/api/server-request";
import type { PublicReadingPath, ReadingPathSearchParams } from "@/lib/api/reading-paths.types";

type Props = { params: Promise<{ slug: string }>; searchParams: Promise<ReadingPathSearchParams> };
const first = (value: string | string[] | undefined) => (Array.isArray(value) ? value[0] : value) || "";
export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const [{ slug }, search] = await Promise.all([params, searchParams]);
  try { const path = await loadPublicReadingPath(slug, first(search.revision)); return { title: path.title, description: path.introduction || "从问题和基础出发，按阶段阅读原典。" }; }
  catch { return { title: "阅读路径" }; }
}
export default async function ReadingPathPage({ params, searchParams }: Props) {
  const [{ slug }, search] = await Promise.all([params, searchParams]);
  let path: PublicReadingPath | null = null;
  try { path = await loadPublicReadingPath(slug, first(search.revision)); } catch (failure) {
    if (failure instanceof ServerApiError && failure.status === 404) notFound();
  }
  if (!path) return <><main className="page-shell"><h1>阅读路径暂时无法读取</h1><p>当前无法核对公开路径，请稍后重新打开。本人已有进度与笔记不会因此删除。</p><Link href={`/theories/reading-paths/${encodeURIComponent(slug)}`}>重新读取路径</Link><p><Link href="/theories/reading-paths">返回阅读路径列表</Link></p></main><SiteFooter /></>;
  return <ReadingPathPublicView path={path} footer={<><PublishedPlacements type="reading_path" id={path.id}/><SiteFooter /></>} initialCopy={first(search.action) === "copy-plan"} initialRevision={first(search.revision)} initialPlanId={first(search.copy)} />;
}
