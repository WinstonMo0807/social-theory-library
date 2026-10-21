import type { ReactNode } from "react";
import type { PublicScholarDetail, ScholarSearchParams } from "@/lib/api/scholars.types";
import { ScholarPublicView } from "./scholar-public-view";

export const scholarSectionTitles: Record<string, string> = {
  overview: "学者概览", biography: "人物资料来源", sources: "人物资料来源", evidence: "代表原文", passages: "代表原文",
  timeline: "生平与时间线", works: "主要作品与版本", concepts: "核心概念", questions: "理论问题", "concept-map": "概念与图谱",
  network: "相关争论与学者", relations: "相关争论与学者", theories: "相关理论", "frequently-read": "相关学者",
  topics: "专题策划", paths: "阅读路径", "reading-paths": "阅读路径",
};
export function ScholarSectionPublicView({ data, section = "overview", initialSection, footer, preview = false, params = {} }: {
  data: PublicScholarDetail; section?: string; initialSection?: string; footer?: ReactNode; preview?: boolean; params?: ScholarSearchParams;
}) {
  return <ScholarPublicView data={data} footer={footer} preview={preview} initialSection={initialSection || section} params={params} />;
}
