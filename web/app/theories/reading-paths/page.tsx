import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ReadingPathList } from "@/components/public/reading-path-list";
import { loadPublicReadingPaths } from "@/lib/api/reading-paths.server";
import { readingPathFilters, type ReadingPathPage, type ReadingPathSearchParams } from "@/lib/api/reading-paths.types";

export const metadata: Metadata = { title: "阅读路径", description: "从问题和基础出发，按阶段阅读原典。" };
export default async function ReadingPathsPage({ searchParams }: { searchParams: Promise<ReadingPathSearchParams> }) {
  const filters = readingPathFilters(await searchParams); let result: ReadingPathPage | null = null, error = "";
  try { result = await loadPublicReadingPaths(filters); } catch { error = "当前无法读取公开路径。筛选条件已保留，可以重试。"; }
  return <><ReadingPathList key={JSON.stringify(filters)} result={result} filters={filters} error={error} /><SiteFooter /></>;
}
