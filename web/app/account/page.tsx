import type { Metadata } from "next";
import { ReaderCenter } from "@/components/reader-center";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = { title: "读者中心" };

export default function AccountPage() {
  return <><ReaderCenter /><SiteFooter /></>;
}
