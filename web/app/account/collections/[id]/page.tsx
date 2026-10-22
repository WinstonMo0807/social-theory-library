import type { Metadata } from "next";
import { ReaderBooklists } from "@/components/research/reader-booklists";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "书单与材料集合" };
export default async function CollectionPage({ params }: { params: Promise<{ id: string }> }) { const { id } = await params; return <><ReaderBooklists id={id} /><SiteFooter /></>; }
