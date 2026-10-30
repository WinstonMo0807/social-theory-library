import { loadHomeViewData } from "@/lib/api/home.server";
import { SiteFooter } from "@/components/site-footer";
import { LayoutPreview } from "./preview";
import "./preview.css";

export const metadata = { title: "首页排版参考" };
export default async function Page() {
  return <><LayoutPreview data={await loadHomeViewData()} /><SiteFooter /></>;
}
