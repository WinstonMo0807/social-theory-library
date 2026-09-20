import { HomePublicView } from "@/components/public/home-public-view";
import { SiteFooter } from "@/components/site-footer";
import { loadHomeViewData } from "@/lib/api/home.server";
export const metadata = { title: "首页", description: "阅读社会理论原典，检索观点并精确回到 PDF 页码。" };
export default async function Home() { return <><div className="page-shell"><HomePublicView {...await loadHomeViewData()} /></div><SiteFooter /></>; }
