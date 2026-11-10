import { SpecialKnowledge } from "@/components/public/special-knowledge";
import { SiteFooter } from "@/components/site-footer";

export const metadata = { title: "知识页" };
export default async function KnowledgeSpecialPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  return <><SpecialKnowledge slug={slug} /><SiteFooter /></>;
}
