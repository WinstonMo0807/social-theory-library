import type { Metadata } from "next";
import { TheoryGraphPage } from "@/components/public/theory-graph-page";
import type { GraphSearchParams } from "@/lib/api/graph.types";

export const metadata: Metadata = { title: "知识地图与学科目录", description: "在局部关系中找方向，并能从图回到叙事、目录与原文。" };

export default async function GraphPage({ searchParams }: { searchParams: Promise<GraphSearchParams> }) {
  return <TheoryGraphPage searchParams={await searchParams} />;
}
