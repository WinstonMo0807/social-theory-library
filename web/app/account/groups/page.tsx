import type { Metadata } from "next";
import { ReaderGroups } from "@/components/research/reader-groups";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "我的小组" };
export default function GroupsPage() { return <><ReaderGroups /><SiteFooter /></>; }
