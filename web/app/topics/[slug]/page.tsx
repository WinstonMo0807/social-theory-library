import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopicPublicView } from "@/components/public/topic-public-view";
import { TopicLoadError } from "@/components/public/topic-load-error";
import { SiteFooter } from "@/components/site-footer";
import { loadTopic } from "@/lib/api/topics.server";
import type { TopicSearchParams } from "@/lib/api/topics.types";
export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  try { const topic = await loadTopic((await params).slug); return { title: topic?.name || "主题" }; } catch { return { title: "主题" }; }
}
export default async function TopicDetailPage({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<TopicSearchParams> }) {
  const { slug } = await params, filters = await searchParams;
  let topic;
  try { topic = await loadTopic(slug, "overview", filters); } catch { return <><TopicLoadError slug={slug} /><SiteFooter /></>; }
  if (!topic) notFound();
  return <TopicPublicView topic={topic} params={filters} footer={<SiteFooter />} />;
}
