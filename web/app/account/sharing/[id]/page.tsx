import type { Metadata } from "next";
import { ReaderSharedContent } from "@/components/research/reader-sharing";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "分享内容与授权" };
export default async function SharedContentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <><ReaderSharedContent id={id} /><SiteFooter /></>;
}
