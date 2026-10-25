import { SiteFooter } from "@/components/site-footer";
import { EditorialDirectoryView } from "@/components/public/editorial-directory";
import { loadEditorialDirectory } from "@/lib/api/recommendation-issues.server";
import { ServerApiError } from "@/lib/api/server-request";
import type { EditorialDirectory, EditorialSearchParams } from "@/lib/api/recommendation-issues.types";

export const metadata = { title: "专题文章索引" };
export default async function Page({ searchParams }: { searchParams: Promise<EditorialSearchParams> }) {
  const params = await searchParams;
  let data: EditorialDirectory | null = null, error = "";
  try { data = await loadEditorialDirectory(params); }
  catch (reason) { error = reason instanceof ServerApiError && reason.status === 400 ? "筛选条件无效，请检查年份范围或重置筛选。" : "专题文章暂时无法读取。当前筛选已保留，请重试。"; }
  return <><EditorialDirectoryView key={JSON.stringify(params)} data={data} params={params} error={error} /><SiteFooter reference="editorial" /></>;
}
