import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ReaderCollectionList } from "@/components/research/reader-collection-list";
export const metadata: Metadata = { title: "引文核验" };
export default function CitationAuditsPage() { return <><ReaderCollectionList kind="citation" /><SiteFooter /></>; }
