import { SiteFooter } from "@/components/site-footer";
import { FeedbackAside, FeedbackForm } from "@/components/public/feedback-form";
import { SupportHero, SupportNavigation } from "@/components/public/support-hero";
import { loadSiteChromeConfig } from "@/lib/api/site.server";
import type { FeedbackCategory } from "@/lib/api/feedback.client";
export const metadata = { title: "提交反馈" };
export default async function FeedbackPage({ searchParams }: { searchParams: Promise<{ category?: string; path?: string }> }) {
  const [chrome, params] = await Promise.all([loadSiteChromeConfig(), searchParams]);
  const category = (["content", "function", "usage", "suggestion", "other"].includes(params.category || "") ? params.category : "content") as FeedbackCategory;
  return <><div className="stl4-support-page stl4-feedback-page"><SupportHero variant="feedback" title="使用帮助与反馈" /><SupportNavigation current="feedback" />{chrome.unavailable ? <p className="stl4-support-status" role="status">网站配置暂时无法加载。提交能否成功以服务返回的操作结果为准。</p> : null}<div className="stl4-feedback-layout"><FeedbackAside /><div id="feedback-form"><FeedbackForm initialCategory={category} initialPath={params.path || ""} /></div></div></div><SiteFooter reference="support" /></>;
}
