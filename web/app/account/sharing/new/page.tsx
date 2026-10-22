import type { Metadata } from "next";
import { ShareComposer } from "@/components/research/share-composer";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "分享或提交策划的内容范围" };
export default async function NewSharePage({ searchParams }: { searchParams: Promise<{ kind?: string; source?: string }> }) {
  const query = await searchParams;
  const sourceId = typeof query.source === "string" && /^[\da-f-]{36}$/i.test(query.source) ? query.source : "";
  return <><ShareComposer sourceId={sourceId} sourceKind={query.kind === "booklist" ? "booklist" : "research"} /><SiteFooter /></>;
}
