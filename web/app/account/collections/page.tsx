import type { Metadata } from "next";
import { ReaderBooklists } from "@/components/research/reader-booklists";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "我的书单" };
export default function CollectionsPage() { return <><ReaderBooklists /><SiteFooter /></>; }
