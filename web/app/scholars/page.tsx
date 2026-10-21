import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ScholarDirectory } from "@/components/public/scholar-directory";
import { loadPublicScholars } from "@/lib/api/scholars.server";
import type { ScholarSearchParams } from "@/lib/api/scholars.types";

export const metadata: Metadata = {title: "学者"};
export default async function ScholarsPage({ searchParams }: {searchParams: Promise<ScholarSearchParams>}) {
  const params = await searchParams;
  let result = null, error = "";
  try { result = await loadPublicScholars(params); } catch { error = "学者目录暂时无法读取，当前筛选仍保留。请重试或清除筛选。"; }
  return <><ScholarDirectory result={result} params={params} error={error} /><SiteFooter /></>;
}
