import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { ReaderCollectionList } from "@/components/research/reader-collection-list";
export const metadata: Metadata = { title: "阅读计划" };
export default function PlansPage() { return <><ReaderCollectionList kind="plans" /><SiteFooter /></>; }
