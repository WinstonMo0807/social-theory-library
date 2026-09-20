import { SiteContentEditor } from "@/components/admin/site-content-editor";
import { loadHomeViewData } from "@/lib/api/home.server";
import { loadSiteStats } from "@/lib/api/site.server";
export const metadata = { title: "网站与关于书库" };
export default async function Page() { const [home, stats] = await Promise.all([loadHomeViewData(), loadSiteStats()]); return <SiteContentEditor home={home} stats={stats} />; }
