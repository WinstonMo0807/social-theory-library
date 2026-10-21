import type { ReactNode } from "react";
import type { PublicTopicDetail, TopicSearchParams } from "@/lib/api/topics.types";
import { TopicProfile } from "./topic-profile";
export function TopicPublicView({ topic, footer, preview = false, initialSection = "overview", params = {} }: { topic: PublicTopicDetail; footer?: ReactNode; preview?: boolean; initialSection?: string; params?: TopicSearchParams }) { return <><TopicProfile topic={topic} preview={preview} initialSection={initialSection} params={params} />{footer}</>; }
