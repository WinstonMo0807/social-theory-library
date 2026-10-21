import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SiteFooter } from "@/components/site-footer";
import { TopicSectionPublicView, topicSectionTitles } from "@/components/public/topic-section-public-view";
import { TopicLoadError } from "@/components/public/topic-load-error";
import { loadTopic } from "@/lib/api/topics.server";
import { topicSection } from "@/lib/api/topics.params";
import type { TopicSearchParams } from "@/lib/api/topics.types";
export async function generateMetadata({ params }: { params: Promise<{ slug: string; section: string }> }): Promise<Metadata> {
  const { slug, section } = await params;
  try { const topic = await loadTopic(slug); return { title: topic ? `${topicSectionTitles[section] || "主题资料"} · ${topic.name}` : "主题资料" }; } catch { return { title: "主题资料" }; }
}
export default async function TopicSectionPage({ params, searchParams }: { params: Promise<{ slug: string; section: string }>; searchParams: Promise<TopicSearchParams> }) {
  const { slug, section: raw } = await params, section = topicSection(raw), filters = { ...await searchParams };
  if (!section) notFound();
  if (raw === "recent" && !filters.sort) filters.sort = "published";
  if (section === "evidence" && !filters.page_size) filters.page_size = "1";
  let topic;
  try { topic = await loadTopic(slug, section, filters); } catch { return <><TopicLoadError slug={slug} /><SiteFooter /></>; }
  if (!topic) notFound();
  return <><TopicSectionPublicView topic={topic} section={section} params={filters} /><SiteFooter /></>;
}
