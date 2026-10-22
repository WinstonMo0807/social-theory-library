import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ReaderNotebook } from "@/components/research/reader-notebook";
export const metadata: Metadata = { title: "笔记、摘录与书签" };
export default function NotesPage() { return <><ReaderNotebook /><SiteFooter /></>; }
