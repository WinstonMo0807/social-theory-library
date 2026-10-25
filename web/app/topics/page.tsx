import type { Metadata } from "next";
import { TopicDirectory } from "@/components/public/topic-directory";
import { loadTopicDirectory } from "@/lib/api/topics.server";
import type { TopicSearchParams } from "@/lib/api/topics.types";
export const metadata: Metadata = { title: "主题与专题方向" };
export default async function TopicsPage({ searchParams }: { searchParams: Promise<TopicSearchParams> }) {
  const params = await searchParams;
  let result = null, error = "";
  try { result = await loadTopicDirectory(params); } catch { error = "请求未完成，当前关键词与筛选条件已保留，请重试。"; }
  return <TopicDirectory result={result} params={params} error={error} />;
}
