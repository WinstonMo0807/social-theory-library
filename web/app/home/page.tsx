import { LibraryEntryTransition } from "@/components/public/library-entry-transition";
import { HomePublicView } from "@/components/public/home-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadHomeViewData } from "@/lib/api/home.server";
import { cookies } from "next/headers";
import { Suspense } from "react";
import Loading from "../loading";
export const metadata = { title: "首页", description: "阅读社会理论原典，检索观点并精确回到 PDF 页码。" };
export const dynamic = "force-dynamic";
async function HomeContent() {
  const [data, cookieStore] = await Promise.all([loadHomeViewData(), cookies()]);
  // A cookie is only a layout hint. Private progress still requires the existing session check.
  const reserveReadingSpace = cookieStore.has(process.env.JWT_ACCESS_COOKIE_NAME || "stl_access")
    || cookieStore.has(process.env.JWT_REFRESH_COOKIE_NAME || "stl_refresh");
  return <><HomePublicView {...data} reserveReadingSpace={reserveReadingSpace} /><SiteFooter /></>;
}
export default function Home() {
  return <><LibraryEntryTransition /><Suspense fallback={<Loading />}><HomeContent /></Suspense></>;
}
