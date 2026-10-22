import type { Metadata } from "next";
import { ReaderSharing } from "@/components/research/reader-sharing";
import { SiteFooter } from "@/components/site-footer";
export const metadata: Metadata = { title: "分享与提交记录" };
export default function SharingPage() { return <><ReaderSharing /><SiteFooter /></>; }
