import type { Metadata } from "next";
import { PublicSharedContent } from "@/components/research/reader-sharing";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "读者分享的内容摘要", robots: { index: false, follow: false }, referrer: "no-referrer" };
export default async function PublicSharePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><PublicSharedContent id={id} /><SiteFooter /></>;
}
