import type { Metadata } from "next";
import { SourceUpdatesWorkspace } from "@/components/research/source-updates-workspace";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "来源订阅" };
export default function SourceUpdatesPage() { return <><SourceUpdatesWorkspace /><SiteFooter /></>; }
