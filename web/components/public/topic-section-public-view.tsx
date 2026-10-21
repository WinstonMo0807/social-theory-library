import type { PublicTopicDetail, TopicSearchParams } from "@/lib/api/topics.types";
import { topicLegacySections, topicSections } from "@/lib/api/topics.params";
import { TopicProfile } from "./topic-profile";
export const topicSectionTitles: Record<string, string> = { ...Object.fromEntries(topicSections.map(row => [row.id, row.label])), ...topicLegacySections, recent: "最近入库", "reading-paths": "研究路径", passages: "原文线索" };
export function TopicSectionPublicView({ topic, section, preview = false, params = {} }: { topic: PublicTopicDetail; section: string; preview?: boolean; params?: TopicSearchParams }) { return <TopicProfile topic={topic} initialSection={section} preview={preview} params={params} />; }
