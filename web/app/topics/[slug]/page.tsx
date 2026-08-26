import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { TopicPublicView } from "@/components/public/topic-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadTopic } from "@/lib/server-api";

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const data = await loadTopic((await params).slug);
  return { title: data?.name ?? "主题" };
}

export default async function TopicDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const topic = await loadTopic((await params).slug);
  if (!topic) notFound();

  return <TopicPublicView topic={topic} footer={<SiteFooter />} />;
}
