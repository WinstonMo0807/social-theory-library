import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ConfirmedNotesWorkspace } from "@/components/research/confirmed-notes-workspace";
export const metadata: Metadata = { title: "已确认笔记" };
export default function ConfirmedNotesPage() { return <><ConfirmedNotesWorkspace /><SiteFooter reference="reader-center" /></>; }
