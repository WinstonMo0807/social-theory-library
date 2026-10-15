import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ReaderCollectionList } from "@/components/research/reader-collection-list";
export const metadata: Metadata = { title: "笔记" };
export default function NotesPage() { return <><ReaderCollectionList kind="notes" /><SiteFooter /></>; }
