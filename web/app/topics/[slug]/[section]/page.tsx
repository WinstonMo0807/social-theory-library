import type { Metadata } from "next";
import { notFound } from "next/navigation";
import {
  TopicSectionPublicView,
  topicSectionTitles,
} from "@/components/public/topic-section-public-view";
import { loadTopic } from "@/lib/server-api";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; section: string }>;
}): Promise<Metadata> {
  const { slug, section } = await params;
  const topic = await loadTopic(slug);
  return { title: topic ? `${topicSectionTitles[section] ?? "主题资料"} · ${topic.name}` : "主题资料" };
}

export default async function TopicSectionPage({
  params,
}: {
  params: Promise<{ slug: string; section: string }>;
}) {
  const { slug, section } = await params;
  if (!topicSectionTitles[section]) notFound();
  const topic = await loadTopic(slug);
  if (!topic) notFound();
  return <TopicSectionPublicView topic={topic} section={section} />;
}
